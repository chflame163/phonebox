#!/usr/bin/env python3
# v4：manifest 静态接收器（进程保活兜底） + requestDismissKeyguard（划开滑动锁屏） + 去掉 3T 上不牢靠的 proximity
import sys
BASE = "/home/cc/phonebox/android/app/src/main/"
M = BASE + "java/net/oxog/phonebox/deskpanel/MainActivity.kt"
A = BASE + "AndroidManifest.xml"

# ---------- AndroidManifest.xml ----------
s = open(A, encoding="utf-8").read()
o = '''    <uses-permission android:name="android.permission.WAKE_LOCK" />'''
n = '''    <uses-permission android:name="android.permission.WAKE_LOCK" />
    <uses-permission android:name="android.permission.DISABLE_KEYGUARD" />'''
assert s.count(o) == 1, "MANIFEST_ANCHOR1"
s = s.replace(o, n, 1)

o = '''    </application>
</manifest>'''
n = '''        <!-- Belt-and-safety receiver: BATTERY_CHANGED is sticky and is ALSO delivered to the context-registered
             receiver in MainActivity (the primary path); this manifest entry only adds a documented edge hook and
             process revival on older OS lines. Primary detection lives in code. -->
        <receiver
            android:name=".PowerReceiver"
            android:enabled="true"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BATTERY_CHANGED" />
            </intent-filter>
        </receiver>
    </application>
</manifest>'''
assert s.count(o) == 1, "MANIFEST_ANCHOR2"
s = s.replace(o, n, 1)
open(A, "w", encoding="utf-8").write(s)

# ---------- MainActivity.kt ----------
m = open(M, encoding="utf-8").read()

# imports
o = "import android.content.pm.ActivityInfo\n"
n = ("import android.app.KeyguardManager\n"
     "import android.content.pm.ActivityInfo\n"
     "import android.os.PowerManager\n")
assert m.count(o) == 1, "KT_ANCHOR_import"
m = m.replace(o, n, 1)

# 成员：广播状态缓存 + 删 proximity 锁
o = "    private var proximitySleepLock: PowerManager.WakeLock? = null\n"
n = ""
assert m.count(o) == 1, "KT_ANCHOR_member"
m = m.replace(o, n, 1)

o = "    private var powerReceiver: BroadcastReceiver? = null\n"
n = ("    private var powerReceiver: BroadcastReceiver? = null\n"
     "    @Volatile private var lastPlugged = true\n")
assert m.count(o) == 1, "KT_ANCHOR_member2"
m = m.replace(o, n, 1)

# onReceive 边缘检测改用静态缓存
o = '''                val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
                if (plugged == pluggedIn) return
'''
n = '''                val status = intent?.getIntExtra(BatteryManager.EXTRA_STATUS, BatteryManager.BATTERY_STATUS_UNKNOWN)
                    ?: BatteryManager.BATTERY_STATUS_UNKNOWN
                val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0 ||
                    status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
                if (plugged == lastPlugged) return
                lastPlugged = plugged
'''
assert m.count(o) == 1, "KT_ANCHOR_receive"
m = m.replace(o, n, 1)

# 去掉灭屏后的 proximity 调用
o = '''                if (!pluggedIn && standbyEnabled) {
                    refreshKeepAwake() // releases the hold; the screen now sleeps at the system timeout
                    sleepNowViaProximity() // and sleep right away: a plain app can force this with the proximity lock
                }
'''
n = '''                if (!pluggedIn && standbyEnabled)
                    refreshKeepAwake() // releases the hold; the screen now sleeps at the system timeout
'''
assert m.count(o) == 1, "KT_ANCHOR_grace"
m = m.replace(o, n, 1)

# 删除 proximity 两个方法（v1/v2 引入）
o_start = "    /** The fake \"ear over the receiver\" lock:"
idx = m.find(o_start)
assert idx != -1, "KT_ANCHOR_prox_start"
end_marker = "    private fun releaseProximitySleep() {\n        proximitySleepLock?.let { if (it.isHeld) it.release() }\n    }\n\n"
idx2 = m.find(end_marker, idx)
assert idx2 != -1, "KT_ANCHOR_prox_end"
m = m[:idx] + m[idx2 + len(end_marker):]

# connected 分支：去掉 release 调用，加 keyguard 解锁
o = '''        if (connected) {
            // Power is back: keep the screen on again and bring the panel forward, even without the agent's adb wake.
            releaseProximitySleep()
            refreshKeepAwake()
            wakeAndShowPanel()
'''
n = '''        if (connected) {
            // Power is back: keep the screen on again and bring the panel forward, even without the agent's adb wake.
            refreshKeepAwake()
            wakeAndShowPanel()
'''
assert m.count(o) == 1, "KT_ANCHOR_conn"
m = m.replace(o, n, 1)

# wakeAndShowPanel：起 Activity 后划掉滑动 keyguard
o = '''        startActivity(Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP))
    }
'''
n = '''        startActivity(Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP))
        // Swipe-keyguard phones (Lineage default, isSecure=false) would otherwise keep the started panel behind the
        // lock screen: an unsatisfying swipe layer no one is there to swipe. requestDismissKeyguard clears it.
        try {
            (getSystemService(KEYGUARD_SERVICE) as? KeyguardManager)?.requestDismissKeyguard(this, null)
        } catch (e: Exception) {
            android.util.Log.w("PhoneBox", "keyguard dismiss failed: " + e)
        }
    }
'''
assert m.count(o) == 1, "KT_ANCHOR_wake"
m = m.replace(o, n, 1)

# onDestroy 去 release
o = '''    override fun onDestroy() {
        releaseProximitySleep()
        mainHandler.removeCallbacksAndMessages(null)
'''
n = '''    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
'''
assert m.count(o) == 1, "KT_ANCHOR_destroy"
m = m.replace(o, n, 1)

# 文件末尾追加 PowerReceiver 类
o = '''        override fun run() {
            try {
                intent?.component = ComponentName(context, MainActivity::class.java)
            } catch (e: Exception) {
            }
            context.startActivity(intent)
        }
    }
}'''
n = '''        override fun run() {
            try {
                intent?.component = ComponentName(context, MainActivity::class.java)
            } catch (e: Exception) {
            }
            context.startActivity(intent)
        }
    }
}

/**
 * Secondary power-edge hook (see AndroidManifest). On Android 8+ BATTERY_CHANGED sticky broadcasts are only
 * delivered to context-registered receivers — MainActivity.registerPowerReceiver is the primary path — while this
 * manifest entry documents the feature and revives the component on older lines. Shared edge cache below.
 */
class PowerReceiver : BroadcastReceiver() {
    companion object {
        @Volatile var lastPlugged = true

        fun edge(intent: Intent?, tag: String): Boolean? {
            val status = intent?.getIntExtra(BatteryManager.EXTRA_STATUS, BatteryManager.BATTERY_STATUS_UNKNOWN)
                ?: BatteryManager.BATTERY_STATUS_UNKNOWN
            val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0 ||
                status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
            if (plugged == lastPlugged) return null
            lastPlugged = plugged
            android.util.Log.i("PhoneBox", "$tag plug edge (static receiver): plugged=" + plugged)
            return plugged
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        edge(intent, "static")
    }
}'''
assert m.count(o) == 1, "KT_ANCHOR_tail"
m = m.replace(o, n, 1)

open(M, "w", encoding="utf-8").write(m)
print("PATCH4_OK")
