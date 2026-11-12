#!/usr/bin/env python3
# v4b：补完 v4 对 MainActivity.kt 的部分（manifest 已就位）。锚点=现场 v3 文本。
import sys
M = "/home/cc/phonebox/android/app/src/main/java/net/oxog/phonebox/deskpanel/MainActivity.kt"
m = open(M, encoding="utf-8").read()
reps = []

reps.append((
"import android.content.pm.ActivityInfo\n",
"import android.app.KeyguardManager\nimport android.content.pm.ActivityInfo\n"))

reps.append((
"    private var proximitySleepLock: PowerManager.WakeLock? = null\n",
""))

reps.append((
"    private var powerReceiver: BroadcastReceiver? = null\n",
"    private var powerReceiver: BroadcastReceiver? = null\n    @Volatile private var lastPlugged = true\n"))

reps.append((
'''                val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0 ||
                    status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
                if (plugged == pluggedIn) return
''',
'''                val plugged = PowerReceiver.edge(intent, "runtime") ?: return
'''))

reps.append((
'''                if (!pluggedIn && standbyEnabled) {
                    refreshKeepAwake() // releases the hold; the screen now sleeps at the system timeout
                    sleepNowViaProximity() // and sleep right away: a plain app can force this with the proximity lock
                }
''',
'''                if (!pluggedIn && standbyEnabled)
                    refreshKeepAwake() // releases the hold; the screen now sleeps at the system timeout
'''))

reps.append((
'''        if (connected) {
            // Power is back: keep the screen on again and bring the panel forward, even without the agent's adb wake.
            releaseProximitySleep()
            refreshKeepAwake()
            wakeAndShowPanel()
''',
'''        if (connected) {
            // Power is back: keep the screen on again and bring the panel forward, even without the agent's adb wake.
            refreshKeepAwake()
            wakeAndShowPanel()
'''))

reps.append((
'''        startActivity(Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP))
    }
''',
'''        startActivity(Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP))
        // A swipe keyguard (Lineage default, isSecure=false) would otherwise keep the woken panel behind a lock
        // screen nobody is there to swipe; requestDismissKeyguard clears it (DISABLE_KEYGUARD is a normal perm).
        try {
            (getSystemService(KEYGUARD_SERVICE) as? KeyguardManager)?.requestDismissKeyguard(this, null)
        } catch (e: Exception) {
            android.util.Log.w("PhoneBox", "keyguard dismiss failed: " + e)
        }
    }
'''))

reps.append((
'''    override fun onDestroy() {
        releaseProximitySleep()
        mainHandler.removeCallbacksAndMessages(null)
''',
'''    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
'''))

reps.append((
'''            pluggedIn = (sticky?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0 ||
                st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL
        }
''',
'''            pluggedIn = (sticky?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0 ||
                st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL
        }
        PowerReceiver.lastPlugged = pluggedIn
'''))

fail = 0
for i, (o, n) in enumerate(reps, 1):
    c = m.count(o)
    if c != 1:
        print(f"ANCHOR{i}_COUNT={c}")
        fail = 1
    else:
        m = m.replace(o, n, 1)
if fail:
    print("PATCH4B_ABORTED")
    sys.exit(2)

# proximity 两方法整段删除（start 注释行 → end 方法块）
start = "    /** The fake \"ear over the receiver\" lock:"
i0 = m.find(start)
assert i0 != -1, "PROX_START"
endmark = "    private fun releaseProximitySleep() {\n        proximitySleepLock?.let { if (it.isHeld) it.release() }\n    }\n\n"
i1 = m.find(endmark, i0)
assert i1 != -1, "PROX_END"
m = m[:i0] + m[i1 + len(endmark):]

# 文件尾追加 PowerReceiver 顶层类
cls = '''
/**
 * Shared plug-edge detection for both receiver paths (manifest entry + the primary context-registered one; see
 * AndroidManifest). On Android 8+ only the context-registered receiver actually receives this sticky broadcast,
 * but the manifest entry documents the feature and revives the component on older OS lines.
 */
class PowerReceiver : BroadcastReceiver() {
    companion object {
        @Volatile var lastPlugged = true

        /** True/false on a plug edge, null when the state did not change. */
        fun edge(intent: Intent?, tag: String): Boolean? {
            val status = intent?.getIntExtra(BatteryManager.EXTRA_STATUS, BatteryManager.BATTERY_STATUS_UNKNOWN)
                ?: BatteryManager.BATTERY_STATUS_UNKNOWN
            val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0 ||
                status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
            if (plugged == lastPlugged) return null
            lastPlugged = plugged
            android.util.Log.i("PhoneBox", "plug edge ($tag): plugged=" + plugged)
            return plugged
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        edge(intent, "static")
    }
}
'''
m = m.rstrip() + "\n" + cls
open(M, "w", encoding="utf-8").write(m)
print("PATCH4B_OK")
