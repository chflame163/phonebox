#!/bin/bash
# pb_chargeguard.sh 的状态机 dry-run 测试（不碰手机：PB_ONESHOT=1 + 注入电量/开关/时间/状态文件）
S=${S:-/tmp/pbg.sh}
T=1794500000                     # 假“现在”
W=604800; Q=7776000               # 7d / 90d
pass=0; fail=0
run() { # run <说明> <期望子串> <state_setup> <extra env> <args...>
  local desc=$1 exp=$2 setup=$3 env=$4; shift 4
  local st out
  st=$(mktemp)
  if [ -n "$setup" ]; then eval "$setup" > "$st"; else rm -f "$st"; fi
  out=$(env PB_ONESHOT=1 PB_STATE="$st" PB_LOG=/tmp/pbg_test.log PB_PUSH=0 PB_NOW=$T \
        S_FILE="$st" $env "$S" "$@" 2>&1)
  if echo "$out" | grep -qF "$exp"; then pass=$((pass+1)); printf '  ok   %-46s %s\n' "$desc" "$out"
  else fail=$((fail+1)); printf '  FAIL %-46s want[%s] got[%s]\n' "$desc" "$exp" "$out"; fi
  rm -f "$st"
}
FRESH="printf 'phase=daily\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'"

echo "=== A. 日常浅循环 65~80 ==="
run "82% 应停充"            "phase=daily[日常] charging_enabled=0" "$FRESH" "PB_LEVEL=82 PB_CHG=1" auto
run "64% 应复充"            "phase=daily[日常] charging_enabled=1" "$FRESH" "PB_LEVEL=64 PB_CHG=0" auto
run "72% 区间中保持原状(1)" "charging_enabled=1" "$FRESH" "PB_LEVEL=72 PB_CHG=1" auto
run "72% 区间中保持原状(0)" "charging_enabled=0" "$FRESH" "PB_LEVEL=72 PB_CHG=0" auto
run "20% 触发安全下限复充"  "charging_enabled=1" "$FRESH" "PB_LEVEL=20 PB_CHG=0" auto
run "5% 无条件复充"         "charging_enabled=1" "$FRESH" "PB_LEVEL=5 PB_CHG=0" auto

echo "=== B. 周校验 40 -> 80 ==="
run "手动进周校验"          "phase=weekly_dis[周校验·放电到 40%] charging_enabled=0" "$FRESH" "PB_LEVEL=88 PB_CHG=1" calib weekly
run "放电中途(60)仍停充"    "phase=weekly_dis" "printf 'phase=weekly_dis\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=60 PB_CHG=0" auto
run "到 39 转入回充"        "phase=weekly_ch[周校验·回充到 80%] charging_enabled=1" "printf 'phase=weekly_dis\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=39 PB_CHG=0" auto
run "回充中途(50)继续充"    "phase=weekly_ch" "printf 'phase=weekly_ch\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=50 PB_CHG=1" auto
run "到 81 回日常"          "phase=daily" "printf 'phase=weekly_ch\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=81 PB_CHG=1" auto

echo "=== C. 季度校验 20 -> 100 + 顶充 30 分钟 ==="
run "手动进季校验"          "phase=qtr_dis[季校验·放电到 20%]" "$FRESH" "PB_LEVEL=88 PB_CHG=1" calib qtr
run "到 19 转入回充"        "phase=qtr_ch[季校验·回充到 100%]" "printf 'phase=qtr_dis\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=19 PB_CHG=0" auto
run "99% 还在回充"          "phase=qtr_ch" "printf 'phase=qtr_ch\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=99 PB_CHG=1" auto
run "100% 转顶充"           "phase=qtr_top[季校验·满充后顶充 30 分钟]" "printf 'phase=qtr_ch\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=100 PB_CHG=1" auto
run "顶充 29 分钟继续等"    "phase=qtr_top" "printf 'phase=qtr_top\nphase_since=$T\nt100=$T\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=100 PB_CHG=1 PB_NOW=$((T+1740))" auto
run "顶充 31 分钟结束回日常" "phase=daily" "printf 'phase=qtr_top\nphase_since=$T\nt100=$T\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=100 PB_CHG=1 PB_NOW=$((T+1860))" auto

echo "=== D. 到期自动起校验（从上次完成时间算） ==="
run "7 天后自动起周校验"    "phase=weekly_dis" "printf 'phase=daily\nphase_since=$T\nt100=0\nlast_weekly=$((T-W))\nlast_quarter=$T\n'" "PB_LEVEL=70 PB_CHG=0" auto
run "90 天后自动起季校验"   "phase=qtr_dis"    "printf 'phase=daily\nphase_since=$T\nt100=0\nlast_weekly=$((T-Q))\nlast_quarter=$((T-Q))\n'" "PB_LEVEL=70 PB_CHG=0" auto
run "季校验优先于周校验"    "phase=qtr_dis"    "printf 'phase=daily\nphase_since=$T\nt100=0\nlast_weekly=$((T-W))\nlast_quarter=$((T-Q))\n'" "PB_LEVEL=70 PB_CHG=0" auto

echo "=== E. 保护与超时 ==="
run "放电阶段超时退回日常"  "phase=daily" "printf 'phase=weekly_dis\nphase_since=$((T-40000))\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=50 PB_CHG=0" auto
run "回充阶段超时退回日常"  "phase=daily" "printf 'phase=qtr_ch\nphase_since=$((T-70000))\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=60 PB_CHG=1" auto
run "校验中电量 5% 立即中止" "phase=daily" "printf 'phase=weekly_dis\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=5 PB_CHG=0" auto
run "reset 回日常"          "phase=daily" "printf 'phase=weekly_ch\nphase_since=$T\nt100=0\nlast_weekly=$T\nlast_quarter=$T\n'" "PB_LEVEL=60 PB_CHG=1" reset

echo
echo "=== 汇总: pass=$pass fail=$fail ==="
[ "$fail" = 0 ] || echo "有失败项，看上面的 FAIL 行"
