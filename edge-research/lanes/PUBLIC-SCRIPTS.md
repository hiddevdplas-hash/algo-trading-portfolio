# Lane: public scripts

**Job:** use open-source TradingView scripts and public strategies as **idea sources** for strategies we rebuild and make our own.

**Sources (decided 2026-11-11, `OPERATIONS.md` §3):** TradingView open-source scripts; **GitHub** repositories with an open licence (search via
the official API); the user's **Strategy inbox** in Notion. For an inbox item, read what it points to (paper, blog, script) at its source.
Share: 15% of the cards tested per week. Trading blogs and whitepapers belong to the literature lane.
**Not used:** RoboQuant (terms forbid automated access), Instagram, TikTok, YouTube. **X:** deferred to the week-6 review; Claude doesn't browse X.

**Where on TradingView (user, 2026-11-16):** Community → Indicators and strategies, in this order: (a) **Popular**, type **Strategies**,
**Open-source only**; (b) the same view, newest first; (c) Editors' picks; (d) indicators and topic lists only when (a)–(c) give nothing.
A published backtest is never the reason to pick a script: our engine does the testing. Pick on a stated market reason and a rule we can
rebuild. Skip URLs already on a card or in the run log; log each script opened and rejected (URL + reason) so later runs skip it.

**Strategy inbox:** Notion data source (ID removed in this public copy). Read rows with Status "New"; set "Read", then
"Card written" (with the card id) or "Skipped" (with a one-line lane note).

**Why this lane faces the highest bar:**
- many public scripts repaint, are tuned showcases, or use future data;
- RoboQuant: 0 of 10 passed;
- many traders run the same scripts, so their trades can match other traders' trades, which the firms flag.

**Rules:**
1. **Read pages one at a time, like a person.** No bulk scraping and no scripts against the site.
   - Check the script's licence (often MPL 2.0) and TradingView's terms.
   - Put the URL, author and licence on the card. **Never copy code** into the repo.
2. **Extract the core concept, then change it substantively:**
   - our own entry and exit logic, stop, timeframe and filters, with reasons;
   - the card says what is new versus the source.
   - Prop firms require your own strategy (`rulebook/DESIGN-CONSTRAINTS.md` §10; FundingPips accepts git history as proof).
3. **Flag repaint risk** on the card: higher-timeframe calls, `security()` look-ahead, pivots confirmed later, `barstate` tricks.
4. **Decayed public strategies** can be revived only through the amber budget: at most 3 variations, each with a stated reason, written before they run.

**Locked period (DESIGN A1):** never open a TradingView strategy tester or performance tab; a performance snapshot on the page counts
as seen: set `locked period seen: yes` (source, date shown; no numbers, no direction). Never record results after 2024-12-31.

**Review fixes first (2026-11-13):** at the start of every run, read `gatekeeper/REVIEW-FIXES.md` and fix the open items in your number range (card v2 and / or module fix, as listed) before writing new cards. These listed changes to existing cards are allowed; mark each `fixed in <commit>` there.

**Two card rules from DESIGN A11 (2026-11-15):** (1) every new card fills the strict rows `| source overlap | yes/no |` and `| source overlap, why | … |` from `ideas/TEMPLATE.md`; yes when any cited source's sample covers any month of 2016-11 → 2024-12, the defaults come from such a source, or you can't tell. An overlapped idea faces the luck bar at the full test count, like a data-mined one. (2) Short-history routes can't realistically pass: a route with about 1.3 unseen years (e.g. DE40 only) needs an unseen daily Sharpe near 3.8 at k ≈ 10,000. Prefer symbols with the full 2014-11 → 2024-12 history.

**Output:** cards in `ideas/cards/`, status `inbox`, data-mined = **yes** unless a real mechanism is stated (who pays, why it persists). 2 cards a run; runs a day are set in `OPERATIONS.md` §2a (scale-up 2026-11-12).

**You may / may not:** as the market-logic lane. Runs **locally** (TradingView pages need a real browser; changed from the cloud 2026-11-10).
Model: Sonnet 5.5 to scan, Opus 5.5 for cards and modules.

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
