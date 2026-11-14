# TESTLOG — first real overnight ErP power-off: deep standby verdict (2026-11-14)

Question: host off 11-13 23:34:25 -> on 11-14 11:31:27 (11h57m), phone reported "battery 0" this
morning - did deep standby work at all? (It had only ever been verified with the CABLE PHYSICALLY
PULLED, 11-12/11-13; every "screen off on shutdown" pass before this was credited to the host-side
sleep hook, so the ErP case was genuinely unproven.)

## Verdict: deep standby DID work. The 0 % was a fuel-gauge lie.

Evidence (batterystats ring covered the whole night, RESET 11-13 13:14:36, dump dir
`/mnt/nvme0n1p1/temp/pb-drain-20261114-125045/`, parser `pb_drain_parse.py` now archived):

- `-screen` exactly once at 23:34:16 (sleep hook + timeout), never `+screen` again until this morning.
- Phone never rebooted (uptime 2d12h45m at 12:49).
- Heartbeat signature all night: paired `+running +wifi_radio wakeupap=u0a154` events (:06/:34
  pattern = connect attempt + ~28 s TCP timeout to the dead host, once per 60 s) - i.e. the app sat in
  DEEP mode (60 s probe, holdCpu=false), NOT the 15 s live standby poll.
- `PhoneBox:probe` PARTIAL_WAKE_LOCK opened exactly ONCE in the 12 h window (would be hundreds in
  non-deep standby mode, one per probe) - the no-lock deep heartbeat confirmed by lock census.
- Real energy: coulomb counter `charge=` 2091 -> 1909 mAh = **182 mAh over 11h52m = 15 mA average**
  (better than the 27 mA measured in the 15-min 11-12 test; at this rate a power-off stretch lasts
  ~10 days, not one night). device_idle cycled light<->off around the heartbeat (it did idle).
- Voltage arc (the arbiter): 23:50 4.020 V -> 01:10 3.994 -> 04:30 3.966 -> 08:40 3.934 -> 11:00
  3.892 V = textbook flat-region decay of a ~60 % pack. A genuinely 1-2 % cell would sit at <=3.6 V.

## What actually showed "0 %"

The gauge's voltage->percent curve, re-anchored after yesterday's 80 %-charge / 23:20 stop-charge
float, collapsed: level column 61 @ 23:50 -> 35 @ 01:10 -> 1 @ 04:30 and stayed 1 until the charger
returned at 11:31 (then 1 -> 76 by 12:49 under a 500 mA cap - physically impossible, mostly OCV
ratchet, matching the known 3T/Lineage gauge chaos of 11-12, charge_counter OCV jumps and the
69->67 capacity correction). So:
- physical state this morning: ~60 %, ~15 mA average overnight consumption. Great.
- displayed state: fiction. Chargeguard's CRIT fired honestly on the lying number
  (level=1 -> charging_enabled 0->1 at 11:32:47) and will ride to 80 normally afterwards.
- Known implication: the phone's own battery % and anything reading `capacity` shares this
  unreliability until the gauge re-learns (the scheduled weekly 40->80 / quarterly 20->100
  calibrations, next 11-19 / 2027-02-10, are exactly the cure; `~/bin/pb_chargeguard.sh calib
  weekly` can run it sooner if the user wants the gauge re-anchored today).

## Not touched (no code change warranted)

hostAlive / standby / deep logic behaved; the ErP worry from this morning ("USB_STATE quirk keeps
hostAlive true so deep never engages", supported by the 11-13 hub-cut observation) did NOT bite
last night: `usb_data` dropped 23:35:34 and stayed gone, and the 60 s no-lock heartbeat proves the
phone-side state machine correctly saw the host as dead. If the quirk ever does hold `configured`
true through a real ErP loss, the symptom would return - then the fix is dropping
`configured || connected` from hostAlive (PR #32's pure-data criterion).
