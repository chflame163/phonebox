# PR proposal: fix Power standby (screen sleep on USB power loss) on Android 8+

**Commit under review:** `tools/power-standby/artifacts/power-standby.patch` (diff vs upstream `723c473`,
tag-equivalent of release 0.9.3), verified on-device and built as `PhoneBox-0.9.3-powerfix.apk` (same dir).

## Problem

Power standby never sleeps the panel after the PC/server powers off (USB power cut) on any Android 8+ device.
On wake-back-after-power-restore the panel also stayed stuck behind the swipe keyguard.

Observed on OnePlus 3T (LineageOS 18.1 / Android 11), PhoneBox 0.9.3:

- panel stayed fully lit for minutes after USB power was cut (batterystats recorded `plug=none`, so the
  power state itself was detected by the system);
- restoring power woke the display but the "swipe to unlock" keyguard remained on top, panel not shown.

## Root causes

1. **The plug broadcasts never arrive.** `ACTION_POWER_CONNECTED` / `ACTION_POWER_DISCONNECTED` are on the
   Android 8 **implicit-broadcast restriction** list and are NOT on the exemptions list, so a
   context-registered receiver never gets them on any modern phone. The feature silently degraded to
   "keep screen on forever". `ACTION_BATTERY_CHANGED` is sticky and exempt for context-registered receivers.
2. **`clearFlags(FLAG_KEEP_SCREEN_ON)` does not reach WindowManager** on a static page: ViewRootImpl only
   re-syncs window attributes during a traversal that requests a layout. Without one,
   `SCREEN_BRIGHT_WAKE_LOCK` (WorkSource = our window) is kept forever and even `keyevent SLEEP` and the
   screen-off timeout are blocked.
3. **Full-battery HAL quirk (3T/Lineage):** at 100% the charger drops `EXTRA_PLUGGED` while
   `EXTRA_STATUS` keeps reporting `CHARGING` — a naive `EXTRA_PLUGGED` edge would sleep the panel on a
   fully-charged desk phone during normal operation.
4. **Wake path doesn't dismiss the swipe keyguard** (`isSecure=false`), so `startActivity` after power
   restore lands behind an undismissed lock screen.

## Fix (three small changes, no behavior change while powered)

- `MainActivity.kt`: watch sticky `ACTION_BATTERY_CHANGED` and treat an `EXTRA_PLUGGED` flip **or**
  `EXTRA_STATUS` in {CHARGING, FULL} as the plug edge (shared `PowerReceiver.edge()` helper, plus a
  manifest `<receiver>` documenting the feature and reviving the component on older lines).
- `MainActivity.kt`: `window.decorView.requestLayout()` right after add/clearFlags in `refreshKeepAwake()`,
  forcing the attribute sync that releases/acquires the keep-awake wakelock.
- `MainActivity.kt` + manifest: after waking on power restore, `KeyguardManager.requestDismissKeyguard()`
  (normal-level `DISABLE_KEYGUARD` permission) so the panel actually comes forward.

An earlier iteration also tried `PROXIMITY_SCREEN_OFF_WAKE_LOCK` for instant blanking; the 3T's
Lineage 18.1 build accepts the lock but does not blank on acquire (and re-sleeps any user-initiated
wake while held), so it was dropped in favor of the timeout path (measured: 5 s standby grace +
10 s system timeout ≈ 16 s to blank; instant on a real shutdown thanks to the PC-side hook).

## Verification (OnePlus 3T, LineageOS 18.1, PhoneBox 0.9.3 agent 0.9.3, USB to Ubuntu server)

- unplug → screen blanks in ~16 s (logs: `plug edge (runtime): plugged=false`, `Display ... OFF`)
- replug → screen wakes by itself, keyguard auto-dismissed, panel foreground
  (`WAKE_REASON_PLUGGED_IN` → `plug edge ... plugged=true` → `Display ... ON`)
- powered + full battery: panel stays awake correctly (`init pluggedIn=true` via the STATUS rule)
- server shutdown → panel killed, phone sleeps; server boot → agent re-wakes panel (unchanged upstream path)

## How to reproduce the bug

Plug the panel phone into a PC, kill the PC power (or `adb shell svc power shutdown` on the phone side
test rig) and watch: the panel never sleeps, `dumpsys power` keeps
`SCREEN_BRIGHT_WAKE_LOCK 'WindowManager' ws=WorkSource{<phonebox uid>}` after the power event.

---

### 中文说明（提交给上游时附 issue 用）

PhoneBox 的"断电待机"在 Android 8+ 上从未生效：`ACTION_POWER_CONNECTED/DISCONNECTED` 属于隐式广播限制
范围且不在豁免清单，运行时注册的接收器根本收不到。本补丁改用 sticky `ACTION_BATTERY_CHANGED` 的
`EXTRA_PLUGGED`（兼容满电时 HAL 报 `STATUS=CHARGING` 而 `PLUGGED=0` 的机型）做插拔沿检测；`clearFlags` 后补
`requestLayout()` 让窗口属性真正同步（否则 keep-awake wakelock 永不释放，连灭屏超时和 SLEEP 按键都被压制）；
唤醒后调用 `requestDismissKeyguard()` 越过无密码滑动锁屏。实测 OnePlus 3T / LineageOS 18.1：拔线约 16 秒
熄屏、回插自动亮屏进面板、满电正常常亮。proximity 立即灭屏方案在该 ROM 上 acquire 不灭屏，已放弃退回超时路径。
