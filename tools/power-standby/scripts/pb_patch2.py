#!/usr/bin/env python3
# v2 修复：ACTION_POWER_CONNECTED/DISCONNECTED 受 Android 8+ 隐式广播限制收不到，
# 改用豁免列表内的 ACTION_BATTERY_CHANGED sticky 广播侦测 EXTRA_PLUGGED 状态变化。
import sys
P = "/home/cc/phonebox/android/app/src/main/java/net/oxog/phonebox/deskpanel/MainActivity.kt"
s = open(P, encoding="utf-8").read()

reps = []

reps.append((
'''        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_POWER_CONNECTED)
            addAction(Intent.ACTION_POWER_DISCONNECTED)
        }
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                val connected = when (intent?.action) {
                    Intent.ACTION_POWER_CONNECTED -> true
                    Intent.ACTION_POWER_DISCONNECTED -> false
                    else -> return
                }
                android.util.Log.i("PhoneBox", "power broadcast: " + intent?.action)
                mainHandler.post { onPowerChanged(connected) }
            }
        }
''',
'''        // ACTION_POWER_CONNECTED/DISCONNECTED are implicit-broadcast-restricted since Android 8 and never reach a
        // runtime receiver on ANY modern phone. Watch the exempt sticky ACTION_BATTERY_CHANGED instead and treat an
        // EXTRA_PLUGGED flip as the connect/disconnect edge.
        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_BATTERY_CHANGED)
        }
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context?, intent: Intent?) {
                val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
                if (plugged == pluggedIn) return
                android.util.Log.i("PhoneBox", "plug edge via battery-changed: plugged=" + plugged)
                mainHandler.post { onPowerChanged(plugged) }
            }
        }
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
    print("PATCH2_ABORTED")
    sys.exit(2)
open(P, "w", encoding="utf-8").write(s)
print("PATCH2_OK")
