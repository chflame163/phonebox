#!/usr/bin/env python3
"""Strata speed + context-fill + box power -> PhoneBox panel (stdlib only).

Auto-discovers the running online serve (process running serve/server.py) for its --config json api_key and
--port, so it survives iq3s / UD swaps. Pushes webhook keys the panel reads with Pushed value widgets:
  strata_tps      decode tokens/sec
  strata_prefill  prefill tokens/sec
  strata_ctx      context fill % (also drives a gauge ring via progress)
  gpu_power       GPU board power draw (W) — nvidia-smi power.draw; level by absolute watts
                  (<=GW_WARN ok, <=GW_ERR warn, above that error — 100/300 as of 2026-11-12 16:0x)
  vram_gb         GPU memory in use as GB (e.g. 23.1 — set the widget's gauge max to 24) — same nvidia-smi call.
                  progress still carries the %, sub "96.3% · 912 MiB free".
                  level = headroom (free<=VR_WARN_FREE warn, <=VR_ERR_FREE error).
                  (Renamed from vram_pct on 2026-11-12 15:5x when the value switched to GB; that key had
                  itself been dropped that afternoon and put back as the VRAM widget.)
  strata_state    the engine's live model state, for the "Model state" Custom HTML widget
                  (6 lit-able badges + progress bar). Raw /metrics live fields are passed through untouched;
                  the widget itself reproduces serve/web/app.js renderMonitor() (label / detail / pct / tone).
                  payload: {state, raw_state, queued, phase, prompt_read, prompt_total, prompt_tokens,
                            generated, max_tokens, tok_s, last_detail?, ttl:20}
                  state = live.state ("idle"|"reading"|"generating"|"unloaded"|"error"); the widget lights
                  "queued" itself when queued > 0, exactly like the engine's own Monitor.
On any read failure it skips the affected push so the last value expires by its ttl.
(cpu_power / power_total were dropped on 2026-11-12 per user request; vram_pct came back with the VRAM widget.)
"""
import json, glob, os, subprocess, time, urllib.request

AGENT = "http://127.0.0.1:8765"
FALLBACK_KEY = os.environ.get("PB_STRATA_FALLBACK_KEY", "REPLACE-WITH-STRATA-API-KEY")
FALLBACK_PORT = "8080"
# vram_pct 的着色按“还剩多少显存”(MiB) 而不是占用百分比：这台引擎常驻就把 24G 吃到 ~96%
# （实测 23,664/24,576 MiB，free 只有 912）。阈值按用户 11-12 15:5x 指定 = 2000 / 500：
# 余量不到 2G 就橙（所以常态 912 本来就是橙色），掉进 500 MiB 以内才算真危险(红)。
VR_WARN_FREE, VR_ERR_FREE = 2000, 500
# gpu_power 按绝对瓦数分级（用户 11-12 16:0x 指定）：≤100W 绿、100–300W 橙、>300W 红。
# 之前是按 power.limit 的 50/80% 比例（350W 墙 ⇒ 175/280），改绝对值后 limit 只进缓存、不参与判定。
GW_WARN, GW_ERR = 100.0, 300.0


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


GPU_CACHE = "/tmp/pb_gpu_cache.json"


def gpu_stats(max_age=5.0):
    """(power_w, power_limit_w, vram_used_mb, vram_total_mb)，nvidia-smi 每 max_age 秒才真查一次
    （结果缓存在 GPU_CACHE）。timer 提到 1s 后不能每秒 fork 一次 nvidia-smi：满载时它自己要等
    0.2-0.5s 的锁。显存是同一次查询顺带拿的，不额外加开销。失败时四项全 None。"""
    try:
        c = json.load(open(GPU_CACHE))
        # used/total 也在才算有效：老缓存只有瓦数，直接复用会让 vram_pct 静默消失
        if time.time() - float(c.get("ts", 0)) < max_age and c.get("used") and c.get("total"):
            return c["draw"], c["limit"], c["used"], c["total"]
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=power.draw,power.limit,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=6).stdout.split("\n")[0]
        p = [x.strip() for x in out.split(",")]
        res = (round(float(p[0]), 1), round(float(p[1]), 1), int(float(p[2])), int(float(p[3])))
        try:
            json.dump({"ts": time.time(), "draw": res[0], "limit": res[1],
                       "used": res[2], "total": res[3]}, open(GPU_CACHE, "w"))
        except Exception:
            pass
        return res
    except Exception:
        return None, None, None, None


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

    # model state: raw live fields + health.loaded 兜底，控件自己复刻引擎 Monitor 的文案与点亮逻辑
    health = get_json(f"{base}/health", api)
    st = live.get("state")
    if health is not None and health.get("loaded") is False and st in (None, "idle"):
        st = "unloaded"
    if st:
        body = {"state": st, "raw_state": live.get("state"),
                "queued": live.get("queued") or 0, "phase": live.get("phase"),
                "prompt_read": live.get("prompt_read"), "prompt_total": live.get("prompt_total"),
                "prompt_tokens": live.get("prompt_tokens"),
                "generated": live.get("generated"), "max_tokens": live.get("max_tokens"),
                "tok_s": live.get("tok_s"), "ttl": 20}
        if latest and latest.get("output_tokens") is not None:
            ld = latest.get("decode_tok_s")
            body["last_detail"] = f"last: {int(latest['output_tokens']):,} tokens" + (
                f" at {float(ld):,.1f} tok/s" if ld else "")
        # generating 的进度分母：引擎自带面板用 max_tokens（本会话客户端给的是 359,945 ⇒ 条子永远贴地）。
        # 这里另给一个经验分母 = 最近 8 个请求 output_tokens 的 p75（下限 512，避免一次短应答就把条顶满），
        # 控件优先用它，生成段就有了真实行程；无样本时控件退 indeterminate 扫动。
        # detail 里的 token 数字仍是引擎原口径，一点没改。
        outs = [int(r.get("output_tokens") or 0) for r in
                sorted(reqs, key=lambda r: r.get("time") or 0)][-8:]
        outs = sorted(o for o in outs if o > 0)
        if outs:
            body["out_est"] = max(outs[min(len(outs) - 1, int(0.75 * len(outs)))], 512)
        push("strata_state", body)

    # GPU power + VRAM（同一次 nvidia-smi 查询）。gpu_power 按 draw/limit 比例着色；
    # vram_pct 按“还剩多少余量”着色：这台 strata 常驻就有 ~88%，所以红线留给真吃紧的 90/95。
    gw, glimit, vu, vt = gpu_stats()          # glimit 现在只进缓存，不参与着色（阈值见 GW_WARN/GW_ERR）
    if gw is not None and gw > 0:
        push("gpu_power", {"value": gw, "unit": "W", "ttl": 20,
                           "level": "error" if gw > GW_ERR else
                                    ("warn" if gw > GW_WARN else "ok")})
    vram_txt = "n/a"
    if vu and vt:
        vp = round(100.0 * vu / vt, 1)
        gb = round(vu / 1024.0, 1)          # 用户 15:5x 要求：值直接显示 GB（如 23.5），gauge max 填 24
        free = vt - vu
        vram_txt = f"{gb}G/{round(vt / 1024.0, 1)}G ({vp}%, free {free} MiB)"
        # key 就叫 vram_gb（11-12 15:5x 用户定的，面板控件的 key 同步改）；progress 仍给百分比供其它样式用
        push("vram_gb", {"value": gb, "unit": "GB", "progress": vp, "ttl": 20,
                          "sub": f"{vp:.1f}% · {free} MiB free",
                          "level": "error" if free <= VR_ERR_FREE else
                                   ("warn" if free <= VR_WARN_FREE else "ok")})

    print(f"base={base} decode={speed} prefill={prefill} fill={fill} gpu_w={gw} vram={vram_txt}")


if __name__ == "__main__":
    main()
