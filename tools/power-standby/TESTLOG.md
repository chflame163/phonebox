# 归档与实测记录（2026-11-11，Strata 服务器 + OnePlus 3T 面板）

## 目录内容

- `scripts/pb_patch*.py`：五代补丁脚本（v1 诊断日志+锁释放+proximity → v2 BATTERY_CHANGED 沿检测 → v3 满电 STATUS 兜底 → v4/v4b keyguard 解除+去 proximity）
- `scripts/pb_build.sh`：服务器端 APK 全自动构建（腾讯 AndroidSDK/Gradle 镜像 + 阿里 Maven 镜像 + JDK17）
- `scripts/pb-sleep.sh` / `scripts/pb-wake.sh`：服务器 systemd 关机/开机钩子（部署于 /home/cc/bin/，unit 见下）
- `scripts/getwv9.ps1`：桌面端 APKMirror WebView 下载舞步脚本（Android 9 时代遗留）
- `artifacts/power-standby.patch`：对基线 723c473 的 git 格式补丁（可直接 -p1 应用）
- `artifacts/PhoneBox-0.9.3-powerfix.apk`：v4 成品（debug 签名，md5 前缀 9f8cc3be）
- `artifacts/agent-config-snapshot.json`：agent 生效配置快照（display.powerStandbyDelaySec=5、homeScreen/keepAwake=true、weather=北京 39.89N/116.84E、updates.auto=false）

## 服务器侧部署（不在本仓库，记录备忘）

- agent：`~/.local/share/PhoneBox/app`，systemd user 服务 `phonebox.service`（enable + loginctl linger）
- 钩子：`phonebox-sleep.service`（ExecStop=pb-sleep.sh：关机瞬间 force-stop→解除 stay_on→keyevent 223 秒熄）、
  `phonebox-wake.service`（ExecStart=pb-wake.sh：开机等 adb→唤醒→dismiss-keyguard→拉起面板），均 root + `HOME=/home/cc`
- 关键坑：OOS9 下 `fastboot flash recovery` 必败（分区 size 0），须 `fastboot boot recovery.img`；
  旧 USB 口对 fastboot 传输不可靠（Protocol error），换口后秒级；老安卓 WebView 13x 世代依赖
  `android.webkit.PacProcessor`，OOS9 定制 framework 缺此类——这是当初整机刷 LineageOS 18.1 的根因

## 实测时间线（手机日志为准）

| 版本 | 场景 | 结果 |
|---|---|---|
| 官方 0.9.3 | 拔线 | 2 分钟不熄（`Wake Locks: SCREEN_BRIGHT ws=WorkSource{10153}` 恒在；batterystats 证实 `plug=none` 已检测）|
| | 真重启 | 熄/亮均靠服务器侧钩子，手机无自愈 |
| v1(+日志) | 包替换后开机态 | `standby receiver registered, init pluggedIn=false` → 13s Dozing：**requestLayout 生效首次实证** |
| v2 | 真机拔插第一轮 | 46s 熄（30s 宽限+15s 超时，`plug edge via battery-changed` 双双在线）；回插亮屏但**卡滑动锁屏** |
| v3 | 满电 100% 插电 | `init pluggedIn=true`：STATUS=CHARGING 兜底生效，杜绝"服务器运行中误灭屏"回归 |
| v4(终版) | 拔线 | **约 16s 熄屏**（delay=5s + timeout=10s）✔ 用户复测通过 |
| | 回插 | **自动越过锁屏直接进面板** ✔（无任何 PhoneBox warning）|
| | 真关机/重启 | 钩子秒熄、开机自动恢复 ✔（v4 前已验，v4 未改钩子）|

## 已知边界

- proximity 立即灭屏在 3T/Lineage18.1 上不生效（acquire 后不灭、常亮期间压用户点屏），v4 弃用；
  如需 <10s 熄屏只剩"关机钩子按键"路径（已实现，真关机=瞬间）
- 拔线手动测试依赖 `EXTRA_STATUS` 沿，100% 满电拔线若 HAL 迟迟不报 DISCHARGING 会晚几秒（本组合未见）
- 上游若发新版：`updates.auto` 已置 false，避免官方版覆盖 debug 签名补丁包；合入上游后换回官方签名即可打开
