#!/bin/bash
# P3 deploy: fork agent (pushItems in the state frame) + vc28 APK, with rollback anchors.
# Idempotent-ish: always re-snapshots the pre-swap agent, re-installs the built APK.
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
K=net.oxog.phonebox.deskpanel
U="adb -s 481fe5dc"
D=$HOME/.local/share/PhoneBox/app
DIST=$HOME/phonebox/agent/PhoneBox.Agent/bin/Release/net10.0
TS=$(date +%Y%m%d-%H%M%S)
BK=/mnt/nvme0n1p1/temp/phonebox-agent-stock093-$TS

echo "== 0) snapshot the stock agent we are leaving =="
mkdir -p "$BK" && cp -a "$D/." "$BK/" && echo "backup: $BK dll=$(md5sum $BK/PhoneBoxAgent.dll | cut -c1-8)"

echo "== 1) install vc28 apk =="
$U install -r $HOME/phonebox/android/app/build/outputs/apk/release/app-release.apk 2>&1 | tail -1
$U shell dumpsys package $K | grep -m1 versionCode | tr -d '\r'

echo "== 2) swap agent to the fork build, restart service =="
systemctl --user stop phonebox
find "$D" -maxdepth 1 -mindepth 1 -delete
cp -a "$DIST/." "$D/"
echo "app dir now: $(ls $D | wc -l) entries, dll=$(md5sum $D/PhoneBoxAgent.dll | cut -c1-8)"
systemctl --user start phonebox; sleep 12
echo "phonebox: $(systemctl --user is-active phonebox)"
journalctl --user -u phonebox -n 3 --no-pager -o short-iso 2>/dev/null | cut -c1-130

echo "== 3) relaunch panel, read the new frame =="
$U shell input keyevent KEYCODE_WAKEUP; sleep 1
$U shell am start -n $K/.MainActivity >/dev/null 2>&1; sleep 6
echo "stay_on=$($U shell settings get global stay_on_while_plugged_in | tr -d '\r')"
curl -s -m 5 http://127.0.0.1:8765/api/state | python3 -c 'import json,sys
d=json.load(sys.stdin); pi=d.get("pushItems")
print("pushVersion in frame:", "pushVersion" in d, "| pushItems keys:", (sorted(pi) if pi else pi))'
curl -s -m 5 http://127.0.0.1:8765/api/phones | head -c 130; echo

echo "== 4) 20s packet capture: GET /api/push must collapse (expect GET_push=0-1, GET_state=0, POST_push=40+) =="
M=/tmp/pbsr2; mkdir -p "$M"
printf "%s\n" "${PB_SUDO_PW:?export PB_SUDO_PW before running}" > $M/sw; printf "#!/bin/sh\ncat $M/sw\n" > $M/sap.sh
chmod 600 $M/sw; chmod 700 $M/sap.sh
SUDO_ASKPASS=$M/sap.sh sudo -A timeout 20 tcpdump -S -A -i any -nnl "tcp port 8765 or tcp port 8766" 2>/dev/null | awk '/GET \/api\/push/{a++} /GET \/api\/state/{b++} /POST \/api\/push/{c++} END{print "GET_push="a+0" GET_state="b+0" POST_push="c+0}'
rm -rf "$M"

$U exec-out screencap -p > /tmp/p3_screen.png && echo "screen: $(md5sum /tmp/p3_screen.png | cut -c1-8)"
echo DEPLOY_DONE
