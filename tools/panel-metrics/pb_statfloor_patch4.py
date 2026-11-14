#!/usr/bin/env python3
# pb_statfloor_patch4.py (fork 2026-11-14 #4, phone side vc29 -> vc30, user request):
# the 5 s silence net now floors D.state as well, so the BUILT-IN stat cards (CPU/GPU/RAM/NETWORK,
# fed from the agent's live frames, not from push) drop to 0 % / 0 W / 0 GB / 0 B/s instead of
# freezing at the last pre-loss reading. Labels and totals survive: only measured values go to zero.
# Anchors assert uniqueness; idempotent.
import pathlib, sys

p = pathlib.Path.home() / "phonebox/android/app/src/main/assets/www/main.js"
s = p.read_text()
if "flooredState" in s:
    print("ALREADY_STATFLOOR")
else:
    # 1) applyState top: ANY good frame retires the floor (also covers stock/no-items agents)
    a = "export function applyState(s) {\n  lastStateAt = Date.now();"
    assert s.count(a) == 1, "applyState head"
    s = s.replace(a, a + "\n  staleFloorDone = false; // any successful frame retires the silence floor (push values and stat cards alike)")

    # 2) upgrade the watchdog body: floor D.state too + announce 'state' for W.stat/W.gauge
    a = """function floorStalePush() {
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
}"""
    assert s.count(a) == 1, "watchdog body"
    s = s.replace(a, """// vc30: the net floors D.state too, so the built-in stat cards (CPU/GPU/RAM/NETWORK read pc/ping from the
// live frames) show 0 % / 0 W / 0 GB / 0 B/s on silence instead of freezing at the last pre-loss reading.
// Only measured values floor - names, totals and limits survive so the cards keep their context.
function flooredState(s) {
  const out = { ...s };
  if (s.pc) {
    const pc = { ...s.pc, cpu: 0, cpuTemp: 0, ramUsedGb: 0, netDownBps: 0, netUpBps: 0 };
    if (s.pc.gpu) pc.gpu = { ...s.pc.gpu, util: 0, temp: 0, power: 0, fan: 0, clock: 0, vramUsed: 0 };
    out.pc = pc;
  }
  if (s.ping) out.ping = { ...s.ping, ms: 0 };
  return out;
}
function floorStalePush() {
  const s = D.state;
  if (!s || staleFloorDone) return; // anchored on state: real frames arrived once and then stopped
  const items = D.push || {};
  const floored = {};
  for (const k of Object.keys(items)) {
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
  D.state = flooredState(s);
  staleFloorDone = true;
  emit('push');
  emit('state'); // W.stat/W.gauge re-render on 'state'
}""")
    p.write_text(s)
    print("PATCHED", p)

# 3) versionCode 29 -> 30
p = pathlib.Path.home() / "phonebox/android/app/build.gradle.kts"
s = p.read_text()
if "versionCode = 30" in s:
    print("ALREADY_GRADLE30")
else:
    a = "        versionCode = 29"
    assert s.count(a) == 1, "versionCode29"
    s = s.replace(a, "        versionCode = 30")
    p.write_text(s)
    print("PATCHED", p)
