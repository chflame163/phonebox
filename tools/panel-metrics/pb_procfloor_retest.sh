#!/bin/bash
# pb_procfloor_retest.sh — install vc31 and prove the Top CPU card empties to "Measuring..." on silence
# (plus everything else floored as before), then recovers within seconds.
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
U="adb -s 481fe5dc"; K=net.oxog.phonebox.deskpanel
APK=$HOME/phonebox/android/app/build/outputs/apk/release/app-release.apk
TS=$(date +%Y%m%d-%H%M%S); BK=/mnt/nvme0n1p1/temp/pb-procfloor-$TS; mkdir -p "$BK"

focus() { $U shell dumpsys window 2>/dev/null | grep -m1 mCurrentFocus | tr -d '\r'; }
raise() { $U shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; sleep 1; $U shell am start -n $K/.MainActivity >/dev/null 2>&1; sleep 3; }
shot() { echo "focus: $(focus)"; $U exec-out screencap -p > "$BK/$1.png" && echo "shot $1: $(md5sum $BK/$1.png | cut -c1-8)"; }

echo "== A) install vc31, panel live =="
$U install -r -t "$APK" | tail -1
$U shell dumpsys package $K | grep -m1 versionCode | tr -d '\r'
raise; shot v4_live

echo "== B) kill -9 the agent (Restart=no drop-in; pushd left running) =="
mkdir -p ~/.config/systemd/user/phonebox.service.d
printf '[Service]\nRestart=no\n' > ~/.config/systemd/user/phonebox.service.d/killtest.conf
systemctl --user daemon-reload
kill -9 "$(systemctl --user show phonebox -p MainPID --value)"
sleep 9

echo "== C) +9 s: Top CPU must read Measuring..., all other cards floored =="
curl -s -m2 http://127.0.0.1:8765/api/push >/dev/null 2>&1 && echo "agent UP (bad)" || echo "agent DOWN"
shot v4_kill9

echo "== D) recover: agent back -> process list refills on its own within ~2 s of 'online' =="
rm ~/.config/systemd/user/phonebox.service.d/killtest.conf; rmdir ~/.config/systemd/user/phonebox.service.d
systemctl --user daemon-reload; systemctl --user reset-failed phonebox 2>/dev/null || true
systemctl --user start phonebox; sleep 8
raise; shot v4_restored
echo "services: $(systemctl --user is-active phonebox pb-strata-pushd | tr '\n' ' ')"; echo "DONE $BK"
