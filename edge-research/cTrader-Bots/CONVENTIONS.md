# cBot conventions (engine parity)

Every cBot in this folder (referees now, finalists later) follows these rules, so that it does what the engine kernel
(`engine/kernel.py`) simulates. The referee comparison (`tests/referees/compare.py`) checks them against cTrader; a rule the
referees prove wrong is fixed in the kernel **and** here, with a new engine hash.

## Event order on a tick
cTrader handles each tick in this order (VWAP `tools/fastbt/RULES.md` A4, A10):
1. **The order engine:**
   - pending orders fill;
   - an open position's stop, then its target.
2. **The cBot, first thing in `OnBarClosed` and in `OnTick`: housekeeping.**
   - Flat time: close the position, cancel the pending order.
   - A pending order past its end: cancel it.
   - Time exit: close.
3. **`OnBarClosed` only: bar-close rules for the bar that just closed.**
   - Trail the stop, or close at once if the new stop is already beaten.
   - Exit signal.
   - Both only for a position filled **before** that bar's close.
4. **`OnBarClosed`: the new intent.**
   - Only if no position or order of this cBot is open after steps 1–3. Otherwise it is dropped and counted.

What follows from this order:
- A pending order can still fill on the tick that ends it.
- An exit and a new entry can share a tick (stop-and-reverse).
- A position never sees the bar-close rules of the tick it filled on.

## Orders
- **Market orders** go out in `OnBarClosed`, on the first tick of the next bar. Buys fill at the ask, sells at the bid.
  The stop and target are sent in pips, relative to the fill (`ExecuteMarketOrder(..., slPips, tpPips, ...)`).
- **Pending orders** (`PlaceStopOrder` / `PlaceLimitOrder` with `ProtectionType.Relative`):
  - If the level is already crossed on the tick the order would go live, the order is **not sent** and is counted
    (`refused_crossed`). Crossed means: buy stop ask ≥ level, buy limit ask ≤ level, sell stop bid ≤ level, sell limit bid ≥ level.
  - **Expiry is handled by the cBot**, not by cTrader's expiration field. With an expiry, the order is cancelled on the first
    tick at or after go-live + expiry. Without one, it is cancelled at the next `OnBarClosed`.
- **One position per cBot per symbol.** Never more than one order or position open at a time.
- **Every order carries a stop.** An intent without a stop is not sent.

## Prices on the tick grid
- **Levels and distances** go on the grid as `n / 10^digits`, where `n = floor(x / tickSize + 0.5)`. This gives the nearest
  double, the same value Python gets (`Grid.rt`).
- **Prices sent to cTrader** (pending levels, modified stops) are sent as `(n + 0.25) / 10^digits`. cTrader truncates a modified
  stop to the symbol's digits (RULES A20), so a value sitting exactly on the grid can drop a tick (for example
  33,725.7 × 100 = 3,372,569.99…). The quarter tick makes truncation and rounding both store `n`.
- **Trailing:**
  - A new stop is used only if it improves the current one by more than half a tick (kernel `min_step`).
  - If the price has already reached it (long: bid ≤ new stop), the position is closed at market on that tick.

## Clocks
- The robot runs with `TimeZone = TimeZones.UTC`.
- New York rules convert each bar time with `TimeZoneInfo` (`America/New_York`, or `Eastern Standard Time` on Windows),
  with DST per date. Python uses `zoneinfo`.
- Amsterdam rules do the same with `Europe/Amsterdam`.

## Indicators
- Plain sequential loops in double precision, over the closed bars from a fixed **seed bar**: the first bar on or after the
  Seed Date. No `Indicators.*` calls, because their warm-up depends on how much history cTrader loads.
- The backtest starts on the Seed Date. Decisions start after a warm-up (100 bars for the referees).
- In `OnBarClosed`, `Bars` excludes the new live bar: the bar that just closed is `Bars.Count - 1`.

## Output
- Each referee writes `~/cAlgo/Exports/referees/<R>_<SYMBOL>_<seed>.csv`: one row per closed position, `#error` lines, and a
  `#summary` line.
- Exit kinds:
  - `StopLoss` and `TakeProfit` come from cTrader;
  - `Closed:<why>` is a cBot close, with why = `signal`, `time`, `flat` or `trail`;
  - `Closed:end` is the backtest end.
