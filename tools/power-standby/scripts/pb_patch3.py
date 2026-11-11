#!/usr/bin/env python3
# v3 修正：100% 满充涓流时 Lineage HAL 报 EXTRA_PLUGGED=0 但 EXTRA_STATUS=CHARGING/FULL——
# 把充电/充满状态也视为“已插电”，否则面板会在服务器正常供电+满电时误判断电而灭屏。
import sys
P = "/home/cc/phonebox/android/app/src/main/java/net/oxog/phonebox/deskpanel/MainActivity.kt"
s = open(P, encoding="utf-8").read()

reps = []
reps.append((
'''            override fun onReceive(context: Context?, intent: Intent?) {
                val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
                if (plugged == pluggedIn) return
''',
'''            override fun onReceive(context: Context?, intent: Intent?) {
                // A charged-to-100% phone drops EXTRA_PLUGGED while EXTRA_STATUS keeps reporting CHARGING/FULL:
                // treat those states as "cable in" too, otherwise a full panel phone sleeps during normal operation.
                val status = intent?.getIntExtra(BatteryManager.EXTRA_STATUS, BatteryManager.BATTERY_STATUS_UNKNOWN)
                    ?: BatteryManager.BATTERY_STATUS_UNKNOWN
                val plugged = (intent?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0 ||
                    status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
                if (plugged == pluggedIn) return
'''))
# init 的 sticky 读取同样加 status 兜底
reps.append((
'''        pluggedIn = (registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            ?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0
''',
'''        run {
            val sticky = registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            val st = sticky?.getIntExtra(BatteryManager.EXTRA_STATUS, BatteryManager.BATTERY_STATUS_UNKNOWN)
                ?: BatteryManager.BATTERY_STATUS_UNKNOWN
            pluggedIn = (sticky?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0) != 0 ||
                st == BatteryManager.BATTERY_STATUS_CHARGING || st == BatteryManager.BATTERY_STATUS_FULL
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
    print("PATCH3_ABORTED")
    sys.exit(2)
open(P, "w", encoding="utf-8").write(s)
print("PATCH3_OK")
