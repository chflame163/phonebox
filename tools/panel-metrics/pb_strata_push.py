#!/usr/bin/env python3
"""Strata speed + context-fill + box power -> PhoneBox panel (stdlib only).

Auto-discovers the running online serve (process running serve/server.py) for its --config json api_key and
--port, so it survives iq3s / UD swaps. Pushes webhook keys the panel reads with Pushed value widgets:
  strata_tps      decode tokens/sec
  strata_prefill  prefill tokens/sec
  strata_ctx      context fill % (also drives a gauge ring via progress)
  gpu_power       GPU board power draw (W) — nvidia-smi power.draw, level color-coded at 50/80% of power.limit
On any read failure it skips the affected push so the last value expires by its ttl.
(vram_pct / cpu_power / power_total were dropped on 2026-11-12 per user request.)
"""
import os, json, glob, subprocess, urllib.request

AGENT = "http://127.0.0.1:8765"
FALLBACK_KEY = os.environ.get("PB_STRATA_FALLBACK_KEY", "REPLACE-WITH-STRATA-API-KEY")
FALLBACK_PORT = "8080"


def discover():
    port, api = FALLBACK_PORT, FALLBACK_KEY
    for cl in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            args = [a.decode("utf-8", "replace") for a in open(cl, "rb").read().split(b"\0")]
        except Exception:
            continue
        if not any(a.endswith("serve/server.py") for a in args):
            continue
        for i, a in enumerate(args):
            if a == "--port" and i + 1 < len(args):
                port = args[i + 1]
            if a == "--config" and i + 1 < len(args):
                try:
                    api = json.load(open(args[i + 1])).get("api_key", api)
                except Exception:
                    pass
        break
    return f"http://127.0.0.1:{port}", api


def get_json(url, api):
    try:
        r = urllib.request.Request(url, headers={"Authorization": f"Bearer {api}"})
        return json.load(urllib.request.urlopen(r, timeout=6))
    except Exception:
        return None


def push(key, body):
    try:
        r = urllib.request.Request(
            f"{AGENT}/api/push/{key}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(r, timeout=6)
        return True
    except Exception as e:
        print(f"push {key} failed: {e}")
        return False


def gpu_stats():
    """One nvidia-smi call -> (power_w, power_limit_w). (None, None) on failure."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw,power.limit",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6).stdout.split("\n")[0]
        p = [x.strip() for x in out.split(",")]
        return round(float(p[0]), 1), round(float(p[1]), 1)
    except Exception:
        return None, None


def main():
    base, api = discover()
    m = get_json(f"{base}/metrics", api)
    slots = get_json(f"{base}/slots", api)

    live = (m or {}).get("live") or {}
    reqs = (m or {}).get("requests") or []
    latest = max(reqs, key=lambda r: r.get("time", 0)) if reqs else None

    # decode speed
    speed = live.get("tok_s") or live.get("tok_s_mean")
    if speed is None and latest:
        speed = latest.get("decode_tok_s")
    if speed is not None:
        try:
            s = round(float(speed), 1)
            push("strata_tps", {"value": s, "unit": "tok/s", "ttl": 20,
                                "level": "ok" if s >= 60 else ("warn" if s >= 20 else "error")})
        except (TypeError, ValueError):
            speed = None

    # prefill speed
    prefill = live.get("prefill_tok_s_mean")
    if prefill is None and latest:
        pt = latest.get("prompt_total") or latest.get("prompt_tokens") or 0
        reused = latest.get("reused") or 0
        pms = latest.get("prompt_ms") or 0
        if pms and pt > reused:
            prefill = (pt - reused) / (pms / 1000.0)
    if prefill is not None:
        try:
            p = round(float(prefill), 1)
            if p > 0:
                push("strata_prefill", {"value": p, "unit": "t/s", "ttl": 20})
        except (TypeError, ValueError):
            prefill = None

    # context fill %
    fill = None
    for slot in (slots or []):
        if slot.get("id") == 0:
            nc = slot.get("n_ctx") or 0
            np = slot.get("n_prompt_tokens") or 0
            if nc:
                fill = round(np / nc * 100, 1)
            break
    if fill is not None:
        push("strata_ctx", {"value": fill, "unit": "%", "progress": fill, "ttl": 60,
                            "level": "error" if fill >= 90 else ("warn" if fill >= 75 else "ok")})

    # GPU power (one nvidia-smi call). gpu_power is colored by % of the current power limit
    gw, glimit = gpu_stats()
    if gw is not None and gw > 0:
        ratio = (gw / glimit) if (glimit and glimit > 0) else (gw / 350.0)
        push("gpu_power", {"value": gw, "unit": "W", "ttl": 20,
                           "level": "error" if ratio >= 0.8 else ("warn" if ratio >= 0.5 else "ok")})

    print(f"base={base} decode={speed} prefill={prefill} fill={fill} gpu_w={gw}")


if __name__ == "__main__":
    main()
