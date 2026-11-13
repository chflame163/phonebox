#!/usr/bin/env python3
"""pb_push_stream_patch1.py - P3: ride pushed values inside the 1 Hz state frame (fork-local).

Why: the panel's push widgets re-render every tick (basic.js W.push needs ['push','tick']) -
rendering was never the slow part. Data latency came from the transport: a Set bumps only
pushVersion, then the phone pays a second GET /api/push round trip per change, on top of the
push script's own 2.2s cadence. The state frame is already 1 Hz and already reaches the phone
in every frame, so the items ride with it: one hop, frame-synchronous.

- agent  Program.cs State(): one line, pushItems = push.Snapshot()  (same shape as the
  GET /api/push handler's items field, so the phone-side consumer is unchanged in kind).
- phone  main.js applyState(): three-way branch - items in frame + new version => apply+emit;
  items + same version => quiet whole-map refresh (expiry drops ride this too);
  no items (older agent) => the classic version-compare refetch. Pairing is compatible both
  ways: old phone ignores the unknown field; new phone with an old agent falls to branch 3.
- versionCode 27 -> 28 (versionName stays 0.9.3).

Usage: python3 -I pb_push_stream_patch1.py <repo-root>
Idempotent (skips when new text present); each anchor must appear exactly once.
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1].rstrip("/"))

CS = "agent/PhoneBox.Agent/Program.cs"
JS = "android/app/src/main/assets/www/main.js"
GR = "android/app/build.gradle.kts"

EDITS = [
    (CS,
     '        pushVersion = push.Version,',
     '        pushVersion = push.Version,\n'
     '        // the values ride the frame next to their version - the phone applies them in place '
     'instead of paying a\n'
     '        // second GET per change (fork 2026-11); the snapshot is the exact shape of GET /api/push\'s items\n'
     '        pushItems = push.Snapshot(),',
     "agent-state-pushitems"),

    (JS,
     '  if (s.pushVersion !== undefined && s.pushVersion !== pushVersion) loadPush();',
     '  // fork: an agent that ships the pushed values inside the frame gets them applied right there -\n'
     '  // widgets re-read D.push on their own every second, so only a version move needs a re-announce.\n'
     '  // Frames without items (stock agents) keep the classic version-compare refetch, so agent and app\n'
     '  // may be old or new in any combination.\n'
     "  if (s.pushItems && s.pushVersion !== pushVersion) { D.push = s.pushItems; pushVersion = s.pushVersion; emit('push'); }\n"
     '  else if (s.pushItems) D.push = s.pushItems;\n'
     '  else if (s.pushVersion !== undefined && s.pushVersion !== pushVersion) loadPush();',
     "mainjs-applyitems"),

    (GR,
     '        versionCode = 27',
     '        versionCode = 28',
     "versioncode-28"),
]

for path, old, new, tag in EDITS:
    p = root / path
    s = p.read_text()
    if new in s:
        print(f"[{tag}] already applied")
        continue
    n = s.count(old)
    assert n == 1, f"[{tag}] anchor found {n} times in {path}"
    p.write_text(s.replace(old, new))
    print(f"[{tag}] applied")

print("ALL OK")
