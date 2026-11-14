#!/bin/bash
# pb_watchdog_test.sh — install vc29 and prove the phone-side floor net on a SIMULATED HARD POWER LOSS:
#  A verify the watchdog code is inside the APK, install -r (data/pairing kept), panel live on vc29
#  B freeze the truth: stop pushd; then SIGKILL the agent with Restart=no drop-in (no handler, no respawn)
#  C +8 s: agent port dead, no graceful-stop journal line possible - screen must show 0 => local watchdog
#  D agent back (drop-in removed, start): pushd still pushing -> real values restore
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
U="adb -s 481fe5dc"; K=net.oxog.phonebox.deskpanel
APK=$HOME/phonebox/android/app/build/outputs/apk/release/app-release.apk
TS=$(date +%Y%m%d-%H%M%S); BK=/mnt/nvme0n1p1/temp/pb-watchdog-$TS; mkdir -p "$BK"

echo "== A) apk content + install =="
python3 - "$APK" <<'PY'
import sys, zipfile
z = zipfile.ZipFile(sys.argv[1])
js = z.read("assets/www/main.js").decode()
print("floorStalePush in apk:", js.count("floorStalePush"), "| tick call:", "lastStateAt > 5000" in js)
PY
$U install -r -t "$APK" | tail -1
$U shell dumpsys package $K | grep -m1 versionCode | tr -d '\r'
$U shell input keyevent KEYCODE_WAKEUP; sleep 4
$U exec-out screencap -p > "$BK/v29_live.png" && echo "A/screen: $(md5sum $BK/v29_live.png | cut -c1-8)"

echo "== B) simulate power loss: freeze values, kill -9 without respawn =="
systemctl --user stop pb-strata-pushd
mkdir -p ~/.config/systemd/user/phonebox.service.d
printf '[Service]\nRestart=no\n' > ~/.config/systemd/user/phonebox.service.d/killtest.conf
systemctl --user daemon-reload
PID=$(systemctl --user show phonebox -p MainPID --value)
kill -9 "$PID"
sleep 8

echo "== C) watchdog window: agent dead 8 s, screen must be floored =="
curl -s -m2 http://127.0.0.1:8765/api/push >/dev/null 2>&1 && echo "agent: UP (bad)" || echo "agent: DOWN"
echo -n "graceful-stop lines (expect 0): "; journalctl --user -u phonebox --since "-2 min" --no-pager 2>/dev/null | grep -c "graceful stop" || true
$U exec-out screencap -p > "$BK/v29_8s_after_kill9.png" && echo "C/screen: $(md5sum $BK/v29_8s_after_kill9.png | cut -c1-8)"

echo "== D) recover: agent back with pushd still frozen => load floor 0, then pushd => real =="
rm ~/.config/systemd/user/phonebox.service.d/killtest.conf; rmdir ~/.config/systemd/user/phonebox.service.d
systemctl --user daemon-reload; systemctl --user reset-failed phonebox 2>/dev/null || true
systemctl --user start phonebox; sleep 6
echo -n "D/agent sees: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value","nofield") for k,v in d["items"].items()})'
$U exec-out screencap -p > "$BK/v29_agentback_floor.png" && echo "D/screen: $(md5sum $BK/v29_agentback_floor.png | cut -c1-8)"
systemctl --user start pb-strata-pushd; sleep 5
echo -n "E/values: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value") for k,v in d["items"].items()})'
$U exec-out screencap -p > "$BK/v29_restored.png" && echo "E/screen: $(md5sum $BK/v29_restored.png | cut -c1-8)"
echo "services: $(systemctl --user is-active phonebox pb-strata-pushd | tr '\n' ' ')"; echo "DONE $BK"
