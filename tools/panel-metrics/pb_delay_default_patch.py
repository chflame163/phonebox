#!/usr/bin/env python3
"""pb_delay_default_patch.py - fork-local: power standby grace default 30 s -> 5 s.

The phone-side criterion is agent-data silence (AGENT_SILENCE_MS = 12 s: a live agent answers
in seconds; only a real shutdown/stop goes silent that long), so the old 30 s USB-blip grace
is oversized for it - the desk standard since 2026-11-12 has been 5 s (measured: unplug ->
silent 12 s + 5 s + system timeout ~10 s -> dark in about 30 s; a Wi-Fi hiccup never reaches
12 s of silence, so no false sleeps). Four default sites move together:
  Config.cs field, three config.default*.json, settings.html's ??= fallback map.
A running agent with no powerStandbyDelaySec key in config.json (the live file's shape since
11-13) simply starts applying 5 s - no config write needed.
Usage: python3 -I pb_delay_default_patch.py <repo-root>; idempotent, anchors unique.
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1].rstrip("/"))

EDITS = [
    ("agent/PhoneBox.Agent/Config.cs",
     '    /// <summary>Grace period in seconds after the power is lost before the screen may sleep; absorbs a rebooting server\'s power blip.</summary>\n'
     '    public int PowerStandbyDelaySec { get; set; } = 30;',
     '    /// <summary>Grace period in seconds after the computer goes quiet before the screen may sleep. The criterion is\n'
     '    /// agent-data silence (12 s), which a live agent never crosses, so a short grace only trims a real\n'
     '    /// shutdown a little - 5 s is the desk standard since 2026-11-12 (measured: dark ~30 s after unplug).</summary>\n'
     '    public int PowerStandbyDelaySec { get; set; } = 5;',
     "config-field-default"),

    ("agent/PhoneBox.Agent/config.default.json",
     '"powerStandby": true, "powerStandbyDelaySec": 30',
     '"powerStandby": true, "powerStandbyDelaySec": 5',
     "default-json"),
    ("agent/PhoneBox.Agent/config.default.linux.json",
     '"powerStandby": true, "powerStandbyDelaySec": 30',
     '"powerStandby": true, "powerStandbyDelaySec": 5',
     "default-json-linux"),
    ("agent/PhoneBox.Agent/config.default.macos.json",
     '"powerStandby": true, "powerStandbyDelaySec": 30',
     '"powerStandby": true, "powerStandbyDelaySec": 5',
     "default-json-macos"),

    ("android/app/src/main/assets/www/main.js",  # (placeholder never used; html file below)
     "powerStandby: true, powerStandbyDelaySec: 30 }))",
     "powerStandby: true, powerStandbyDelaySec: 5 }))",
     "settings-fallback"),
]

# the settings.html fallback map lives in the agent's own page, not the phone assets
EDITS[-1] = ("agent/PhoneBox.Agent/settings.html", EDITS[-1][1], EDITS[-1][2], "settings-fallback")

s_root = str(root)
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
