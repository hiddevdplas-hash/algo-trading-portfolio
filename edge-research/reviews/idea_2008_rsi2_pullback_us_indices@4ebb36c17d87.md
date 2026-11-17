VERDICT: FAIL

# Look-ahead review: IDEA-2008 (RSI(2) pullback, US indices)

- Module: `strategies/idea_2008_rsi2_pullback_us_indices.py` (last commit 4ebb36c, clean in the working tree)
- Card: `ideas/cards/IDEA-2008-rsi2-pullback-us-indices.md` (v1)
- Interface: `engine/STRATEGY-API.md`; kernel semantics checked in `engine/kernel.py` (bar-exit events, `free_from`)
- Reviewed at HEAD 73bd17c (6de3acc is an ancestor). Code only: no backtest run, no results looked at.

## Finding (the reason for the FAIL)

**F1. strategies/idea_2008_rsi2_pullback_us_indices.py:99: the exit rule is not the card's rule.**

```python
exl[cc[(C > sma_exit) & ~entry]] = True
```

The card says: exit "at the close of the first h1 bar ending 16:00 ET (after entry) whose cash close is above SMA(5)". It makes no
exception. The `& ~entry` mask drops the exit flag on any cash close that also carries an entry signal. That only matters when a
position is **already open**. Then:
- **What the card says:** the open position exits at that close. The kernel lets a new intent go live on the exit tick
  (`kernel.py:323` `free_from = ex`; "the tick an order / position ended on counts"). So the old trade closes and a new trade opens
  with a new k x ATR stop and a new 28-day clock.
- **What the code does:** the old position stays open, with its old stop and old time-exit clock. The new entry is dropped as busy
  (`C_DROPPED_BUSY`). That changes both the trade list and the dropped-signal count.

The mask is not needed for the case it seems to guard against. The kernel starts bar-close exit events at the first bar whose close is
after the fill (`kernel.py:193`, `searchsorted(bar_close_ms, t[j], side="right")`). So a flag on the entry bar can never close the
position that this bar opens.

The case is rare: an open position, RSI(2) < rsi_lo, close > SMA(200) and close > SMA(5) all on the same cash close. It is still a
rule the card does not state.

**Smallest fix:** `exl[cc[C > sma_exit]] = True`. Re-commit and re-review. Per the review rules, no result from the current version counts.

## Per area

1. **Bar timing:** clean.
   - Cash closes are picked by the bar's local close time (`close_ms` converted to New York time, exactly 16:00, Mon–Fri on the local
     close).
   - Every value at cash close j uses bars ≤ cc[j]:
     - Day high / low use `reduceat` over (cc[j-1], cc[j]], sliced to `cc[-1]+1`.
     - RSI uses `diff` of past closes.
     - Wilder recursions are causal.
     - The SMA comes from a cumulative sum with a trailing window.
   - No `shift(-k)`, no centred windows, no `[-1]` on full-period arrays.
   - The entry is a market order at the 16:00 bar's close, so it goes live at the first tick at or after that close. The bar's own close
     is known at that point.
2. **Full-period statistics:** clean. SMA(200), SMA(5), RSI(2) and ATR(10) are all trailing. Nothing is normalised over the sample.
3. **Higher timeframes:** clean.
   - The daily series is built only from closed h1 bars at the cash close. There is no resampling and no partial daily bar.
   - The day's high / low cover the h1 bars after the previous cash close up to and including this one, as the card says.
   - The offset is looked up per UTC hour, so DST is handled. That includes the DST-gap weeks.
4. **Calendar and news:** clean. The calendar is not read. `datetime` / `zoneinfo` are used only to convert the clock.
5. **Data range:** clean. There is no file, network or path access; only the passed bars are used. The runner trims bars to `end_ms`
   (≤ 2024-12). `live` restricts entries to `open_ms >= first_ms`, and the runner enforces this too.
6. **Card match:**
   - FAIL on F1 above.
   - Otherwise everything matches the card: symbols and timeframe are in the job, plus RSI 2 Wilder, SMA 200, SMA 5, ATR 10 Wilder,
     16:00 ET, the 28-day time exit, defaults rsi_lo = 10 and k = 3.0, and grids {5,10,15} x {3,4,5} come in through params.
   - The fixed constants (2, 200, 5, 10, 28 d, 16:00) are all listed on the card as fixed.
   - Unstated details with no effect:
     - The Wilder seed is the simple mean of the first n values. It washes out long before the 200-close SMA warm-up ends.
     - RSI is set to 100 when both averages are 0. That blocks the entry, and RSI = 50 would block it too at every grid value.
7. **Prop rules:**
   - Clean: every entry has `sl_dist = k x ATR > 0` (it is guarded by `isfinite(atr) & atr > 0`). The strategy is long only, with one
     intent per cash close. There is no grid and no martingale.
   - **Note (not a code defect):**
     - Friday 16:00 ET entries are emitted and fall inside FTMO's 2-h-before-close block, so the engine drops them. The card says this
       explicitly, and the API forbids coding blocks into the strategy. Expect about 1/5 of entry signals in `C_BLOCKED_ENTRY`, which
       inflates the dropped-signal count.
     - The same applies to any pre-holiday day where the index closes within 2 h of 16:00 ET.

## Informational
- **Warm-up:** SMA(200) needs 200 cash closes before the first entry. If the h1 history in the store starts close to the 2014-11 period
  start, the first ~10 months of the period can produce no entries. That affects the walk-forward split, not validity.
