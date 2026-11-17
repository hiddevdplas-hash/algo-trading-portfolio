# Lane: your ideas (sparring session)

**Job:** turn the user's own ideas into idea cards and strategy modules, by sparring with the user in one interactive session
("Your ideas: sparring", local on the Mac). Started 2026-11-17 at the user's request. Ideas come from the user's own creativity, from
something seen online, or from earlier projects. The cards then go through the same pipeline as every other lane: look-ahead review,
screen, walk-forward, stress, luck bar, sceptic, locked period. **Card numbers: 0001–0999** (`OPERATIONS.md`). IDEA-0001 (weekly VWAP
Monday drift, draft) moves to this lane.

## How a sparring round works
1. **The user brings an idea** in any form: a sentence, a chart observation, a link, a screenshot.
2. **Claude makes it testable and pushes back.** Before any card:
   - who is on the other side and why they pay; why it would persist; when it should fail;
   - what exactly triggers entry and exit, on which symbols and timeframe, with what stop;
   - whether it duplicates or re-skins an existing card, or a red idea's family (red is final: a re-skin is refused);
   - whether it is buildable in the engine (`engine/STRATEGY-API.md`; context symbols and CFTC data under DESIGN A14 once in the engine).
   Agreeing to keep things moving is the failure mode: say plainly, with numbers, when an idea is weak, needs data we don't have, or is
   selection on noise.
3. **The card** (`ideas/TEMPLATE.md`, `ideas/cards/IDEA-0NNN-<slug>.md`, next free number, status `inbox`, lane `your ideas`), with the
   user agreeing the rules, symbols, at most 3 tuned parameters and their grids, and the walk-forward length **before** it is committed.
4. **The module** (`strategies/idea_0NNN_<slug>.py`, `intents(bars, params, ctx)`), checked with py_compile and once on 600 synthetic
   random-walk bars (built in the scratchpad, never market data). Commit card + module on main.
5. The gatekeeper's screen runs (14:15, 21:15) review and screen it; the user gets the push. **This session never grades the idea**,
   never runs a backtest and never queues jobs.

**Other markets and outside series are in the engine (DESIGN A14, engine c4bbd3a56c61, 2026-11-17).** A card may now use:
- **Context symbols:** up to 3 other store symbols as inputs, never traded, in the row `| context symbols | US500, STOXX50 |` (or
  `none`). Only symbols tradable at the firms (not AUS200, F40, HK50, US2000). The module reads `ctx["context"][SYM]` (aligned closed
  bars with `close_ms` and `age_ms`; NaN before history, in data holes and for FX context in May–Jul 2015) and the card says how stale
  values are treated. Families retail tools miss: lead-lag (USDJPY → JP225, oil → CAD pairs, gold → AUD), one index against another,
  risk-on / risk-off across markets, spreads as the signal. A card that only swaps context symbols of an idea with a result is a
  variation of that idea, not a new card.
- **Outside series:** row `| outside series | name; name |` (or `none`); `ctx["series"][name]` gives the latest value released before
  the bar's close. Names: `cot:<legacy|disagg|tff>:<CFTC market code>:<column>` (CFTC positioning; say "current vintage"; prefer levels
  or ≥ 52-week percentiles over week-on-week changes near a threshold; fix report, trader category and contract mapping on the card),
  `vix:<VIX|VIX3M|VIX9D>:<open|high|low|close>`, `calendar:<monthly_expiry|quarterly_expiry|index_roll>`. US yields (FRED) are not
  stored yet. Never the news calendar as an entry signal.
- Details: `engine/STRATEGY-API.md`; the look-ahead reviewer's check 9 applies.

## Honest flags (the part that matters most for your own ideas)
- **Locked period seen (A1):** ideas formed by watching markets in 2025–26, or from a source showing 2025+ results, are `yes`. Ask the
  user where and when the idea came from and write it on the card. A "yes" idea can still pass, but its locked-period result counts only
  as "not independent" (A1.3).
- **Data-mined:** `yes` if the idea, its parameters or its symbols were picked from looking at charts or backtests (including published
  TradingView backtests or the user's own earlier tests).
- **Seen family (§3.7):** ideas derived from the VWAP project (session, weekly or intraday-dual VWAP, Monday / weekly cells) or repairing
  a failed RoboQuant template are strict-rule ideas: clean data only (VWAP: 2014-11 → 2017-12 and the 14 untested symbols; RoboQuant:
  2014-11 → 2015-12), and the data-mined bar at the count of all tests. Read `../VWAP Mean Reversion Strategy (Claude)/CLOSE-OUT.md`
  (read-only) before carding a VWAP-derived idea. US2000 is not in the research store.
- **Source overlap (A11.3):** `yes` when any source's tested sample covers any month of 2016-11 → 2024-12, or when unsure.
- **Tick volume:** only whole-session volume profiles (A13); everything else with tick volume stays parked.

## Never
- Read data (`~/cAlgo/Exports/`, `../data/`), run backtests, write the ledger, or touch `engine/`.
- Read `ledger-mining/`, `runs/mining/` or `mining/` (A15 firewall), or card anything prompted by a mined result.
- Edit other lanes' cards or modules, the VWAP or RoboQuant folders (read-only), `DESIGN.md`, `STATUS.md`, `LOG.md`, `DIGEST.md`.
- `rm` or delete anything. `git add` only this session's files; never `git add -A` / `commit -a`; commit messages end with the
  attribution line; `git push` after each commit.

## The Notion Strategy inbox
Stays as the quick capture from the phone (X posts, links). Items the user marks as their own idea are brought to this session;
everything else stays with the public-scripts lane.
