#!/usr/bin/env python3
# pb_procfloor_patch6.py (fork 2026-11-14 #5, phone side vc30 -> vc31, user request):
# the Top CPU / Top memory process list joins the 5 s silence net. The widgets (W.topprocs in pc.js,
# W.processes in basic.js, both needs:['procs']) already carry an empty-state placeholder
# ("Measuring..."), so the honest floor for a process table is an empty one: stale rows from a dead
# host say nothing true about it, and while online:false nothing refills D.procs - the 2 s loadProcs
# interval is gated on online + a procs widget being visible, so recovery refills it within 2 s on its own.
# Anchors assert uniqueness; idempotent.
import pathlib, sys

p = pathlib.Path.home() / "phonebox/android/app/src/main/assets/www/main.js"
s = p.read_text()
if "floorStalePush_v31" in s:
    print("ALREADY_PROCFLOOR")
else:
    a = """  D.push = floored;
  D.state = flooredState(s);
  staleFloorDone = true;
  emit('push');
  emit('state'); // W.stat/W.gauge re-render on 'state'
}"""
    assert s.count(a) == 1, "watchdog tail"
    s = s.replace(a, """  D.push = floored;
  D.state = flooredState(s);
  D.procs = { groups: [], total: 0, groupCount: 0 }; // vc31: process cards fall back to their "Measuring..." empty state
  staleFloorDone = true; // floorStalePush_v31
  emit('push');
  emit('state'); // W.stat/W.gauge re-render on 'state'
  emit('procs'); // W.topprocs/W.processes re-render on 'procs'
}""")
    p.write_text(s)
    print("PATCHED", p)

# versionCode 30 -> 31
p = pathlib.Path.home() / "phonebox/android/app/build.gradle.kts"
s = p.read_text()
if "versionCode = 31" in s:
    print("ALREADY_GRADLE31")
else:
    a = "        versionCode = 30"
    assert s.count(a) == 1, "versionCode30"
    s = s.replace(a, "        versionCode = 31")
    p.write_text(s)
    print("PATCHED", p)
