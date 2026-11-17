# Referee comparison, 2026-11-12 (DESIGN §4.5 item 2): **PASS, 5 of 5 at ≥ 99%**

cTrader runs by the user (IC, tick data, ~15:15–15:22 Amsterdam), trade lists in `~/cAlgo/Exports/referees/`; engine run on the same
IC ticks (`tests/referees/referees.py`), compared trade for trade (`tests/referees/compare.py`: side, fill time, entry, exit time, exit
price ±0.1 tick, exit kind). Engine hash after the fix: `ca862f7f5425`.

| referee | symbol, chart | trades engine / cTrader | identical | before the fix |
|---|---|---|---|---|
| R1 EMA cross, stop-and-reverse | EURUSD m15 | 245 / 245 | **100%** | 97.14% |
| R2 Donchian stop order, target, 24 h exit | XAUUSD h1 | 151 / 151 | **99.34%** | 96.05% |
| R3 timed session 10:00 → 15:30 NY | US500 m5 | 85 / 85 | **100%** | 100% |
| R4 limit fade, 60 min expiry | XAUUSD m15 | 431 / 431 | **100%** | 97.45% |
| R5 SMA cross, ATR trail, Friday flat | EURUSD h1 | 97 / 97 | **100%** | 100% |

(The "+1" rows in R1, R3 and R4 were each file's `#summary` line, not trades. R5's last position was open at the end in both.)

## The one systematic difference, fixed in the kernel
cTrader stores a stop and target as **entry ± (distance / PipSize) × PipSize in raw double arithmetic** (e.g. 1.0740100000000001,
2024.1799999999998), not on the price grid. An exact touch of the grid value then does not fill in cTrader. That was all 23 mismatches
(R1 7, R4 11, R2 5, including R2's 11 Oct 2023 long whose stop at 1868.1899999999998 never filled at bid 1868.19, so cTrader time-exited
the next day and the following trade differed). The formula reproduces **959 of 959** stored stops and targets bit for bit
(entry ± distance: 958; grid-rounded, the engine's earlier guess: 723). Kernel option `digits` replaced by `pip_size` (the runner
always sets it, so research runs behave like the cBots too).

## The one mismatch left: explained by a loader rule
R2, 3 Dec 2023 23:20:44 UTC (gold's Sunday-open spike): cTrader filled the target at bid 2099.44 on a **crossed tick** (ask 2098.76,
0.68 below the bid); the loader drops crossings above one point (DESIGN §3.3 rule 1), so the engine filled on the next tick (2099.94).
By design: a crossed quote isn't a fill a firm would give.

## The three open questions in the run list
1. **Stop and target of a pending order filled at another price: set around the actual fill.** 120 R2 stop entries filled past their
   level, 347 R4 limits better than theirs; every stored stop / target = actual fill ± distance.
2. **Pending order price: stored as the intended grid level** (truncation or rounding of the ¼-tick send): 31 R2 and 84 R4 fills touched
   the level exactly, all identical in cTrader.
3. **A limit gapped through fills at the tick's price**, not the level: 347 R4 fills, all identical.

The cBots don't change, so the user does not need to re-run anything.
