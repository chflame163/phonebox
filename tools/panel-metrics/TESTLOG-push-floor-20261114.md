# TESTLOG — push cold-start floor (2026-11-14)

## What changed and why

User requirement: on a cold start the controls must NOT show the numbers saved from the last
session — every pushed key should be sent at its lowest value (0) until fresh data arrives.

Two things in `agent/PhoneBox.Agent/PushStore.cs` stood in the way:

1. `Load()` restored `data.json` verbatim — the old contract ("values survive restarts") is what
   could pin pre-shutdown numbers on the panel.
2. Worse in practice: `Changed()` re-armed the 2 s persist debounce on EVERY push. The resident
   `pb-strata-pushd` pushes every second, so the timer never fired — `Persist()` only ran during
   quiet gaps, and the live `~/.config/PhoneBox/data.json` was literally `{}` (mtime 11-13 22:42).
   So today's cold start restores nothing at all: after boot the strata widgets sit on
   "No data yet" until the engine is up, and what the user sees as "上次保存的冷数据" in the first
   seconds is the phone app's own RAM echo (its process survives the server reboot; the numbers
   vanish once the agent's first frame arrives — not fixable agent-side, see Residual).

Patch (`pb_push_floor_onload_patch1.py`, anchors asserted, idempotent):

- `Load()` runs every restored item through `FloorOnLoad`: objects → `{"value":0}` keeping only
  `unit` for context, arrays → `[]`, scalars → `0`; `At` re-stamped (the phone's `W.push` skips the
  redraw while `item.at === lastAt`, so a fresh stamp is REQUIRED to overwrite pre-shutdown numbers
  already on screen), `ExpiresAt` → null so the floor never ages out and rides until a real push
  replaces it.
- `Changed()` arms the debounce only when none is pending (`_saveQueued` flag, cleared at the top of
  `Persist()`): floor = one disk write per ~2 s even under the 1 s push cadence.

## Deploy

- Server repo `~/phonebox` master `c554cfa` + patch → `dotnet build -c Release` **0W 0E (warm 0.9 s)**.
- `dotnet test PhoneBox.Agent.Tests` → **284/284 passed (8.5 s)**.
- dll swapped: `9d8088c1` → **`518c6693`** into `~/.local/share/PhoneBox/app/`
  (pre-swap snapshot incl. `data.json.pre`: `/mnt/nvme0n1p1/temp/pb-push-floor-20261114-115044/`).
- Stale nested `app/linux-x64/` (1.6 M, pre-existing copy from DIST; ExecStart is the top-level
  apphost) removed. Phone app untouched (vc28 already carries the P3 `pushItems` frame).

## Proof (`pb_push_floor_deploy.sh`, all stages green)

- A — agent alone, pre-state `data.json={}` → `/api/push items {}`.
- B — pushd on: real values back AND `data.json` finally persists: 1055 B with all six keys,
  mtime advanced +5 s over a 5 s observation window (writes every ~2 s).
- C — simulated cold boot (pushd stays down, agent restarts): all six keys
  `{"value":0, unit}` (`strata_state` → `{"value":0}`), `expiresAt: null`, `at` fresh; still 0 after
  +8 s. Phone screenshot `screen_zeros.png` (md5 `b4ae51c4`): GPU POWER **0 W** empty ring,
  VRAM **0 GB**, CONTEXT **0 KB**, DECODE **0 tok/s**, PREFILL **0 t/s**, Model state six pills at
  floor + "Waiting for a request" + "—". Titles render neutral (no stale `level`), stale `sub`
  lines gone. Built-in stat cards (CPU/GPU/RAM/NETWORK) keep live system values — they were never
  persisted, untouched by design.
- D — pushd restarted: real values within seconds (`screen_real.png` md5 `145bffa0`): 24 W green,
  23.1 GB orange, 279 KB green ring, 88.2 / 80.4, `last: 72 tokens at 88.2 tok/s` restored.

Real-reboot expectation: agent boots → first state frame already carries every key at 0 (floored
from the ~2 s-fresh data.json), gpu keys live within ~1 s of pushd start, strata keys stay at the
floor until the engine answers `/metrics` (~5 min) instead of showing "No data yet".

## Residual (phone-side, by design not patched)

The 3T never power-cycles with the server, so between panel wake (boot+~6 s) and the agent's first
frame (boot+~15 s) the WebView still renders its own pre-shutdown RAM values for those few seconds.
If that echo ever becomes unacceptable, zero `D.push` in `main.js` when the stream drops (one line,
needs a new APK) — the agent-side floor already guarantees the connected state is honest.

## Rollback

```
systemctl --user stop pb-strata-pushd phonebox
find ~/.local/share/PhoneBox/app -maxdepth 1 -mindepth 1 -delete
cp -a /mnt/nvme0n1p1/temp/pb-push-floor-20261114-115044/. ~/.local/share/PhoneBox/app/
rm -rf ~/.local/share/PhoneBox/app/linux-x64 ~/.local/share/PhoneBox/app/data.json.pre
systemctl --user start phonebox pb-strata-pushd
```
(source-level: revert this commit; the live dll swap must be undone either way.)
