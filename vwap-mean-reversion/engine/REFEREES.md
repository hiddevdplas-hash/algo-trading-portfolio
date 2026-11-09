# Replica vs every v2 map and the check grids (re-run 2026-10-21/22, engine with RULES A15–A20, stop first A17)

**Rule (PROTOCOL v3):** a pass matches when its trade list is the same as cTrader's (entries, exits, direction, volume) and
its net is within $1. Passes that lose ≥ 90% of the account and passes where cTrader crashed the cBot (RULES A18, read
from the raw export's logs; the maps have no logs left, so only the check grids are checked for crashes) are left out, and
the number left out is shown. Bar: ≥ 99% per map. Swap rate and rollover time are fitted from each archive
(`fullgrid.py` default); box = cTrader's "download historical data for additional symbols" (non-USD quotes).
Other columns: identical = same trade count and net to the cent; within $1 = same trade count and net within $1 (all
passes); same trade list = share of all passes with the same trades.

Reproduce: `~/.venvs/fastbt/bin/python tools/fastbt/fullgrid.py <export> optimisation/<SYM>/<Mode>/<map>` (prints a RULE line;
`--spread` / `--commission` when the referee ran with other values than the export, `--logs <raw export>` for crashes).

**Result: 59 of 64 maps at ≥ 99%** (EURAUD Session 00_map not counted: run with the box OFF). The 5 below 99%: AUDNZD
Session and NZDCHF Session run2 / Weekly (98.3–98.8%, cents of commission on the crosses; these cells are out of Python by
the user's decision) and XAUUSD / XAGUSD Weekly (98.9 / 98.3%, one entry cTrader skipped; their fresh check grids match 100%).

**Check grids (`optimisation/_referee/`):** all re-run on 21 Oct 21:24 (EURAUD_S_fresh 21:40), after the A17 stop-first change
(engine.py 21:17), and again on 22 Oct on the committed engine (c7fd76d, `run_grid.engine_hash()` 5112c0ebe312): every RULE
line identical. 22 Oct 08:30: A20 extended to the target re-sent at break-even (engine hash b1210a0638a5); no map or other
check grid has break-even passes, all check grids re-run: RULE lines unchanged (US30_hedge_track 55 of 58 without its
logs = the same 55 matches, its 3 crashed passes not identifiable without the trashed logs).

| grid | passes | match (rule) | left out | what it checks |
|---|---|---|---|---|
| US30_hedge_track | 144 | **55 of 55 (100%)** | 89 (86 lose ≥ 90%, 9 crashed, some both) | hedging × Track Touches; 130 / 144 same trade list |
| US30_W_fresh | 108 | **108 of 108 (100%)** | 0 | ran on **US2000** at spread 9 (log), compared as such; 14 Jun 2021 12:22 = A20 |
| US2000_data_test | 108 | **108 of 108 (100%)** | 0 | data vs rule: 0 of 108 without A20 → the moment is a rule |
| USDJPY_W_data_test | 144 | **144 of 144 (100%)** | 0 | data vs rule: 84 of 144 without A20 |
| USDJPY_W_spread9 | 144 | **114 of 114 (100%)** | 30 | spread 9, commission 0; 143 / 144 same trade list |
| XAUUSD_W_fresh | 72 | **72 of 72 (100%)** | 0 | the Weekly cell below 99% on its map |
| XAGUSD_W_fresh | 96 | **71 of 71 (100%)** | 25 | the Weekly cell below 99% on its map |
| EURAUD_S_fresh | 96 | **81 of 81 (100%)** | 15 | Session referee with the box ON (the map had it OFF); max net difference $0.70 |
| EURUSD_edge | 96 | **94 of 94 (100%)** | 2 | far ends of the v3 ranges (stop 8, TP 4, Session band 2 + Block First 18 h, Weekly blocks 24 h), break-even on FX, hedging × Track Touches outside US30; 96 / 96 same trade list; before the A20 target fix 90 / 94 |
| NZDCHF_SW_fresh | 96 | 73 of 86 (84.9%) | 10 | cross commission cents (A16); cells out of Python |
| AUDNZD_S_fresh | 96 | 50 of 66 (75.8%) | 30 | cross commission cents (A16); cell out of Python |

## Every v2 map
| map | match % (rule) | left out | identical | within $1 | same trade list | passes | swap L / S (pips) | rollover UTC | box | below 99%: main cause |
|---|---|---|---|---|---|---|---|---|---|---|
| AUDJPY/Session/00_map | **99.72%** | 33 | 55.10% | 99.5% | 100.0% | 2,570 | 0.81 / -1.31 | 21:30 | ON |  |
| AUDJPY/Weekly/00_map | **99.28%** | 63 | 66.56% | 99.2% | 100.0% | 2,285 | 0.81 / -1.31 | 21:30 | ON |  |
| AUDNZD/Session/00_map | **98.84%** | 64 | 77.11% | 97.1% | 99.9% | 1,525 | 0.38 / -0.92 | 21:30 | ON | same trades, nets just over $1 apart in many-trade passes: commission / swap cents of the cross (A16); cell out of Python |
| AUDNZD/Weekly/00_map | **99.78%** | 67 | 37.94% | 98.8% | 99.9% | 2,380 | 0.38 / -0.92 | 21:30 | ON |  |
| AUDUSD/Session/00_map | **99.94%** | 22 | 82.32% | 99.9% | 100.0% | 1,810 | -0.22 / -0.48 | 21:30 | USD |  |
| AUDUSD/Weekly/00_map | **99.40%** | 35 | 59.32% | 99.4% | 99.4% | 2,190 | -0.22 / -0.48 | 21:30 | USD |  |
| DE40/Session/00_map | **100.00%** | 33 | 100.00% | 100.0% | 100.0% | 575 | -49.26 / -11.84 | 21:30 | ON |  |
| DE40/Session/00_map_run2 | **99.00%** | 47 | 98.95% | 99.0% | 99.0% | 1,050 | -49.26 / -11.84 | 21:30 | ON |  |
| DE40/Weekly/00_map | **100.00%** | 27 | 100.00% | 100.0% | 100.0% | 2,570 | -49.26 / -11.84 | 21:30 | ON |  |
| EURAUD/Session/00_map | **11.37%** | 25 | 10.11% | 11.2% | 98.1% | 1,335 | -1.355 / 0.53 | 21:00 | OFF | map run with the box OFF (P&L at one constant AUDUSD rate): not a referee |
| EURAUD/Weekly/00_map | **100.00%** | 16 | 54.78% | 100.0% | 100.0% | 575 | -1.29 / 0.56 | 21:30 | ON |  |
| EURAUD/Weekly/00_map_run2 | **99.95%** | 58 | 46.26% | 99.9% | 99.9% | 2,190 | -1.29 / 0.56 | 21:30 | ON |  |
| EURCHF/Session/00_map | **99.32%** | 67 | 69.67% | 98.2% | 99.8% | 2,285 | 0.36 / -1.08 | 21:30 | ON |  |
| EURCHF/Weekly/00_map | **99.55%** | 49 | 70.99% | 98.8% | 99.9% | 1,620 | 0.36 / -1.08 | 21:30 | ON |  |
| EURGBP/Session/00_map | **99.54%** | 102 | 28.44% | 98.5% | 99.9% | 2,950 | -0.59 / 0.02 | 21:30 | ON |  |
| EURGBP/Weekly/00_map | **99.84%** | 33 | 52.39% | 99.0% | 100.0% | 670 | -0.59 / 0.02 | 21:30 | ON |  |
| EURGBP/Weekly/00_map_run2 | **99.75%** | 50 | 50.24% | 99.1% | 100.0% | 1,240 | -0.59 / 0.03 | 21:00 | ON |  |
| EURJPY/Session/00_map | **100.00%** | 87 | 44.05% | 100.0% | 100.0% | 2,665 | 0.41 / -0.99 | 21:30 | ON |  |
| EURJPY/Weekly/00_map | **99.84%** | 64 | 69.59% | 99.9% | 99.9% | 1,335 | 0.41 / -0.99 | 21:30 | ON |  |
| EURNZD/Session/00_map | **99.88%** | 29 | 68.14% | 99.8% | 99.9% | 860 | -0.46 / -0.23 | 21:30 | ON |  |
| EURNZD/Session/00_map_run2 | **99.97%** | 51 | 66.17% | 99.8% | 99.9% | 3,045 | -0.46 / -0.23 | 21:30 | ON |  |
| EURNZD/Weekly/00_map | **99.90%** | 63 | 54.94% | 99.9% | 100.0% | 2,095 | -0.46 / -0.23 | 21:30 | ON |  |
| EURUSD/Session/00_map | **100.00%** | 44 | 77.65% | 100.0% | 100.0% | 765 | -0.8 / 0.13 | 21:30 | USD |  |
| EURUSD/Session/00_map_run2 | **99.46%** | 47 | 48.32% | 99.4% | 99.4% | 2,475 | -0.8 / 0.13 | 21:30 | USD |  |
| EURUSD/Weekly/00_map | **100.00%** | 48 | 50.04% | 100.0% | 100.0% | 2,570 | -0.8 / 0.13 | 21:30 | USD |  |
| GBPCAD/Session/00_map | **99.76%** | 92 | 19.13% | 98.9% | 99.9% | 2,190 | 0.27 / -1.38 | 21:30 | ON |  |
| GBPCAD/Weekly/00_map | **99.82%** | 46 | 21.22% | 99.4% | 100.0% | 1,715 | 0.27 / -1.38 | 21:30 | ON |  |
| GBPUSD/Session/00_map | **99.97%** | 89 | 84.54% | 100.0% | 100.0% | 3,235 | -0.48 / -0.32 | 21:30 | USD |  |
| GBPUSD/Weekly/00_map | **100.00%** | 21 | 66.38% | 100.0% | 100.0% | 1,145 | -0.48 / -0.32 | 21:30 | USD |  |
| JP225/Session/00_map | **99.32%** | 0 | 99.32% | 99.3% | 99.4% | 1,905 | -109.43 / -57.32 | 21:30 | ON |  |
| JP225/Weekly/00_map | **99.43%** | 1 | 99.43% | 99.4% | 99.5% | 2,475 | -109.43 / -57.32 | 21:30 | ON |  |
| NZDCHF/Session/00_map | **99.19%** | 25 | 66.54% | 98.6% | 100.0% | 765 | 0.2 / -0.57 | 21:30 | ON |  |
| NZDCHF/Session/00_map_run2 | **98.30%** | 23 | 66.27% | 96.9% | 99.9% | 670 | 0.21 / -0.56 | 21:00 | ON | same as AUDNZD Session; cell out of Python |
| NZDCHF/Weekly/00_map | **98.55%** | 31 | 48.14% | 97.6% | 100.0% | 860 | 0.2 / -0.57 | 21:30 | ON | same as AUDNZD Session; cell out of Python |
| NZDCHF/Weekly/00_map_run2 | **99.02%** | 54 | 35.89% | 98.4% | 100.0% | 2,095 | 0.21 / -0.56 | 21:00 | ON |  |
| NZDUSD/Session/00_map | **100.00%** | 25 | 81.75% | 100.0% | 100.0% | 1,430 | -0.4 / 0.01 | 21:30 | USD |  |
| NZDUSD/Weekly/00_map | **99.31%** | 26 | 60.62% | 99.3% | 99.3% | 1,620 | -0.4 / 0.01 | 21:30 | USD |  |
| UK100/Session/00_map | **100.00%** | 38 | 99.53% | 99.8% | 99.8% | 860 | -24.93 / -0.8 | 21:30 | ON |  |
| UK100/Session/00_map_run2 | **99.16%** | 50 | 99.03% | 99.2% | 99.2% | 1,240 | -24.93 / -0.8 | 21:30 | ON |  |
| UK100/Weekly/00_map | **99.52%** | 59 | 99.53% | 99.5% | 99.5% | 2,570 | -24.93 / -0.8 | 21:30 | ON |  |
| US2000/IntradayDual/00_map | **100.00%** | 16 | 100.00% | 100.0% | 100.0% | 1,145 | -6.65 / -0.08 | 21:30 | USD |  |
| US2000/Session/00_map | **100.00%** | 55 | 99.95% | 100.0% | 100.0% | 2,190 | -6.65 / -0.08 | 21:30 | USD |  |
| US2000/Weekly/00_map | **100.00%** | 46 | 100.00% | 100.0% | 100.0% | 1,620 | -6.65 / -0.08 | 21:30 | USD |  |
| US30/IntradayDual/00_map | **100.00%** | 7 | 100.00% | 100.0% | 100.0% | 1,810 | -121.99 / -1.54 | 21:30 | USD |  |
| US30/Session/00_map | **100.00%** | 44 | 100.00% | 100.0% | 100.0% | 2,285 | -121.99 / -1.54 | 21:30 | USD |  |
| US30/Weekly/00_map | **100.00%** | 32 | 99.95% | 100.0% | 100.0% | 2,190 | -121.99 / -1.54 | 21:30 | USD |  |
| US500/IntradayDual/00_map | **99.96%** | 28 | 94.97% | 99.9% | 100.0% | 2,665 | -18.5 / -0.23 | 21:30 | USD |  |
| US500/Session/00_map | **99.91%** | 75 | 94.98% | 99.9% | 99.9% | 3,425 | -18.5 / -0.23 | 21:30 | USD |  |
| US500/Weekly/00_map | **99.96%** | 48 | 47.04% | 99.9% | 99.9% | 2,570 | -18.5 / -0.23 | 21:30 | USD |  |
| USDCAD/Session/00_map | **100.00%** | 20 | 100.00% | 100.0% | 100.0% | 1,335 | 0.36 / -1.14 | 21:30 | ON |  |
| USDCAD/Weekly/00_map | **100.00%** | 21 | 99.85% | 100.0% | 100.0% | 1,335 | 0.36 / -1.14 | 21:30 | ON |  |
| USDCHF/Session/00_map | **100.00%** | 88 | 99.98% | 100.0% | 100.0% | 4,185 | 0.62 / -1.31 | 21:30 | ON |  |
| USDCHF/Weekly/00_map | **100.00%** | 46 | 100.00% | 100.0% | 100.0% | 1,145 | 0.62 / -1.31 | 21:30 | ON |  |
| USDJPY/Session/00_map | **100.00%** | 27 | 100.00% | 100.0% | 100.0% | 2,760 | 0.82 / -1.7 | 21:30 | ON |  |
| USDJPY/Weekly/00_map | **100.00%** | 20 | 99.71% | 99.9% | 99.9% | 1,050 | 0.82 / -1.7 | 21:30 | ON |  |
| USTEC/IntradayDual/00_map | **99.82%** | 32 | 98.77% | 99.8% | 100.0% | 2,285 | -73.25 / -0.93 | 21:30 | USD |  |
| USTEC/Session/00_map | **100.00%** | 24 | 99.48% | 99.8% | 99.7% | 575 | -73.25 / -0.93 | 21:30 | USD |  |
| USTEC/Session/00_map_run2 | **99.57%** | 61 | 99.19% | 99.6% | 99.6% | 2,855 | -73.25 / -0.93 | 21:30 | USD |  |
| USTEC/Weekly/00_map | **100.00%** | 27 | 91.91% | 100.0% | 100.0% | 1,335 | -73.25 / -0.93 | 21:30 | USD |  |
| XAGUSD/Session/00_map | **99.47%** | 129 | 97.56% | 99.5% | 99.5% | 2,380 | -0.82 / 0.57 | 21:30 | USD |  |
| XAGUSD/Weekly/00_map | **98.28%** | 81 | 69.11% | 98.2% | 98.3% | 955 | -0.82 / 0.57 | 21:30 | USD | one extra trade in the replica in 15 passes: cTrader skipped that entry (pattern of the A18 crash; maps keep no logs). Fresh grid: 100% |
| XAUUSD/Session/00_map | **99.88%** | 48 | 99.65% | 99.8% | 99.9% | 1,715 | -57.03 / 39.77 | 21:30 | USD |  |
| XAUUSD/Weekly/00_map | **98.93%** | 26 | 98.76% | 99.0% | 99.0% | 1,050 | -57.03 / 39.77 | 21:30 | USD | one extra trade in the replica in 11 passes, as XAGUSD Weekly. Fresh grid: 100% |
| XTIUSD/Session/00_map | **99.87%** | 61 | 96.30% | 99.7% | 99.7% | 2,380 | 12.95 / -21.25 | 21:30 | USD |  |
| XTIUSD/Weekly/00_map | **99.74%** | 79 | 37.44% | 99.7% | 99.8% | 3,520 | 12.95 / -21.25 | 21:30 | USD |  |

**59 of 64 maps at >= 99% under the rule** (EURAUD Session 00_map not counted: box OFF).
