#!/bin/bash
# 手机电池维护策略（PMIC 停充，不动 USB 口；root 写 charging_enabled：0=停充 1=允许充）
#
#   日常    ：>= STOP(80) 停充，<= RESTART(65) 复充，中间保持（浅循环）
#   每周    ：一次 40 -> 80 的深一点的放电/回充（W_DAYS=7）
#   每季度  ：一次 20 -> 100，且到 100% 后再顶充 Q_TOPMIN(30) 分钟，然后断（Q_DAYS=90）
#   任何阶段：电量 <= CRIT(8) 一律允许充（别把手机耗死）；阶段超过超时窗自动退回日常并告警
#
# 用法:  pb_chargeguard.sh [auto|status|on|off|calib weekly|calib qtr|reset]
#   auto    默认，按策略写开关（timer 每 60s 调一次）
#   status  只读：电量/开关/当前阶段/下次校验倒计时
#   on|off  手动写一次开关（不动阶段状态）
#   calib   立刻进入 weekly / qtr 校验阶段
#   reset   退回日常阶段（保留 last_weekly / last_quarter 时间戳）
#
# dry-run（不碰手机也能验状态机）：PB_LEVEL=<n> 假装电量、PB_NOW=<epoch> 假装时间、
#   PB_STATE=<file> 用临时状态文件、PB_ONESHOT=1 不碰手机 adb。
set -u

SER=${PB_SERIAL:-481fe5dc}
NODE=${PB_NODE:-/sys/class/power_supply/battery/charging_enabled}
CAPN=${PB_CAPACITY_NODE:-/sys/class/power_supply/battery/capacity}
STATE=${PB_STATE:-$HOME/.local/state/pb_chargeguard.state}
LOGF=${PB_LOG:-/mnt/nvme0n1p1/temp/pb_chargeguard.log}
PUSHURL=${PB_PUSH_URL:-http://127.0.0.1:8765/api/push/charge_state}

STOP=${PB_STOP_LEVEL:-80}
RESTART=${PB_START_LEVEL:-65}
FLOOR=${PB_FLOOR_LEVEL:-25}
CRIT=${PB_CRIT_LEVEL:-8}
W_START=${PB_W_START:-40};  W_STOP=${PB_W_STOP:-80};  W_DAYS=${PB_W_DAYS:-7}
Q_START=${PB_Q_START:-20};  Q_STOP=${PB_Q_STOP:-100}; Q_DAYS=${PB_Q_DAYS:-90}
Q_TOPMIN=${PB_Q_TOPOFF_MIN:-30}
DIS_TMO=${PB_DIS_TMO_S:-36000}      # 放电阶段上限 10h（正常 40% 跨度约 2h）
CHG_TMO=${PB_CHG_TMO_S:-64800}      # 回充阶段上限 18h（500mA 预算下可能很慢）
BEAT=${PB_BEAT:-30}                 # 心跳：每 N 次 auto 记一行（60s 一次 => 30 分钟）
MODE=${1:-auto}
CAL=${2:-weekly}

log() { local l; l="$(date -Iseconds) $*"; echo "$l" >> "$LOGF" 2>/dev/null || echo "$l" >&2; }
a() { timeout 15 adb -s "$SER" shell "$1" 2>/dev/null | tr -d '\r'; }

# ---------- 状态文件 ----------
mkdir -p "$(dirname "$STATE")" 2>/dev/null || true
[ -f "$STATE" ] || { now0=$(date +%s); printf 'phase=daily\nphase_since=%s\nt100=0\nlast_weekly=%s\nlast_quarter=%s\n' "$now0" "$now0" "$now0" > "$STATE" 2>/dev/null || true; }
phase=$(sed -n 's/^phase=//p' "$STATE" 2>/dev/null); phase=${phase:-daily}
since=$(sed -n 's/^phase_since=//p' "$STATE" 2>/dev/null); since=${since:-0}
t100=$(sed -n 's/^t100=//p' "$STATE" 2>/dev/null); t100=${t100:-0}
lw=$(sed -n 's/^last_weekly=//p' "$STATE" 2>/dev/null); lw=${lw:-0}
lq=$(sed -n 's/^last_quarter=//p' "$STATE" 2>/dev/null); lq=${lq:-0}
save_state() { printf 'phase=%s\nphase_since=%s\nt100=%s\nlast_weekly=%s\nlast_quarter=%s\n' \
  "$phase" "$since" "$t100" "$lw" "$lq" > "$STATE" 2>/dev/null || log "状态文件写不了: $STATE"; }

NOW=${PB_NOW:-$(date +%s)}
PHASE_LABEL() { case "$1" in
  daily) echo "日常";; weekly_dis) echo "周校验·放电到 ${W_START}%";; weekly_ch) echo "周校验·回充到 ${W_STOP}%";;
  qtr_dis) echo "季校验·放电到 ${Q_START}%";; qtr_ch) echo "季校验·回充到 ${Q_STOP}%";;
  qtr_top) echo "季校验·满充后顶充 ${Q_TOPMIN} 分钟";; *) echo "$1";; esac; }

# 日常区间（校验阶段结束/超时后立刻按它取值，免得多空转一轮）
apply_daily() {
  want=$CHG
  [ "$LVL" -ge "$STOP" ]    && want=0
  [ "$LVL" -le "$RESTART" ] && want=1
  [ "$LVL" -le "$FLOOR" ]   && want=1
}

# ---------- 手机在不在 / 读电量与开关 ----------
if [ "${PB_ONESHOT:-0}" = 1 ]; then      # dry-run：电量/开关都能注入，不碰手机
  LVL=${PB_LEVEL:-}; CHG=${PB_CHG:-}; USBON=${PB_USBON:-1}; ST_LABEL=${PB_STATUS:-dry}
else
  if ! timeout 8 adb devices 2>/dev/null | grep -qE "^[[:space:]]*$SER[[:space:]]+device"; then
    [ "$MODE" = auto ] && log "no adb device $SER (服务器关机或线已拔) -> 不做处理"
    echo "offline"; exit 0
  fi
  if [ "$(a 'id -u')" != "0" ]; then            # adbd 需要 root（手机重启后会退回 shell）
    timeout 15 adb -s "$SER" root >/dev/null 2>&1; sleep 3
    timeout 15 adb -s "$SER" wait-for-device >/dev/null 2>&1
    [ "$(a 'id -u')" != "0" ] && { log "adb root 不可用：手机上开 开发者选项>Root 身份调试"; echo "noroot"; exit 1; }
  fi
  LVL=$(a "cat $CAPN" | tr -dc '0-9')
  CHG=$(a "cat $NODE" | tr -dc '0-9')
  USBON=$(a 'cat /sys/class/power_supply/usb/online' | tr -dc '0-9')
  ST_LABEL=$(a "cat /sys/class/power_supply/battery/status")
fi
[ -n "${PB_LEVEL:-}" ] && LVL=$PB_LEVEL
[ -z "$LVL" ] && { log "读不到电量，跳过"; echo "level=? phase=$phase"; exit 0; }

want=$CHG
pl=$(PHASE_LABEL "$phase")

# ---------- 手动模式 ----------
if [ "$MODE" = on ] || [ "$MODE" = off ]; then
  [ "$MODE" = on ] && want=1 || want=0
elif [ "$MODE" = status ]; then
  dw=$([ "$lw" = 0 ] && echo 0 || echo $(( (NOW - lw) / 86400 )))
  dq=$([ "$lq" = 0 ] && echo 0 || echo $(( (NOW - lq) / 86400 )))
  echo "level=$LVL charging_enabled=${CHG:-?} usb_online=${USBON:-?} status=${ST_LABEL:-?}"
  echo "phase=$phase ($pl)  距上次周校验 ${dw}/${W_DAYS}d，距上次季校验 ${dq}/${Q_DAYS}d"
  echo "阈值: 日常 $RESTART~$STOP (下限 $FLOOR 强制复充, $CRIT 无条件复充) | 周 $W_START~$W_STOP | 季 $Q_START~$Q_STOP+顶充${Q_TOPMIN}min"
  exit 0
elif [ "$MODE" = calib ]; then
  [ "$CAL" = qtr ] && phase=qtr_dis || phase=weekly_dis
  since=$NOW; t100=0
  log "手动进入校验阶段: $pl (level=$LVL)"
elif [ "$MODE" = reset ]; then
  phase=daily; since=$NOW; t100=0; log "手动 reset -> 日常"
fi

# ---------- 策略判定（auto / calib 后的持续阶段） ----------
if [ "$MODE" != status ] && [ "$MODE" != on ] && [ "$MODE" != off ]; then
  if [ "$LVL" -le "$CRIT" ]; then           # 快没电了：先保命，校验作废
    [ "$phase" != daily ] && { log "电量 $LVL <= $CRIT，中止校验 $pl -> 日常"; phase=daily; since=$NOW; }
    want=1
  else
    case "$phase" in
      weekly_dis) want=0
        [ "$LVL" -le "$W_START" ] && { phase=weekly_ch; since=$NOW; want=1
          log "周校验放电完成($LVL%) -> 当场开始回充"; } ;;
      weekly_ch)  want=1
        [ "$LVL" -ge "$W_STOP" ]  && { phase=daily; since=$NOW; lw=$NOW; apply_daily
          log "周校验完成(充到 $LVL%) -> 回日常"; } ;;
      qtr_dis)    want=0
        [ "$LVL" -le "$Q_START" ] && { phase=qtr_ch; since=$NOW; want=1
          log "季校验放电完成($LVL%) -> 当场开始回充到 $Q_STOP%"; } ;;
      qtr_ch)     want=1
        [ "$LVL" -ge "$Q_STOP" ]  && { phase=qtr_top; t100=$NOW; want=1
          log "季校验到 100% -> 顶充 ${Q_TOPMIN} 分钟"; } ;;
      qtr_top)    want=1
        [ "$t100" = 0 ] && t100=$NOW
        [ $(( NOW - t100 )) -ge $(( Q_TOPMIN * 60 )) ] && { phase=daily; since=$NOW; lq=$NOW; lw=$NOW; apply_daily
          log "季校验完成（100% + 顶充 ${Q_TOPMIN}min）-> 回日常"; } ;;
      *)                                  # 日常
        apply_daily
        if [ "$MODE" = auto ]; then      # 到点就起一次校验（季度优先；间隔从上次完成算）
          if [ "$lq" = 0 ] || [ $(( NOW - lq )) -ge $(( Q_DAYS * 86400 )) ]; then
            [ "$lq" != 0 ] && { phase=qtr_dis; since=$NOW; t100=0; log "季度校验到期($(( (NOW-lq)/86400 ))d) -> 放电到 $Q_START%"; }
          elif [ "$lw" = 0 ] || [ $(( NOW - lw )) -ge $(( W_DAYS * 86400 )) ]; then
            [ "$lw" != 0 ] && { phase=weekly_dis; since=$NOW; log "周校验到期($(( (NOW-lw)/86400 ))d) -> 放电到 $W_START%"; }
          fi
        fi ;;
    esac
    # 超时保护：某个阶段卡住（充电电流不够、负载太高）就别一直停着
    if [ "$phase" = weekly_dis ] || [ "$phase" = qtr_dis ]; then
      [ "$since" != 0 ] && [ $(( NOW - since )) -gt "$DIS_TMO" ] && { phase=daily; since=$NOW; apply_daily
        log "告警: 放电阶段超时 $(( (NOW-since)/3600 ))h 仍在 $LVL% -> 退回日常"; }
    elif [ "$phase" = weekly_ch ] || [ "$phase" = qtr_ch ] || [ "$phase" = qtr_top ]; then
      [ "$since" != 0 ] && [ $(( NOW - since )) -gt "$CHG_TMO" ] && { phase=daily; since=$NOW; lw=$NOW; apply_daily
        log "告警: 回充阶段超时 $(( (NOW-since)/3600 ))h 只到 $LVL% -> 退回日常（这口径下 500mA 不够，考虑换 USB3 口/带供电 hub 或改浅区间）"; }
    fi
  fi
fi

pl=$(PHASE_LABEL "$phase")     # 阶段可能在本轮里跳了好几步，标签取最终值
save_state

# ---------- 写开关 ----------
if [ -n "$want" ] && [ "$want" != "$CHG" ] && [ "${PB_ONESHOT:-0}" != 1 ]; then
  a "echo $want > $NODE"
  NOWV=$(a "cat $NODE" | tr -dc '0-9')
  log "level=$LVL charging_enabled ${CHG:-?} -> $want (读回 ${NOWV:-失败}) phase=$phase[$pl] usb_online=${USBON:-?}"
elif [ "${PB_VERBOSE:-0}" = 1 ] || [ "$MODE" != auto ]; then
  log "level=$LVL phase=$phase[$pl] want=${want:-?} charging_enabled=${CHG:-?} mode=$MODE"
fi

# ---------- 心跳 + 面板状态 ----------
CNTF=${PB_COUNT_FILE:-/tmp/pb_chargeguard.count}
n=$(cat "$CNTF" 2>/dev/null | tr -dc '0-9'); n=${n:-0}; n=$((n+1)); [ "$n" -ge "$BEAT" ] && n=0
echo "$n" > "$CNTF" 2>/dev/null || true
if [ "$MODE" = auto ] && [ "$n" = 0 ] && [ "${PB_ONESHOT:-0}" != 1 ]; then
  log "心跳 level=$LVL charging_enabled=${CHG:-?} phase=$phase[$pl] usb_online=${USBON:-?}"
fi
if [ "${PB_PUSH:-1}" = 1 ] && [ "${PB_ONESHOT:-0}" != 1 ] && command -v curl >/dev/null 2>&1; then
  curl -s -m 3 -X POST -H 'Content-Type: application/json' \
    -d "{\"value\":\"$pl\",\"sub\":\"电量 ${LVL}% · charging_enabled=${CHG:-?}\",\"ttl\":600,\"level\":\"$([ "${CHG:-1}" = 0 ] && echo warn || echo ok)\"}" \
    "$PUSHURL" >/dev/null 2>&1 || true
fi

echo "level=$LVL phase=$phase[$pl] charging_enabled=${want:-$CHG}"
