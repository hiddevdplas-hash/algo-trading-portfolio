# Lane: literature

**Job:** turn published research and practitioner write-ups into idea cards. **From 2026-11-17 it runs on the Mac** (task
`edge-literature-local`, 11:45 and 18:45, commits on main; the cloud card runs and shortlist scans are paused after 5 runs in 48 h gave
0–1 cards). On the Mac the built-in browser reaches SSRN and university repositories that blocked the cloud; a sign-in wall is logged,
never signed into. Added sources: central-bank working-paper series (BIS, Fed Board FEDS / IFDP, New York Fed Staff Reports, ECB, BoE,
Bank of Canada, Riksbank, SNB), individual Quantpedia strategy pages and the Quantocracy archive. Up to 3 cards a run; fewer is fine.
(`OPERATIONS.md` §2–3). Shares: papers + Quantpedia 30%, websites + whitepapers 15% of the cards tested per week.

**Sources (decided 2026-11-11):**
- **Papers:** arXiv q-fin (official API: scan everything new); SSRN (**targeted searches only**, read one at a time; no bulk downloading,
  its terms forbid it); journal articles; NBER; Fed, ECB, BoE and BIS working papers (incl. FX flows).
  **SSRN blocks the cloud run (HTTP 403 "Content Blocked", 11–12 Nov). Mirrors first (user, 2026-11-12):** for an SSRN paper, read the
  author's own page or university copy, RePEc / IDEAS, NBER or the central-bank series instead. If no mirror has it, mark its numbers on
  the card **`unverified (SSRN only)`**, with exactly that wording, so the evening prep can count them.
- **Quantpedia:** free strategy descriptions, one page at a time.
- **Practitioner websites**, one page at a time: Quantocracy (daily), Robert Carver's blog, Robot Wealth, Alpha Architect, Ernie Chan's blog,
  Quantpedia's blog, Concretum Group.
- **Free whitepapers:** AQR, Man Group, central banks, BIS.
- **PDFs: legal sources only** (open access, author- or publisher-released, public domain). Never pirated copies of commercial books.

**Filter:**
- **time-series effects on what we trade:** indices, FX, metals, oil. Not equity cross-section: a CFD account can't hold a sorted stock portfolio;
- an out-of-sample or post-publication check, where the paper has one;
- **decay:** published effects shrink by about half after publication (McLean & Pontiff 2016). The card states the effect size the paper found and the size we'd need after costs to pass;
- **costs:** many intraday papers ignore spreads. Check that the effect survives a worst-firm spread before writing the card;
- futures or ETF effects that depend on the overnight return may vanish on CFDs, because of swap (DESIGN-CONSTRAINTS; RESEARCH-DESIGN-DRAFT §5).

**Locked period (DESIGN A1):** never record results after 2024-12-31 from any source; if a source shows them, set `locked period seen: yes`
(source, months; no numbers, no direction). Don't pick symbols, direction or parameters from how markets behaved after 2024.

**Shortlist first (2026-11-16):** Sonnet scan runs (05:40, 11:40) fill `lanes/literature-shortlist.md` with papers that have a free
full text. Card runs take its `open` rows oldest first, read each source themselves, mark it `carded IDEA-2xxx` or `rejected: <reason>`,
and scan on their own only when fewer than 3 usable rows are open.

**Review fixes first (2026-11-13):** at the start of every run, read `gatekeeper/REVIEW-FIXES.md` and fix the open items in your number range (card v2 and / or module fix, as listed) before writing new cards. These listed changes to existing cards are allowed; mark each `fixed in <commit>` there.

**Two card rules from DESIGN A11 (2026-11-15):** (1) every new card fills the strict rows `| source overlap | yes/no |` and `| source overlap, why | … |` from `ideas/TEMPLATE.md`; yes when any cited source's sample covers any month of 2016-11 → 2024-12, the defaults come from such a source, or you can't tell. An overlapped idea faces the luck bar at the full test count, like a data-mined one. (2) Short-history routes can't realistically pass: a route with about 1.3 unseen years (e.g. DE40 only) needs an unseen daily Sharpe near 3.8 at k ≈ 10,000. Prefer symbols with the full 2014-11 → 2024-12 history.

**Output:** cards in `ideas/cards/`, status `inbox`.
- "Evidence before testing" cites the paper: authors, year, link, sample, market, effect size.
- Rebuild the rule from the paper's description; don't copy code.
- 3 cards a run; runs a day are set in `OPERATIONS.md` §2a (scale-up 2026-11-12). Check the ledger and existing cards for duplicates.

**You may / may not:** as the market-logic lane (`lanes/MARKET-LOGIC.md`).
- Cloud session: push only to `lane/literature`; the gatekeeper merges. Never touch the ledger, the engine or `main`.
- Model: Sonnet 5.5 to scan and triage; Opus 5.5 to write the card and module of what's selected.

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
