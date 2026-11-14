#!/bin/bash
# pb_push_floor_deploy.sh — deploy the cold-start floor build and prove the behavior in four stages:
#   A swap dll (store loads old data.json -> nothing/empty)
#   B pushd back -> real values AND data.json finally persists (debounce-starvation fix)
#   C simulated cold boot: pushd stopped + agent restarted alone -> every restored key = value 0 / floor
#   D pushd back -> real values within seconds; screenshots of the zero window and the restored panel
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
D=$HOME/.local/share/PhoneBox/app
DIST=$HOME/phonebox/agent/PhoneBox.Agent/bin/Release/net10.0
DJ=$HOME/.config/PhoneBox/data.json
TS=$(date +%Y%m%d-%H%M%S)
BK=/mnt/nvme0n1p1/temp/pb-push-floor-$TS
mkdir -p "$BK" && cp -a "$D/." "$BK/"
cp -a "$DJ" "$BK/data.json.pre" 2>/dev/null || echo "(no data.json to back up)"
echo "backup=$BK old_dll=$(md5sum $BK/PhoneBoxAgent.dll | cut -c1-8)"

echo "== A) swap dll, start agent alone (pre-state data.json was: $(cat $DJ 2>/dev/null | head -c 80)) =="
systemctl --user stop pb-strata-pushd phonebox
find "$D" -maxdepth 1 -mindepth 1 -delete
cp -a "$DIST/." "$D/"
systemctl --user start phonebox; sleep 6
echo "phonebox=$(systemctl --user is-active phonebox) new_dll=$(md5sum $D/PhoneBoxAgent.dll | cut -c1-8)"
echo -n "A/api/push: "; curl -s -m5 http://127.0.0.1:8765/api/push | head -c 240; echo

echo "== B) pushd on: real values + persistence no longer starved =="
systemctl --user start pb-strata-pushd; sleep 10
ls -la "$DJ"; echo -n "B/data.json head: "; head -c 300 "$DJ"; echo
MT1=$(stat -c %Y "$DJ"); sleep 5; MT2=$(stat -c %Y "$DJ")
echo "B/mtime advance over 5s: $((MT2-MT1)) (expect 4-6 = writing every ~2s)"
echo -n "B/api/push values: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value") for k,v in d["items"].items()})'

echo "== C) simulated cold boot: pushd stays down, agent restarts -> expect every key floored to 0 =="
systemctl --user stop pb-strata-pushd
systemctl --user restart phonebox; sleep 6
curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys
d=json.load(sys.stdin)
for k,v in sorted(d["items"].items()):
    print(k, "|", json.dumps(v["data"], ensure_ascii=False), "| at_age_ms", __import__("time").time()*1000-v["at"], "| expiresAt", v["expiresAt"])'
adb -s 481fe5dc exec-out screencap -p > "$BK/screen_zeros.png" && echo "C/screen: $(md5sum $BK/screen_zeros.png | cut -c1-8)"
sleep 8
echo -n "C/still zero after 8s more: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value","no-value-field") for k,v in d["items"].items()})'

echo "== D) pushd back -> real values replace the floor within seconds =="
systemctl --user start pb-strata-pushd; sleep 5
echo -n "D/api/push values: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value") for k,v in d["items"].items()})'
adb -s 481fe5dc exec-out screencap -p > "$BK/screen_real.png" && echo "D/screen: $(md5sum $BK/screen_real.png | cut -c1-8)"
echo -n "D/services: "; systemctl --user is-active phonebox pb-strata-pushd | tr '\n' ' '; echo
echo DONE
