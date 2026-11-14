#!/bin/bash
# pb_bootcheck.sh - one-shot boot evidence collector for the power-standby desk (run by
# pb-bootcheck.service at each boot; also runnable by hand). Two samples: boot+120 s (the
# wake chain should have landed the panel by ~46 s) and boot+300 s (it should have stuck,
# and nothing should have re-entered deep standby while the agent answers).
# 11-13 lesson applied: spool the raw logcat windows DURING the event - the ring gets
# flushed by system noise and later readbacks miss the interesting minutes.
set -uo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)
U="adb -s 481fe5dc"
OUT=/mnt/nvme0n1p1/temp/pb-bootcheck-$(date +%Y%m%d-%H%M)
mkdir -p "$OUT"
TL=$OUT/timeline.txt
T() { echo "$(date '+%T')  $*" >> "$TL"; }

W_BOOT=$(date +%s)
T "bootcheck start; host boot was: $(uptime -b 2>/dev/null)"
systemd-analyze > "$OUT/boot-analyze.txt" 2>&1

snap() { # $1 label, $2 window-from(epoch), $3 window-to(epoch)
  T "== sample $1 (logcat window $2..$3) =="
  T "wakefulness: $($U shell dumpsys power 2>/dev/null | grep -m1 mWakefulness | tr -d '\r')"
  T "focus:       $($U shell dumpsys window 2>/dev/null | grep -m1 mCurrentFocus | tr -d '\r')"
  T "stay_on:     $($U shell settings get global stay_on_while_plugged_in 2>/dev/null | tr -d '\r')"
  $U logcat -d -v epoch 2>/dev/null | awk -v a="$2" -v b="$3" '($1>=a&&$1<=b)' \
    | grep -iE " PhoneBox:|PowerManagerService:|deep standby|trimmed|Waking up|Dozing" > "$OUT/logcat-$1.txt"
  echo "  logcat lines spooled: $(wc -l < "$OUT/logcat-$1.txt")" >> "$TL"
  $U exec-out screencap -p > "$OUT/screen-$1.png" 2>/dev/null
  T "push age(s): $(curl -s -m 4 http://127.0.0.1:8765/api/push 2>/dev/null | python3 -c 'import json,sys,time
try:
    it = (json.load(sys.stdin) or {}).get("items") or {}
    now = time.time() * 1000
    print(len(it), {k: round((now - v["at"]) / 1000, 1) for k, v in sorted(it.items())})
except Exception as e:
    print("agent not answering:", e)' 2>/dev/null)"
  T "phones:      $(curl -s -m 4 http://127.0.0.1:8765/api/phones 2>/dev/null | head -c 130)"
}

sleep 120
# window starts 10 min before this boot: the SHUTDOWN side of the previous boot lives in the
# phone's logcat (the phone never rebooted), so the screen-off hook events fall in range too
snap "t120" $((W_BOOT - 600)) "$W_BOOT"
sleep 180
snap "t300" "$W_BOOT" "$(date +%s)"

{ echo "user: phonebox=$(systemctl --user is-active phonebox) pushd=$(systemctl --user is-active pb-strata-pushd) chargeguard.timer=$(systemctl --user is-active pb-chargeguard.timer)"
  echo "system: sleep=$(systemctl is-active phonebox-sleep 2>&1) wake=$(systemctl is-active phonebox-wake 2>&1)"; } > "$OUT/units.txt" 2>&1
journalctl --user -u pb-strata-pushd -b --no-pager -o short-iso 2>/dev/null | head -10 > "$OUT/pushd-first-lines.txt"
journalctl -b  -u phonebox-wake.service -u phonebox-sleep.service --no-pager > "$OUT/hooks-thisboot.txt" 2>&1
journalctl -b -1 -u phonebox-sleep.service --no-pager > "$OUT/hooks-lastboot-sleep.txt" 2>&1
T "DONE - evidence dir: $OUT"
echo done > "$OUT/status"
