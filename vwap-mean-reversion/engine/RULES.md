# What decides the trades and their P&L — VwapMeanReversionBot.cs in a cTrader m1-bar backtest

Step 1 of the fastbt study. Line numbers refer to `cTrader-Bots/VwapMeanReversionBot.cs`. "TC" = the cBot's trading
clock = New York time + 6 h (18:00 NY reopen = 00:00 TC, 17:00 NY close = 23:00 TC; Amsterdam time is usually the same as TC,
except in the weeks when US and EU daylight saving differ). Every rule below is implemented in `engine.py` unless marked *(later)*.

## A. cTrader backtest engine (not in the cBot; confirmed with the US30 export + archive, 2026-10-20)
1. **One tick per m1 bar.** "m1 bars from server" gives the cBot exactly one tick per m1 bar: the bar's **open**, at the bar's
   open time (2,095,538 ticks = 2,095,538 m1 bars, 100% equal to the m1 open). The cBot (OnBarClosed / OnTick) runs only there.
2. **But SL/TP also see the m1 high and low.** cTrader's order engine checks each m1 bar's high and low after its open and fills
   a stop or target that the high/low crosses **at that high/low price** (not at the level), stamped with the time of the next
   tick (normally the end of the minute; after a data gap the next tick's time). Example: sell stop 25,509.57, the 17:29 bar's high
   25,511.5 (+0.9 spread = ask 25,512.4) → "Stop Loss Hit" at 17:30 for 25,512.4. This is why TP fills beyond the target
   (`tools/tp_cap.py`) and SL fills average −1.07 R. Which of high/low is checked first matters only when both levels sit in one
   m1 bar: **the stop wins** (A17).
3. **Bid bars + fixed spread.** Bars are bid; ask = bid + 0.9 exactly in floating point (9 pips × pip size 0.1), every tick.
4. **Entry fill** = the tick that opens the next chart bar (buy at ask, sell at bid). OnBarClosed fires before OnTick there.
5. **SL/TP placement**: the distances are rounded to 0.1 pip (the tick size) and placed around the **unrounded** fill
   (bid + 0.9); only the reported entry price is rounded to 2 decimals. |entry − SL| equals the archive to the last bit on
   16,346 of 16,346 trades; this decides the rare cases where a high/low touches a level exactly.
6. **Sizing**: `VolumeForFixedRisk` already rounds down to the 0.1 step and caps at the maximum volume (250).
7. **P&L** = price move × volume ($1 per point per unit), rounded to cents half away from zero; commission 0 (FX: A15, A16).
8. **Swap** ("Pips" type, triple on the symbol's 3-day weekday): the **rate and the rollover time are the broker's settings on
   the day the backtest runs**, applied to all history, and both change over time. US30: −139.37 / −17.23 pips long/short and
   rollover **21:00 UTC** in the grids of 19–20 Oct 2026 and the export of 20 Oct; −121.99 / −1.54 pips and **21:30 UTC** in
   the v2 maps of 16–18 Oct. The Automate API shows the rate (export meta.json) but not the time, so referee comparisons fit
   both from the archive (`fullgrid.py --swap fit --roll fit`, the default). Rollover Monday–Friday, charged when a later tick
   arrives and **at most one rollover per tick**, each
   charge rounded to cents. A stop/target filled on that tick pays no swap for it; a force close by the cBot on that tick does.
   Two one-offs not modelled: a Sunday-evening FX rollover (EURGBP 5 Nov 2023 21:30 UTC, the US clock-change day) was
   charged once and not in 2 other Sunday cases; a cBot close exactly on the rollover tick (EURJPY 10 Nov 2022 21:30) paid no
   swap in cTrader while the US30 rule above charges it.
   After a holiday gap the second missed night is charged one tick later (archive: force-closed at the 06:00 UTC reopen on
   2 Jan 2019 = 1 night, closed at 07:22 = 2 nights). The rollover pointer **starts at the first rollover after the pass's
   first entry** and moves only on ticks that start with a position open. A pass that was flat for months therefore first
   works through old rollovers (no charge) and can miss a fresh one when the position closes at a gap (holiday early close,
   the winter 16:49 NY safety-net close). Fitted 2026-10-21 on all 2.94 M rollover-spanning trades of the US30 Session Fixed TP
   and Rstep grids (pass 11136, first trade Oct 2019: charged on 3 Jul 2020; pass 11159, first trade Feb 2018, few trades
   since: not charged). Starting the pointer at the backtest start instead was the 2026-10-20 model (99.42% / 95.8%).
9. **Broker trading hours** (`Symbol.MarketHours`) are today's schedule (US30: Sun–Fri 23:00 → 21:59 UTC, fixed in UTC), used
   for every historical day. In winter the market "closes" at 16:59 NY by that schedule, so the safety net closes positions at
   16:49 NY; in summer the 16:50 NY force-close window comes first. The export records time-to-close at every tick, so this is
   replayed exactly — but cTrader's own results shift if the broker changes the schedule (DST weeks): export and grids must
   run under the same schedule.
10. **Order of events when a tick arrives**: (1) SL/TP on the previous m1 bar's high/low, (2) SL/TP on this tick's price,
    (3) one pending swap charge, (4) the cBot: OnBarClosed (force closes, signals, entries), OnTick (force closes).
11. **Bars that already existed when the backtest started** are history: OnBarClosed never fires for the bar before them.
12. **No margin check, but a stop-out at zero equity.** cTrader keeps opening full-size trades on a nearly empty account
    (pass 11230: a $450k-notional trade with $131 left). Once equity (balance + open P&L **at a tick price**; the in-bar
    high/low does not count) reaches zero, the position is stopped out and the backtest ends; that "Stop Out" close is not in
    the archive (build_archive keeps SL/TP/Position closed only). A balance at or below zero after a normal close also ends it
    (pass 127: −$0.26). Counting the in-bar high/low too ended ~50 wiped-out Rstep passes one trade early.

13. **The backtest runs to the last price.** After the last chart bar that closes, open positions keep running on the
    remaining ticks (Weekly h4: the Friday 16:49 NY close of 29 Dec 2023 comes two hours after the last h4 bar close).
14. **Exact touches fill.** A stop or target whose price equals a minute's high/low or a tick price fills (≤ / ≥); making
    the test strict is much worse everywhere (21 Oct). The apparent exceptions (moved stops touched exactly that cTrader
    filled a minute later, or a minute earlier for sells) are A20: cTrader's modified stop is one tick lower than the
    cBot's value in those cases.
15. **Symbols not quoted in USD** (v2 maps vs the exports of 21 Oct, cTrader's "download historical data for additional
    symbols" box ON; the maps match ON: EURGBP volumes and gross 12,255 of 12,255 with historical GBPUSD, 3% with today's
    constant rate): the quote currency is converted at the conversion pair's price of the tick (the export records the pair's
    bid/ask at every tick; for JPY quotes the pair is USDJPY, inverted). **Sizing** (`VolumeForFixedRisk`) uses the **higher**
    of the two rates, **P&L and swap the lower** one: EURGBP (GBPUSD) ask / bid: volumes 19,488 of 19,488, gross 19,487 of
    19,488; USDJPY and EURJPY (JPY→USD = 1/USDJPY) 1/bid / 1/ask: EURJPY volumes 3,005 of 3,005, gross 3,004. The swap is
    charged at the rollover tick (99.8% of 73,720 EURGBP one-night long charges at 21:30 UTC, the maps' rollover time, as on
    US30's maps). **When the pair is the symbol itself** (USDJPY, USDCAD, USDCHF), a stop or target fill (in the bar or at
    the tick) converts at the symbol's **previous** tick: cTrader's order engine fills before the tick updates the symbol
    (USDJPY Weekly map: 100% of such fills, 1/ask at the tick only 10–25%); a close by the cBot converts at the tick (100%).
    With another pair (GBPUSD for EURGBP) every fill converts at the tick (in-bar fills 100%).
16. **Commission** ("USD per million USD volume", 30 for FX and metals, the symbol's broker setting; backtests use the value
    typed in the backtest settings, keep them equal): both sides are charged **at the close**, each side
    = vol × rate × 30 / 1,000,000 rounded to the cent, rate = base currency → USD **truncated to 2 decimals** (cTrader's
    AssetConverter truncates: the export's `convert` column = GBPUSD bid truncated on 99.997% of ticks). Which rate:
    - base is USD (USDJPY, USDCAD, USDCHF): 1.
    - the rate is the symbol's own price (EURUSD, GBPUSD, AUDUSD, NZDUSD, XAUUSD, XAGUSD): its **bid**, at the **previous
      tick for a stop/target fill** (the order engine fills before the tick updates the symbol, as in A15) and at the tick for
      a close by the cBot: XAUUSD 6,401 of 6,401 one-day trades, EURUSD 4,358 of 4,368.
    - a cross (EURGBP, EURJPY, AUDJPY …): the **bid of the base currency's own USD pair** (EURUSD for EURGBP, AUDUSD
      for AUDJPY, read from that symbol's export next to this one) at its last tick at or before the close: EURGBP 98.8%,
      AUDJPY 99.1%, GBPCAD 98.6%, NZDCHF 99.4%, EURCHF 98.8% of one-day trades (the cross estimate mid × quote→USD, used
      when that export is missing: 97.5–99.1%). The rest are stops filled inside a minute where that pair crossed a cent
      of rate within the minute: a few cents per affected trade, not replayable from minute data.
17. **Stop and target inside the same minute bar** (both touched by the high/low): cTrader fills the **stop**, for buys and
    sells: 21 of 21 such exits across US30, NZDCHF, EURGBP, EURUSD, XAUUSD and US500 referees (high-first: 6 of 21). The
    US30 fit of "high first" had only sells, where both rules agree. NZDCHF fresh grid passes 3 / 27 / 51 / 75 ($5,424 off:
    7 May 2019 04:31, a buy whose minute reached both) are this case.

18. **cTrader sometimes crashes the cBot at an entry** (optimisation runs): the log shows "Crashed in OnBarClosed with
    InvalidOperationException: Subscription already exist." at the bar close that should have entered, with no order line
    before it; that entry is skipped and the backtest goes on. Our cBot subscribes to nothing there, so it comes from inside
    the cTrader API on the way to the order (probably the volume sizing call). Check grid of 21 Oct: 9 of 144 passes, one crash
    each, all among passes 2–12 (the first batch the optimiser runs in parallel), on scattered 2020 dates. The replica does
    not reproduce it (it is not the strategy): referee comparisons leave out passes whose cTrader log shows a crash. The
    archives keep no logs, so older referees cannot be checked for it; `build_archive.py` should record crashes per pass.

19. **Stop tighter than the spread** (found 21 Oct on the XAGUSD map, spread 4 pips; in the engine since 21 Oct): a buy's stop
    ask − d with d < spread lies above the bid, so cTrader opens the trade without a stop and the cBot closes it at once
    ("entry protection missing": Position closed in the same minute, loss = spread × volume); with d = spread the stop is set
    and filled on the entry tick (38 of 96 trades of XAGUSD Session map pass 7). Both are replayed at entry: XAGUSD Session
    map 90.6% → 97.2% identical, US30 unchanged.

20. **cTrader truncates a modified stop to the symbol's digits** (found 21 Oct): the stored stop is floor(stop × 10^digits)
    / 10^digits in floating point. A stop whose double lies just below its decimal value loses one tick: 33,725.7 × 100 =
    3,372,569.9999999995 → 33,725.69; 128.784 → 128.783; 0.60852 → 0.60851. So a buy's stop touched exactly by the low
    does not fill, and a sell's stop is hit one tick early. It explains 2,515 of 2,542 exact-touch moved-stop buys on
    four FX maps (the stop as set: 2,252), cTrader's earlier sell fills at exactly the export's high + spread (NZDUSD:
    102 of 107), and the moments 23 Feb 2022 05:43 (US30), 14 Jun 2021 12:22 (US2000, a sell filled at 2,337.46 for a
    stop sent as 2,337.47), 5 May 2022 01:24 (USDJPY). Initial stops are placed from the raw fill (A5) and are not
    truncated. **The target re-sent with the break-even stop is truncated the same way** (found 22 Oct, EURUSD_edge check grid,
    the only archive with break-even passes): the cBot sends `position.TakeProfit` (reported at the symbol's digits, 1.18942)
    and cTrader stores 1.18941, so the m1 high of exactly 1.18941 on 10 Sep 2020 12:37 UTC filled it (passes 3/7/11/15);
    truncating the raw target instead breaks 15 other passes. With A20 the check grid is 55 / 55, EURUSD_edge 94 / 94,
    and EURUSD / USDCAD / US30 / US2000 Weekly maps 100% under the referee rule.

## B. Data the cBot computes from bars
1. **Chart bars** of the chosen timeframe (m5/m10 for US30 Session). Whether cTrader builds them from the m1 bars (and how
   it sums tick volume) is checked against the export (`chart_*.csv.gz` vs `m1.csv.gz`).
2. **VWAP** (lines 815–832, 1312–1341): per bar, source price (grids: Close) × **bar tick volume**, accumulated in double
   precision; band = vwap ± mult × √max(0, Σpv²/Σv − vwap²). Bars with tick volume ≤ 0 are ignored.
   Resets: Session at each TC date (18:00 NY); Weekly at TC Monday; IntradayDual ETH (00:00–15:30 TC) and RTH (15:30–23:00 TC),
   two accumulators, each reset at a new TC date. The band of a bar is its own segment's; Intraday Dual "ETH only" /
   "RTH only" gives the other segment no band (its candles only re-arm). VWAP trails use the trade's own VWAP; in Intraday
   Dual only while the bar is in that segment.
3. **ATR**: cTrader `AverageTrueRange(Bars, 14, WilderSmoothing)` on the chart bars, including the ~200 history bars before
   the backtest start: Wilder RMA of the true range (archive: ATR × stop mult = every archived stop distance, 41,058 trades).
   The chart bars are the server's m5/m10 bars with real tick volume (identical to the export's bars). Locked at the signal bar.
4. **ATR ready**: bar index (in cTrader's Bars, history included) ≥ ATR length and ATR > 0 (line 788).

## C. Signal rules (ProcessClosedBar, lines 277–347), evaluated on each completed chart bar
1. **Schedule** (line 901): Session: TC minute of the bar's open ≥ Block First and < 1380 − Block Last. Weekly: not in the
   first hours after TC Monday 00:00 or the last hours before TC Friday 23:00. Intraday Dual: per segment (ETH: minute ≥ First
   and < 930 − Last; RTH: minutes since 15:30 TC ≥ First and < 450 − Last); the segment not selected is always eligible.
   Day block windows are not simulated (pass_vector refuses them).
2. **Track Touches During Blocked Candles = No** (grids): a blocked bar does not touch the arm state at all.
3. **Touch**: long if low ≤ lower band, short if high ≥ upper band, using the band after this bar is included.
4. **Pause / re-arm**: a side signals only if the previous eligible bar did not touch that side; the arm state updates on every
   eligible bar, also while a position is open or the entry is refused later.
5. **Both sides touched** → SkipBoth (grids).
6. **Entry gates** (line 336): no entry if the force-close window is active, the signal's VWAP period has ended (Session:
   TC date of the signal bar + 23:00), the broker close is imminent (C4), a force-close boundary lies between the signal bar's
   open and now, the last exit was ≤ 1 s ago, ATR not ready, or a position is open (no hedging in the grids).
7. **Filters** (Qualifies, lines 769–797): distance (signal close vs band, ≤ ATR × max), penetration (wick or close beyond the
   band, ≤ ATR × max), ATR percentile (share of the previous Lookback values of a second Wilder ATR ≤ the current one, ≤ max;
   AtrReady then needs bar index ≥ max(ATR length, lookback + percentile length)). Max entry spread filter: not simulated.
8. **News filter** (lines 857–876, 1440–1610): the calendar is read from the cBot's NewsCalendar block. A candle
   [open, open + span] is blocked when it overlaps [release − before, release + duration + after) (span = the smallest gap
   between bar opens seen so far; BoJ windows 180 min). Mode 2 also closes trades at the first "release − close minutes"
   after the entry and blocks entries from max(before, close) minutes. Track Touches During News Block decides the arm state.

## D. Open-trade rules
1. **Fixed TP** (Management 0): SL = ATR × Stop mult, TP = SL distance × TargetR, both fixed. Break-even option *(fine grids, later)*.
2. **Rstep** (Management 1–4, lines 447–451, 558–604; Bar Close timing): no TP. Step / gap / activation in R: 1 = ½ / 1 / ½,
   2 = ½ / ½ / ½, 3 = 1 / 1 / 1, 4 = ½ / 1 / 1. At each chart-bar close (OnBarClosed, after the force closes, before the signal):
   reached R = (bar high − entry) / risk for longs, (entry − bar low) / risk for shorts (bid bars; entry = the reported, rounded
   fill; risk = ATR × stop mult, unrounded). If reached ≥ activation: milestone = ⌊reached / step⌋ × step, new stop = entry ±
   (milestone − gap) × risk, rounded to the tick (`RoundToTick`); it is used only if it improves the current stop by more than
   half a tick. If the new stop is not beyond the current price (long: < bid − tick, short: > ask + tick) the position is
   closed at market on this tick ("Position closed"); otherwise the broker uses the new stop from the next price on (the
   next m1 bar's high/low). US30 Session Rstep full grid: 16,781 of 16,800 passes identical.
   **VWAP band trail** (5 static, 6 dynamic, lines 606–745): at each bar close, a stage from the trigger price (bar high/low,
   or its close) against the trade's VWAP ±1/2/3 σ; static: stop to entry, then the 2σ/1σ band, the VWAP, … behind the price
   minus the ATR cushion, tighten only; dynamic: the band one stage further back, may loosen but never beyond the original
   stop. A level must sit beyond the bar's close by a tick; one already beaten at the new bar's open closes at market.
   **Break-even** (Fixed TP, fine grids): once a bar reaches the trigger R and closes beyond the entry, the stop moves to the
   entry (TP kept), same "already beaten → close at market" rule.
3. **Force close** (lines 1011–1050): Session: with "close at session end" = Yes, every TC day at 22:50 (16:50 NY); with
   Friday close, every TC Friday at 22:50. Weekly: Friday close only. Intraday Dual: RTH close every TC day at 22:50, ETH
   close at 15:20 (09:20 NY), Friday close; a 10-minute window before each boundary plus the boundary-crossing check. Closes at the first tick at or after that time — after a holiday early close or a data
   gap this is the next session's first tick (archive: Mon 18:00 NY after MLK day, Thanksgiving, etc.).
4. **Broker-hours safety net** (line 1056, on in the grids): when force close applies today, also close (and block entries)
   once the broker schedule says the market closes within 10 minutes.
5. **Last exit**: any exit sets the last-exit time used by C6.

## E. What is not simulated (no effect on these backtests)
Live-only code: recovery state, restarts, labels, retries, LocalStorage, timer, order rejections (a backtest never rejects).
