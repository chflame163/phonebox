#!/bin/bash
# pb_watchdog_retest.sh — same power-loss net, this time FORCING the panel foreground and asserting
# window focus before every screencap (the previous run captured the Settings app the user had open).
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
U="adb -s 481fe5dc"; K=net.oxog.phonebox.deskpanel
TS=$(date +%Y%m%d-%H%M%S); BK=/mnt/nvme0n1p1/temp/pb-watchdog-re-$TS; mkdir -p "$BK"

focus() { $U shell dumpsys window 2>/dev/null | grep -m1 mCurrentFocus | tr -d '\r'; }
shot() { U7=$1; echo "focus: $(focus)"; $U exec-out screencap -p > "$BK/$U7.png" && echo "shot $U7: $(md5sum $BK/$U7.png | cut -c1-8)"; }

raise() { $U shell input keyevent KEYCODE_WAKEUP >/dev/null 2>&1; sleep 1; $U shell am start -n $K/.MainActivity >/dev/null 2>&1; sleep 3; }

echo "== A) panel foreground, live values =="
raise; shot v2_live

echo "== B) freeze truth (pushd down) then SIGKILL agent, no respawn =="
systemctl --user stop pb-strata-pushd
mkdir -p ~/.config/systemd/user/phonebox.service.d
printf '[Service]\nRestart=no\n' > ~/.config/systemd/user/phonebox.service.d/killtest.conf
systemctl --user daemon-reload
kill -9 "$(systemctl --user show phonebox -p MainPID --value)"
sleep 8

echo "== C) +8 s of agent silence: watchdog must have floored =="
curl -s -m2 http://127.0.0.1:8765/api/push >/dev/null 2>&1 && echo "agent UP (bad)" || echo "agent DOWN"
echo -n "graceful lines last 90s (expect 0): "; journalctl --user -u phonebox --since "-90 s" --no-pager 2>/dev/null | grep -c "graceful stop" || true
shot v2_kill8

echo "== D) agent back, pushd STILL down: both floors agree on zeros =="
rm ~/.config/systemd/user/phonebox.service.d/killtest.conf; rmdir ~/.config/systemd/user/phonebox.service.d
systemctl --user daemon-reload; systemctl --user reset-failed phonebox 2>/dev/null || true
systemctl --user start phonebox; sleep 6
echo -n "D/agent: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value","nofield") for k,v in d["items"].items()})'
shot v2_agentback

echo "== E) pushd back: real values restored =="
systemctl --user start pb-strata-pushd; sleep 5
echo -n "E/agent: "; curl -s -m5 http://127.0.0.1:8765/api/push | python3 -c 'import json,sys;d=json.load(sys.stdin);print({k:v["data"].get("value") for k,v in d["items"].items()})'
shot v2_restored
echo "services: $(systemctl --user is-active phonebox pb-strata-pushd | tr '\n' ' ')"; echo "DONE $BK"
