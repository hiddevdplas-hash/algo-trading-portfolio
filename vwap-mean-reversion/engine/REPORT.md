# fastbt — a fast Python copy of the cTrader backtest (feasibility study 2026-10-20, step 1 Rstep 2026-10-21)

## Verdict: feasible, and it works

For US30 Session (Fixed TP and R-step) the Python replica reproduces cTrader's m1-bar backtest almost exactly, and it
is thousands of times faster:

| | cTrader | replica |
|---|---|---|
| US30 Session Fixed TP full grid (22,400 passes) | 11.4 h on one instance (`results.optres`) | **3 s** to compute, **110 s** including writing all trade lists |
| passes per hour, whole Mac | ~5,500 (several instances) | **~28 million** compute only · **~730,000** with full trade lists written |
| Fixed TP: passes identical to cTrader (same trades, net to the cent) | — | **22,384 of 22,400 = 99.93%** |
| Fixed TP: archived trades identical (entry, exit, event, net to the cent) | — | **8,960,741 of 8,960,743** (+16 extra in the replica) |
| R-step (Management 1, 3, 4) full grid, 16,800 passes: passes identical | — | **16,781 of 16,800 = 99.89%** (2 s compute, 42 s with trade lists) |
| R-step: archived trades identical | — | **3,750,656 of 3,750,690 = 99.999%** |

Step 1 (2026-10-21) also fixed the swap rule (the rollover counter starts at a pass's first entry, RULES A8) and the stop-out
rule (only tick prices count, A12); that lifted Fixed TP from 99.42% to 99.93%. `split_plateau.py` on the replica's R-step
grid prints **the same report** as on cTrader's archive (same 121 regions, same numbers; only the pass ids differ, because
cTrader numbers grid passes in its own order).

The normal analysis on the replica's output (`tp_cap.py` → `fullgrid_report.py`) picks **the same 10 best plateau
centres with the same numbers** as the report made from cTrader's own archive (only the pass ids differ, because the
replica numbers passes in its own order). The holding summary differs in the last digit (7,959 vs 7,956 pairs with a
profitable side; median Δnet −1,128 vs −1,122).

**What it means:** once the other management families and VWAP modes are added, the ~800,000-pass v2 queue (~145 h in
cTrader) would take about an hour, writing included. cTrader stays the referee: fine-grid winners, tick in-sample and OOS
keep running in cTrader.

## Step 2 (2026-10-21): every mode and family, news filter, stats-only mode

The engine now covers Session, Weekly and Intraday Dual VWAP; Fixed TP (+ break-even), R-step 1–4, VWAP band trails 5–6;
the entry filters (distance, penetration, ATR percentile); the news filter (calendar read from the cBot); hedging and Track
Touches (implemented, referee grid pending). Checked against every US30 cTrader archive:

| referee (cTrader m1, 2018–2023) | covers | passes | identical |
|---|---|---|---|
| Session full grid Fixed TP (19–20 Oct) | m5/m10, holding | 22,400 | **99.93%** |
| Session full grid Rstep | Management 1/3/4 | 16,800 | **99.89%** |
| Session fine Fixed TP m5 | break-even 0.5/1.0/1.5 R | 4,200 | **99.74%** |
| Session fine Rstep | | 2,280 | **99.74%** |
| Intraday Dual full grid Fixed TP | ETH/RTH, both blocks, closes | 52,920 | **99.95%** |
| Session map (16–18 Oct) | all 7 management types, filters, news 0/1/2, m5–h2 | 2,285 | **99.65%** |
| Weekly map | the same, m15–h4 | 2,190 | 98.81% |
| Intraday Dual map | the same, m5–h2 | 1,810 | 98.62% |

Two things changed between the maps (16–18 Oct) and the grids (19–20 Oct), and cTrader uses the value of the run day for all
history: **the swap rate** (US30 long −121.99 → −139.37 pips) and **the rollover time** (21:30 → 21:00 UTC). The comparison
fits both from each archive. The rest of the map misses (Weekly / Intraday Dual just under 99%) are a dozen market moments
where cTrader did not fill an exact touch of a moved stop on 16–18 Oct, which it does everywhere else (RULES A14): most likely
slightly different minute data on those days. The 52,920-pass Intraday Dual grid, run on the export's data, is at 99.95%.

**Stats-only mode** (`run_grid.py --stats` → `plateau.py`): per-pass statistics inside the engine, no trade lists.
1,277,640 passes (US30 Session Fixed TP, broad ranges) in 4 min 21 s ≈ 17.6 million passes/hour, 1.3 GB memory, a 410 MB
table; the plateau analysis on it takes 2 s. On the US30 full grids `plateau.py` prints the same report as `split_plateau.py`
on cTrader's archives (all numbers; only pass ids differ, cTrader numbers grid passes in its own order); every per-pass
difference lies in the ~0.1% of passes the replica does not match.

## Step 3 (2026-10-21 evening): step-1 runner, compact storage, real speeds, FX conversion

**Storage.** Stats are int32 and exact: money in cents (every trade is whole cents), counts as they are, close times in
seconds; only the equity DD (an in-bar extreme) is rounded to the cent. They are written column-major and compressed per chunk
of 500,000 passes: **37 bytes per pass** (US30 Session Rstep v3: 3.34 M passes = 124 MB). The universe at 1.25 billion passes
≈ 46 GB; every grid now in `_v3_grids` for all 26 symbols (151.6 M passes each, 3.9 billion) ≈ 146 GB. Writing uses the
same RAM whatever the grid size. `plateau.py` on the int32 stats prints the same report as on the float64 stats (3 grids
checked line by line). It reads the chunks one column at a time and keeps the full-size arrays only for what the
neighbour search needs: a 46 M-pass grid (Intraday Dual Both Fixed TP size) takes about 1 min and 7.2 GB (25 GB before).

**`step1.py`** tested on US30 Session Rstep v3 (3,341,520 passes): stopped after 4 min, rerun with the same command, it
continued after the last finished chunk; 400 random passes recomputed from scratch equal the stored rows exactly. The
plateau check took 3 s, and the three small outputs (`plateau.txt`, `regions.jsonl`, `grid.json`) went to the output folder.

**Speeds** (stats-only, M4 Max, 16 threads, US30; passes inside a chunk are shuffled so all threads get equal work, +40%):

| grid | passes | speed |
|---|---|---|
| Session Rstep v3 (all, through step1.py) | 3,341,520 | 12.9 M passes/h (16 min) |
| Weekly Rstep (all, grid of 17:43) | 642,600 | 8.8 M passes/h |
| Intraday Dual Both Fixed TP, every 20th pass | 2,296,350 | 11.9 M passes/h (m5 10.5 … m30 13.9) → full 45.9 M grid 3.8 h |

So per symbol with today's grids: Session 25.9 M ≈ 2 h, Weekly 13.4 M ≈ 1.5 h, Intraday Dual 112 M ≈ 9.4 h, about 13 h for
all three modes; **1.25 billion passes ≈ 105–110 h** (not 71 h: the 17.6 M/h was a Session Fixed TP grid; Weekly holds
positions longer, and the per-pass cost is the minutes spent in a position).

**FX (EURGBP, export of 21 Oct 18:15 with "precise profit calculation" on, like the maps).** RULES A15–A17: volume sized
on the GBPUSD ask, P&L and swap converted on the bid, commission at the close with EUR→USD truncated to 2 decimals, swap
−0.59 / +0.02 pips at 21:30 UTC (the maps' run days). Against the v2 maps:

| referee | passes | same trades | identical to the cent | net difference per pass |
|---|---|---|---|---|
| EURGBP Session map | 2,950 | 2,947 (99.9%) | 744 (25.2%) | median $0.10, 95% $0.51, 99% $1.58 |
| EURGBP Weekly map | 670 | 670 (100%) | 224 (33.4%) | median $0.07, 95% $0.90, 99% $2.10; 4 passes ≈ $2,450 (A17) |

Trade by trade, 98.7% of 109,572 trades (400 Session passes) are identical to the cent. Nearly all the rest is the
commission of stops filled inside a minute: cTrader converts EUR at EURUSD inside that minute, truncated to whole cents of
rate, and the export has no EURUSD. That is a few cents per affected trade, so **the 99%-identical-pass rule cannot hold for
FX crosses** with this data, while the trades themselves match. Options: judge FX referees on identical trades plus a small
net tolerance per pass, or add the base currency's USD pair to the export and test whether its minute data closes the gap.

The US30 export was redone on 21 Oct 18:23 (same minute data, swap now −140.28 / −18.23 pips): the US30 referees are still
99.93% / 99.89% / 99.95% with the archives' own swap (`--swap fit`, the default); step-1 runs use the export's (today's) rate.

## Step 4 (2026-10-21 evening): hedging × Track Touches check grid, referees on all v2 maps

**Check grid `optimisation/_referee/US30_hedge_track`** (144 passes, run 21 Oct 19:06): 116 identical (80.6%). Three causes:
- **9 passes: cTrader crashed the cBot at one entry** ("Subscription already exist", RULES A18): the entry is skipped.
  That is cTrader's fault, not the strategy's; those passes are not a fair referee.
- **86 passes lose ≥ 90% of the account** (no pass is profitable: stop 2 / 4 ATR with narrow bands, my grid design, a poor one); their
  last trades depend on stop-out details. Strategy-wise irrelevant.
- **One market moment, 23 Feb 2022 05:43 UTC** (RULES A14): a VWAP-trail stop on a buy touched exactly; cTrader filled it a
  minute later. It costs 8 Intraday Dual VWAP-trail passes; the cause is still open.

| mode | all passes | without crashed or ≥ 90%-loss passes |
|---|---|---|
| Weekly | 45 / 48 (93.8%) | 13 / 13 (100%) |
| Session | 42 / 48 (87.5%) | 24 / 24 (100%) |
| Intraday Dual | 29 / 48 (60.4%) | 13 / 18 (72.2%): the 5 misses are the 05:43 moment |
| all | 116 / 144 (80.6%) | 50 / 55 (90.9%) |

Hedging on: 26 / 28 of those passes identical, with ~9,900 trades opened while an opposite position was open; Track
Touches on: 24 / 27. So both switches are replayed right; the misses are the one moment above.
Lesson for check grids: cTrader silently ignores an optset without the UTF-8 BOM or without min/max/step on fixed numeric
parameters (it then runs the instance's old settings). Build optsets from a cTrader-exported optset (`make_cbotset.py`,
`build_fine_grid.py` style), and keep stops wide enough that few passes lose the account.

## Step 5 (2026-10-21 late): A19, the PROTOCOL v3 referee rule, all 65 maps re-run

- **A19** (stop tighter than / equal to the spread) is in the engine: XAGUSD Session map 90.6% → 97.2% identical.
- `fullgrid.py` prints the **referee rule** (same trade list + net within $1, passes losing ≥ 90% or crashed left out,
  `--logs <raw export>` for crashes). **21 of 64 maps reach ≥ 99%** (EURAUD Session 00_map not counted: box OFF); the check
  grid 50 / 55 (90.9%). Table and causes: `REFEREES.md`.
- Misses are spread over many moments on 5-digit FX and gold (a rule gap, not data): moved stops touched exactly that
  cTrader fills a minute later (A14). Every "strict" variant tested is far worse, so it is not plain strictness; cTrader's
  log shows the stop value equal to the replica's. Open; the two data-test grids (`_referee/US2000_data_test`,
  `_referee/USDJPY_W_data_test`) and their logs are the next evidence. Crosses: commission cents (A16), nets beyond $1 in
  many-trade passes.

## Step 6 (2026-10-21 night): A20 stop truncation, cross commissions from the base pair → 58 of 64 maps ≥ 99%

- **A20:** cTrader stores a modified stop truncated to the symbol's digits (floor(price × 10^digits)); a stop whose double
  lies just below its decimal ends one tick lower. That was the whole "moved stop, exact touch" gap: EURUSD Weekly
  88% → 100%, NZDUSD Weekly 58% → 99.3%, USDCAD Weekly 74% → 100%, US30 / US2000 Weekly 100%, check grid 55 / 55.
- **Cross commissions** now use the bid of the base currency's own USD pair from its export (EURUSD for EURGBP …):
  GBPCAD Weekly 97.1% → 99.8%.
- **58 of 64 maps ≥ 99%** under the PROTOCOL v3 rule (EURAUD Session 00_map not counted, box OFF); the six below are
  commission / swap cents on NZDCHF / AUDNZD and one skipped entry per pass on the metals Weekly maps (likely A18).
  Fresh-day check grids: US2000 Weekly at spread 9, 108 / 108; USDJPY Weekly at spread 9, 114 / 114. Table: `REFEREES.md`.
- `fullgrid.py --spread / --commission` replays a referee that ran with other costs than the export.

## Step 7 (2026-10-22): A17 stop first, 59 of 64 maps, clean speeds, the step-1 queue

- **A17 (the NZDCHF $5,424 passes):** when one minute bar reaches both the stop and the target, cTrader fills the **stop**,
  for buys and sells (21 of 21 such exits across six symbols). The replica took the high first, which agrees for sells only, so
  NZDCHF fresh passes 3 / 27 / 51 / 75 (a buy on 7 May 2019 04:31 UTC = 06:31 TC whose minute reached both) were $5,424 off.
  Not a NZDCHF issue: the rule is general, the engine now uses stop first everywhere, and every referee was re-run.
- **Re-run of every map (ref6): 59 of 64 maps ≥ 99%** under the rule (`REFEREES.md`); below: AUDNZD S / NZDCHF S run2 / NZDCHF W
  (commission cents, cells out of Python) and XAUUSD / XAGUSD Weekly (one entry cTrader skipped; their fresh check grids: 100%).
- **Speeds, measured clean** (stats-only through `run_grid.run_stats`' chunk path, M4 Max 16 threads, nothing else running;
  a 1/N slice of each grid, Python chunk building included):

| grid (symbol) | slice | M passes/h | trades per pass |
|---|---|---|---|
| Weekly Rstep (EURGBP) | 1/5 | 8.1 (m15 10.1 … h4 6.9) | 118–274 |
| Weekly Fixed TP (EURGBP) | 1/20 | 7.2 | |
| Weekly Fixed TP (US500) | 1/20 | 9.2 | 116–165 (h2–h4) |
| Session Fixed TP (EURGBP) | 1/40 | 11.3 | |
| Session Fixed TP (US500) | 1/40 | 14.5 | |
| Session Fixed TP (XAUUSD) | 1/40 | 12.2 | |
| Intraday Dual Both Fixed TP (US500) | 1/100 | 13.0 | 407–529 |
| Intraday Dual Both VWAP trail (US500) | 1/100 | 20.2 | |
| (step 3) Session Rstep (US30, whole grid via step1.py) | all | 12.9 | |

  **All 53 cells ≈ 124 h ≈ 5.2 days** of continuous running (1.405 billion passes; families not measured at the slowest rate of
  their mode / symbol type): Go A 10 cells 24 h, Go B 7 cells 24.5 h (three Intraday Dual cells ≈ 7.5 h each), Go C 9 cells
  19 h, Park 27 cells 57 h. Per cell: Session 1.8 h (index) – 2.3 h (FX), Weekly 1.5–1.8 h, Intraday Dual 7.5 h. Disk: ~37
  bytes per pass → ~52 GB in `~/fastbt-runs` (469 GB free on 22 Oct).
- **Step-1 tests on the new modes / symbol types:** EURGBP Weekly Rstep (1.72 M passes, 28 min under contention; FX
  conversion + cross commission path) and US500 Intraday Dual RTH Rstep (0.6 M passes, 4 min) ran end to end through
  `step1.py` (stats → plateau → regions); EURGBP's stats checked row by row against single-pass replays.
- **Step-1 analysis chain** (`step1_analysis.py`), tested on the US30 Session Rstep test grid (65 regions) and a small US30
  Session Fixed TP grid (14,112 passes, 6 regions): region trade lists via `run_grid --passes`, TP-capped for Fixed TP, then
  `structural_check.py`, `timeprofile.py` and the per-region read (long / short, first 6 h after the reset or Sun + Mon,
  strongest hour / weekday, best year, COVID, flags). Archive nets = stats nets to the cent (Fixed TP capped on both sides).
  The US30 Rstep test stats (21 Oct 18:31) are **$1–89 off** the current engine in 65 of 65 regions: they predate A17 / A19 /
  A20, so they are stale — which is why every stats run now records an **engine fingerprint** (`run_grid.engine_hash()`,
  engine.py + data.py) in progress.json / grid.json: a run refuses to resume across an engine change, and
  `step1_analysis.py` warns when a grid's stats come from another engine. Rule: after any engine change, step-1 outputs made
  before it are re-run, not reused.
- **Queue and summary:** `step1_batch.py` runs step 1 over every cell of INSTANCES table C in the order Go A → Go B → Go C →
  Park (cells marked out of Python skipped), resumable, Mac kept awake, one log; `step1_summary.py` reads the outputs and
  writes the step-1 verdict per cell (yes / yes (near) / park / not finished) as a table-C markdown table.

## Step 8 (2026-10-22): steps 2, 3, 4 and 6 in Python, tested end to end

Test root `~/fastbt-runs/_v3test` (fresh step-1 R-step grids on the committed engine, nothing in `optimisation/`): US30 Session
(index) and EURGBP Weekly (FX), every step from the step-1 regions to the candidate list; Fixed TP / break-even on a small
US30 Session Fixed TP grid; step 6 on the archived v2 tick checks of US2000 Session.

| step | US30 Session R-step | EURGBP Weekly R-step |
|---|---|---|
| 1 full grid | 3.34 M passes, 17 min; 634 sets qualify in both halves; 64 regions | 1.72 M passes, 15 min; 280 sets; 27 regions |
| 1 analysis | archive = stats to the cent; flags: concentration 34 (15:00 TC, the US cash open) | 27 regions, no flag (Sun + Mon 38%) |
| 2 fine grids | 64 grids, 158,000 passes, 2 min; hedging / Track Touches pass on none | 27 grids, 60,500 passes, 1 min; none pass |
| 3 filters | 256 grids, 3 min; distance (E) kept on 23 of 64 cores, nothing else | 108 grids, 1 min; ATR percentile (D) kept on 3 → penetration (C) run on those 3 |
| 4 candidates | **1**: US30_S_RS3_B3.75_S8 (PF 1.63, 4.1 tr/mo, DD 4.4 / 4.7%, ×1.5 spread PF 1.62, shift −1 h 1.37 / +1 h 1.21, flag: 70% of net at 15:00 TC); 52 cores fail the rules (best year > 40–45%, < 100 trades with the filter), 11 not distinct | **2**: EURGBP_W_RS1_B2_S7.5 (PF 1.44) and EURGBP_W_RS2_B3_S7.75 (near-miss, H1 half); 25 not distinct; both N6 versions fail on their own (news closes cost PF 0.15–0.35) |

Fixed TP (small US30 grid, 6 regions): break-even 0.5 / 1.0 / 1.5 R never passes (0.5 R: dPF −0.05 … −0.15); 1 candidate,
the others not distinct (66–100% shared trades). The candidate's `params/<name>.json` → `step5_check.py make` → `.cbotset`;
the replica on the .cbotset's values (71 settings at the cBot's defaults) gives the same 294 trades to the cent.
Step 6 on US2000 Session v2 tick checks: R-step pass 1694 tick / m1 106%, 158 of 160 trades matched, PASS; Fixed TP pass 1358
103%, 157 / 159, PASS (the old `tools/tick_compare.py` gives the same numbers).

Fixed on the way: `paired.py` read the stored gross loss with the wrong sign (every comparison looked "0% better"); fine grids
lost one-value settings of the full grid (Management 0, Force Close 1 → would have run on the cBot default); merging
overlapping regions into one fine grid grew to 816k passes (a second broad grid) → one compact grid per region;
`step5_check make` failed on enums with explicit numbers (RestartPolicy) for parameter files that leave settings at defaults;
`step1.py --list` created an empty run folder.

New in `run_grid.py`: filter axes `@News / @ATR / @Dist / @Pen` ("off" or "label:Param=value;…") and `BreakEven` (off or the
trigger), so a filter's off state runs once; `--spread / --commission` and `override_costs()` (cost stress; fullgrid uses it);
spread and commission are part of a stats run's state (a run never resumes at other costs).

## What was built (all in `tools/fastbt/`)

| file | what it does |
|---|---|
| `RULES.md` | every rule that decides trades and P&L: the cBot's rules with line numbers, plus what cTrader's backtest engine does on its own (found here) |
| `FastBtExport.cs` + `EXPORT-HOWTO.md` | a cBot that never trades; one normal cTrader backtest per symbol records every tick, the m1 and chart bars with tick volume, and the symbol specs. US30 ran once: 99 MB in `~/cAlgo/Exports/fastbt/US30_m5_20180101/` |
| `data.py` | reads an export (cached as `.npz` next to it, outside iCloud) |
| `engine.py` | the replica (numba): all three VWAP modes, all 7 management types, filters, news, cTrader's fill, swap and stop-out rules; per-pass statistics; many passes in parallel |
| `compare.py` | replays archived passes and compares them trade for trade |
| `fullgrid.py` | runs a whole archived grid, fits its swap rate and rollover time, compares every pass and times it |
| `run_grid.py` | runs a grid from a `settings.optset` or a JSON grid: `--stats` = one row of statistics per pass (millions of passes; compact, compressed, resumable), `--passes` = trade lists for chosen passes in the archive format (the existing tools read them) |
| `plateau.py` | `split_plateau.py` on a `--stats` run: same rules, same report; `--regions` writes the listed distinct regions |
| `step1.py` | PROTOCOL v3 step 1 for one symbol × mode: all its v3 grids, stats-only, then `plateau.py`; resumable, progress + time left in a log |
| `step1_batch.py` | step 1 for every cell of INSTANCES table C (Go A → B → C → Park, out-of-Python cells skipped), one cell after the other through `step1.py`; resumable, caffeinate, one log (`~/fastbt-runs/step1_batch.log`), `--list` = queue, done, hours left |
| `step1_summary.py` | the step-1 verdict per cell from the plateau outputs (regions passing full period + both halves: yes / yes (near) / park), as a table-C markdown table |
| `step1_analysis.py` | step 1's structural part on the regions that passed: trade lists (`run_grid --passes`, TP-capped for Fixed TP), `structural_check.py`, `timeprofile.py`, and per region long vs short (beta read), young-band / Monday share, strongest hour / weekday, best year, COVID, flags |
| `step2_fine.py` | step 2: a fine grid per region (half steps, block windows in 30-min / 1-h steps, break-even, hedging × Track Touches), `--run` through step1's runner, `--report` = paired switch verdicts |
| `paired.py` | the compare_filter / filter_check rule on a stats run: each value of one axis against its baseline on every core |
| `step3_filters.py` | step 3: per step-2 core (switches decided by the paired rule) one small grid per filter — A Block Last, B news Off / N12 6/6/6 / 5/10/5, D ATR percentile, E distance, C penetration (only after D or E passes) — × a wide band range × stop / TP neighbours; verdicts, per-band table, `cores.jsonl` |
| `step4_candidates.py` | step 4: every core as Noff and N6 (3/3/3) through the v2 rules (plateau, set, halves, years, Monday) with the near-miss tolerance, flags (COVID, concentration, beta, cost stress spread × 1.5, time shift ±1 h), distinctness (≤ 50% shared trades, daily P&L corr ≤ 0.5), max 4 per family, short-code names, `params/<name>.json` for step 5 |
| `step6_tick.py` | step 6: cTrader tick in-sample report(s) (Bar Close and / or Tick timing) against the candidate's Python m1 trade list: matched trades, fills vs missing entries, the tick rule (PF ≥ 1.25, net ≥ 75% of m1) and the timing rule |
| `names.py` | PROTOCOL short codes (`<SYM>_<Mode>_<Mgmt>_B<band>_S<stop>`) and compact setting labels |
| `step5_check.py` | PROTOCOL v3 step 5 (m1 check): `make` writes a candidate's `.cbotset` (+ README with the run settings) from its parameter dict; `compare` replays it and compares trade for trade with cTrader's backtest report under the referee rule (PASS / MISMATCH, first differences in UTC and TC, A18 crash lines, both sets of stats); `compare-archive` does the same against an archived grid pass |

Python lives in `~/.venvs/fastbt` (numpy 2.0, numba 0.60, pandas), outside iCloud.

## What cTrader's m1-bar backtest really does (the surprises)

The archive alone could not show these; the export plus the archive pinned them down:

1. **One price per minute for the cBot.** With "m1 bars from server" the cBot sees exactly one tick per m1 bar: its
   **open** price, at the start of the minute. Highs, lows and closes never reach `OnTick` / `OnBarClosed`.
2. **But stops and targets also see each minute's high and low** and fill **at that high or low**, not at the level, timed
   at the start of the next minute. Example: a sell stop at 25,509.57; the 17:29 bar's high of 25,511.5 (+0.9 spread) fills it
   at 25,512.4, timed 17:30 (23:30 Amsterdam). This is why targets fill beyond the target (`tp_cap.py`) and stops average −1.07 R.
3. **Stop and target prices** are placed around the *unrounded* fill (bid + 0.9). This matters only when a high or low
   touches a level exactly. It reproduces the archived stop distance to the last binary digit on all 16,346 trades checked.
4. **Swap** −13.94 $/lot/night long, −1.72 short, triple on Friday. It is charged at the rollover at 21:00 UTC (23:00 Amsterdam
   in summer, 22:00 in winter), but only when the next price arrives, and **at most one rollover per price**. So:
   - a trade stopped out at the 22:00 UTC reopen pays no swap for that night;
   - after a holiday, the second missed night is charged a minute later;
   - passes that trade very rarely catch up on old rollovers first.
5. **No margin check, but the backtest ends when equity hits zero** (a "Stop Out"). That last trade is missing from the
   archive because `build_archive.py` keeps only SL / TP / Position closed events. Three wiped-out passes now match exactly.
6. **Today's broker trading hours are used for every historical day** (US30: 23:00 → 21:59 UTC). Because of that the
   cBot's safety net closes positions at 16:49 NY (22:49 Amsterdam) in winter instead of 16:50. The export records this per
   price, so it is replayed exactly. But it means cTrader's own results can move a little when the broker changes its
   schedule (clock-change weeks): **run the export under the same schedule as the grids you compare with.**
7. Chart bars are the server's m5/m10 bars with real tick volume. ATR is the standard Wilder ATR (all 41,058 archived stop
   distances match). VWAP math in double precision matches bit for bit.

## What doesn't match yet, and why (Fixed TP 16 of 22,400 passes; R-step 19 of 16,800)

| group | passes | effect | cause |
|---|---|---|---|
| one entry taken or skipped differently (Fixed TP 826–838: 2021 and 2023, two on the 08:30 NY CPI bar) | ~10 | one trade missing or extra, later trades shift; \|Δnet\| up to $3k | not found; news filter is off, bars, bands and arm state check out |
| one extra trade in the replica that cTrader never opened, everything else identical (e.g. Fixed TP 8335 on 3 Jul 2020, R-step 793 on 8 Mar 2023, 8444 on 16 Jun 2020) | ~15 | net differs by exactly that trade | not found; normal size, no margin issue |
| R-step passes that lose the account (band 3, holding overnight) | ~10 | the last trades before the account hits zero | stop-out timing on the last trades |
| swap on 3 Jul 2020 | 2 | one trade's swap | rollover counter edge case |

None of these change which parameter areas look good: the plateau reports are the same.

## Plan and effort for the rest

Each step is checked the same way: replay the existing archive and require ≥ 99% identical passes.

| step | what | effort | checked against |
|---|---|---|---|
| 1 | **Rstep** (Management 1–4): stop moves at bar close, plus close at market if the new stop is already beaten — **done 2026-10-21, 99.89%** | ½ day | `US30/Session/02_fullgrid_Rstep` (16,800 passes) |
| 2 | **VWAP trail** (5, 6): band stages, cushion, the dynamic variant — **done 2026-10-21** (maps) | 1 day | the v2 maps |
| 3 | **Weekly** and **IntradayDual** modes: their resets, schedules and force closes — **done 2026-10-21** | 1–1½ days | US30 ID full grid 99.95%, maps |
| 4 | **Other symbols**: one export each (~2 min cTrader run). For FX: commission ($30 per million), P&L conversion for non-USD quote currencies — **built 2026-10-21 on EURGBP** (trades 98.7% to the cent; passes off by cents, see Step 3); USDJPY (inverted pair) and percentage swaps still to check | 1–2 days | each symbol's archive |
| 5 | **Fine-grid options**: break-even and news filter **done**; hedging × Track Touches implemented, waiting for the check grid `optimisation/_referee/US30_hedge_track` | 1 day | fine-grid archives, maps |
| 6 | Stats-only mode for broad grids — **done 2026-10-21**; trade lists only for chosen passes (`run_grid.py --passes`) | ½ day | split_plateau reports |

**The effort column is Claude's build-and-check time, not computer time** (running a grid takes seconds to minutes). Each piece
is: write the rule, replay its cTrader archive, find out why passes differ, repeat until ≥ 99% match. Step 1 took about
3 hours, most of it finding the swap rule. The v2 maps (`<SYMBOL>/<Mode>/00_map`, cTrader m1 2018–2023, same cBot version
since 2026-10-14) vary all management types, modes, timeframes, entry filters and the news filter on every symbol, so they
serve as referees for most pieces once each symbol has an export.
The same engine design (export the ticks → replay with cTrader's fill rules) carries over to ORB and momentum later. Only
the strategy logic changes; the fill, swap and stop-out rules stay.

## How to use it

```
~/.venvs/fastbt/bin/python tools/fastbt/compare.py  ~/cAlgo/Exports/fastbt/US30_m5_20180101 optimisation/US30/Session/02_fullgrid_FixedTP --sample 20
~/.venvs/fastbt/bin/python tools/fastbt/fullgrid.py ~/cAlgo/Exports/fastbt/US30_m5_20180101 optimisation/US30/Session/02_fullgrid_FixedTP
~/.venvs/fastbt/bin/python tools/fastbt/step1.py US30 Session --list
caffeinate -i nohup ~/.venvs/fastbt/bin/python tools/fastbt/step1.py US30 Session > /dev/null 2>&1 &
~/.venvs/fastbt/bin/python tools/fastbt/run_grid.py ~/cAlgo/Exports/fastbt/US30_m5_20180101 <grid.json or settings.optset> <new folder> --stats
~/.venvs/fastbt/bin/python tools/fastbt/plateau.py <that folder> --diagnose --regions regions.jsonl [--dump all_qualifying.jsonl]
~/.venvs/fastbt/bin/python tools/fastbt/run_grid.py ~/cAlgo/Exports/fastbt/US30_m5_20180101 <stats folder>/grid.json <another new folder> --passes 123,4567
```
Step 1 for all cells, then the verdict and the structural read per cell:
```
~/.venvs/fastbt/bin/python tools/fastbt/step1_batch.py --list
nohup ~/.venvs/fastbt/bin/python tools/fastbt/step1_batch.py > /dev/null 2>&1 &        (log: ~/fastbt-runs/step1_batch.log)
~/.venvs/fastbt/bin/python tools/fastbt/step1_summary.py [--md table_c.md]
~/.venvs/fastbt/bin/python tools/fastbt/step1_analysis.py <SYMBOL> <Mode>               (-> step1_analysis.txt, regions_check.jsonl)
```
Step 2 (fine grids per region; build, run, paired switch verdicts):
```
~/.venvs/fastbt/bin/python tools/fastbt/step2_fine.py <SYMBOL> <Mode> [--skip-flags Monday] [--list]
~/.venvs/fastbt/bin/python tools/fastbt/step2_fine.py <SYMBOL> <Mode> --run
~/.venvs/fastbt/bin/python tools/fastbt/step2_fine.py <SYMBOL> <Mode> --report
```
Steps 3, 4 and 6:
```
~/.venvs/fastbt/bin/python tools/fastbt/step3_filters.py <SYMBOL> <Mode>            (build; then --run, then --report)
~/.venvs/fastbt/bin/python tools/fastbt/step4_candidates.py <SYMBOL> <Mode> [--stress 1.5]
~/.venvs/fastbt/bin/python tools/fastbt/step6_tick.py <SYMBOL> optimisation/<SYM>/<Mode>/v3_05_candidates/params/<code>.json --bc <tick BC report.html> [--tt <tick TT report.html>]
```
`run_grid.py --spread PIPS --commission X` runs a grid at other costs than the export's (recorded in grid.json; `run_grid.override_costs`).
Step 5 (m1 check of a candidate; params.json = its full parameter dict, archive strings, e.g. `run_grid.pass_values` + overrides):
```
~/.venvs/fastbt/bin/python tools/fastbt/step5_check.py make <SYMBOL> params.json <folder>/<name>.cbotset
~/.venvs/fastbt/bin/python tools/fastbt/step5_check.py compare <SYMBOL> params.json <folder>/report.html --log <folder>/log.txt
```
The swap rate and rollover time of the run day are fitted from the report's own swaps. Tested 21 Oct: US30 Session full-grid pass
100 vs its archive PASS (1,134 trades to the cent), pass 828 MISMATCH (one extra replica trade, shown); NZDCHF fresh-grid passes 3 and 7
vs cTrader's report.html PASS to the cent; the written .cbotset equals cTrader's own parameters.cbotset string for string (apart from
three values of switched-off filters, which take the cBot default).
`step1.py <SYMBOL> <Mode>` is PROTOCOL v3 step 1 in one command: every `optimisation/_v3_grids/<Mode>*` grid, stats-only,
into `~/fastbt-runs/<SYMBOL>/<Mode>/v3_02_fullgrid_<Family>[_<source>]/`, then `plateau.py`; only the small outputs
(`plateau.txt`, `regions.jsonl`, `grid.json`) go to `optimisation/<SYMBOL>/<Mode>/<same folder>/`. Resumable at any point
(rerun the same command), log with progress and time left in `~/fastbt-runs/<SYMBOL>/<Mode>/step1.log`.
A JSON grid is `{"fixed": {param: value}, "axes": {param: [values]}}` with the cBot's parameter names (plus `Timeframe`);
a stats run's own `grid.json` works too (use it for `--passes`, so the pass ids are those of that run even if the grid
file changed since). Stats are stored compressed per chunk of 500,000 passes: keep runs outside iCloud (`~/fastbt-runs/`).
`run_grid.py` refuses settings it does not support yet (day block windows, Tick timing, other VWAP sources; for non-USD quotes an export without conversion prices; percentage swaps, other commission types). Always write to a new folder,
never over a cTrader archive.
