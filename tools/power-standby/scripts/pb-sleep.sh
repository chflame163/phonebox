#!/bin/sh
# shutdown moment: kill panel (releases keep-awake), clear stay-awake, force sleep NOW via adb channel
adb -s 481fe5dc shell am force-stop net.oxog.phonebox.deskpanel 2>/dev/null
adb -s 481fe5dc shell settings put global stay_on_while_plugged_in 0 2>/dev/null
adb -s 481fe5dc shell input keyevent 223 2>/dev/null
exit 0
