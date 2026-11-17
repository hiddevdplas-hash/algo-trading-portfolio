VERDICT: PASS

# Re-review of IDEA-1021 (autocall dealer-gamma session fade)

**Files reviewed:**
- Module: `<project>/Edge Research/strategies/idea_1021_autocall_dealer_gamma_session_fade.py`. It has not changed since 83e4775. `git diff 83e4775 HEAD` on it is empty (HEAD f077fec).
- Card: `<project>/Edge Research/ideas/cards/IDEA-1021-autocall-dealer-gamma-session-fade.md`, v2, commit d531b03.
- Earlier FAIL: `<project>/Edge Research/reviews/idea_1021_autocall_dealer_gamma_session_fade@83e47751ff80.md`

**Results:** none are voided. There are no IDEA-1021 rows in `ledger/` and no IDEA-1021 jobs in `queue/`. The only grep hits were job ids that happen to contain "1021".

## The two earlier findings are resolved
1. **Barrier warm-up (L73-L75).**
   - Card v2 says: "before 250 sessions exist, the highest close of all previous sessions is used (from the first completed session; the first session is not blocked)".
   - The code matches exactly. On the first session `closes` is empty, so `ok` stays True. After that, `max(closes[-250:])` is taken over however many sessions exist.
2. **Session close (L81, L77).**
   - Card v2 says: "close of the last m15 bar ending at or before the time exit (15:00 Tokyo / 15:30 Frankfurt), not the exchange's closing price".
   - The code matches. `cur["close"]` is updated only on same-day session bars with `cmin <= exit_min`.

## Per area
1. **Bar timing:** clean.
   - The open is `o` of the 09:00 bar. The decision at bar i uses `c[i]` and sends a market intent.
   - R20 and the barrier use only completed earlier sessions. A session is appended only when a later local day's bar arrives (L64-L67).
   - There is no shift, no forward indexing and no centred window.
   - `hold_ms` is the exit wall-clock time minus bar i's close, using the UTC offset at bar i. DST changes happen overnight, so this is safe.
2. **Full-period statistics:** clean. R20 is a trailing 20-session mean and the barrier is a trailing max of up to 250 sessions.
3. **Higher timeframes:** clean. The module uses m15 bars only, with no resampling. `local_ms` only converts clocks.
4. **Calendar and news:** clean. The module never reads the calendar.
5. **Data range:** clean.
   - It reads only `bars`, `params` and `ctx`, with no file or path access.
   - Entries are gated on `oms[i] < first_ms` (L82).
6. **Card match:** clean.
   - Defaults are k 0.55 and s 0.45. The grid is 3×3 = 9, matching the card.
   - The fixed values LOOKBACK 20, BARRIER_N 250 and BARRIER_FRAC 0.80 are on the card's fixed list.
   - Both symbols' session, decision and exit times match the card.
   - These rules all match: the 09:00 bar defines a session, the barrier blocks the day, entry against d, stop s·R20, target |d|, first trigger only, and "no trade until 20 sessions".
   - The card now covers both behaviours it was missing before.
7. **Prop rules:** clean.
   - Every intent has a stop, `sl_dist = s·R20 > 0`, guarded by `r20 > 0` at L88.
   - There is at most one trade per symbol per day, with no grid and no martingale.
   - Exits come well before the flat time, and no entries depend on the engine's blocked windows to drop them.
8. **Tick volume:** clean. The module never reads `bars["vol"]`.

## Notes (none of these block)
- **Stale docstring:** the docstring at L2 still says "v1". You could update it to v2 next time the module changes for another reason; it does not affect behaviour.
- **Notes from the first review still apply:**
  - The stop and target are distances from the fill, so the target is the open plus or minus the close-to-fill gap.
  - The time exit is measured from the fill.
  - There is no `timeframe == "m15"` guard, so the job must declare m15.