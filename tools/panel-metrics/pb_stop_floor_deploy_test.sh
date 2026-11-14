#!/bin/bash
# pb_stop_floor_deploy_test.sh — deploy stop-floor dll and prove the goodbye zeros reach the phone:
#  A swap dll, everything live again (real values on screen)
#  B stop pushd (freeze last known truth = real values), then stop phonebox WITHOUT -9 so the handler runs
#  C 3 s later the agent is gone: screencap must show 0 (only source = the goodbye frame)
#  D start agent alone: /api/push still zeros (persisted + load floor), screencap still 0
#  E start pushd: real values back within seconds
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
D=$HOME/.local/share/PhoneBox/app
DIST=$HOME/phonebox/agent/PhoneBox.Agent/bin/Release/net10.0
U="adb -s 481fe5dc"
TS=$(date +%Y%m%d-%H%M%S)
BK=/mnt/nvme0n1p1/temp/pb-stopfloor-$TS
mkdir -p "$BK" && cp -a "$D/." "$BK/"
echo "backup=$BK old_dll=$(md5sum $BK/PhoneBoxAgent.dll | cut -c1-8)"

echo "== A) swap + go live =="
systemctl --user stop pb-strata-pushd phonebox
find "$D" -maxdepth 1 -mindepth 1 -delete
cp -a "$DIST/." "$D/"
systemctl --user start phonebox pb-strata-pushd; sleep 8
echo "new_dll=$(md5sum $D/PhoneBoxAgent.dll | cut -c1-8) active=$(systemctl --user is-active phonebox pb-strata-pushd | tr '\n' ' ')"
echo -n "A/values: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value") for k,v in d["items"].items()})'

echo "== B) stop pushd, real values become last-truth; then graceful stop of agent =="
systemctl --user stop pb-strata-pushd; sleep 2
echo -n "B/before stop: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value") for k,v in d["items"].items()})'
systemctl --user stop phonebox

echo "== C) agent gone 3 s: phone must be on zeros now (goodbye frame was the only writer) =="
sleep 3
$U exec-out screencap -p > "$BK/screen_after_graceful_stop.png" && echo "C/screen: $(md5sum $BK/screen_after_graceful_stop.png | cut -c1-8)"
echo -n "C/agent port answers: "; curl -s -m2 http://127.0.0.1:8765/api/push >/dev/null 2>&1 && echo UP || echo DOWN
journalctl --user -u phonebox --since "-3 min" --no-pager -o short-iso 2>/dev/null | grep -iE "floored|graceful stop" | cut -c1-160
echo -n "C/data.json now holds: "; python3 -c 'import json;d=json.load(open("/home/cc/.config/PhoneBox/data.json"));print({k:v["Data"].get("value") for k,v in d.items()})'

echo "== D) agent starts alone: load floor keeps zeros (no resurrect) =="
systemctl --user start phonebox; sleep 5
echo -n "D/values: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value","no-field") for k,v in d["items"].items()})'
$U exec-out screencap -p > "$BK/screen_agentdown_then_boot.png" && echo "D/screen: $(md5sum $BK/screen_agentdown_then_boot.png | cut -c1-8)"

echo "== E) pushd back -> real values =="
systemctl --user start pb-strata-pushd; sleep 5
echo -n "E/values: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value") for k,v in d["items"].items()})'
$U exec-out screencap -p > "$BK/screen_restored.png" && echo "E/screen: $(md5sum $BK/screen_restored.png | cut -c1-8)"
echo DONE
