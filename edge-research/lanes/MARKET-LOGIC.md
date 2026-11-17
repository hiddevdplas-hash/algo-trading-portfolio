# Lane: market logic

**Job:** write idea cards from first principles: who pays, and why it persists. The first lane in the queue (the best expected quality per test):
40% of the cards tested per week (`OPERATIONS.md` §4). Local, Opus 5.5.

**Aim at small-capacity niches.** Claude's plain ideas are the average of the literature, the trades everyone already makes. Prefer what big
funds skip: single-session effects on CFDs, smaller symbols, holding periods shaped by the firms' rules, flows a retail-size book can trade.

**Families to work** (CFD plan §0.1, `DESIGN-CONSTRAINTS.md` §10):
- time-series trend / momentum, two-sided;
- intraday momentum, including into the close (no Friday late entries at FTMO);
- session and opening-range effects;
- short-term reversal after overreaction;
- FX fixing flows;
- calendar and flow effects (turn of month, quarter end, index rebalancing): two-sided or small;
- carry (class C only, low fit);
- price-only levels: prior day, session highs and lows, time-based profiles.
- **TPO / market profile (auction theory), a named theme from 2026-11-16 (user):** profiles built from price × time only (count of
  closed bars touching each price bin): point of control, value area high / low, initial balance, single prints, poor highs / lows,
  profile shapes (P / b / D / double distribution), prior-day / prior-week value as reference. State the bin size, the session, which bars
  build the profile and when it is final (only closed bars: a profile is known at the close of its last bar, never before). Who pays:
  responsive vs initiative traders, inventory correction, stop runs beyond poor extremes. Check existing cards first (3003 red; 3005,
  3013 waiting) so you don't re-skin them. **Volume profiles: allowed under DESIGN A13** (2026-11-17): only over a whole session (cash, 24 h or week), the card names its TPO twin and picks one as default (the other only as an amber variation), states session, bin size in ATR units and when the profile is final; a twin with a red screen can't be re-carded as volume. Every other tick-volume use stays parked (§5).

**Not:**
- volume-based logic (IC tick volume isn't real volume);
- entries triggered by upcoming news;
- grids, martingale;
- long-only as the main logic;
- overnight-gap logic.

**Locked period (DESIGN A1):** never record results after 2024-12-31 from any source; if a source shows them, set `locked period seen: yes`
(source, months; no numbers, no direction). Don't pick symbols, direction or parameters from how markets behaved after 2024.

**Review fixes first (2026-11-13):** at the start of every run, read `gatekeeper/REVIEW-FIXES.md` and fix the open items in your number range (card v2 and / or module fix, as listed) before writing new cards. These listed changes to existing cards are allowed; mark each `fixed in <commit>` there.

**Open slot (user, 2026-11-16):** at most **1 of a run's 3 cards** may be any testable idea you come up with, without a who-pays
mechanism: indicator-based, chart pattern, volatility, statistical or calendar regularity, cross-symbol, anything a rule can express. It still
states a hypothesis (why it might work, when it should fail), stays off the **Not** list below (no volume logic: IC tick volume isn't real
volume), sets `data-mined` **yes** ("open slot, no mechanism": the luck bar then counts every real test), and is not a re-skin of an
existing or dead card. The other cards stay mechanism-first. Why only one: plain indicator ideas behave like the random strategies of the
noise check (5% amber, 0% reach the gatekeeper), so they cost test count and seldom pass; the slot gives breadth without flooding the k.

**Two card rules from DESIGN A11 (2026-11-15):** (1) every new card fills the strict rows `| source overlap | yes/no |` and `| source overlap, why | … |` from `ideas/TEMPLATE.md`; yes when any cited source's sample covers any month of 2016-11 → 2024-12, the defaults come from such a source, or you can't tell. An overlapped idea faces the luck bar at the full test count, like a data-mined one. (2) Short-history routes can't realistically pass: a route with about 1.3 unseen years (e.g. DE40 only) needs an unseen daily Sharpe near 3.8 at k ≈ 10,000. Prefer symbols with the full 2014-11 → 2024-12 history.

**Output:** cards in `ideas/cards/` from `ideas/TEMPLATE.md`, status `inbox`.
- Quality over count: 3 well-built cards a run; runs a day are set in `OPERATIONS.md` §2a (scale-up 2026-11-12).
- Check the ledger and `ideas/cards/` first, so you don't repeat a dead idea. A genuinely different mechanism is a new card; a re-skin of a dead one isn't.
- Spread the cards over the four exposures (equities, USD, metals, oil).

**You may:**
- queue jobs for your own cards once the engine is live;
- write amber variations on your cards (with reasons, before they run).

**You may not:** change the engine, edit the ledger, read data after 2024-12-31 or `~/cAlgo/Exports/`, or move a card past `stress`.

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

**Theme: institutional-schedule catalogue (user, 2026-11-17: "add all four").** Flows that recur on a known clock, not retail patterns.
Work through this list, at most one card per schedule, mechanism first (who must trade at that time, why it persists, when it fails):
- **FX fixes:** WM/R London 4pm (16:00 London), ECB reference rate (14:15 CET), Tokyo fix (09:55 JST), the FX options New York cut
  (10:00 New York), the Tokyo cut (15:00 JST). **Gotobi days** (the 5th, 10th, 15th, 20th, 25th and month-end in Tokyo, rolled to the
  previous business day; the module computes them from bar timestamps and states that Japanese holidays are not in the data).
- **Expiries and rolls:** US equity-options expiry weeks (declare both `calendar:monthly_expiry` and `calendar:quarterly_expiry`: the
  monthly one excludes Mar / Jun / Sep / Dec), quarterly index rebalance and roll (`calendar:index_roll`), commodity futures roll windows.
- **Month, quarter and year ends** beyond 1011 (red): e.g. the FX month-end fix demand, Japanese fiscal year-end (March), the US
  quarter-end window dressing; never a re-skin of a red idea.
- **Already tested (red, final; don't re-card the family):** 1001 oil settlement window, 1011 month-end balanced-fund rebalance,
  1016 US close-auction pressure, 1022 PBoC fix repricing. 1007 (monthly opex dealer hedge flow) exists: check it before any expiry card.
- Never the news calendar as an entry signal; a schedule is a clock or a rule-derived date, not an event release.
