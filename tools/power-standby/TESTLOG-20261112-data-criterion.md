# power-standby 判据改造（数据可达性）实测记录 — 2026-11-12

改动：`MainActivity.kt` 的熄屏判据从「USB 有没有供电」换成「**agent 还在不在回话** + 手机自己看到的 **USB 数据线状态**」两者取或。
提交：服务器 `~/phonebox` 分支上 `b39e0ae`（tag `power-standby-data`），`+127 / -31`，只碰 `MainActivity.kt` 与 `build.gradle.kts`（versionCode 24→25）。
最终包：`artifacts/PhoneBox-0.9.3-data-criterion.apk` = md5 `429618cca5bf03bfef8e3bde598aff4f`（时序数据出自同逻辑的前一版 md5 `25ee74abda0f417a145207155779f0f2`，两版仅差一处日志去重守卫）。

## 环境

| 项 | 值 |
|---|---|
| 手机 | ONEPLUS A3010（3T）/ LineageOS 18.1-20240305-nightly-oneplus3（Android 11）/ WebView 122 |
| 手机网络 | `wlan0` = 192.168.5.208/24，SSID `cc-home`（2.4G ch9，RSSI −23，link 86M），gateway 192.168.5.1 |
| 服务器 | cc-Ubuntu-3090 = 192.168.5.197，PhoneBox agent 0.9.3（`127.0.0.1:8765` + `0.0.0.0:8766`，lan enabled，证书持久化 `~/.config/PhoneBox/lan-cert.pfx`） |
| 接线 | 手机在 `/sys/bus/usb/devices/1-12`（xhci root 口，**不能软件断电**）；三个 ppps hub（2-8 / 1-10 / 1-13）当时全是空口 → 用手动拔插线等效 ChargeGuard 断充 |
| 参数 | `AGENT_SILENCE_MS=12s`，健康轮询 2s（判死后降 30s 并每次抓 6s PARTIAL_WAKE_LOCK），宽限 `display.powerStandbyDelaySec=5s`，`screen_off_timeout=10000ms` |
| 取证 | 服务器侧 user 服务 `pb-logcat`（logcat −b main/system/events，串口在 481fe5dc↔192.168.5.208:5555 自动切）→ `/tmp/pb_logcat.log`；`pb-state` 每 5s 一行 → `artifacts/state-timeline-20261112.csv`；`pb-seqtest` 一次性脚本 → `/tmp/pb_seq.log`。三者在 `…/phonebox-powerstandby-20261112-111552/` 有副本 |
| 备注 | 拔线后仍可观测 = 临时开了无线 adb（`adb tcpip 5555` + `adb connect 192.168.5.208:5555`），测毕已 `adb usb` 复原（`service.adb.tcp.port` = null） |

## 前置：手机经 Wi-Fi 取数已单独验证（11:08:43）

把 USB 隧道改指死端口（`adb reverse tcp:8765 tcp:19999`，agent 看门狗只看 `reverse --list` 里有没有 `tcp:8765` 字符串，改远程端口不会触发修复）并 `am force-stop` + `am start` 强制重连后，手机 **3 秒内自动回落 Wi-Fi**：agent 侧 8766 出现 6 条来自 192.168.5.208 的 ESTABLISHED、journal 打 `live stream opened (phone, Wi-Fi)`、`GET 127.0.0.1:8765/api/phones` 的 `via` 由 USB 翻成 Wi-Fi、屏幕保持 Awake；恢复 reverse 后 10 秒内自动回到 USB。结论：**配对不需要在手机上手点**，app 在 USB 上每 60s 自拉 `/api/pair` 已把 hosts/port/token/证书指纹存好（`AgentLink.kt`）。
坑：**只改 reverse 规则不会断已建立的隧道 socket**——第一次实验 24 秒内 agent 连 `live stream closed` 都没打，必须 force-stop 才作数。

## 三场景实测（11:22–11:26，用户物理拔插一次，其余脚本自动）

| 时刻 | 事件 | 证据 |
|---|---|---|
| 11:23:06 | **拔线**（场景①：服务器开着、断充、有数据） | CSV：serial 切到 192.168.5.208:5555、`USBpowered:false`、`status:3` 放电 |
| 11:23:09 → 11:24:04 | 面板**一直亮**、常亮锁不松 | `mWakefulnessAwake` + `wlock_uid=10154` 全程在；App 日志「agent silent 18s」反推数据流动到 11:24:10（= agent 停止那一刻）→ **①通过** |
| 11:24:06 | `systemctl --user stop phonebox`（场景②：无电 + 无数据） | `pb_seq.log`、journal `Stopping phonebox.service` |
| 11:24:28.565 | App 松开常亮锁 | `PhoneBox: standby: agent silent 18s, no USB link -> releasing the screen`（停止后 **22.5s**，符合 12+2+5 设计）；CSV `wlock_uid=` 空 |
| 11:24:38.6 / 39.4 | 系统熄屏 | `PowerManagerService: Going to sleep due to timeout` → `Dozing...` → `screen_state=off`；距数据消失 **约 33 秒** → **②通过** |
| 11:25:23 | **回插**（场景③：有电、agent 仍未起） | `status:2` 充电、plug edge plugged=true |
| 11:25:23 → 11:25:45 | 屏幕**没有因来电而亮**（USB 尚未 configured） | CSV 连续 5 行 `mWakefulnessDozing` → 符合「USB 来电先不亮屏」 |
| 11:25:53.870 | 手机自己亮屏 | `PhoneBox: standby: the computer answers again (silent for 103s) -> waking` → `PowerManagerService: Waking up from Dozing (uid=10154, reason=WAKE_REASON_APPLICATION, details=PhoneBox:powerStandby)`、`Screen on took 202 ms`。此刻 **agent 仍未运行**（脚本 11:26:51 才 start），驱动信号是手机侧 USB 数据线 `configured` → 手机端逻辑独立成立 → **③通过** |
| 11:26:51 / 11:28:36 | agent 回来，面板恢复实时数据 | journal `live stream opened (phone, USB/local)`、`via:USB`、reverse 恢复 |

## 已知行为与结论

- 判死之后 App 每 30s 才探测一次（省电），所以**回插/开机到亮屏最多约 30s**；真实开机路径还有 agent 的 `adb reverse` 唤醒与 `phonebox-wake.service`，通常几秒内就亮。要更快就调小 `STANDBY_POLL_MS`。
- 优雅关机仍由 `phonebox-sleep.service` 在关机瞬间 force-stop + `keyevent 223` 秒熄；本改动的价值在于 crash / 跳闸 / 直接断电这类钩子叫不到的场景。
- 服务器开着但 **Wi-Fi 与 USB 数据线同时断** → 会判关机而熄屏（预期行为，回一条即可自愈）。
- 实测中出现「releasing the screen」在判死后每个 tick 重复打印（共 3 次，无害）→ 已在 `b39e0ae` 的最终包里加 `if (hostAlive && …)` 守卫消除。
- 本次改造顺带让 3T 满电时 `EXTRA_PLUGGED` 翻 0 那个老坑不再影响熄屏（判据已不看电量状态）。

## 遗留 / 待办

1. 真关机 + 真开机端到端各一次（会断这次 Claude 会话；11-11 已用旧包验过同类链路）。
2. ChargeGuard 若还要用，得把手机线挪到可逐口断电的 hub 口，并把 config 的 `charge` 重新配成 `enabled:true / method:"usb" / location / port`（今早 08:59-09:03 用户在 8765 页面保存时被改回 `enabled:false / method:"ha"`，location/port 键已丢失）。
3. 上游：本次改动可以并入 issue #30 的后续 PR（判据升级 + 手机侧自唤醒）。

## 回滚

```
adb -s 481fe5dc install -r -t /mnt/nvme0n1p1/temp/phonebox-backup-20261112-094409/phone-apk/phonebox-0.9.3-installed.apk   # md5 9f8cc3be, vc24
# 源码前态：/mnt/nvme0n1p1/temp/phonebox-powerstandby-20261112-111552/pre/ ；服务器仓库回滚：git -C ~/phonebox checkout f35cbb2 -- android/app
```
