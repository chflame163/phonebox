#!/bin/sh
# 服务器开机后：唤醒面板手机、去掉锁屏层、拉起 PhoneBox（幂等，agent 也会自己开面板）
DEV=481fe5dc
PKGB=net.oxog.phonebox.deskpanel
adb() { /usr/bin/adb -s $DEV "$@" >/dev/null 2>&1; }
# 等手机出现在 adb 里（最长 ~2 分钟）
i=0
while [ $i -lt 40 ]; do
  /usr/bin/adb devices 2>/dev/null | grep -q "^$DEV\s*device" && break
  i=$((i+1)); sleep 3
done
[ $i -ge 40 ] && exit 0
adb shell input keyevent KEYCODE_WAKEUP
i=0
while [ $i -lt 6 ]; do adb shell wm dismiss-keyguard; sleep 2; i=$((i+1)); done
adb shell am start -n $PKGB/.MainActivity
exit 0
