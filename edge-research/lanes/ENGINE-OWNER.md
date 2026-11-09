# Engine owner

**Job:** build and keep the engine that every other session uses (`DESIGN.md` §3–4, §7–8). The only session that changes `engine/`.

## Build list (week 1, DESIGN §12)
1. **Research store** `../data/ic-research-2014-2024/`, research period only:
   - measure size and decompression speed on EURUSD and XAUUSD first;
   - check counts against `data-checks/ic-tick/*.json`.
2. **Cost table v1** `engine/costs.json` (DESIGN §3.5) from the FTMO feed comparisons and the firms' published commission and swap (`rulebook/SYMBOLS.md`).
3. **Kernel:** orders from closed bars, live from the next tick; fills at bid / ask on ticks; stop wins when both levels are crossed; time exits; 1 R sizing.
4. **Rules layer** (DESIGN §4.2) with real time zones; **trade log** fields (§4.3).
5. **News calendar** extended back to 2014-11 (DESIGN §3.6), copied from the VWAP generator, not edited there.
6. **Ledger writer, queue, runner** (14 workers, launchd), engine hash.
7. **Tests:** unit, determinism, DST weeks.
8. **5 referee strategies**, in Python and as self-contained cBots in `cTrader-Bots/`, plus a run list for the user (tick mode, IC, 3–6 months each). Comparison ≥ 99% identical trade lists.
9. **Random-strategy generator** and the null calibration batch (DESIGN §8).
10. **Look-ahead reviewer agent** wired into the queue: no review pass, no counted result.

## Rules
- **Generic engine:** no strategy-specific code in the kernel. A strategy that needs a new feature asks for it, and the feature is added for all strategies, with tests.
- **Every change gets a new engine hash,** a LOG entry, and a note on which results it invalidates.
- **Copy from VWAP's `tools/fastbt/`** (RULES.md fill rules, cTrader traps, NY clock, news filter) **without editing it there.**
