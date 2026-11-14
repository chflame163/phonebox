# PR (lean A+B variant): PC powers off → the phone sleeps; PC powers on → the panel wakes by itself

**Branch/diff:** `fix/power-standby-ab` (single commit, tag `phonebox-pr-ab`) — **2 files, +38/−10 lines**.
Build-verified (`BUILD SUCCESSFUL`): `artifacts/PhoneBox-0.9.3-pr-ab.apk` (md5 `f43c4033…`), applicable via
`git apply artifacts/power-standby-ab.patch` onto current `main`.

## What the user gets

- **电脑主机关机 → 手机熄屏**: when the computer (agent host) powers off, USB power drops and the phone
  screen sleeps by itself (measured: 5 s standby grace + 10 s system screen-off timeout ≈ 16 s to blank;
  with stock timeouts ≈ 35 s).
- **电脑主机开机 → 手机跳过锁屏、自动拉起面板**: when the computer powers back on, USB power returns, the
  phone wakes itself and the panel comes forward *without* the "swipe to unlock" layer in the way — no
  touches, no adb, fully on-phone.

## What was broken

Power standby never fired on ANY Android 8+ phone: `ACTION_POWER_CONNECTED/DISCONNECTED` are on the
implicit-broadcast restriction list and are **not** exempted, so the runtime receiver registered in
`MainActivity` never receives them (feature silently degraded to "screen on forever"). On top of that,
`clearFlags(FLAG_KEEP_SCREEN_ON)` alone never reaches WindowManager on a static page — ViewRootImpl only
pushes window attributes during a layout-requesting traversal — so the keep-awake
`SCREEN_BRIGHT_WAKE_LOCK` stayed held forever, blocking even the screen-off timeout and SLEEP keyevents
(`dumpsys power` shows `ws=WorkSource{<phonebox uid>}` persisting after a power loss). Finally, waking on
power restore left an undismissed swipe keyguard on top: the panel was started but occluded.

## Changes

1. **Plug-edge detection via sticky `ACTION_BATTERY_CHANGED`** (which IS delivered to context-registered
   receivers on Android 8+): an `EXTRA_PLUGGED` flip **or** `EXTRA_STATUS ∈ {CHARGING, FULL}` drives
   `onPowerChanged()`. The STATUS rule matters for desk phones: charged to 100 %, Lineage's HAL on the
   OnePlus 3T drops `EXTRA_PLUGGED` while still reporting `CHARGING`, which would otherwise put a fully
   charged, perfectly powered panel to sleep. A small `lastPlugged` edge cache keeps it one event per edge.
2. **`window.decorView.requestLayout()` after add/clearFlags** in `refreshKeepAwake()` — forces the window
   attribute re-sync that actually releases (or re-acquires) the keep-awake wakelock.
3. **`KeyguardManager.requestDismissKeyguard()` in `wakeAndShowPanel()`** (adds the normal-level
   `DISABLE_KEYGUARD` permission) so the woken panel is not hidden behind a swipe keyguard.

Note: `PROXIMITY_SCREEN_OFF_WAKE_LOCK` was tried for instant blanking and dropped — on the 3T's
LineageOS 18.1 `acquire()` succeeds but does not blank the display, and holding it suppresses
user-initiated wakes; the timeout path is both reliable and good enough.

## Test evidence (OnePlus 3T, LineageOS 18.1 / Android 11, agent 0.9.3 over USB to an Ubuntu server)

- unplug → blank in ~16 s: `plug edge via battery-changed: plugged=false` → grace 5 s → flag released →
  `Display ... OFF` at timeout.
- replug → `WAKE_REASON_PLUGGED_IN` → `plug edge ... plugged=true` → `Display ... ON`, panel foreground,
  no keyguard layer, agent re-attaches and data resumes.
- powered + 100 % battery: `init pluggedIn=true` via the STATUS rule; panel correctly stays awake.
- Before the fix, the same unplug test: screen stayed awake indefinitely (2+ min, stale wakelock confirmed
  in `dumpsys power` / `dumpsys batterystats`).

## Reproduction

Power the panel phone from a PC, cut PC power (or emulate: `adb -s <serial> shell svc power stop usb` —
hmm, simplest: just unplug from a powered-off PC). Watch `dumpsys power | grep -A1 "Wake Locks"`: on 0.9.3
the `WindowManager` `SCREEN_BRIGHT` lock with `ws=WorkSource{<uid>}` never goes away after the unplug, and
no power broadcast lines appear (the receiver is registered but starved).

---

### 中文摘要（issue 关联用）

关机熄屏/开机亮屏这两个行为在 Android 8+ 上从未生效：CONNECTED/DISCONNECTED 属隐式广播限制范围，
运行时 receiver 收不到；即使收到，clearFlags 后无 layout traversal，keep-awake wakelock 也永不释放（实测
batterystats 已记录断电、屏幕却长亮 2 分钟+）；回电唤醒还会被无密码滑动锁屏挡在门外。本 PR 三处小改
（BATTERY_CHANGED 沿检测＋满电 STATUS 兼容、requestLayout 强制同步、requestDismissKeyguard），+38/−10 行，
3T/Lineage18.1 实测拔线 16 秒熄屏、回插越过锁屏自动上面板。
