# VWAP Mean Reversion — close-out (2026-11-01)

> **Portfolio copy** of the project's close-out. Paths refer to the private working repository (533 commits), which is not public.
> Details of specific personal trading accounts and the copy-trading setup have been removed; the results and lessons are unchanged.

**Closed on 2026-11-01: the edge is not real.** Nothing went live. No demo, no evaluation, no money at risk.

## What it was
- **Idea:** a portfolio of VWAP mean-reversion "cells" (symbol × VWAP mode: Session, Intraday Dual, Weekly) on IC Markets cTrader. Each cell
  was optimised and validated on its own, then the cells were combined for prop-firm accounts.
- **Time:** 2026-09-30 → 2026-11-01, 533 commits.
- **Method:** PROTOCOL v1 → v3.
  - In-sample 2018–2023, searched in Python (`engine/`, verified trade-for-trade against cTrader).
  - m1 and tick checks in cTrader.
  - A committed pre-registration per cell, then an untouched tick out-of-sample run from 2024 to now.
  - An independent AI reviewer (`oos-sceptic`) at every gate.

## Result
- **147 v3 OOS files, family total −398 R.**
- **Passing didn't persist:**
  - in-sample vs OOS R/month correlation **−0.13**;
  - files that "passed" on 2024–25 lost **−88 R in 2026**.
- The go-live sceptic said NO-GO: zero edge is the realistic planning case (`SCEPTIC-GO-LIVE-excerpt.md`). A 4–6 week forward test couldn't
  confirm an edge; that would take about 30 months for the evaluation set and about 72 for the funded set.

## Lessons for the next project
1. **Heavy optimisation per cell fitted noise.** Grids of thousands of variants per cell, with plateau and region checks, still picked
   parameters with no future. Next time, test the **simplest version of an idea first**. Only an idea that shows an edge un-optimised earns any
   tuning.
2. **Count the tests.** About 150 OOS files at a fixed bar produce passes by luck alone. Compare each batch's hit rate with the zero-edge rate
   before believing any single pass.
3. **Check persistence before scaling.** A pass is evidence only if the passers keep earning in a later period. Check that on a slice of data
   before building a portfolio.
4. **What worked: keep it.**
   - The pre-registration plus untouched OOS plus sceptic caught this before any money was at risk.
   - The Python replica made searching about 100× faster than cTrader.
5. **Process cost.** Manual cTrader runs were the bottleneck: queues, exports, intake. Use as few as possible: only to referee Python
   and for the final tick checks.
6. **cTrader traps** (still true for any cBot):
   - m1 fills take-profits beyond the target, so cap them;
   - float ranges drop their last value;
   - backtest swap uses today's rate at 21:00 UTC;
   - m1 uses a fixed spread, so check news trades on tick;
   - export file names can be wrong, so check what is inside;
   - check the real start of tick history (USTEC and GBPCAD reach 2018).

## What carried over to the next project
| what | where (in this portfolio) |
|---|---|
| Python backtest engine + cTrader referee checks | `engine/` (`REPORT.md`, `RULES.md`, `REFEREES.md`, `EXPORT-HOWTO.md`, `FastBtExport.cs`) |
| cTrader report parser, stats, Monte Carlo, OOS check | `tools/report_stats.py` |
| The cBot itself (C#, with NY-time / DST handling and a news filter) | `cbot/VwapMeanReversionBot.cs` |
| The sceptic agent and the lessons | `../edge-research/agents/`, `../edge-research/DESIGN.md` |

## If VWAP is ever reopened
Only with a **new mechanism or a new market**, on data after 2026-11-01 as a fresh holdout, under the next project's process (simple first,
tests counted, persistence checked). Never re-tune the closed cells. Every v3 OOS result here has been seen, so those years are no longer
out-of-sample.
