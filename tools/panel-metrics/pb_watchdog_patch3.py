#!/usr/bin/env python3
# pb_watchdog_patch3.py (fork 2026-11-14 #3, phone side vc28->29): the panel floors its own cached push
# values when the agent goes silent for >5 s (stream AND poll dead). Covers hard power loss where no
# ApplicationStopping ran, and swallow windows where stream flaps eat the agent's goodbye frame.
# main.js: floorStalePush() + one call from the 1 Hz tick, reset when a frame carries pushItems again.
# Anchors assert uniqueness; idempotent.
import pathlib, sys

p = pathlib.Path.home() / "phonebox/android/app/src/main/assets/www/main.js"
s = p.read_text()
if "floorStalePush" in s:
    print("ALREADY_MAINJS")
else:
    # 1) watchdog + flag, inserted before the live-stream section comment
    a = "// Live stream from the Android shell (see AgentStream.kt); polling below is the fallback when it is not running."
    assert s.count(a) == 1, "stream comment"
    block = """// Fork 2026-11 (floor net): if not a single state frame arrives for five seconds - stream closed AND poll
// failing, which means the agent died or the PC is off - collapse every cached pushed value to its floor
// locally: objects become {"value":0} with the unit kept, arrays empty, anything else zero; at is re-stamped
// so the one-second widgets redraw (they skip the redraw while item.at is unchanged). The agent floors values
// on load and on a graceful stop (PushStore.Floored / SealAndFloorAll), but neither can run during hard power
// loss and stream flaps can swallow the goodbye frame - this net cannot. staleFloorDone fires it once per
// silence episode; a live agent replaces the whole table on its next frame anyway.
let staleFloorDone = false;
function floorStalePush() {
  const items = D.push || {};
  const keys = Object.keys(items);
  if (!keys.length || staleFloorDone) return;
  const floored = {};
  for (const k of keys) {
    const d = (items[k] || {}).data;
    floored[k] = {
      data: d && typeof d === 'object' && !Array.isArray(d)
        ? Object.assign({ value: 0 }, d.unit ? { unit: d.unit } : {})
        : Array.isArray(d) ? [] : 0,
      at: Date.now(),
      expiresAt: null,
    };
  }
  D.push = floored;
  staleFloorDone = true;
  emit('push');
}

""" + a
    s = s.replace(a, block)

    # 2) applyState chain: track when the agent's own items land, reset the floor latch
    a = """  if (s.pushItems && s.pushVersion !== pushVersion) { D.push = s.pushItems; pushVersion = s.pushVersion; emit('push'); }
  else if (s.pushItems) D.push = s.pushItems;
  else if (s.pushVersion !== undefined && s.pushVersion !== pushVersion) loadPush();"""
    assert s.count(a) == 1, "applyState push chain"
    s = s.replace(a, """  if (s.pushItems) { D.push = s.pushItems; staleFloorDone = false; } // agent is talking: retire the local floor
  if (s.pushVersion !== undefined && s.pushVersion !== pushVersion) {
    if (s.pushItems) { pushVersion = s.pushVersion; emit('push'); }
    else loadPush(); // stock agents that do not ship items keep the classic version-compare refetch
  }""")

    # 3) the classic refetch path also clears the latch
    a = "    D.push = r.items || {};\n    pushVersion = r.version;"
    assert s.count(a) == 1, "loadPush body"
    s = s.replace(a, "    D.push = r.items || {};\n    staleFloorDone = false; // refetched from a live agent\n    pushVersion = r.version;")

    # 4) the 1 Hz net itself
    a = "  if (!nightOn) emit('tick');"
    assert s.count(a) == 1, "tick emit"
    s = s.replace(a, """  // fork 2026-11: five seconds of total agent silence floors the cached push values (see floorStalePush);
  // runs even in night mode so the RAM the panel wakes a reboot with is already zeros.
  if (lastStateAt && Date.now() - lastStateAt > 5000) floorStalePush();
  if (!nightOn) emit('tick');""")
    p.write_text(s)
    print("PATCHED", p)

# 5) versionCode 28 -> 29
p = pathlib.Path.home() / "phonebox/android/app/build.gradle.kts"
s = p.read_text()
if "versionCode = 29" in s:
    print("ALREADY_GRADLE")
else:
    a = "        versionCode = 28"
    assert s.count(a) == 1, "versionCode"
    s = s.replace(a, "        versionCode = 29")
    p.write_text(s)
    print("PATCHED", p)
