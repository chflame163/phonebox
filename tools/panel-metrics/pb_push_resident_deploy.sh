#!/bin/bash
# R' deploy: patch live+repo scripts, install pb-strata-pushd.service, cut over from the timer,
# then measure the real per-key cadence for 30 s. Rollback: disable+stop pushd, enable+start timer.
set -euo pipefail
export XDG_RUNTIME_DIR=/run/user/$(id -u)

echo "== 1) patch both script copies (asserts + py_compile inside) =="
python3 -I /tmp/pb_push_resident_patch1.py /home/cc/bin/pb_strata_push.py
python3 -I /tmp/pb_push_resident_patch1.py /home/cc/phonebox/tools/panel-metrics/pb_strata_push.py

echo "== 2) resident unit =="
cat > ~/.config/systemd/user/pb-strata-pushd.service <<'UNIT'
[Unit]
Description=Push panel metrics once a second (resident loop; GPU fields ride the agent's own nvidia-smi stream)
After=phonebox.service

[Service]
Type=simple
Environment=PB_RESIDENT=1
ExecStart=/usr/bin/python3 %h/bin/pb_strata_push.py
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT

echo "== 3) cut over =="
systemctl --user daemon-reload
systemctl --user disable --now pb-strata-push.timer
systemctl --user start --now pb-strata-pushd.service
sleep 12
echo "pushd=$(systemctl --user is-active pb-strata-pushd) timer=$(systemctl --user is-active pb-strata-push.timer 2>/dev/null || echo inactive)"
echo "pushd enabled at boot: $(systemctl --user is-enabled pb-strata-pushd)"
echo "== journal lines (cadence by eye) =="
journalctl --user -u pb-strata-pushd.service --no-pager -o short-iso 2>/dev/null | tail -6 | cut -c1-155

echo "== 4) 30 s per-key cadence sample =="
python3 -I <<'PYEOF'
import json, time, urllib.request
t0 = time.time(); prev = {}; chg = {}; last = {}
while time.time() - t0 < 30:
    try:
        d = json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/push", timeout=3))["items"]
    except Exception:
        time.sleep(0.4); continue
    for k, v in d.items():
        val = (v["data"].get("value") if isinstance(v.get("data"), dict) else None) or v["at"]
        if k in prev and prev[k] != val:
            chg[k] = chg.get(k, 0) + 1; last[k] = time.time() - t0
        prev[k] = val
    time.sleep(0.4)
print("cadence = seconds between value/refresh moves (lower is better)")
for k in sorted(prev):
    n = chg.get(k, 0)
    print("%-14s changes=%-3d cadence=%ss" % (k, n, round(30.0 / n, 2) if n else "-"))
PYEOF
echo DEPLOY_R_DONE
