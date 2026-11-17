# Volume-profile data checks (2026-11-16)

Gatekeeper request, user decision 2026-11-16 ("TPO now, VP after check"). Two **data checks, not strategy tests**: no runner job, no
ledger row, nothing counts toward k, nothing read after 2024-12-31. DESIGN §5 still parks volume-based ideas. An addendum A13 is
the gatekeeper's call; these are the numbers it rests on. Engine owner, engine 882d0efed853 (not changed; these scripts only read).

| file | what |
|---|---|
| `vp.py` | shared code: readers, ATR, profiles, comparisons |
| `check1_brokers.py` → `check1_brokers.json` | IC vs FTMO tick-count profiles, 28 FX pairs |
| `check2_tpo.py` → `check2_tpo.json` | tick-count vs TPO profiles on IC, 6 symbols, 2014-11 → 2024-12 |

Run: `~/.venvs/fastbt/bin/python data-checks/volume-profile/check1_brokers.py`, then `check2_tpo.py`. Each takes a few minutes (16 cores).

## Method
- **Profile:** the count per price bin over a trading day (17:00 New York → 17:00 New York, which is 23:00 → 23:00 Amsterdam) or over a
  Monday–Friday week.
  - **Bins:** one bin = scale × daily ATR, where ATR = the mean true range of the 14 previous days, from IC m1 bars.
  - **Grid:** bins sit on a fixed price grid (bin = ⌊price / width⌋), so two feeds or two methods share the same bins.
  - **Scale:** 0.1 is the headline; 0.05 and 0.2 are in the JSON. A week uses the ATR of its first day.
- **Tick profile:** one count per tick. Check 1 uses mid prices (the two brokers' spreads differ); check 2 uses bid prices (as the
  m1 bars do).
- **TPO profile:** each m1 bar adds 1 to every bin from its low to its high.
- **Comparisons, per day or week:**
  - Pearson correlation of the bin shares, over the union of both profiles' bins.
  - POC, VAH and VAL distance in bins. The value area is 70%, grown one bin at a time from the POC towards the larger neighbour.
  - Value-area overlap (Jaccard).
- **Baseline ("range-only"):** a POC at the middle of the period's range and a value area at its central 70%. Any comparison clears
  this partly just because both profiles share the same range.
- **Days used:** weekdays only, with at least 600 m1 bars (cash sessions: at least 80% of the session's minutes) and at least 500
  ticks in each feed. The FX quarantine of May–July 2015 is excluded.
- **Data:**
  - IC: the research store (ends 2024-12).
  - FTMO: `~/cAlgo/Exports/fastbt-ftmo-tick/<pair>_2020040[1-9]` ticks. These run 2020-04-01 → 2021-07-02, then a gap, then
    2025-06 →. The reader decompresses the file in blocks and, in the block that reaches 2021-08-01, finds the first such line by
    bisection on line timestamps alone. Only the text before it is parsed, so no row after the gap is parsed (0 in every file).
    This is the cut the locked-period rule needs, not just a later filter.

## Check 1: do two brokers' tick counts give the same profile?
28 FX pairs, 324 days each (2020-04 → 2021-07), 9,072 days and 1,736 weeks. Each number is the median over the 28 pairs.

**Tick rates differ:** FTMO has 0.16–0.37 × IC's ticks per day on the crosses and 0.8–1.1 × on the majors (median 0.31 ×). The
activity agrees over time: the correlation of log hourly tick counts is 0.82, and of daily totals 0.83.

| daily, bin 0.1 ATR (10 bins median) | corr median | corr p10 | POC same bin | POC within 1 | VAH within 1 | VAL within 1 | VA overlap |
|---|---|---|---|---|---|---|---|
| **IC tick vs FTMO tick** | **0.992** | 0.968 | **85%** | 92% | 95% | 95% | 1.00 |
| IC tick vs IC TPO | 0.948 | 0.853 | 67% | 80% | 85% | 85% | 0.83 |
| FTMO tick vs IC TPO | 0.946 | 0.837 | 65% | 79% | 85% | 84% | 0.83 |
| IC tick vs range-only | — | — | 10% | 44% | 56% | 64% | 0.67 |

| weekly, bin 0.1 ATR (21 bins median) | corr median | POC same bin | POC within 1 | VA overlap |
|---|---|---|---|---|
| IC tick vs FTMO tick | 0.994 | 83% | 90% | 1.00 |
| IC tick vs IC TPO | 0.970 | 68% | 82% | 0.92 |

**Beyond TPO:** this asks whether the part of the tick profile that TPO does not explain is the same on both brokers. Residual
r = tick share − TPO share per bin (IC's TPO for both feeds).

| | daily 0.05 | **daily 0.1** | daily 0.2 | weekly 0.1 |
|---|---|---|---|---|
| corr(IC residual, FTMO residual), median (p10) | 0.91 (0.68) | **0.94 (0.73)** | 0.97 (0.73) | 0.92 (0.76) |
| periods where IC's tick POC ≠ the TPO POC | 3,760 | 3,090 | 2,409 | 545 |
| … and FTMO's POC = IC's tick POC | 67% | **74%** | 79% | 70% |
| … and FTMO's POC = the TPO POC | 16% | **16%** | 15% | 15% |

All 28 pairs have a residual correlation of 0.897–0.984 at daily 0.1, so none is an outlier.

## Check 2: is a tick-volume profile almost the same as a TPO profile?
IC data. Cash sessions: US500 09:30–16:00 New York, DE40 09:00–17:30 Amsterdam. DE40 and XTIUSD start where the store starts.
Bin 0.1 ATR.

| symbol | period | session | days | corr median | corr p10 | POC same bin | POC within 1 | VAH within 1 | VAL within 1 | VA overlap | range-only POC within 1 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| EURUSD | 2014-11 → 2024-12 | full day | 2568 | 0.947 | 0.842 | 66% | 78% | 86% | 86% | 0.857 | 37% |
| USDJPY | 2014-11 → 2024-12 | full day | 2569 | 0.974 | 0.913 | 77% | 87% | 92% | 91% | 1.0 | 42% |
| XAUUSD | 2014-11 → 2024-12 | full day | 2622 | 0.961 | 0.867 | 70% | 82% | 86% | 87% | 0.889 | 41% |
| US500 | 2014-11 → 2024-12 | full day | 2596 | 0.936 | 0.759 | 64% | 78% | 82% | 79% | 0.8 | 40% |
| US500 | 2014-11 → 2024-12 | cash day | 2448 | 0.972 | 0.881 | 76% | 89% | 94% | 91% | 1.0 | 54% |
| DE40 | 2021-09 → 2024-12 | full day | 826 | 0.865 | 0.7 | 49% | 63% | 71% | 68% | 0.714 | 35% |
| DE40 | 2021-09 → 2024-12 | cash day | 826 | 0.976 | 0.896 | 79% | 89% | 95% | 94% | 1.0 | 55% |
| XTIUSD | 2017-07 → 2024-12 | full day | 1912 | 0.915 | 0.746 | 57% | 71% | 80% | 78% | 0.8 | 36% |
| EURUSD | | full week | 498 | 0.97 | 0.931 | 69% | 82% | 82% | 82% | 0.9 | 18% |
| USDJPY | | full week | 499 | 0.981 | 0.958 | 75% | 86% | 87% | 87% | 0.944 | 19% |
| XAUUSD | | full week | 500 | 0.979 | 0.945 | 73% | 85% | 83% | 84% | 0.922 | 18% |
| US500 | | full week | 484 | 0.954 | 0.887 | 66% | 78% | 76% | 73% | 0.889 | 22% |
| DE40 | | full week | 154 | 0.94 | 0.887 | 53% | 76% | 80% | 78% | 0.889 | 20% |
| XTIUSD | | full week | 365 | 0.953 | 0.904 | 62% | 78% | 82% | 78% | 0.889 | 20% |

**By year** (full day, corr / POC within 1): stable. EURUSD runs 0.91–0.96 / 68–81%. US500 is 0.91–0.96 / 68–82%, lower in
2023–24 (0.908). DE40 is 0.92 in 2021, then 0.85–0.87. XTIUSD runs 0.87–0.94. Per-year numbers are in the JSON.

## Reading
1. **Broker agreement: yes.** Two brokers whose tick rates differ by up to 6× give practically the same profile: daily correlation
   0.99, the same POC bin on 85% of days, and value-area edges within one bin on 95%. More to the point, the part of the tick profile
   that is *not* time-at-price replicates across the brokers:
   - the residual correlation is 0.94;
   - on the 3,090 days where tick volume moves the POC away from the TPO POC, FTMO moves it to the same bin as IC on 74% of days, and
     back to the TPO POC on only 16%.

   So the tick-count profile measures something market-wide, not one feed's quoting.
2. **Tick volume vs TPO: close in broad shape, different where it matters.**
   - Correlation is 0.87–0.97 daily and 0.94–0.98 weekly, but the POC differs from the TPO POC on 23–51% of full days at 0.1 ATR.
   - It differs by 2 bins or more (≥ 0.2 ATR) on 13–37% of full days.
   - The difference is largest over the full 24-hour day: DE40 0.865, US500 0.936, XTIUSD 0.915. Within an index cash session it is
     small: corr 0.97–0.98, POC within one bin 89%, value area practically the same.

   The pattern fits time-of-day weighting. TPO counts a quiet overnight minute like a busy one; tick volume weights them by activity.
   Check 1 shows that weighting is real (the same on two brokers), not feed noise.
3. **What these checks do not show:**
   - **Tick count is still not traded volume.** No futures volume is here, and the RoboQuant lesson stands. Both brokers may also
     share upstream liquidity providers, which would make their quote rates agree for reasons other than trading.
   - **Nothing here says a volume-profile level predicts anything.** That is a strategy question for the pipeline, at its k.
   - **Within a cash session, a tick-volume profile adds little over TPO** (POC within one bin 89%, value area the same). There, a
     VP idea is close to a TPO idea; over 24-hour or weekly profiles it differs on about a quarter to a third of POCs.

Both checks support A13 as framed: profiles built over at least 1 day, with tick volume as a stated proxy. Possible conditions for
A13 (the gatekeeper's and the user's call):
- **Name the TPO twin.** A VP card states its TPO counterpart, and a VP idea and its TPO twin count as one family for k (seen
  family). Otherwise the same idea runs twice under two names.
- **Name the session.** The card states which profile it uses (cash or 24 h).
