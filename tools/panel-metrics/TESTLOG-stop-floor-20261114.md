# TESTLOG — goodbye zeros + silence net (2026-11-14, second half)

Follow-up to TESTLOG-push-floor-20261114.md. Yesterday's load floor fixed what the **agent** sends
at cold start; the remaining stale display was the **phone app's own RAM** - the 3T process survives
server power cycles, and its WebView keeps the last frame it ever received. Two more layers now
close that, the second one per user requirement "意外停电时关机钩子不能生效".

## Layer 2 - agent says goodbye with zeros (`pb_stop_floor_patch2.py`, dll 518c6693 -> 19a77cca)

- `PushStore`: `FloorOnLoad` renamed `Floored` (shared by load and stop); `SealAndFloorAll()` seals the
  store (late `Set` calls are swallowed, no resurrection), floors every key, `Changed()+Persist()` at once.
- `Program.cs`: `ApplicationStopping` -> SealAndFloorAll + `Thread.Sleep(1300)` so the per-second
  live-stream frame (`/api/stream`, confirmed 1 Hz unconditional) delivers the zeros before the process dies.
  Covers SIGTERM at stop/reboot and `/api/restart`. The pushd unit stops **before** phonebox by unit order
  (`After=phonebox.service`), so nothing refills the goodbye window.
- Build 0W0E, `dotnet test` 284/284 (8 s).
- Proof `pb_stop_floor_deploy_test.sh`: journal `graceful stop: floored 6 pushed values so the phone
  sleeps on zeros` @12:01:32; `data.json` immediately holds all-zero values; agent boot with pushd down
  keeps zeros (no resurrect). Phone screencap during the stop (`screen_after_graceful_stop.png` md5
  68c1c379) still showed OLD numbers with "PC not connected" - **the phone happened to sit in a stream
  flap window and missed the goodbye frame** (the known 38-46 s disconnect cycle). One frame later
  (`screen_agentdown_then_boot.png` md5 361d7dba) it was all zeros: the boot-side load floor works end to
  end on screen. Flap-proofing is exactly why layer 3 exists.

## Layer 3 - the panel floors itself after 5 s of silence (`pb_watchdog_patch3.py`, APK vc28 -> **vc29** f0f68d01)

- `main.js`: new `floorStalePush()` called from the 1 Hz `tick()` when `lastStateAt` is >5 s old
  (that stamp already exists and is refreshed by BOTH stream and poll in `applyState`): every cached
  push item becomes `{value:0}` (+unit), arrays `[]`, scalars `0`, `at: Date.now()` (redraw guard),
  `expiresAt:null`; one `emit('push')` re-announces to built-in widgets and the HTML sandbox.
  Latch `staleFloorDone` fires once per silence episode and resets the moment the agent's own
  `pushItems` (or a classic `loadPush`) arrive again. Runs in night mode too, so the RAM a reboot
  wakes into is already zeros.
- Graceful-stop chain untouched; the two layers overlap on purpose: when the goodbye lands, zeros
  arrive ~6 s earlier; when it doesn't (hard power loss, flap), the net catches 5 s after last frame.
- Build: gradle assembleRelease (server cache warm, ~2 min); installed with `install -r -t` over vc28,
  data/pairing kept (`versionCode=29` on device).
- First proof run was VOID (`pb_watchdog_test.sh`, screenshots 166 KB): the user had the Settings app
  open on the phone and `pm install -r` kills the panel process without relaunching it - all four
  captures showed Settings. Redone with `am start` + `mCurrentFocus` asserted before every shot
  (`pb_watchdog_retest.sh`, panel focus in all four stages):
  - A live values `v2_live.png` (md5 1d29f5c6);
  - B `systemctl --user stop pb-strata-pushd` then **kill -9 with a temporary Restart=no drop-in**
    (phonebox.service really has Restart=on-failure - without the drop-in the agent respawns in ~1 s
    and the 5 s net never sees silence; drop-in removed + daemon-reload + reset-failed afterwards);
  - C +8 s: agent port DOWN, `grep -c "graceful stop"` over the window = **0** (no handler ran), yet
    the screen reads **0 W / 0 GB / 0 KB / 0 tok/s / 0 t/s + Model state floor + "PC not connected"**
    (`v2_kill8.png` md5 05220afb) - only possible writer is the watchdog.
  - D agent restarted, pushd still frozen: agent and panel agree on zeros (`v2_agentback.png` 2b28b39d).
  - E pushd on: live values back (`v2_restored.png` 85977fef).
- Known remaining nuance (not push, out of the agreed scope): the BUILT-IN stat cards (CPU/GPU/RAM/
  NETWORK/topprocs) freeze at their last state-frame values while the agent is away - they are not
  persisted and were never part of "上次保存的冷数据"; zeroing them on silence would be a one-line
  sibling change in the same tick if ever wanted.

## Rollbacks

- agent layer: `systemctl --user stop phonebox` then restore
  `/mnt/nvme0n1p1/temp/pb-stopfloor-20261114-120121/.` into `~/.local/share/PhoneBox/app/` (dll 518c6693), restart.
- panel layer: rebuild/revert vc28 (main.js + build.gradle.kts = `git revert` commit2, assembleRelease,
  `install -r -t`); no user data at stake either way.
- Both: `git revert` the two commits; live artifacts (dll/APK) must be restored regardless.


## Layer 4 (later the same day, user follow-up) - the built-in stat cards join the net: vc29 -> **vc30** (APK `4842f32e`)

The four stat cards (CPU / GPU / RAM / NETWORK) are fed by the live frames' `pc`/`ping` blocks, not by
push values, so the 5 s net left them frozen at the last pre-loss reading. `floorStalePush` now swaps
`D.state` for a floored copy too - `cpu`/`cpuTemp`, `gpu.util/temp/power/fan/clock/vramUsed`,
`ramUsedGb`, both net rates and `ping.ms` go 0, while names, totals and limits survive so the cards keep
their context (`0 / 126 GB`, `↑ 0 B/s · 0 ms`) - and emits `state` because `W.stat`/`W.gauge` re-render
on that kind. The `staleFloorDone` latch reset moved to the top of `applyState`: any successful frame
retires the whole silence floor (also fixes the stock-agent path where frames carry no pushItems).

Desk proof `pb_statfloor_retest.sh` (mCurrentFocus asserted before all three captures): kill -9 behind
the temporary `Restart=no` drop-in, +9 s every card reads 0 while pushed keys floor as before -
`v3_kill9.png` md5 54e91158 (live before: 52eebf9b, after recovery: 4efc145d). vc30 APK archived at
`/mnt/nvme0n1p1/temp/pb-statfloor-20261114-121842/apk/PhoneBox-0.9.3-vc30.apk`.

Still frozen by design: the Top CPU process list (not one of the four cards - it takes one line in the
same flooredState net if ever wanted).


## Layer 5 (same day, third follow-up) - the Top CPU list joins the net: vc30 -> **vc31** (APK `2a30a5aa`)

The process cards (`W.topprocs` in pc.js / `W.processes` in basic.js, both `needs: ['procs']`) carry
their own empty-state placeholder, so an EMPTY table - not zeroed rows - is their honest floor: the
silence net now also sets `D.procs = {groups:[], total:0, groupCount:0}` and emits `procs`, rendering
"Measuring..." (a frozen process list from a dead host would claim knowledge it no longer has).
No reset code is needed: the 2 s `loadProcs` interval is gated on `online`, so nothing overwrites the
empty state while the agent is away, and recovery refills it within one interval.

Desk proof `pb_procfloor_retest.sh` (mCurrentFocus asserted at all three captures): kill -9, +9 s the
whole desk is floor and TOP CPU reads "Measuring..." - `v4_kill9.png` md5 0efc133a (live before
70d453c8, restored after 9eb45196). vc31 APK archived at
`/mnt/nvme0n1p1/temp/pb-procfloor-20261114-122413/apk/`. This supersedes layer 4's "still frozen by
design" note: every card on the home layout now floors within 5 s of the agent going silent.
