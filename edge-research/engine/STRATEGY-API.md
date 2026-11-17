# Strategy interface (published 2026-11-12, engine owner)

Lanes write one strategy module per idea in `strategies/` and queue jobs; the runner does the rest (`OPERATIONS.md` §1).

## The module
```python
# strategies/idea_NNNN_<slug>.py   (committed before the job is submitted; the ledger records its commit)
import numpy as np

def intents(bars, params, ctx):
    """bars:   dict of numpy arrays for the job's timeframe, every bar up to the period end, history before the period
               included for warm-up: open_ms (UTC), o, h, l, c (bid), vol (tick volume), close_ms (= open_ms + timeframe).
       params: the variant's parameters (the card's defaults, a grid point, or an amber variation).
       ctx:    symbol, timeframe, tick (price step), digits, first_ms / end_ms (the period: decide only on bars with
               open_ms >= first_ms); ctx["context"] only when the job declares context symbols (below).
       Returns a dict of arrays aligned to bars (only 'side' is required):"""
    n = len(bars["c"])
    return {
        "side":      np.zeros(n, np.int64),     # +1 buy / -1 sell / 0 nothing, decided at bar i's close
        "otype":     np.zeros(n, np.int64),     # 0 market, 1 stop order, 2 limit order
        "price":     np.full(n, np.nan),        # stop / limit level
        "sl_dist":   np.full(n, np.nan),        # stop distance from the fill (required: an order without a stop is refused)
        "tp_dist":   np.full(n, np.nan),        # target distance from the fill (NaN = none)
        "expiry_ms": np.full(n, np.nan),        # pending order life (NaN = until the next bar's close)
        "hold_ms":   np.full(n, np.nan),        # time exit after the fill (NaN = none)
        "trail_long": np.full(n, np.nan), "trail_short": np.full(n, np.nan),   # candidate stops at bar i's close (tighten only)
        "exit_long": np.zeros(n, bool), "exit_short": np.zeros(n, bool),       # close at market at bar i's close
        # optional: "flat_ms": the strategy's own flat times (UTC ms), added to its class's
    }
```

## What the engine does with it (`engine/kernel.py`, `engine/rules.py`, `cTrader-Bots/CONVENTIONS.md`)
- An intent goes live on the **first tick at or after its bar's close**.
- Fills, stops and targets are simulated on ticks, at FTMO's spread.
- One position at a time per strategy and symbol: an intent while one is open is dropped and counted.
- Results are in R; 1 R = the stop distance at the fill.
- Class rules (A flat 22:45 Amsterdam, B flat Friday 22:45, C may hold), entry blocks, the four news modes and the trade caps are
  applied **by the engine**. Never code them into the strategy.
- Costs (spread, commission, swap, slippage) are added in the trade log, on both venues.

## Rules for the module (checked by the look-ahead reviewer)
- **Closed bars only:** the value at bar i may use bars ≤ i, never i + 1. No centred windows, and no normalising over the whole period.
- **No calendar to enter:** the strategy never reads the news calendar to trade.
- **No randomness without a fixed seed** from params. **No file, network or data access:** only the bars passed in.
- **Generic engine:** a missing feature (an order type, an exit rule) is asked from the engine owner and added for every strategy.
- **Only the card's parameters,** with the card's defaults. Grids and amber variations as declared on the card.

## Context symbols (DESIGN A14.1, `engine/inputs.py`)
- A card may declare up to **3 other store symbols as inputs**: the row `| context symbols | US500, STOXX50 |` (or `none`), and every job
  of the idea carries the same list: `"context": ["US500", "STOXX50"]`. The runner refuses a job whose list differs from the card's
  row (either way), a name the store doesn't have (`STOXX50`, not `EU50`), more than 3, or a symbol the job also trades. Context symbols
  are never traded and never a grid axis; changing them is a new card.
- The module gets, per context symbol, that symbol's bars of the job's timeframe **aligned to the traded bars**:
  `ctx["context"]["US500"] = {"open_ms", "close_ms", "age_ms", "o", "h", "l", "c"}`, arrays of `len(bars["c"])`. Element i is the
  **last context bar whose close_ms <= bars["close_ms"][i]**: closed at the decision time, never a later one; `age_ms` = the traded
  bar's close minus that close_ms. Where the context market is shut **on schedule** (other sessions, weekends, holidays) the value is
  that stale last bar and `age_ms` says how old it is; the card states how the module treats staleness.
- **NaN, never stale** (prices NaN, `open_ms` / `close_ms` / `age_ms` -1): before the context history starts (DE40 2021-09, oil 2017-07),
  inside its **data holes** (A8.8 unscheduled breaks of >= 2 h, any silence over 3.5 days without a holiday, e.g. 10-19 Oct 2014; HK50 /
  JP225 / AUS200 holidays count as holes) until the first context bar after the hole has closed, and for an FX context symbol in the FX
  quarantine (May-Jul 2015). A module must handle NaN (e.g. no entry). Time in holes, 2014-11 -> 2024-12: FX 0.01%, indices 0.06-0.83%,
  HK50 2.9%, metals / oil 0.02-0.13%. No tick volume and no unaligned context bars.
- **DESIGN A14.1.3-5:** a card that differs from an idea with a result only in its context symbols is one of that idea's amber variations
  (or counts as seen); an FX context symbol makes the idea run fx2015 as an FX idea; context symbols must be available at the target firms.
- The ledger row of such a job gets `"context"`, and its `data_hash` covers the context symbols too.

## Outside series (DESIGN A14 §2, `engine/series.py`)
- A card declares them in the row `| outside series | name; name |` (or `none`); every job carries the same list as `"series"`
  (the runner refuses any difference). Names:
  - `cot:<legacy|disagg|tff>:<CFTC market code>:<column>`: CFTC Commitments of Traders, futures only, e.g.
    `cot:tff:13874A:Lev_Money_Positions_Long_All`, `cot:legacy:099741:Noncommercial Positions-Long (All)` (column names exactly as in
    CFTC's files; `engine.series._load("cot", report)["cols"]` lists them);
  - `vix:<VIX|VIX3M|VIX9D>:<open|high|low|close>`: CBOE daily values;
  - `calendar:<monthly_expiry|quarterly_expiry|index_roll>`: rule-derived dates, no download.
- The module gets `ctx["series"][name] = {"value", "release_ms", "age_ms"}` aligned to the traded bars: the value with the latest
  as-of among those **released strictly before** bar i's close (NaN / -1 before the first one). Release times: COT = the actual
  release date of each report at 15:30 New York (holiday shifts, shutdowns, revised weeks at their revision date; later candidate when
  unsure); VIX = 16:15 New York on the day. Calendars: `{"dates_ms"}` (00:00 New York of each event date, 2010-2024; known in advance).
- The store (`../data/series-2014-2024/`, built by `tools/series/`) holds only values released before 2025-01-01; raw files stay outside.
- COT values are CFTC's **current vintage**, not as first published (A14 §2.3): the card says so, prefers levels or >= 52-week
  percentiles over week-on-week changes near a threshold, and fixes report, trader category, contract and futures-only.
- The ledger row of such a job gets `"series"`, and its `data_hash` covers the store files read.

## The job (`engine/runner.py submit <job.json>`)
```json
{"idea_id": "IDEA-1001", "card": "ideas/cards/IDEA-1001-....md", "lane": "market logic", "stage": "screen",
 "strategy": "strategies/idea_1001_x.py:intents", "params": {"fast": 20}, "grid_id": null, "grid_size": 1,
 "symbols": ["EURUSD", "GBPUSD"], "timeframe": "h1", "period": ["2014-11", "2024-12"], "class": "A", "note": "default run"}
```
- The card and the module must be committed and unchanged, or the job is refused.
- **DESIGN A10.4, A11.3 (luck bar):** the card must have the table rows `| data-mined | yes |` or `no`, `| seen family | yes |` or
  `no`, `| source overlap | yes |` or `no` (exactly; the reasons go in other rows, e.g. `| source overlap, why | ... |`) and
  `| grid size | N |` (the declared grid's number of points). The runner refuses a real job whose card lacks any of them or reads
  anything else, and copies them into the ledger row (`card_flags`). k reads them from the idea's **first** screen row (A11.4): a
  later card change has no effect on k.
- **Tune grids (A11.2, `engine/ideas.py`):** one `tune` row per declared grid point, same symbols, filters and other parameters as
  the route's screen row; the screen row's parameters are the defaults the walk-forward falls back to in a training window with no
  trades. `route_g1` judges the route with k from the ledger and appends the judgement to `results/g1.jsonl`.
- Every real job has a `route`: `base` (stage `screen`), `V1`-`V3` (stage `amber-V1`...`V3`; derived) and, for `tune`, `wf` and
  `stress-*` jobs, the route they belong to (required). Grid points of a route run as stage `tune` with that route.
- **Symbol names (guard, 2026-11-15):** a real job whose module returns no entry intent at all on one of its symbols over the
  period is refused before any trade runs (queue/failed, `ZERO INTENTS`, no ledger row): key on the store's names (e.g. `STOXX50`,
  not `EU50`). A symbol emptied by the job's filter still runs and is flagged in `zero_trade_symbols`.
- The period is never past 2024-12, and the stage is never `locked`.
- All four news modes run unless `modes` says otherwise.
- **Lanes don't submit while the engine is being checked.** First real tests: after the referee comparison, the random-strategy check
  and the frozen thresholds (`OPERATIONS.md` §6).
