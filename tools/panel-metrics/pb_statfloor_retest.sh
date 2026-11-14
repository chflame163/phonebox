#!/bin/bash
# pb_statfloor_retest.sh — install vc30 and prove the built-in stat cards floor on silence too:
# A panel foreground live; B SIGKILL agent (Restart=no drop-in, pushd left running to also show the
# goodbye-net path is irrelevant here); C +9 s every card including CPU/GPU/RAM/NETWORK reads zero;
# D agent back -> everything refills by itself.
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
U="adb -s 481fe5dc"; K=net.oxog.phonebox.deskpanel
APK=$HOME/phonebox/android/app/build/outputs/apk/release/app-release.apk
TS=$(date +%Y%m%d-%H%M%S); BK=/mnt/nvme0n1p1/temp/pb-statfloor-$TS; mkdir -p "$BK"

focus() { $U shell dumpsys window 2>/dev/null | grep -m1 mCurrentFocus | tr -d '\r'; }
raise() { $U shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; sleep 1; $U shell am start -n $K/.MainActivity >/dev/null 2>&1; sleep 3; }
shot() { echo "focus: $(focus)"; $U exec-out screencap -p > "$BK/$1.png" && echo "shot $1: $(md5sum $BK/$1.png | cut -c1-8)"; }

echo "== A) install vc30, panel live =="
$U install -r -t "$APK" | tail -1
$U shell dumpsys package $K | grep -m1 versionCode | tr -d '\r'
raise; shot v3_live

echo "== B) kill -9 the agent (no handler, no respawn; pushd keeps hammering the dead port) =="
mkdir -p ~/.config/systemd/user/phonebox.service.d
printf '[Service]\nRestart=no\n' > ~/.config/systemd/user/phonebox.service.d/killtest.conf
systemctl --user daemon-reload
kill -9 "$(systemctl --user show phonebox -p MainPID --value)"
sleep 9

echo "== C) +9 s: built-in cards must have floored too =="
curl -s -m2 http://127.0.0.1:8765/api/push >/dev/null 2>&1 && echo "agent UP (bad)" || echo "agent DOWN"
shot v3_kill9

echo "== D) recover =="
rm ~/.config/systemd/user/phonebox.service.d/killtest.conf; rmdir ~/.config/systemd/user/phonebox.service.d
systemctl --user daemon-reload; systemctl --user reset-failed phonebox 2>/dev/null || true
systemctl --user start phonebox; sleep 7
raise; shot v3_restored
echo "services: $(systemctl --user is-active phonebox pb-strata-pushd | tr '\n' ' ')"; echo "DONE $BK"
