#!/usr/bin/env python3
"""pb_push_resident_patch1.py - R': true 1 s push cadence (apply to live AND repo script copies).

Two problems fixed at once, both measured 2026-11-13 21:5x (see TESTLOG-push-stream §6):
  * gpu_power / vram_gb numbers only moved every ~6 s: gpu_stats() re-reads its nvidia-smi
    5 s cache (that cache existed only to keep the 1 s oneshot timer from forking nvidia-smi
    every round - and that fork was itself what slowed the loop down).
  * the script cadence was 2.2 s, not 1 s: every round paid a fresh interpreter, and at boot
    the 1 s timer tripped systemd's default start limit (StartLimitIntervalSec=10s/Burst=5)
    and dropped rounds ('start-limit-hit' in the journal).

Fix: the agent already keeps a resident `nvidia-smi -lms 1000` stream and publishes its fields
(power / powerLimit / vramUsed / vramTotal) inside every 1 Hz /api/state frame - the exact same
query the script used to fork. So gpu_stats_agent() reads that over loopback (0.0002 s, no
subprocess, 1 Hz fresh), with the old nvidia-smi+cache path kept as the fallback for when the
agent is down. And PB_RESIDENT=1 runs main() in one process once a second (simple systemd unit
replaces the oneshot+timer), which also makes the start limit moot.

Usage: python3 -I pb_push_resident_patch1.py <script-path>
Idempotent (skips edits whose new text is present); every anchor must be unique.
"""
import pathlib
import sys

path = pathlib.Path(sys.argv[1])

EDITS = [
    # ---- 1. agent-first GPU source, inserted above the cache constant ----
    ('GPU_CACHE = "/tmp/pb_gpu_cache.json"',
     'GPU_CACHE = "/tmp/pb_gpu_cache.json"\n'
     '\n'
     '\n'
     'def gpu_stats_agent(timeout=1.0):\n'
     '    """(draw, limit, used_mb, total_mb) from the agent\'s own resident nvidia-smi -lms 1000\n'
     '    stream: loopback GET /api/state, fields pc.gpu.power/powerLimit/vramUsed/vramTotal - the\n'
     '    same query gpu_stats() used to fork, at true 1 Hz freshness and zero subprocess cost\n'
     '    (vram arrives in GB there, converted back to MiB for the old interface). All-None when\n'
     '    the agent is not answering; gpu_stats() (nvidia-smi + 5 s cache) then serves as fallback."""\n'
     '    try:\n'
     '        g = json.load(urllib.request.urlopen(AGENT + "/api/state", timeout=timeout))["pc"]["gpu"]\n'
     '        return (round(float(g["power"]), 1), round(float(g["powerLimit"]), 1),\n'
     '                int(round(float(g["vramUsed"]) * 1024)), int(round(float(g["vramTotal"]) * 1024)))\n'
     '    except Exception:\n'
     '        return None, None, None, None\n'
     '\n'
     '\n'
     'def gpu_stats_any():\n'
     '    res = gpu_stats_agent()\n'
     '    return res if res[0] is not None else gpu_stats()',
     "gpu-source-agent-first"),

    # ---- 2. main() takes the new entry point ----
    ('    gw, glimit, vu, vt = gpu_stats()',
     '    gw, glimit, vu, vt = gpu_stats_any()',
     "main-uses-any"),

    # ---- 3. loopback/lan calls: fail fast, the loop re-runs in 1 s anyway ----
    ('        return json.load(urllib.request.urlopen(r, timeout=6))',
     '        return json.load(urllib.request.urlopen(r, timeout=2))',
     "get_json-timeout-2"),
    ('        urllib.request.urlopen(r, timeout=6)',
     '        urllib.request.urlopen(r, timeout=2)',
     "push-timeout-2"),

    # ---- 4. journal needs the lines when they happen, not when the buffer fills ----
    ('    print(f"base={base} decode={speed} prefill={prefill} fill={fill} gpu_w={gw} vram={vram_txt}")',
     '    print(f"base={base} decode={speed} prefill={prefill} fill={fill} gpu_w={gw} vram={vram_txt}", flush=True)',
     "print-flush"),

    # ---- 5. the resident loop ----
    ('if __name__ == "__main__":\n'
     '    main()',
     'def _run_forever():\n'
     '    """PB_RESIDENT=1 under a simple systemd unit: one process, one push per second. The\n'
     '    oneshot+timer shape never reached 1 s - every round paid a fresh interpreter, its own\n'
     '    nvidia-smi, and at boot the 1 s cadence tripped systemd\'s default start limit\n'
     '    (10 s / 5 starts) and dropped whole rounds. Measured effective cadence: 2.2 s."""\n'
     '    while True:\n'
     '        start = time.time()\n'
     '        try:\n'
     '            main()\n'
     '        except Exception as e:                      # a broken tick must not take the loop down\n'
     '            print("tick failed:", e, flush=True)\n'
     '        time.sleep(max(0.05, 1.0 - (time.time() - start)))\n'
     '\n'
     '\n'
     'if __name__ == "__main__":\n'
     '    import os\n'
     '    if os.environ.get("PB_RESIDENT"):\n'
     '        _run_forever()\n'
     '    else:\n'
     '        main()',
     "resident-loop"),
]

s = path.read_text()
for old, new, tag in EDITS:
    if new in s:
        print(f"[{tag}] already applied")
        continue
    n = s.count(old)
    assert n == 1, f"[{tag}] anchor found {n} times"
    s = s.replace(old, new)
    print(f"[{tag}] applied")
path.write_text(s)

import py_compile
py_compile.compile(str(path), doraise=True)
print("py_compile OK")
