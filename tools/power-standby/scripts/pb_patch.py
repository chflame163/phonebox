#!/usr/bin/env python3
# PhoneBox Android 断电灭屏修复 + 诊断日志补丁（0.9.3 源码精确锚点）
import sys
P = "/home/cc/phonebox/android/app/src/main/java/net/oxog/phonebox/deskpanel/MainActivity.kt"
s = open(P, encoding="utf-8").read()

reps = []

# 1) 成员：proximity 灭屏锁
reps.append((
'''    private var powerReceiver: BroadcastReceiver? = null
''',
'''    private var powerReceiver: BroadcastReceiver? = null
    private var proximitySleepLock: PowerManager.WakeLock? = null
'''))

# 2) 广播接收日志
reps.append((
'''                    else -> return
                }
                mainHandler.post { onPowerChanged(connected) }
''',
'''                    else -> return
                }
                android.util.Log.i("PhoneBox", "power broadcast: " + intent?.action)
                mainHandler.post { onPowerChanged(connected) }
'''))

# 3) refreshKeepAwake：强制窗口属性重新同步
reps.append((
'''        if (!standbyEnabled || pluggedIn) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
''',
'''        if (!standbyEnabled || pluggedIn) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        // Force ViewRootImpl to push the new window attributes on the next traversal: without a layout request a
        // static page never relayouts, so WindowManager keeps the stale keep-awake wakelock forever (Android 11+).
        window.decorView.requestLayout()
    }
'''))

# 4) onPowerChanged：日志 + 主动 proximity 灭屏 / 恢复时释放
reps.append((
'''    private fun onPowerChanged(connected: Boolean) {
        pluggedIn = connected
        mainHandler.removeCallbacksAndMessages(null)
        if (connected) {
            // Power is back: keep the screen on again and bring the panel forward, even without the agent's adb wake.
            refreshKeepAwake()
            wakeAndShowPanel()
        } else if (standbyEnabled) {
            // De-bounce: a rebooting server drops USB for a moment; a transient loss should not blank the panel.
            mainHandler.postDelayed({
                if (!pluggedIn && standbyEnabled)
                    refreshKeepAwake() // releases the hold; the screen now sleeps at the system timeout
            }, standbyDelayMs)
        } else {
            refreshKeepAwake()
        }
    }
''',
'''    private fun onPowerChanged(connected: Boolean) {
        android.util.Log.i("PhoneBox", "power changed: connected=" + connected + " standby=" + standbyEnabled + " delayMs=" + standbyDelayMs)
        pluggedIn = connected
        mainHandler.removeCallbacksAndMessages(null)
        if (connected) {
            // Power is back: keep the screen on again and bring the panel forward, even without the agent's adb wake.
            releaseProximitySleep()
            refreshKeepAwake()
            wakeAndShowPanel()
        } else if (standbyEnabled) {
            // De-bounce: a rebooting server drops USB for a moment; a transient loss should not blank the panel.
            mainHandler.postDelayed({
                if (!pluggedIn && standbyEnabled) {
                    refreshKeepAwake() // releases the hold; the screen now sleeps at the system timeout
                    sleepNowViaProximity() // and sleep right away: a plain app can force this with the proximity lock
                }
            }, standbyDelayMs)
        } else {
            refreshKeepAwake()
        }
    }

    /** The fake "ear over the receiver" lock: a no-root way to blank the display; released the moment power is back. */
    @Suppress("DEPRECATION")
    private fun sleepNowViaProximity() {
        val pm = getSystemService(PowerManager::class.java) ?: return
        try {
            val lock = proximitySleepLock
                ?: pm.newWakeLock(PowerManager.PROXIMITY_SCREEN_OFF_WAKE_LOCK, "PhoneBox:proximitySleep").also { proximitySleepLock = it }
            if (!lock.isHeld && pm.isInteractive) lock.acquire()
            android.util.Log.i("PhoneBox", "proximity sleep acquired, held=" + lock.isHeld)
        } catch (e: Exception) {
            android.util.Log.w("PhoneBox", "proximity sleep failed: " + e)
        }
    }

    private fun releaseProximitySleep() {
        proximitySleepLock?.let { if (it.isHeld) it.release() }
    }
'''))

# 5) 初始化日志（证明 receiver 注册 + 初始插拔状态）
reps.append((
'''        pluggedIn = (registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
        refreshKeepAwake()
''',
'''        pluggedIn = (registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
        android.util.Log.i("PhoneBox", "standby receiver registered, init pluggedIn=" + pluggedIn)
        refreshKeepAwake()
'''))

# 6) onDestroy 释放锁
reps.append((
'''    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
''',
'''    override fun onDestroy() {
        releaseProximitySleep()
        mainHandler.removeCallbacksAndMessages(null)
'''))

fail = 0
for i, (o, n) in enumerate(reps, 1):
    c = s.count(o)
    if c != 1:
        print(f"ANCHOR{i}_COUNT={c} (need exactly 1)")
        fail = 1
    else:
        s = s.replace(o, n, 1)
if fail:
    print("PATCH_ABORTED")
    sys.exit(2)
open(P, "w", encoding="utf-8").write(s)
print("PATCH_OK")
