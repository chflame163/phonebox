#!/bin/sh
# 关机瞬间：屏幕要立刻黑、而且此后没有任何东西消耗这台手机的电。
# 注意不再 force-stop 面板 app —— 它留着当守门人：主机重新枚举(开机)那一秒事件就把屏幕点亮，
# 而它自己会在熄屏 5 分钟后进入深睡(停止轮询与 stream)，doze 才真的能生效。
adb -s 481fe5dc shell settings put global stay_on_while_plugged_in 0 2>/dev/null
adb -s 481fe5dc shell am kill-all 2>/dev/null
for p in org.lineageos.jelly org.lineageos.snap org.lineageos.eleven org.lineageos.etar \
         org.lineageos.recorder org.lineageos.updater org.lineageos.setupwizard \
         org.lineageos.audiofx org.lineageos.profiles org.lineageos.pocketmode; do
  adb -s 481fe5dc shell am force-stop $p 2>/dev/null
done
adb -s 481fe5dc shell input keyevent 223 2>/dev/null
exit 0
