# 手机电池维护策略（pb_chargeguard）

2026-11-12 起在 Strata 服务器上运行。目标：让长期插电做面板的 3T 既不长期浮在 4.35V、又能定期做深充/满充校准。

## 策略（三层）

| 层 | 动作 | 默认参数 |
|---|---|---|
| 日常 | 电量 ≥80 停充；≤65 复充；中间保持原状（滞回） | `PB_STOP_LEVEL=80` `PB_START_LEVEL=65` `PB_FLOOR_LEVEL=25` |
| 每周 | 完整走一次 **40% → 80%**（先断充放到 40，再放开充回 80，然后回日常） | `PB_W_DAYS=7` `PB_W_START=40` `PB_W_STOP=80` |
| 每季度 | 完整走一次 **20% → 100%**，且**到 100% 后再顶充 30 分钟**才断（让恒压段走完、燃料计校准） | `PB_Q_DAYS=90` `PB_Q_START=20` `PB_Q_STOP=100` `PB_Q_TOPOFF_MIN=30` |

保护与兜底：电量 ≤`PB_CRIT_LEVEL=8` 无条件允许充电并中止当期校验；放电阶段超 `PB_DIS_TMO_S=36000`（10h）或回充阶段超 `PB_CHG_TMO_S=64800`（18h）自动退回日常并在日志里告警（后者告警会提示"这口径下 500mA 不够"）。季度校验完成后会把"上次周校验"时间一并置为现在（20→100 显然覆盖了 40→80）。

## 机制

写手机 PMIC 的 sysfs 开关，**不切 USB 口**：root 下 `echo 0|1 > /sys/class/power_supply/battery/charging_enabled`。停充时 VBUS 与 adb 数据链都还在，所以面板不受影响（已实测）。

前提：手机 Lineage 18.1 是 userdebug 且开发者选项里开了 **Root 身份调试**（`adb root` 可用；手机重启后 adbd 退回 shell，脚本会自动重试一次）；agent 自带的 ChargeGuard（uhubctl/HA 那两条路）在这台机器上切不到手机，保持 `charge.enabled:false`。

跑法：cc 的 **user** timer `pb-chargeguard.timer` 每 60 秒跑一次 `~/bin/pb_chargeguard.sh auto`（OnBootSec=90s，靠 Linger 常驻；服务器关机时 `adb devices` 里没有手机，脚本立刻退出、零副作用）。

## 命令

```
~/bin/pb_chargeguard.sh              # = auto，按策略写开关（timer 用这个）
~/bin/pb_chargeguard.sh status       # 只读：电量/开关/当前阶段/距下次校验
~/bin/pb_chargeguard.sh calib weekly # 立刻开始一次 40→80 周校验
~/bin/pb_chargeguard.sh calib qtr    # 立刻开始一次 20→100+顶充 季校验
~/bin/pb_chargeguard.sh on | off     # 手动写一次开关（不动阶段）
~/bin/pb_chargeguard.sh reset        # 立刻回日常（保留日程时间戳）
```
状态文件 `~/.local/state/pb_chargeguard.state`（phase / phase_since / t100 / last_weekly / last_quarter，重启机器不丢）；日志 `/mnt/nvme0n1p1/temp/pb_chargeguard.log`，每 `PB_BEAT=30` 次（约 30 分钟）写一行心跳 `level=… charging_enabled=… phase=…` —— **用它判断 65% 复充后能不能爬回 80%**。面板状态推 key `charge_state`（值就是当前阶段名）。

停 timer：`systemctl --user disable --now pb-chargeguard.timer`；恢复：`systemctl --user enable --now pb-chargeguard.timer`。
彻底回滚：再 `adb -s 481fe5dc shell "su 0 sh -c 'echo 1 > /sys/class/power_supply/battery/charging_enabled'"`（或 root adb 下 `echo 1 > …`）让它正常满充。

## dry-run（不碰手机就能验策略）

`pb_gtest.sh` 里 24 条断言覆盖：区间滞回、安全下限、CRIT 中止、周/季各阶段跳转、顶充计时、到期自动起校验、季度优先于周、两类超时回退、reset。实现方式是给脚本注入假输入：

```
PB_ONESHOT=1 PB_LEVEL=39 PB_CHG=0 PB_NOW=<epoch> PB_STATE=<临时文件> PB_PUSH=0 \
  ~/bin/pb_chargeguard.sh auto
```
跑测试：`S=/path/to/pb_chargeguard.sh bash pb_gtest.sh` → 期望 `pass=24 fail=0`（2026-11-12 实测如此）。这样季度校验不用等 90 天才第一次验证。

## 已知待观察

停充期间实测掉电很快（3T 亮屏负载大于该 USB2 口的 500mA 预算，心跳日志里 100→86 用了约 40 分钟），所以 65% 复充后能否爬回 80 还没有长程数据；若日志显示复充阶段涨不动甚至继续掉，解法按优先级：换 **USB 3.x（SS，900mA）** 口或带独立供电的 hub（顺带还给出可 uhubctl 断电的口）、或把日常区间改浅（`PB_STOP_LEVEL=100 PB_START_LEVEL=90`，几乎不等爬升）、或把 `PB_CHG_TMO_S` 调小让它及早认输回日常。
