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

## 6. R' - 常驻 1s + GPU 数据源切到 agent 自己的 nvidia-smi 流（同夜 22:05 追加，解决 §4 前两条）

起因=用户观察"pushed value 还是 ~5s 一刷"。35s 采样实锤：`gpu_power` 6s 一跳（`max_age=5.0`
缓存 × 2.2s 轮次量化）、strata 系 2.2s（oneshot+timer 的真实节奏，开机还撞 start-limit-hit 丢轮）。

改动（`pb_push_resident_patch1.py` 六锚点，live+repo 双份、py_compile 过）：
- 新增 `gpu_stats_agent()`：loopback `GET /api/state` 取 `pc.gpu` 四项（与 nvidia-smi 同一组字段；
  GB→MiB 折算对齐旧接口），失败回退原 `gpu_stats()`（nvidia-smi+5s 缓存）；main 走 `gpu_stats_any()`。
  脚本自此 **零 nvidia-smi fork**（agent 那条常驻 `-lms 1000` 流就是数据源）。
- `get_json`/`push` timeout 6→2；`print(..., flush=True)`（journal 实时逐行）；
  `_run_forever()` 每秒一轮（tick 异常只打印不杀循环），`PB_RESIDENT=1` 启用。
- unit：`pb-strata-pushd.service`（Type=simple、After=phonebox.service、Restart=always、已
  **enable**，WantedBy=default.target）；旧 timer disable 未删=回滚件。

部署验收（22:05-22:06）：journal **每秒一行**；30s 采样 `gpu_power` 换值节奏 **1.07s**、
`strata_state` **1.03s**；`tps/prefill/ctx` 的 value 变化慢系采样窗引擎空闲（decode 恒 110.8
数个周期），非传输；`vram_gb` 数值本就稳定。开机侧顺带免费拿到 P0 大部分收益：pushd
`After=phonebox.service`、agent 就绪即 1s/轮（GPU 键首帧=agent ready+1s，不再等 60s timer；
strata 键真实下限=引擎加载 ~5min）。§4 前两条就此关闭，只剩 stream flapping 独立案。

回滚一行：`systemctl --user disable --now pb-strata-pushd && systemctl --user enable --now pb-strata-push.timer`
（脚本无需回退：不设 env 即回单轮模式）。
