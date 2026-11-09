> **Portfolio copy.** The working design of the Edge Research project, as of 2026-11-08. References to private planning files (capital plan, firm rulebook, venue models, logs) point to documents that are not included here. One line about specific personal trading accounts has been removed; nothing else is edited.

# Edge Research: design (v1, 2026-11-06)

**What this is.** How Edge Research finds, tests and hands over strategies for the CFD prop plan (`CFD-PORTFOLIO-PLAN.md` §0).
It replaces `RESEARCH-DESIGN-DRAFT.md`; the user's decisions there (§8) are carried over unchanged.

**How to read it.** Each rule is marked:
- **[D]** decided by the user (date in `RESEARCH-DESIGN-DRAFT.md` §8 or `CFD-PORTFOLIO-PLAN.md` §0);
- **[P]** proposed by Claude and not yet decided. Every [P] is listed in §13, and is decided **before the first real idea is tested**.

**Change rule.** A rule that governs a result is changed only by a dated addendum at the end of this file, committed **before** the run it
governs. A rule is never changed for an idea whose result has already been seen.

---

## 1. Goal and what success looks like
- **Goal:** 4–8 strategies whose daily P&L is uncorrelated, that fit the core six firms' rules, ready for the first evaluation in early 2027.
  A new strategy is judged on what it adds to the pool, not only on its own numbers.
- **Success at each stage:**
  - **Week 1:** engine, ledger, cost table and locked period in place; random-strategy check run; bars frozen and reviewed by the sceptic.
  - **Weeks 2–8:** a steady flow of idea cards through the pipeline, with the batch pass rate compared against the random-strategy rate.
  - **First candidates:** strategies that pass the locked period, go to the cTrader check, the firm feed check and the 1-week bot test.
- **Failure is a valid outcome.** If nothing beats the random-strategy rate, the report says so plainly, and nothing is bought (the buying plan
  says nothing is bought until edges and a portfolio exist).

## 2. Lessons this design is built on
| lesson | source | where it lands here |
|---|---|---|
| Heavy optimisation fitted noise: in-sample vs out-of-sample correlation −0.13, −398 R over 147 OOS files | VWAP close-out | §6 simple first, three optimisation rules, test counting |
| Lucky passes grow with the number of tests: after 1,000 zero-edge tests the luckiest looks better than a real strategy | draft §1 | §7 ledger, §8 random-strategy check |
| In-sample showcases don't survive: 0 of 10 RoboQuant templates passed | RoboQuant STATUS | §5 public-scripts lane, highest bar |
| Tick volume isn't futures volume (VWAP and IVB conversions failed) | RoboQuant | volume-based ideas parked (§5) |
| The Python replica was ~100× faster than cTrader, and matched it trade for trade | VWAP `tools/fastbt` | §4 engine, referee runs |
| cTrader runs by hand were the bottleneck | VWAP close-out | cTrader only for referee runs and finalists |
| A "self-improving" loop that adds filters after seeing results is noise-fitting | review of a social-media post, 2026-11-06 | §6 amber budget, look-ahead review, no live re-tuning |

## 3. Data
### 3.1 Sources and periods
- **Research data [D]:** IC Markets tick exports, `~/cAlgo/Exports/fastbt-ic-tick/` (42 symbols, 2014-01 → 2026-11-05, 193 GB), checked in
  `data-checks/IC-TICK-CHECK.md`.
- **Research period [D]: 2014-11-01 → 2024-12-31.** The shared hole of 10–19 Oct 2014 stays out.
- **Locked period [D]: 2025-01-01 onwards** (about 22 months today; later data is locked too). Only the gatekeeper opens it, once per
  candidate (§9).
- **Firm feeds:** FTMO tick exports (`~/cAlgo/Exports/fastbt-ftmo-tick/`, 12 symbols) for costs and the firm feed check. Other firms' feeds when they become relevant.

### 3.2 Symbols [D]
**The 39 that all core firms publish:**
- 28 G8 FX pairs;
- indices: US500, USTEC, US30, DE40, JP225, UK100, EU50 (IC: STOXX50);
- metals: XAUUSD, XAGUSD;
- oil: WTI (XTIUSD), Brent (XBRUSD).

AUS200, FRA40, HK50 and US2000 are data only. Each idea card declares its own short symbol list, with a reason. More symbols means more tests (§7).

Four independent exposures (`DESIGN-CONSTRAINTS.md`, CFD plan §E3): **equities, USD, metals, oil.** Start with one two-sided strategy per exposure.

Short histories: DE40 starts 2021-09 (about 3 research years), oil 2017-07. Thin months are listed in the data check.

### 3.3 Data quality rules (in the loader, not left to each strategy)
1. **Crossed ticks** (ask < bid) are dropped for fills. FX 2017–2019 crossings of −0.1 pip are treated as zero spread.
2. **FX May–July 2015 is quarantined.** An idea that trades FX shows its result with and without those months. If it passes only with them, it fails.
3. **Thin months** from the data check are flagged on every result that uses them.
4. **h2 / h4 bars** don't line up with UTC multiples in cTrader (anchor unknown). Use the exported h2 / h4 bars or avoid them; never build them in Python until the anchor is known.
5. **Signals use cTrader's exported bars** (what the cBot sees). **Fills use ticks** (bid / ask). Bars of other timeframes are built from exported m1 (checked 100% on m5–h1).

### 3.4 Research store [D 2026-11-08]
Reading 193 GB of csv.gz for every run is far too slow, and mirroring every tick uncompressed won't fit (294 GB free).
- **Research store:** `~/Projects/Algo Trading/data/ic-research-2014-2024/`, outside the repo.
  - Per symbol: exported bars (m1 → h4) as numpy arrays.
  - Ticks per symbol-month, compressed (time and price deltas, zstd).
  - **Only 2014-11-01 → 2024-12-31 is converted.** The locked period is not in the research store at all, so a research session can't read
    it by accident.
- **Target:** ≤ 80 GB, a month of ticks decompressed in under 1 second. Measured on EURUSD and XAUUSD first.
  - **Fallback if it doesn't fit:** ticks are kept only for bars where an order level is touched, and m1 bid / ask bars are used elsewhere.
- **The raw exports stay where they are** (the shared rule: trash only after an archive is verified, and only on the user's word).

### 3.5 Costs [D 2026-11-08]
- **Research on IC prices; judged on FTMO's costs; IC's costs shown alongside** (user, 2026-11-08; replaces "worst firm" and the ×1.25 guess).
- **One simulation per run, at FTMO costs:**
  - fills use IC's bid / ask plus FTMO's extra spread, because a wider spread can hit a stop that IC's spread wouldn't;
  - each trade carries two cost lines, IC and FTMO, and the ledger stores both;
  - **pass or fail uses FTMO's number only.** IC's is information: cost sensitivity, which symbols suffer, a cheaper venue later. It is slightly approximate (the trades are FTMO's).
- **Cost table v1** (`engine/costs.json`, part of the engine hash):
  - **spread, FTMO:** IC's real tick spread at that moment, plus a per-symbol add-on = (FTMO median − IC median), by hour of day where FTMO data shows a pattern.
    FTMO's data starts 2020-04, so before that the add-on assumes FTMO's markup over IC stayed the same (flagged);
  - **spread, IC:** IC's real tick spread;
  - **commission:** each venue's published rate. FTMO's FX rate (about $5 per lot round trip) is confirmed by one test trade on the FTMO trial;
  - **swap:** modelled from past central-bank rates (the rate gap between the two currencies, or the benchmark rate for indices and gold),
    plus each venue's markup fitted on today's swaps across all symbols. The fit's quality is reported: one consistent markup = credible; arbitrary per-symbol values = weak, said so.
    **Oil:** today's rate, flagged (its swap follows the futures curve, not rates);
  - **slippage:** 0 on limit orders; on stop and market orders, one extra spread at the 5 minutes around high-impact news.
- **Stress runs (G2):** spread × 1.5; swap × 1.5 for classes B and C; **positive swap set to zero** (no strategy may pass on carry income alone; a carry idea must say on its card why the carry persists).
- **FTMO measured on 12 symbols.** The other 27 research symbols get the add-on of the most similar measured symbol, flagged, until the user exports them from FTMO's cTrader (`runlists/FTMO-EXPORTS-27.md`, the referee evening).
- **The other five firms** may be dearer on some symbols: that is caught by each firm's feed check (G3) before money goes in.

### 3.6 News calendar and news modes [D 2026-11-08]
**The calendar** (built once, in the engine week, before the random-strategy check):
1. **Events:** the union of every core firm's high-impact sources: FTMO's restricted list, FundingPips' dashboard list, ForexFactory
   high-impact (Instant Funding, BrightFunded, Aqua), FXStreet high-impact (Instant Funding), Myfxbook high-impact (Aqua). **Today's** event
   types are applied to the whole history: strategies trade under today's rules. Each event is tagged with the firms that restrict it.
2. **Dates and times** from the official release archives (statistics agencies, central banks, EIA), back to 2014-11. A public ForexFactory
   history only as a cross-check (any such dataset is itself scraped; licence unclear). Unscheduled events (emergency cuts) are left out:
   no cBot can filter them live either. The VWAP calendar (2018 →) is copied, not edited.
3. **Window, research standard:** **T−6 → T+6 min** (wider than FTMO ±2, Instant Funding ±4, the others ±5). Each firm's own window is
   used only in the firm simulation (§10), never to judge research.
   **Speeches, press conferences, testimony** (user's method, 2026-11-08): block from T−6 until 5 min after the **end**.
   - Event names come from ForexFactory and the FundingPips dashboard; start times from official sources.
   - End times from the official record where it exists (Fed and ECB press-conference videos and transcripts, Congress hearing records,
     official speech videos); each event marked "official" or "assumed".
   - Where none exists, a conservative default: **60 min** for speeches and press conferences, **3.5 h** for testimony. A longer block only
     removes trading time; it never lets a forbidden trade through.
   - Collected at a normal pace from the official sites in the engine week, before any result.
   **Firm calendar time vs official time** (user, 2026-11-08): firms judge by **their own reference calendar** (ForexFactory for Instant Funding,
   BrightFunded, Aqua; their own for FTMO and FundingPips), not the official time.
   - **Live (cBot):** the window is the **union** of the firm's calendar time and the official time. The earlier opens it, the later closes it.
   - **Research:** official actual times (ForexFactory's history can't be used). Events without a fixed time (Bank of Japan decisions,
     speeches without a fixed start) get a window covering their **whole usual release range plus the actual time**, not ±6 around one minute.
     The trading time this removes is reported.
   - **One check while building:** compare a few current weeks of ForexFactory with the official times. Event types whose times don't
     match to the minute get the wider window too. Holiday shifts (e.g. oil inventories moved a day) come from the official schedule.
4. **Symbols an event blocks:** the currency's FX pairs; USD also gold, silver and US indices; EUR also DE40 and EU50; GBP UK100; JPY JP225;
   oil inventories WTI and Brent.
5. **Tiers:**
   - **Tier 1:** rate decisions of the eight central banks (Fed, ECB, BoE, BoJ, BoC, RBA, RBNZ, SNB), US CPI, US jobs report (NFP),
     FOMC and ECB press conferences;
   - **Tier 2:** every other event in the union.

**News modes:** every run computes all four, with the same rules and parameters:
| mode | tier 1 | tier 2 | used by |
|---|---|---|---|
| **M0** | free | free | the raw edge |
| **M1** | flat at T−6 (unless far-stop), no entries until the window ends | free | Fintokei, firms without a tier-2 rule |
| **M2** | flat (unless far-stop) | **hold without target:** no entries; target removed in the window, stop kept; after the window, close at market if price is past the target | FundingPips, BrightFunded, Aqua; FTMO and Instant Funding evaluations |
| **M3** | flat (unless far-stop) | **flatten** at T−6 (unless far-stop), no entries until T+6 | FTMO and Instant Funding funded |

- **Release slippage** comes from the ticks in every mode (a stop fills at the first real tick past it), plus the buffer of §3.5 for
  firm fills worse than IC's quotes.
- **Discovery is judged on M0:** quick screen and amber variations. All four modes are computed and shown from the first run.
- **News flag (6):** a strategy keeping **less than half its M0 profit in M3** is a news strategy: not for funded accounts with a news rule.
  Shown at every stage.
- **Rule A, robust parameters:** in tuning and in each walk-forward training window, a parameter set is scored on the **worst** of M0, M2 and M3
  (neighbourhood average, §6.6). One fixed rule, not an extra look.
- **Rule B:** one parameter set for all firms; never tuned per firm.
- **Rule C, firm eligibility:** a strategy is eligible at a firm **if and only if** it passes the walk-forward bars in that firm's mode. It is never re-run,
  re-tuned or re-argued for a firm it failed.
- **Rule D:** random strategies follow the identical rules. A random strategy eligible at **at least one** firm counts as a pass (§8), so the extra
  looks from several firms are priced into the bars.
- **Rule E:** every mode check is a ledger test, linked to its variant.
- **Far-stop exemption, part of M1, M2 and M3** (user, 2026-11-08, decided before any result): a position may stay open through a tier-1 or
  tier-2 window if, at T−6, its stop is further from price than **1.5 × the 99th percentile of the high-low range in that window**, for that
  symbol and event type, measured over 2014-11 → 2024-12. The target is removed for the window and the stop kept. After the window: close at
  market if price is past the target, otherwise the target goes back. Fixed engine rule, the same for every strategy, never tuned. The
  engine reports how often each strategy used it. Purpose: swing trades with a far trailed stop ride big releases instead of being forced out.
- **No stop or target changes inside a window** (user, 2026-11-08): the only changes are the target removal before the window (M2,
  far-stop) and putting it back after. Trailing pauses during the window.
- **Firm-specific exceptions are not used for eligibility** (user, 2026-11-08). Examples: FTMO doesn't block DE40 on euro events;
  FundingPips exempts trades opened ≥ 5 h before; BrightFunded exempts the target on trades held ≥ 48 h; Aqua caps instead of forbidding.
  The generic modes are stricter than every firm's exact rules, so a pass is valid at every firm using that mode. The firm simulation applies
  each firm's exact rules (and its own symbol mapping) **for sizing, daily limits and payouts only, never to make a strategy eligible.**
- **Live calendar** for the cBots: part of the cBot risk-engine work (CFD plan §0.2), with a snapshot of each firm's rules at purchase.
- Oil stays in research (user, 2026-11-08).

### 3.7 Families already seen on parts of the data [D 2026-11-08]
Two earlier projects looked at results on parts of this data. You can't un-know a result, and an idea born from it is selected on it,
so "ignoring what we saw" isn't enough for ideas **derived from** those projects. Unrelated ideas are not affected.

| project | what we saw | contamination | rule |
|---|---|---|---|
| **VWAP** mean reversion (session, weekly, intraday dual) | heavy optimisation 2018-01 → 2026-11 on its 26 symbols: which symbols, modes, days and settings worked | **strong** | ideas derived from it count **only clean data**: 2014-11 → 2017-12; the 14 research symbols VWAP never tested (EURCAD, GBPJPY, GBPCHF, GBPAUD, GBPNZD, AUDCHF, AUDCAD, NZDJPY, NZDCAD, CADJPY, CADCHF, CHFJPY, EU50, Brent), all years; and data from 2026-11-01 on |
| **RoboQuant** templates | 5 templates tested exactly as published, 2016 → 2026, no tuning, all failed | **weak** | **normal ideas**, including opening-range and session breakouts on USTEC / US500. Only an idea that repairs a specific failed template ("template X plus filter Y, because it lost in 2022") gets the strict rule: clean data = 2014-11 → 2015-12, untested symbols, data from 2026-11-01 on |

A strict-rule idea:
- says so on its card;
- has its walk-forward and locked-period results counted on the clean parts only;
- faces the data-mined bar at the count of all tests (§7);
- goes to the back of the queue.

## 4. Engine
### 4.1 What it must do
- **One generic engine** (`engine/`), not a strategy per file of kernel code.
  - The VWAP engine is used as a reference for fill rules and cTrader traps (`../VWAP…/tools/fastbt/RULES.md`). It is not extended, because it is VWAP-specific.
- **Strategy interface:**
  - a strategy module computes, from **closed bars only**, an order intent per decision bar: side, type (market / stop / limit), price,
    stop-loss, take-profit, expiry, exit rule;
  - the kernel makes an order live from the **first tick after that bar closes**, and simulates fills, stops, targets and time exits on ticks;
  - one position per strategy per symbol (no grids or pyramiding: the firms' rules ban grids).
- **Fills:**
  - buys at ask, sells at bid;
  - a stop or target fills at the first tick that crosses it, at that tick's price (gaps fill at the gap price);
  - when both are crossed by the same tick, the stop wins.
- **Sizing in research:** every trade risks **1 R**. Firm % risk, the risk ladder and daily guards are applied later, in the portfolio and firm simulation (§10).

### 4.2 Prop rules in every run [D principle, `DESIGN-CONSTRAINTS.md`]
Research runs with the funded rules on (the strictest), except news, which runs in the four modes of §3.6:

| rule | engine behaviour |
|---|---|
| strategy class A / B / C (card) | A: flat by 22:45 Amsterdam. B: flat before the weekend. C: may hold over weekends |
| no entries 22:45 → 00:15 Amsterdam | entries blocked |
| no entries ≤ 2 h before a close of ≥ 2 h | blocked, using the symbol's exported trading hours |
| news around high-impact releases | four news modes M0–M3 per run, tiers and windows as in §3.6 |
| no strategy may enter because news is coming | the look-ahead review checks that no rule uses the calendar to enter |
| hold time | share of trades under 2 min reported; above 10% → fail. Median hold ≥ 15 min reported |
| ≤ 10 trades per strategy per day, ≤ 2 orders per symbol per 60 s | extra signals dropped and counted |
| broker-side stop on every order | an order without a stop is refused |
| one direction per bloc across the book | checked at portfolio level (§10) |

Times are converted per bar with real time zones: Amsterdam and New York change clocks on different dates.

### 4.3 Trade log, from the first run [D, §8 item 11]
For every trade:
- times, side, prices, stop, target;
- risk, and R before and after each cost (spread, commission, swap, slippage);
- **MFE and MAE** in R;
- **exit reason**;
- **market context:** session, volatility percentile, trend state, news day, day of week, month;
- symbol, timeframe, idea, variant, engine hash.

That's what the amber diagnostics and portfolio checks read.

### 4.4 Version hash and reproducibility
- Every result carries the **engine hash** (engine code + cost table + rules config), the **data hash** and the idea card's version.
- A change that alters results invalidates the old ones. They are re-run, or flagged as from an older engine.
- Same inputs → same outputs, bit for bit (a test in `tests/`).

### 4.5 Checks before the engine is trusted
1. **Unit tests:** fills, gaps, both levels crossed by one tick, time zones and DST weeks, the rules in 4.2, costs.
2. **Referee runs in cTrader [D]:** 5 simple reference strategies, run by the user in cTrader **tick mode** on IC over 3–6 months each, compared
   trade for trade with the engine. The five are an m15 EMA cross, an h1 Donchian break with an ATR stop, a timed session entry and exit,
   a limit-order fade and a trailing stop, spread over EURUSD, XAUUSD and US500.
   - **Bar:** ≥ 99% identical trade lists; every mismatch explained. One evening of cTrader runs for the user.
3. **Look-ahead review** (agent `lookahead-reviewer`): reads every strategy module before any of its results count (§6.2).

### 4.6 Speed and the job queue
- A queue of job files (`queue/`) and one runner (`engine/runner.py`) using 14 of the 16 cores, run in the background by launchd.
  - It writes trade lists to `runs/` (not in git) and one ledger row per test.
- **The Mac must stay awake and on mains power** for overnight batches. A small home machine is planned for FundingPips and Instant Funding
  anyway (no VPS allowed there), and could take over the runner later.
- **Throughput:** thousands of variants a day; 10–30 properly built ideas a day. The limit is the quality of ideas, not CPU.

## 5. Where ideas come from: the lanes [D: all lanes from the start]
| lane | source | bar | notes |
|---|---|---|---|
| **Market logic** | Claude's own hypotheses: who pays, why it persists. Trend / time-series momentum, intraday momentum, session effects, short-term reversal, carry, calendar and flow effects; price-only levels (prior-day, session highs and lows, time-based profiles) | normal | first in the queue |
| **Literature** | SSRN, arXiv q-fin, journal articles: time-series effects on indices, FX, metals and oil (not equity cross-section) | normal, + decay | published effects shrink by about half after publication (McLean & Pontiff 2016) |
| **Public scripts** | TradingView open-source scripts, public strategies | **highest** | ideas only: rebuilt from scratch, changed substantively, licence and source recorded on the card, never code copied. Many repaint or are showcases. Prop "own strategy" rules (`DESIGN-CONSTRAINTS.md` §10) |
| **Gatekeeper** | none: owns the ledger, the locked period, the random-strategy check, the sceptic, the portfolio | — | sessions can't grade their own work |

- **Volume-based ideas are parked:** IC tick volume isn't real volume (RoboQuant).
- Lanes write **idea cards only** (`ideas/cards/`). They don't run tests, change the engine or read the locked period.
- Until the engine passes its checks (§4.5), cards wait in the queue.
- Lane briefs are in `lanes/`.

## 6. The pipeline [D]
```
idea card → look-ahead review → quick screen → (green) tuning → walk-forward → stress tests → gatekeeper (locked period, sceptic, portfolio)
         → cTrader tick check + journal report → firm feed check → 1-week bot test → first evaluation (buying plan)
```

### 6.1 Idea card (G0) [D]
Template in `ideas/TEMPLATE.md`. It is written before any backtest, and includes:
- **four "why should this exist" lines:** who pays, why it persists, when it should fail, evidence before testing;
- family; lane; data-mined yes / no; seen family (§3.7); class A / B / C; symbols and timeframe with reasons;
- every parameter with a default, a reason and its allowed values (fewest possible);
- the walk-forward length;
- the expected trades per year.

### 6.2 Look-ahead review [D, §8 item 11]
A separate agent reads the strategy code and the card before any result counts. It checks for:
- data from the future: bar t's close used to enter at bar t, centred windows, full-period normalisation, reading the calendar to enter;
- repainting;
- rules the card doesn't state.

A fail sends the code back, and the fix is logged. A fixed strategy's earlier results don't count.

### 6.3 Quick screen [D]
- **Runs once, with defaults, on the full research period**, at worst-firm costs, in funded mode. No tuning.
- **Zones [D, thresholds P]:**
  | zone | what the base result shows | next |
  |---|---|---|
  | **Green** | a real edge after costs, over enough trades | tuning (fewest parameters), then walk-forward |
  | **Amber** | something there but not enough: an edge before costs that costs eat, or clearly working in one session, regime or symbol group for a reason that makes sense | the creative budget |
  | **Red** | nothing, not even before costs; looks like random entries | killed. A genuinely different idea gets a new card |
- **Cut-offs [D 2026-11-08]**, judged on news mode M0 at FTMO costs (t-stat = mean R per trade ÷ its standard error):
  - **Green:** after costs ≥ **+0.05 R per trade**, **t ≥ 2.0**, ≥ **150 trades**. At about 1.1 R spread per trade: +0.18 R at 150 trades, +0.13 R at 300, +0.07 R at 1,000.
  - **Amber:** not green, but **before costs t ≥ 1.5**, **or** one slice from the fixed list that would be green on its own.
  - **Red:** neither.
- **Fixed slice list** (the same for every idea and for the random strategies):
  - session (Asia, London, New York);
  - volatility third (low, middle, high);
  - trend vs range;
  - long vs short;
  - bloc (equities, USD, metals, oil);
  - **recent regime: the last 4 research years, 2021-01 → 2024-12.**
  A slice earns only the amber budget, never a pass.
- **The random-strategy check (§8) can raise the cut-offs, never lower them:** green is raised if more than 10% of random strategies land
  green; amber likewise if too much noise gets the budget. The final values are frozen by addendum and reviewed by the sceptic before the first real idea.

### 6.4 Amber creative budget [D]
- **At most 3 variations,** each written on the card **with its reason before it runs.**
- Each **adds information** (a session, a volatility regime, a trend filter, a real market driver), not parameter knob-turning.
- Every variation is a ledger test, judged on walk-forward unseen data.
- If none turns green, the idea dies, and **the budget can't be topped up.**
- **Regime variation [D 2026-11-08]** (the user's concern: an edge that only started working recently). One of the 3 variations may declare a
  **regime start date**, only with an **external, dated reason** written before it runs (e.g. daily-expiry US index options from 2022; the rate
  cycle turning in March 2022). Never a date chosen from the chart.
  - Walk-forward is then judged **from that date**: ≥ 200 unseen trades and the yearly rule within the new regime.
  - **The locked period counts fully** (it lies inside the new regime) and becomes the main test.
  - Random strategies get the same route: the recent slice, plus a regime date drawn from a fixed list of candidate dates.
  - Fewer unseen years means weaker evidence; this is stated on the result.
- The decayed case (worked before, not now) needs no rule: walk-forward and the locked period fail it.
- The random-entry strategies get the same treatment (§8). If they come out green too often, the budget is too loose.

### 6.5 Tuning [D: three optimisation rules]
1. **Simple first:** tuning only after the default run shows something.
2. **Every parameter combination is a test** in the ledger: a 1,000-point grid is 1,000 tests, and the bar rises with it.
3. **Fewer parameters is better:** at most 3 tuned, each with a reason on the card. Grids are declared on the card before the first run.

### 6.6 Walk-forward (G1) [D: 24 / 3]
- **Train 24 months, test 3, step 3.** 12 / 2 only when declared on the card before any run, and only if the idea trades ≥ 100 times per 12 months.
- The first test window starts 2016-11. About 33 steps, about 8 unseen years.
- **In each training window,** the parameters come from the declared grid by a declared rule: the best **neighbourhood average**, not the
  single best point (the VWAP lesson on spiky optima), scored on the **worst of news modes M0, M2 and M3** (§3.6, rule A).
- **Firm eligibility:** the bars below are checked in each news mode; a strategy is eligible at a firm only if it passes in that firm's mode (§3.6, rule C).
- **Judged only on the stitched unseen windows** [D principle, bars P]:
  - ≥ 200 unseen trades;
  - profit factor ≥ 1.15 after costs;
  - positive in ≥ 60% of the yearly blocks (D2 said windows; a 3-month window can hold only a handful of trades);
  - Monte Carlo 95th-percentile drawdown ≤ 70% of the firms' max loss at funded risk;
  - **and** above the count-adjusted bar (§7).
  These are the D2 values as a floor **[D 2026-11-08]**. **The random-strategy check may raise them, never lower them.**
  - The drawdown bar is checked per firm, at that firm's max loss and funded risk (FTMO: 10% at 0.75% → about 9.3 R).
  - The count-adjusted bar is part of G1 (§7).

### 6.6a Near-miss lane [D 2026-11-08, the user's idea]
A strategy that fails **exactly one** G1 / G2 bar by no more than a fixed margin, and passes all the others, may go on as a **near miss**:

| bar | normal | near miss down to |
|---|---|---|
| profit factor | 1.15 | 1.12 |
| profitable years | 60% | 50% |
| unseen trades | 200 | 170 |
| profit kept with jitter | 75% | 70% |
| profit factor at 1.5× spread | 1.05 | 1.03 |
| profit kept at neighbouring values | 70% | 65% |

- **Never a near miss on the safety bars:** count-adjusted bar, drawdown bar, long / short, single-symbol share, FX 2015, positive swap at zero.
- **The price:** at the locked period, a near miss needs an average per trade at or above the walk-forward's **median** (not the 10th percentile).
- Random strategies use the same lane, so it is priced into the 1% target (§8).
- A near miss is labelled as one in the ledger and the portfolio.
- The margins are fixed here; they are never widened for a result already seen.
- **TradeZella / Ergodic Labs are veto only, never a rescue:** they test the same data, so they add no new evidence.

### 6.7 Stress tests (G2) [D 2026-11-08, from D2; floor, near-miss lane §6.6a]
| test | pass |
|---|---|
| noise: prices jittered by 1 spread, signals ±1 bar | keeps ≥ 75% of the base P&L |
| cost stress: spread × 1.5 (swap × 1.5 for B / C) | profit factor ≥ 1.05 |
| positive swap set to zero (B / C) | still passes G1, or the card explains why the carry persists |
| parameter neighbours (one step each way) | keep ≥ 70% of the P&L |
| without the best year, and without the top 5 trades | still positive |
| FX May–Jul 2015 removed (FX ideas) | still passes G1 |
| long and short separately | no side below −0.05 R per trade (the firms flag one-sided bets) |
| per symbol in the declared list | no single symbol carries more than half the P&L |

### 6.8 Gatekeeper (§9), then before money [D]
1. **cTrader tick check:** the hand-written cBot vs the Python version on IC ticks over a fixed 12-month window inside the research period.
   ≥ 95% of trades the same (±1 bar); the same run's report goes to TradeZella / Ergodic.
2. **Firm feed check (G3):** the strategy on the target firm's feed for the overlap window. ≥ 80% of trades within ±1 bar; P&L per trade inside the noise-test range.
3. **1-week bot test (G4)** on free trials: mechanics only, not edge (CFD plan §0.1).
4. **First evaluation (G5) and scaling (G6)** per the buying plan; the kill rule from CFD plan D2. **A strategy is never re-tuned on live data.**

## 7. The ledger and test counting [D]
- **One ledger for every test of every session** (`ledger/*.jsonl`), written **only by the runner**, never by hand.
  - Append-only: a correction is a new row that names the row it replaces.
  - Schema in `ledger/README.md`.
- **What counts as a test:** every run of every variant at every stage (screen, each grid point, each amber variation, each walk-forward grid, each stress test that is pass / fail).
- **Count-adjusted bar [P]:** the walk-forward Sharpe must clear the 95th percentile of the best zero-edge Sharpe at the current **effective** number of ideas.
  - Effective number: grid points of one idea are correlated, so they count as one idea × a factor measured in the random-strategy check.
  - The table in `RESEARCH-DESIGN-DRAFT.md` §1 gives the scale: about 1.2 at 1,000 tests over 7 unseen years.
  - Data-mined ideas and seen families (§3.7) face the bar at the count of **all** tests, not ideas.
- **The batch test:** every week the gatekeeper compares the share of real ideas reaching each stage with the random-strategy share. If real ideas don't do better than random, single passes aren't believed.

## 8. The random-strategy check (null calibration) [D]
Before any real idea is screened:
- **About 300 random-entry strategies,** matched to real ideas in trade frequency, hold time, stop and target style, symbols and class.
  - Random entry times and directions; stops and targets in ATR multiples; same costs and rules.
- **Each goes through the whole pipeline with the same news modes and rules** (§3.6; a random strategy eligible at at least one firm counts as a pass),
  including **the amber budget:**
  - 3 creative variations each, drawn from the same menu of filters (session, volatility regime, trend);
  - then tuning, walk-forward and stress tests.
- **Outputs:**
  - the share of random strategies landing green / amber / red;
  - the share rescued by the amber budget;
  - the share passing walk-forward and stress;
  - the grid-correlation factor for §7.
- **Thresholds [P]:** the quick-screen zones, and any raise of the G1 / G2 bars, are set so that **at most 1% of random strategies reach the gatekeeper.**
  - At 200 ideas a quarter, that is about 2 false candidates a quarter before the locked period.
  - The locked period then lets through about a quarter of zero-edge strategies (draft §3), so about 1 false finalist every two quarters.
    That is the reason the bot test, the first evaluation and G6 still exist.
- **The thresholds are frozen** in an addendum, the sceptic reviews them (shared rule: before every pre-registration), and only then do real ideas run.

## 9. The gatekeeper and the locked period [D: opened once per candidate]
- **The locked store doesn't exist until a candidate needs it.** `gatekeeper/open_locked.py <candidate>`:
  1. converts 2025-01-01 → latest for that candidate's symbols only;
  2. runs the **frozen** candidate (engine hash, card version, parameters fixed by the last walk-forward window's rule);
  3. writes the result to the ledger;
  4. logs the open in `gatekeeper/OPENS.md`.
  A candidate can't be changed after its open. A fail is final for that idea, and its family is noted.
- **Before the open:** the `oos-sceptic` agent reviews the candidate (ledger history, count, card, look-ahead review, stress), and its report goes to the user unedited.
- **Locked-period bar [P]:**
  - net after costs > 0;
  - expectancy per trade at or above the walk-forward's 10th percentile;
  - drawdown inside the walk-forward Monte Carlo 95th percentile.
  - Power, honestly: over 22 months a zero-edge strategy passes about a quarter of the time. This filters; it doesn't prove.
- **Portfolio contribution:** daily P&L correlation with the pool < 0.3, and < 30% of losing days shared (CFD plan §0.2 proposal). Judged on balance **and** equity drawdown.
- **It's a rule backed by tooling, not a vault:** the raw exports still contain 2025–2026. Research sessions never read `~/cAlgo/Exports/`, and the ledger shows every open.

## 10. From strategies to accounts
- **Portfolio and firm simulation:** the candidates' R streams run through each firm's rules in Python:
  daily floors and reset times, open-winner floor raises, the risk ladder, √n sizing, 50% / 80% daily guards, open-risk caps.
  Inputs come from `DESIGN-CONSTRAINTS.md` §3–4 and the ramp model in `venue-decision/`.
- **One direction per bloc across the book; no hedges inside an account** (`rulebook/CROSS-FIRM-HEDGING.md`).
- **An account keeps its strategy set** from evaluation to funded.
- **The cBot side** (risk engine, firm config files, news filter, restart recovery): CFD plan B #12. Built once, for the first finalists.

## 11. How the sessions work together
| session | does | doesn't |
|---|---|---|
| **Engine owner** (build week; later on request) | data store, engine, costs, rules, ledger, queue, tests, referee strategies + cBots | write idea cards, judge ideas |
| **Market logic, Literature, Public scripts** | idea cards; amber variations (written before they run); queue jobs for their own cards once the engine is live | change the engine, edit the ledger, read the locked period, raise their own budget |
| **Gatekeeper** (daily) | ledger audit, batch vs random, sceptic, locked-period opens, portfolio, digest | write ideas, tune |

- **Files are the interface:** idea cards, queue jobs, the ledger, `DIGEST.md`. Sessions don't need to talk to each other.
- **Git:** each session commits only its own files. Ledger rows are committed by the gatekeeper once a day.
- **Where sessions run [P]:** engine, gatekeeper and testing run locally (the data is on the Mac). The literature and public-scripts lanes need only the web and the repo, so they could run as cloud sessions **once the repo has a GitHub remote**.
- **Max plan:** start with all lanes, but watch usage in week 1 and pause a lane rather than lower quality.
- **Without you present:** Python batches run around the clock; Claude sessions stop for permission prompts and at the end of turns. Plan for a daily check-in, not true 24/7 sessions.
- **Digest [D]:** `DIGEST.md` (the source), mirrored to a Notion page:
  - tests run, ideas by zone, real vs random, candidates, locked opens, blockers;
  - an Amsterdam-time stamp.

## 12. Build order and timeline (Amsterdam dates)
| when | Claude | user |
|---|---|---|
| **Fri 6 Nov** | project set up: repo, CLAUDE.md, this design, lanes, templates, agents | review the [P] items (§13) |
| **Sat 7 – Sun 8** | research store (convert, measure size and speed); cost table v1; engine core (orders, fills, costs) | — |
| **Mon 9 – Wed 11** | rules layer, trade log, unit tests; ledger, queue, runner; 5 referee strategies in Python and as cBots; extend the news calendar to 2014 | build the 5 referee cBots and run them in cTrader tick mode, **and export the 27 remaining symbols from FTMO's cTrader** (one evening; `runlists/`) |
| **Thu 12 – Fri 13** | referee comparison; random-strategy check (overnight batches); look-ahead reviewer | — |
| **Mon 16 – Tue 17** | freeze thresholds by addendum; sceptic review; **first real ideas tested** | read the sceptic report |
| **Late Nov – Dec** | pipeline running; weekly batch vs random | daily digest |
| **Jan – Feb 2027** | gatekeeper candidates → cTrader check → firm feed check → 1-week bot test | cTrader runs; buying decision per the buying plan |

**Honest timing:** "testing within a week" means the first real tests around 16–17 Nov, not 13 Nov. The days in between are the engine checks and the random-strategy check, the parts that would have saved VWAP. Lanes start writing cards on day one, so no time is lost on ideas.

## 13. Proposals waiting for the user's decision (before the first real test)
1. ~~**Research store** (§3.4): compressed ticks per month plus bars, research period only; locked period not converted.~~ **Decided 2026-11-08 (user): accepted as written**, fallback included.
2. ~~**Cost table v1** (§3.5)~~ **Decided 2026-11-08 (user), revised:** judged on FTMO's costs, IC's shown alongside; swap modelled from past rates + today's markup, oil flagged; stress run with positive swap at zero; user exports the other 27 symbols from FTMO.
3. ~~**News calendar back to 2014** (§3.6)~~ **Decided 2026-11-08 (user), extended:** union of all firms' high-impact lists, official dates back to 2014-11,
   ±6 min, two tiers, four news modes (discovery on M0, robust parameters on the worst of M0 / M2 / M3, firm eligibility by mode, same rules for
   random strategies), news flag at < 50%; oil stays.
4. ~~**Seen families** (§3.7)~~ **Decided 2026-11-08 (user), revised:** strict rule for VWAP-derived ideas (clean data only); RoboQuant ideas are normal, except repairs of a specific failed template.
5. ~~**Quick-screen starting thresholds** (§6.3)~~ **Decided 2026-11-08 (user), extended:** cut-offs as proposed, fixed slice list, raise-only adjustment; plus the recent-regime slice and the regime variation (§6.4).
6. ~~**G1 / G2 bars** (§6.6, §6.7)~~ **Decided 2026-11-08 (user), extended:** D2 values as a floor (raise only), count-adjusted bar in G1, drawdown per firm; plus the near-miss lane (§6.6a) with a stricter locked-period bar; TradeZella / Ergodic veto only.
7. **Target: ≤ 1% of random strategies reach the gatekeeper** (§8).
8. **Locked-period bar** (§9).
9. **Lanes in the cloud** for literature and public scripts, after a GitHub remote exists (§11).

## Addenda
(none yet)
