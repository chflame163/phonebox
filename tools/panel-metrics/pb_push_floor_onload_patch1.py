#!/usr/bin/env python3
# pb_push_floor_onload_patch1.py — fork master agent change (2026-11-14):
# 1) PushStore loads data.json on startup; previously the raw values of the last session were served
#    verbatim until ttl/purge (and in practice the panel could keep showing pre-shutdown numbers).
#    Now every restored key is floored to its minimum: objects -> {"value":0, unit kept}, arrays -> [],
#    scalars -> 0; At re-stamped (phones skip redraw when item.at is unchanged), ExpiresAt=null so the
#    floor rides until a real push replaces it. Cold start = every control shows its lowest value (0).
# 2) Changed() re-armed the 2 s debounce timer on every push; a producer pushing every 1 s (pb-strata-pushd)
#    starved Persist forever -> data.json stayed "{}" -> cold start restored nothing at all.
#    Now a pending write is not re-armed: floor is one disk write per ~2 s, data.json actually keeps keys.
# Idempotent; asserts every anchor is unique. Run on the server: python3 pb_push_floor_onload_patch1.py
import pathlib, sys

p = pathlib.Path.home() / "phonebox/agent/PhoneBox.Agent/PushStore.cs"
s = p.read_text()

if "FloorOnLoad" in s:
    print("ALREADY_PATCHED", p)
    sys.exit(0)

# 1) using for JsonNode
a = "using System.Text.Json;\n"
assert s.count(a) == 1, ("anchor using", s.count(a))
s = s.replace(a, "using System.Text.Json;\nusing System.Text.Json.Nodes;\n")

# 2) docstring: keys survive, values are floored
a = "/// Values survive restarts (data.json next to config.json); events are kept in memory only."
assert s.count(a) == 1, ("anchor doc", s.count(a))
s = s.replace(a, "/// Keys survive restarts (data.json next to config.json) but restored values are floored to their\n/// minimum until the producer pushes fresh data; events are kept in memory only.")

# 3) load: floor each restored item
a = "                    if (ValidKey(k)) _items[k] = v;"
assert s.count(a) == 1, ("anchor load", s.count(a))
s = s.replace(a, "                    if (ValidKey(k)) _items[k] = FloorOnLoad(v);")

# 4) field for the pending-write flag
a = "    private long _seq;\n"
assert s.count(a) == 1, ("anchor seq", s.count(a))
s = s.replace(a, "    private long _seq;\n    private int _saveQueued;\n")

# 5) Changed(): never starve the debounce while a write is already pending
a = """    private void Changed()
    {
        Interlocked.Exchange(ref _version, Math.Max(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), Interlocked.Read(ref _version) + 1));
        _saveTimer.Change(2000, Timeout.Infinite); // debounce disk writes
    }"""
assert s.count(a) == 1, ("anchor changed", s.count(a))
s = s.replace(a, """    private void Changed()
    {
        Interlocked.Exchange(ref _version, Math.Max(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), Interlocked.Read(ref _version) + 1));
        // Re-arming the debounce on every change starves the disk write when a producer pushes every second
        // (our resident pushd meant data.json never left "{}"), so while one write is pending later changes
        // just ride it; Persist clears the flag - the floor is one write per two seconds. (fork 2026-11)
        if (Interlocked.CompareExchange(ref _saveQueued, 1, 0) == 0) _saveTimer.Change(2000, Timeout.Infinite);
    }""")

# 6) Persist(): clear the pending flag first so the next change can arm a new write
a = """    private void Persist()
    {
        try
        {"""
assert s.count(a) == 1, ("anchor persist", s.count(a))
s = s.replace(a, """    private void Persist()
    {
        Interlocked.Exchange(ref _saveQueued, 0); // the next change may arm a new write
        try
        {""")

# 7) the helper itself, inserted before PurgeExpired
a = "    /// <summary>Drops values whose TTL has passed; that is a change too, so phones reload and drop them as well.</summary>"
assert s.count(a) == 1, ("anchor purge", s.count(a))
helper = """    /// <summary>
    /// Fork change (2026-11): a value restored from disk is not current truth - the producer (script, cron, CI...)
    /// pushes again within seconds, and a producer that stays away must not pin last session's numbers on the panel
    /// forever. So a cold start presents every restored key at its lowest value: objects floor to {"value":0} with
    /// the unit kept for context, arrays to empty, anything else to zero. At is re-stamped (phones skip the redraw
    /// when item.at is unchanged) and ExpiresAt is dropped so the floor rides until a real push replaces it.
    /// </summary>
    private static PushItem FloorOnLoad(PushItem v)
    {
        JsonElement floor;
        switch (v.Data.ValueKind)
        {
            case JsonValueKind.Object:
            {
                var o = new JsonObject { ["value"] = 0 };
                if (v.Data.TryGetProperty("unit", out var u) && u.ValueKind == JsonValueKind.String) o["unit"] = u.GetString();
                floor = JsonSerializer.SerializeToElement(o);
                break;
            }
            case JsonValueKind.Array: floor = JsonSerializer.SerializeToElement(new JsonArray()); break;
            default: floor = JsonSerializer.SerializeToElement(0); break; // numbers, strings, bools all floor to zero
        }
        return v with { Data = floor, At = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(), ExpiresAt = null };
    }

""" + a
s = s.replace(a, helper)

p.write_text(s)
print("PATCHED", p)
