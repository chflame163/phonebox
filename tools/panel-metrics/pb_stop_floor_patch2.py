#!/usr/bin/env python3
# pb_stop_floor_patch2.py (fork 2026-11-14 #2): graceful stop pushes the floor out over the live stream.
#  PushStore: rename FloorOnLoad -> Floored (load AND stop use it), add _stopping seal + SealAndFloorAll().
#  Program.cs: ApplicationStopping -> SealAndFloorAll + 1.3 s hold, so the per-second state frame carries
#  zeros to the phone BEFORE the process dies. The phone app outlives the server (ErP), and its WebView RAM
#  is exactly where pre-shutdown numbers survived yesterday's load-floor fix - this closes that echo too.
# Anchors assert uniqueness; idempotent.
import pathlib, sys

agent = pathlib.Path.home() / "phonebox/agent/PhoneBox.Agent"

# ---------------- PushStore.cs ----------------
p = agent / "PushStore.cs"
s = p.read_text()
if "SealAndFloorAll" in s:
    print("ALREADY_PUSHSTORE")
else:
    a = "Floored" if "Floored" in s else "FloorOnLoad"
    n = s.count(a)
    assert n == 2, ("helper occurrences", n, a)
    s = s.replace(a, "Floored")

    a = "    /// when item.at is unchanged) and ExpiresAt is dropped so the floor rides until a real push replaces it.\n    /// </summary>"
    assert s.count(a) == 1, "doc tail"
    s = s.replace(a, "    /// when item.at is unchanged) and ExpiresAt is dropped so the floor rides until a real push replaces it.\n    /// Used both on load and at a graceful stop (SealAndFloorAll).\n    /// </summary>")

    a = "    private int _saveQueued;\n"
    assert s.count(a) == 1, "saveQueued field"
    s = s.replace(a, a + "    private int _stopping;\n")

    a = """        if (!ValidKey(key)) return "key must be 1-64 characters: letters, digits, '.', '_' or '-'";\n"""
    assert s.count(a) == 1, "set validkey"
    s = s.replace(a, a + "        if (Volatile.Read(ref _stopping) != 0) return null; // stop in progress: the floor is already out, don't let a late push resurrect it\n")

    a = "    public bool Remove(string key)"
    assert s.count(a) == 1, "remove anchor"
    s = s.replace(a, """    /// <summary>Graceful stop (fork 2026-11): seal the store so no later push can resurrect real values, floor
    /// every key to its minimum and persist immediately. The live stream sends one state frame per second, so a
    /// caller that then waits ~1.3 s gets the zeros onto the phone before the process dies - the panel stops
    /// keeping pre-shutdown numbers in its own RAM, wakes after a reboot already showing 0, and the next boot's
    /// load finds the floored data.json anyway. Returns the number of keys floored.</summary>
    public int SealAndFloorAll()
    {
        Interlocked.Exchange(ref _stopping, 1);
        var floored = 0;
        foreach (var k in _items.Keys.ToArray())
            if (_items.TryGetValue(k, out var v)) { _items[k] = Floored(v); floored++; }
        if (floored == 0) return 0;
        Changed();
        Persist();
        return floored;
    }

""" + a)
    p.write_text(s)
    print("PATCHED", p)

# ---------------- Program.cs ----------------
p = agent / "Program.cs"
s = p.read_text()
if "ApplicationStopping" in s:
    print("ALREADY_PROGRAM")
else:
    a = """app.Lifetime.ApplicationStarted.Register(() =>
    app.Logger.LogInformation("PhoneBox agent {Version} ready on http://127.0.0.1:{Port} (config: {Path})", AppPaths.Version, Port, configPath));"""
    assert s.count(a) == 1, "started anchor"
    s = s.replace(a, a + """

// Graceful stop (fork 2026-11): say goodbye with zeros. SealAndFloorAll floors every pushed key and persists
// it; holding ~1.3 s here lets the live stream (one state frame per second) carry the floor to the phone, so
// the panel - which outlives the server across ErP power cycles - caches 0 instead of the pre-shutdown numbers.
// Covers SIGTERM at shutdown/reboot AND /api/restart self-restarts; pushd stops before phonebox by unit order.
app.Lifetime.ApplicationStopping.Register(() =>
{
    var floored = app.Services.GetRequiredService<PushStore>().SealAndFloorAll();
    if (floored == 0) return;
    app.Logger.LogInformation("graceful stop: floored {Count} pushed values so the phone sleeps on zeros", floored);
    Thread.Sleep(1300); // one more state frame per live stream, then let the host shut down
});""")
    p.write_text(s)
    print("PATCHED", p)
