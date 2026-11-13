# TESTLOG - pushed values ride the 1 Hz state frame (P3) - 2026-11-13 深夜

## 0. 一句话

push 控件的"值变了→手机再 GET 一趟"第二跳被消灭：`State()` 里带上 `pushItems`，手机
`applyState` 就地消化。实测手机对 `/api/push` 的轮询 **9 次/24s → 0 次/20s**，六控件照常 1Hz
刷值（含 stream 断开走 poll 兜底时——poll 的 `/api/state` 响应同样带值，白天的 SSE 38~46s
flapping 就此变得无害）。分析全文见 `C:\work\phonebox\phonebox-push-boot-latency-feasibility-20261113.md`。

## 1. 改动（3 文件 +11/-2，`pb_push_stream_patch1.py` 幂等锚点）

- `agent/PhoneBox.Agent/Program.cs` — `State()` 内 `pushVersion` 行后加 `pushItems = push.Snapshot(),`
  （Snapshot 与 `GET /api/push` 的 items 完全同形状；1Hz 帧 +~1.5KB）。
- `android/app/src/main/assets/www/main.js` — `applyState()` pushVersion 比对改三路：
  帧内有 items 且版本变→直填 `D.push`+emit；版本未变→静默换引用（过期蒸发随整图替换生效）；
  帧内无 items（stock agent）→ 保持经典 version→GET。手机/agent 新旧任意组合均兼容。
- `android/app/build.gradle.kts` — versionCode 27→28（versionName 仍 0.9.3）。
- `widgets/basic.js` 零改动（`W.push` 本就 `needs:['push','tick']`，渲染侧一直是 1Hz）。

## 2. 部署（`pb_push_stream_deploy.sh`，21:53）

| 项 | 改前 | 改后 |
|---|---|---|
| agent | 原版 0.9.3 dll `16a2fe7b` | **fork master 构建** dll `311d7dce`（快照回滚锚点 `/mnt/nvme0n1p1/temp/phonebox-agent-stock093-20261113-215330/`）|
| APK | vc27 `0c6dc633` | **vc28** `bda89ec7`（同 debug key 签名，`install -r` 数据/配对无损）|

服务重启后 journal：phone connected→stay_on 写 7（keepAwake）→live stream opened (phone, USB/local) ✓。

## 3. 验收（真机 + 抓包）

- `GET 127.0.0.1:8765/api/state` → `pushVersion` 在、`pushItems` = 六键
  `['gpu_power','strata_ctx','strata_prefill','strata_state','strata_tps','vram_gb']` ✓
- 20s tcpdump（lo+8766）：**`GET /api/push` = 0**（改前白天实测 11 次/24s）、
  `POST /api/push` = 54（脚本 6 键/2.2s 节奏正常）、`GET /api/state` = 18——该窗口页面走的是
  **poll 兜底**（stream flapping 实况再现），值照样全活 ⇒ P3 双通道等价，flapping 降级为纯传输切换（无害）。
- 截图（手机 screencap `5babbaa0`）：GPU POWER 252W / VRAM 23.1GB / CONTEXT 16.3KB /
  DECODE 65.3 / PREFILL 887 / Model state "Thinking 110 tokens · 65.3 tok/s"（当时正是本
  Claude 会话在生成），六控件 age 全 "just now" ✓
- 面板自恢复链：agent 换新后 reverse/keepAwake/am-start 全由 Ensure 自动完成 ✓

## 4. 未解决（不在 P3 范围）

- 值新鲜度节奏仍是脚本的 ~2.2s（渲染 1Hz 但数字 2.2s 一变）——要真 1s 做 R（脚本常驻化）。
- 开机首帧仍等脚本第一推（timer 地板 + purge 旧值）——要开机即有画面做 P0/R（+可选 P1 stale 载入）。
- stream 为何 38~46s 一断（`AgentStream.kt`/路由 flapping？）——独立案子（白天文档 §4-C）。

## 5. 回滚

- agent 一行：`systemctl --user stop phonebox && find ~/.local/share/PhoneBox/app -maxdepth 1 -mindepth 1 -delete && cp -a /mnt/nvme0n1p1/temp/phonebox-agent-stock093-20261113-215330/. ~/.local/share/PhoneBox/app/ && systemctl --user start phonebox`
- 手机一行：`adb -s 481fe5dc install -r /mnt/nvme0n1p1/temp/phonebox-deepstandby-20261112-131324/app-release-v27.apk`（vc27 同日线上版）
- git：本 commit revert 即回源码态（新 phone+老 agent、老 phone+新 agent 都兼容，revert 不必急）。
