# Edge Research: design (v1, 2026-11-06)

> **Portfolio copy.** The working design of the Edge Research project as of 2026-11-17, including its dated addenda A1–A16. References to private planning files (capital plan, firm rulebook, venue models, logs) point to documents that are not included here. One line about specific personal trading accounts and one local file path have been removed; nothing else is edited.

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
  - **commission:** each venue's published rate. **FTMO FX confirmed 2026-11-10: $5.00 per lot round trip** (test trade on the FTMO trial,
    1 lot EURUSD: price result −$7.00, net −$12.00; statement `~/cTrader/Statements/Spotware/<statement>`);
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
| **Public scripts** | TradingView open-source scripts, public strategies, trading blogs; **X posts via the user's Strategy inbox** (no Instagram, TikTok or YouTube) | **highest** | ideas only: rebuilt from scratch, changed substantively, licence and source recorded on the card, never code copied. Many repaint or are showcases. Prop "own strategy" rules (`DESIGN-CONSTRAINTS.md` §10) |
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

## 8. The random-strategy check (null calibration) [D; target D 2026-11-08]
Before any real idea is screened:
- **1,000 random-entry strategies** (300 would make 1% only 3 strategies, too few to measure), matched to real ideas in trade frequency, hold time, stop and target style, symbols and class.
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
- **Built-in-edge strategies:** alongside the random ones, strategies with a known edge of **+0.05 R and +0.10 R per trade** go through the
  same pipeline, to measure how many real edges each target blocks.
- **Target [D 2026-11-08]:** the share of random strategies reaching the gatekeeper (through every route: amber budget, recent-regime route,
  near-miss lane, eligibility at any firm). **Default 1%.** It is **chosen with the user from the calibration's trade-off table**
  (0.5% / 1% / 2%: random through vs +0.05 R and +0.10 R through), before any real idea runs:
  - 0.5% if that blocks few real edges;
  - 2% only if 1% blocks most of the +0.10 R strategies.
  - Scale: per 100 ideas, 1% = about 1 false candidate; the locked period lets through about a quarter, so about 0.25 false finalist.
    At ~900 ideas a quarter that is about 2 false finalists a quarter, each costing about one evaluation fee before the kill rule.
    The luck bar rises as the ledger grows, and the weekly batch test checks real vs random.
- **One knob:** if too much noise gets through, the **count-adjusted (luck) bar** is raised first, not every bar a little. Turning many
  knobs to hit the target would itself be fitting.
- **The thresholds are frozen** in an addendum, the sceptic reviews them (shared rule: before every pre-registration), and only then do real ideas run.

## 9. The gatekeeper and the locked period [D: opened once per candidate]
- **The locked store doesn't exist until a candidate needs it.** `gatekeeper/open_locked.py <candidate>`:
  1. converts 2025-01-01 → latest for that candidate's symbols only;
  2. runs the **frozen** candidate (engine hash, card version, parameters fixed by the last walk-forward window's rule);
  3. writes the result to the ledger;
  4. logs the open in `gatekeeper/OPENS.md`.
  A candidate can't be changed after its open. A fail is final for that idea, and its family is noted.
- **Before the open:** the `oos-sceptic` agent reviews the candidate (ledger history, count, card, look-ahead review, stress), and its report goes to the user unedited.
- **Locked-period bar [D 2026-11-10]**, checked in each firm's news mode (as eligibility):
  - net after costs > 0;
  - expectancy per trade at or above the walk-forward's 10th percentile (a near miss: the walk-forward **median**, §6.6a);
  - drawdown inside the walk-forward Monte Carlo 95th percentile.
  - Power, honestly (normal approximation, walk-forward found +0.10 R): zero edge passes about 37% at 60 trades a year, 23% at 120, 9% at 250;
    a real edge of the walk-forward's size passes about 73%; a real edge half that size about half the time. This filters; it doesn't prove.
    Slow strategies get the weakest test here, which is why the random-strategy check and the luck bar come first.
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
- **Where sessions run [D 2026-11-10]:** engine, gatekeeper, market logic and testing run locally (the data and the ledger are on the Mac).
  The **literature lane runs as a cloud session** (public scripts: local, see below) from the private GitHub repo, can be scheduled, and push idea cards only
  to their own branch (`lane/literature`, `lane/public-scripts`); the gatekeeper reviews and merges them daily. A cloud session never touches
  the ledger, the engine or `main`.
- **Strategy inbox [D 2026-11-10]:** a Notion database the user fills from the phone (link, a line of notes, source). The public-scripts lane
  reads it daily. **Sources: X posts and anything else the user comes across** (blogs, papers, scripts). Instagram, TikTok and YouTube are
  dropped (user): what is useful there usually exists as a blog, paper or script. Claude can't browse X (login, terms, paid API), so the lane
  builds each card from what the post points to, read **directly at its source**. Inbox cards are data-mined, face the highest bar and count as tests.
- **Operations plan [D 2026-11-11]:** sessions, models, sources per lane, source shares with the week-6 review, daily rhythm and timeline are in
  `OPERATIONS.md`. Change from above (user): the **public-scripts lane runs locally**, not in the cloud (TradingView pages need a real browser).
  X is deferred to the week-6 review.
- **Max plan:** start with all lanes, but watch usage in week 1 and pause a lane rather than lower quality.
- **Without you present:** Python batches run around the clock; Claude sessions stop for permission prompts and at the end of turns. Plan for a daily check-in, not true 24/7 sessions.
- **Digest [D]:** `DIGEST.md` (the source), mirrored to a Notion page:
  - tests run, ideas by zone, real vs random, candidates, locked opens, blockers;
  - an Amsterdam-time stamp.

## 12. Build order and timeline (Amsterdam dates)
**Replaced 2026-11-11 by `OPERATIONS.md` §6.** The engine build had not started by 11 Nov (7–11 Nov went into the §13 decisions), so every date
moved about a week: research store, costs and engine core Thu 12 – Sat 14; rules, ledger, runner and referees Sun 15 – Tue 17; the user's
referee evening Wed 18 or Thu 19; referee comparison and random-strategy check Fri 20 – Sun 22; bars frozen and sceptic Mon 23 – Tue 24;
**first real ideas tested Wed 25 Nov**; week-6 review about Tue 6 Jan 2027; candidates and buying Jan – Feb 2027.

## 13. Proposals waiting for the user's decision (before the first real test)
1. ~~**Research store** (§3.4): compressed ticks per month plus bars, research period only; locked period not converted.~~ **Decided 2026-11-08 (user): accepted as written**, fallback included.
2. ~~**Cost table v1** (§3.5)~~ **Decided 2026-11-08 (user), revised:** judged on FTMO's costs, IC's shown alongside; swap modelled from past rates + today's markup, oil flagged; stress run with positive swap at zero; user exports the other 27 symbols from FTMO.
3. ~~**News calendar back to 2014** (§3.6)~~ **Decided 2026-11-08 (user), extended:** union of all firms' high-impact lists, official dates back to 2014-11,
   ±6 min, two tiers, four news modes (discovery on M0, robust parameters on the worst of M0 / M2 / M3, firm eligibility by mode, same rules for
   random strategies), news flag at < 50%; oil stays.
4. ~~**Seen families** (§3.7)~~ **Decided 2026-11-08 (user), revised:** strict rule for VWAP-derived ideas (clean data only); RoboQuant ideas are normal, except repairs of a specific failed template.
5. ~~**Quick-screen starting thresholds** (§6.3)~~ **Decided 2026-11-08 (user), extended:** cut-offs as proposed, fixed slice list, raise-only adjustment; plus the recent-regime slice and the regime variation (§6.4).
6. ~~**G1 / G2 bars** (§6.6, §6.7)~~ **Decided 2026-11-08 (user), extended:** D2 values as a floor (raise only), count-adjusted bar in G1, drawdown per firm; plus the near-miss lane (§6.6a) with a stricter locked-period bar; TradeZella / Ergodic veto only.
7. ~~**Target: ≤ 1% of random strategies reach the gatekeeper** (§8)~~ **Decided 2026-11-08 (user), revised:** 1,000 random strategies plus built-in-edge strategies; target chosen together from the trade-off table (default 1%) before any real idea; one knob (the luck bar).
8. ~~**Locked-period bar** (§9)~~ **Decided 2026-11-10 (user):** net > 0, average ≥ walk-forward 10th percentile (near miss: median), drawdown inside the 95% range, per firm mode.
9. ~~**Lanes in the cloud** (§11)~~ **Decided 2026-11-10 (user):** literature and public-scripts lanes in the cloud on their own branches; Strategy inbox in Notion for X posts and other finds; Instagram, TikTok, YouTube dropped.

**All nine proposals decided (2026-11-10). Operations plan decided 2026-11-11 (`OPERATIONS.md`). Next: setup and the engine build.**

## Addenda

### A1 (2026-11-11, user): sources that show locked-period results
Written before any test. Found when the research lane's source for IDEA-2001 (Concretum, version of Sep 2025) showed Jan–Aug 2025 results.
Papers, blogs, script pages and posts published after 2024 often report 2025–2026 performance, so this will recur.
1. **Lanes never record** returns, Sharpe ratios, trade outcomes or charts for any date after 2024-12-31 from a source, on the card or
   anywhere in the repo. When a source shows them, the card gets **`locked period seen: yes`** with the source and the months it covers
   (no numbers, no direction). A lane checks every source dated after 2024 for this.
2. **Public scripts:** never open a TradingView strategy tester or performance tab; a performance snapshot on the script page counts as
   seen, flagged with its date.
3. **The locked-period open still runs** for a flagged candidate, with the same bar (§9). A fail is final, as always. A pass is labelled
   **"not independent"** in `gatekeeper/OPENS.md` and the ledger, and counts as the deciding out-of-sample proof only through its
   **unseen remainder**: the months after the last month the source showed. The candidate needs net > 0 after costs on that remainder too.
   If the remainder holds fewer than 30 trades, the sceptic says so, and the go-live decision is the user's with that in view; the 1-week
   bot test and the firm feed check then carry the weight.
4. **The sceptic checks the flag** before every locked-period open (agent attack 1).
5. **Claude's own knowledge runs to mid-2026** and can't be switched off. No lane chooses symbols, direction, parameters or a family because
   of how markets behaved after 2024; every card's reason must hold with 2014–2024 knowledge alone. The sceptic asks this for every candidate.

### A2 (2026-11-11, user: "Yes, both"): oil swap cap; 2025+ spreads for cost measurement only
Written before any test; changes §3.5.
1. **Oil: positive swap capped at 0** in every run, for all history (FTMO and IC). Today's positive long swaps (FTMO Brent +18%/yr, IC Brent
   +48%/yr, WTI +3.7% / +8%) are a backwardation snapshot; in the contango years of 2014–2024 longs paid. Negative swaps stay as modelled
   (today's swap as a share of price, flagged). G2's "positive swap = 0" is unchanged and now also covers oil by construction.
2. **2025+ spreads, cost measurement only.** The engine owner, and no other session, may read FTMO and IC ticks after 2024-12-31 for
   **XAGUSD, EU50 (IC STOXX50), JP225, Brent (XBRUSD / UKOIL.cash) and WTI (XTIUSD / USOIL.cash)**, because FTMO's history for them starts
   2025-06. One script (`engine/spread_2025.py`) computes **only spread statistics** (median and percentiles, in bp of price and in
   points, overall and per New York hour). It never outputs or stores prices, returns, ranges, volatility or charts. The script and its
   output (`data-checks/spreads-2025-26.json`) are committed and logged. The add-ons it gives replace the proxies in the cost table
   (new engine hash). The research store still holds nothing after 2024; no other session reads this data.

### A3 (2026-11-12, user: "Approve A3"): pipeline mechanics the design left open
Written before any test and before the random-strategy check; the sceptic reviews it with the frozen thresholds. Applies to real and random
strategies alike.
1. **Amber variation (§6.4).** Each variation reruns the quick screen (full research period, defaults plus its one added filter). If it
   lands green it goes on to tuning and walk-forward; its pass / fail comes only from walk-forward. Random strategies also get:
   - the **recent-regime slice** (2021-01 → 2024-12) on the fixed slice list;
   - the **regime-variation route**, with a start date drawn from this fixed list (external, dated reasons): **2018-02** (volatility
     shock, end of the short-volatility regime), **2020-03** (COVID crash, zero rates and QE), **2022-03** (Fed hiking cycle begins),
     **2022-05** (Tuesday / Thursday daily expiries for US index options). Walk-forward is then judged from that date (§6.4);
   - the **near-miss lane** (§6.6a).
2. **Walk-forward training score (§6.6).** Per grid point: total net R after FTMO costs in the 24-month training window, in the **worst**
   of news modes M0, M2, M3. Then the average over the point and its ±1-step neighbours in each dimension (fewer at the grid edges). The
   best average wins. Total net R, not the mean per trade.
3. **Walk-forward mechanics.** Each grid point runs once over the full research period; trades go to train / test windows by entry time;
   the chosen point's test-window trades are stitched together. Approximation, stated: a position opened under one window's parameters
   stays in that window's accounting, and a parameter switch applies only to new entries.
4. **"Trend vs range" slice (§6.3).** Trend when, on the last **closed** h4 bar at the entry's decision time, |close − SMA(200)| >
   2 × ATR(14); otherwise range. The share of h4 bars in each state per symbol is reported (a data description) before any idea uses it.
5. **"Bloc" slice (§6.3), in this order:** XAU / XAG → metals; WTI / Brent → oil; indices → equities; other pairs containing USD → USD;
   crosses without USD → no bloc.
6. **Random-strategy profiles (§8).** Half drawn from the declared profiles of all committed idea cards at generation time (trades per
   year, class, timeframe, symbols, stop / target style, grid size), half from a broad spread (trades per year 50 / 150 / 400; class A / B / C;
   stop 1–3 ATR; target 1–3 R, none, or a time exit; 1–4 of the 39 research symbols; m15 / h1 / h4; amber filters from the menu: session,
   volatility third, trend). Seeded; the seed and the card snapshot (ids and versions) are committed before the run. The batch covers
   all of §8: screen, amber budget, tuning, walk-forward, G2 stress, eligibility per firm news mode, and the built-in-edge strategies
   (+0.05 R and +0.10 R per trade).

### A4 (2026-11-12, user: "Yes, replace it"): the single-symbol share bar in G2
Written before any test and before the random-strategy check. Found in the engine owner's smoke test: as worded, "no single symbol carries
more than half the P&L" (§6.7) fails every 1-symbol strategy (100%) and nearly every 2-symbol one, even with an equal edge (50.1% and
54.3% in the smoke test).
1. **Replaced by: without its best symbol, the strategy is still net positive after costs** (≥ 2 symbols in the declared list). With 2
   symbols this means both make money; with more, the rest make money without the best one.
2. **1-symbol strategies:** the test doesn't apply; the strategy is labelled **"single symbol"** in the ledger and the portfolio, and its
   concentration is judged by the portfolio check (§9: correlation, shared losing days).
3. It stays a **safety bar** (§6.6a: never a near miss). Known trade-off: with 4 or more symbols it is looser than the old bar (one symbol
   at 80% with the rest slightly positive passes); the built-in-edge strategies in the calibration show what it lets through.
4. **Noise test, "signals ±1 bar" (§6.7), added the same day (user: "Approve, per symbol"):** signals shift **later only** (+1 bar). Moving an
   entry one bar earlier gave it the later bar's stop, target and level (a look-ahead found by the engine owner, E1): easier for
   breakouts, harder for fades. The jitter of prices by up to 1 spread is unchanged.
5. **"Trend vs range" threshold (A3.4), added the same day:** trend when |close − SMA(200)| > **k_symbol** × ATR(14) on the last closed h4
   bar. **k_symbol = that symbol's median** of |close − SMA(200)| / ATR(14) over closed h4 bars **2014-11 → 2016-10** (before the first
   walk-forward test window; price data only, no strategy result). A symbol with fewer than 12 months of h4 bars in that window uses the
   pooled median of the 39 research symbols, **k = 3.56** (measured 2026-11-12; with k = 2 the window was 70.5% trend). Per-symbol medians
   ran from 2.42 (CADCHF) to 4.76 (GBPJPY), which is why one shared k would sort symbols rather than conditions.

### A5 (2026-11-12, user: "ok, I approve all your recommendations"): news calendar scope and defaults
Written before the random-strategy check and before any test; changes §3.6. Raised by the engine owner while building the calendar
(`news/REPORT-usd-eur-gbp.md`).
1. **Which lists set the research blocks.** Tier-2 events = the union of **ForexFactory high-impact (red), FTMO's restricted list and
   FundingPips' dashboard list**. Event types that only **FXStreet** (Instant Funding, funded accounts only) or **Myfxbook** (Aqua, which
   caps news profit and doesn't breach) list are left out of the research modes. They are tagged per firm and checked in the firm
   simulation (§10), where they can only **remove** a firm's eligibility, never add it. So a pass in a mode stays valid at every firm
   that uses that mode.
2. **Speeches (Fed Chair, ECB President, BoE Governor, and any other red ForexFactory speech):** start time from the official source
   (central bank calendar, video or transcript) where one exists; otherwise the §3.6 rule for events without a fixed time: the bank's
   usual range for that day. Collected in the background with the rest of the calendar; the calendar is final before the calibration.
3. **Press conferences without an official end time:** default **75 min** (not 60); FOMC press conferences run 60–65 min. Speeches stay
   at 60 min and testimony at 3.5 h. Each event stays marked "official" or "assumed".
4. **ISM dates** derived from ISM's own rule (manufacturing: first business day, services: third, 10:00 ET) because its archive needs a
   login; marked "derived". Each is cross-checked against the saved ForexFactory pages; where they differ, **both dates are blocked**.

### A6 (2026-11-12, user: "Yes, do it now. Same for all three."): speeches, press conferences and testimony at the research standard
Written before any real idea has a result. The random-strategy run started at about 20:50 under the old rule; it is stopped and its partial
output is not used. The calibration reruns in full with the same plan and seed on the new engine hash. Changes §3.6 ("block from T−6 until
5 min after the end", user's method of 2026-11-08) and A5.3.
1. **Research modes M1–M3:** speeches, press conferences and testimony with an **official start** are blocked **T−6 → T+6 around that
   start**, like every other tier-2 event. The research window no longer runs to the event's end.
2. **Unchanged:** events without an official start keep the window over the whole usual range (A5.2; committee appearances 08:00–20:00
   local, user 2026-11-12); ISM mismatches keep both dates blocked (A5.4); the far-stop exemption is unchanged (thresholds rebuilt on the
   new windows).
3. **Why:** of the six firms, only FundingPips blocks a speech until its end (funded Master: "until 5 min after the end"); FTMO doesn't
   restrict speeches, Instant Funding, BrightFunded and Aqua block a fixed ±4–5 min around the calendar time, Fintokei nothing. Tuning
   every strategy on one firm's rule (robust parameters on the worst of M0 / M2 / M3, §3.6 rule A) bends all parameters for one firm.
4. **FundingPips' whole-event rule moves to where firm rules belong:** the FundingPips firm simulation (§10), which can only **remove**
   FundingPips eligibility, and the FundingPips live cBot. Window: T−6 → 5 min after the end, for speeches, press conferences and
   testimony; the end from the official record where it exists, else assumed **90 min** (speech, press conference) or **3.5 h**
   (testimony). FundingPips names no source for a speech's end (its dashboard shows a start only); the user may ask FundingPips directly,
   and its answer goes into `rulebook/FUNDINGPIPS.md` with the date.
5. **Cost, stated before any result:** a live FundingPips account skips trades during speeches that research didn't remove; the firm
   simulation reports that cost per strategy.

### A7 (2026-11-13, user: "Yes, after costs"): built-in edges in the random-strategy check are net of costs
Written before any real idea has a result. Changes §8 ("a known edge of +0.05 R and +0.10 R per trade", which didn't say before or after
costs). Raised by the engine owner after the first full run (`3ce6a6d`): the edge was added before costs, and random entries with ATR stops
pay about 0.15 R a trade, so a "+0.10 R" strategy netted about −0.03 R (median) and blocking it was correct, not a sign of strict bars.
1. **The built-in edges are +0.05 R and +0.10 R per trade after FTMO costs:** each edge strategy's planted edge = x + that strategy's own
   measured cost per trade (spread, commission, swap, slippage from its screen run), so its expected net result is x per trade.
2. **Rerun only the 200 edge strategies,** same plan and seed (`null/PLAN.json` from `8abc040`), same engine hash. The 1,000 random
   strategies and their result stay as run (0 of 1,000 reached the gatekeeper). The first run's edge rows stay in the ledger, labelled
   "gross edge (pre-A7)", and are not used for the trade-off table.
3. The trade-off table (§8) is built from the 1,000 random strategies and the rerun edge strategies.

### A8 (2026-11-13, user: "Yes, fix it"): class A and B are flat before every market break of 2 h or more
Written before any real idea has a result. Corrects the engine and the cBot to the §5 table ("A: flat by 22:45 Amsterdam. B: flat
before the weekend"), which both implemented as a fixed 22:45 Amsterdam time. Found by the cBot test run R1 (2026-11-13): in the weeks
when only the US is on summer time (about 3 in March, 1 in Oct / Nov) the FX market closes on Friday at 17:00 New York = 22:00 Amsterdam,
before 22:45, so class A and B positions open at the close were held over the weekend (3 times in R1; about 4 weekends a year in research).
1. **Class A:** flat every day at **22:45 Amsterdam or 5 min before the symbol's session close, whichever is earlier**, when that close
   starts a break of 2 h or more (weekend, holiday, early close). Daily breaks under 2 h don't move it.
2. **Class B:** flat at the same time on the **last trading session before every break of 2 h or more** (normally Friday; also before a
   holiday closure of the symbol).
3. Session closes come from the exported trading hours the engine already uses for the 2-h pre-close entry block (§5 table, entries).
4. **Consequence:** new engine hash, so the random-strategy check reruns in full (1,000 random + 200 edge strategies, A7 net edges, same plan
   and seed). The runs on engine `504406fbaacd` stay in the ledger and are not used for the trade-off table.
5. **Amended 2026-11-13, before any result on the new engine (replaces item 3):** the exported trading hours are one fixed weekly
   schedule (cTrader's backtest `TimeTillClose`), so they miss DST shifts and holiday early closes (engine owner: FX on Fri 15 Mar 2024
   scheduled 22:57 Amsterdam, last tick 21:56; US500 holiday early closes last tick 19:14 vs scheduled 21:59–22:59). **Closes come from
   the ticks:** close = the scheduled close if it falls within 1 min after the last tick before a gap, otherwise the last tick + 1 min; a
   break is reopen − close ≥ 2 h. The 2-h pre-close entry block uses the same closes.
6. **Class B means weekends and holidays, as the user approved ("before the weekend or a holiday"):** class B flattens before every break
   of 2 h or more **except the symbol's regular daily break** (a break that starts on a weekday within 1 h of the symbol's usual close for
   that weekday and ends within 1 h of its usual reopen the next weekday; e.g. STOXX50, F40, AUS200, HK50, XBRUSD overnight). Class A
   flattens before every break of 2 h or more, daily ones included, and at 22:45 Amsterdam at the latest.
7. **Unscheduled gaps** (breaks of 2 h or more that are no weekend, holiday, early close or regular daily break: data outages) are treated
   as closes, a small look-ahead; the engine owner reports their count per symbol before the calibration rerun.
8. **Unscheduled gaps, measured 2026-11-13 (engine owner, `49bb545`):** 508 of 32,512 breaks of 2 h or more (2014-11 → 2024-12, 42
   symbols) are no weekend, holiday, early close or regular daily break: FX 2 per pair (two feed outages), and data holes on some plan
   symbols in May–Jul 2015 and Sep–Dec 2017. On the pre-A8 screen trades they touch 0.29% of class B and 0.04% of class A trades.
   **Kept as closes** (gatekeeper's call, below the A8.7 threshold in effect): the engine stays as it is. **Guard:** before a candidate's
   locked-period open, the gatekeeper counts its trades flattened at an unscheduled gap; if they are more than 1% of its trades or more than
   10% of its net R, its walk-forward is recomputed without that flatten before the open.
   Regular daily break, as implemented: a break that starts Mon–Thu and matches at least 3 of the symbol's gaps of 30 min or more in the
   previous 14 days (close and length each within 61 min); past data only.

### A9 (2026-11-13, user: "if there is an edge, it needs to reach the Gatekeeper. It doesn't matter if the drawdown is too high"): drawdown is a deployment question, not a G1 bar
Written after the calibration rerun on engine `8086385d1f5f` (synthetic strategies only), before any real idea has a result. The user's
rule: an edge reaches the gatekeeper whatever its drawdown; which strategies go live, and at what size, is decided when the portfolio is
built ("If one has too big of a drawdown but does have an edge, we just don't deploy it live").
1. **The G1 drawdown bar** (§6.6: Monte Carlo 95th-percentile drawdown ≤ 70% of the firm's max loss at funded risk) **is no longer a
   pass / fail bar** and no longer decides firm eligibility. G1 still computes it in every news mode and reports, per firm, the **fit
   risk**: the largest risk per trade at which the Monte Carlo 95th-percentile drawdown stays ≤ 70% of that firm's max loss.
2. **Where drawdown is judged instead:** the portfolio contribution check (§9) and the step from strategies to accounts (§10), on balance
   and equity drawdown, with each strategy at its fit risk or lower. A strategy whose fit risk is too small to be useful reaches the
   gatekeeper and is recorded, but is not deployed.
3. **Objection on record:** this lowers a §6.6 floor, which §8 lets the random-strategy check only raise. It is the user's decision with
   that in view. The numbers it rests on (rerun report, `null/REPORT.json`, d0a5ca9): only 2 of 1,000 random strategies reached G1 at all,
   both failing other bars, so the drawdown bar did no noise filtering; without it 0 random strategies pass G1. It blocked real edges:
   recomputed on the same results, G1 passes go from 29% to 62% (+0.05 R net) and from 26% to 74% (+0.10 R net).
4. **Unchanged:** the locked-period drawdown check (§9: drawdown inside the walk-forward Monte Carlo 95th percentile; it compares a
   strategy with itself), all other G1 and G2 bars, the firm simulation (§10).
5. **Consequence:** the engine owner changes G1 (new engine hash, logged), runs the G2 stress tests for the routes that become eligible,
   and recomputes the verdicts and the trade-off table. Screen, amber and grid rows are reused only if the engine owner shows the kernel's
   results unchanged (a re-run sample, logged); otherwise the check reruns in full.
6. **Luck bar (§7), for the freeze:** the rerun report built it from the random strategies' Sharpe after costs (mean −1.93, spread 1.58,
   of which most is cost: Sharpe vs log trade count correlates −0.70; luck alone about 0.78). That sets it at the wrong level and width.
   It is built instead from the random strategies' unseen daily Sharpe **before costs** (zero edge by construction), same normal fit, and
   the trade-off table is reported with it applied at k = 10, 100 and 1,000 effective ideas. Its values are fixed in the freeze addendum
   and reviewed by the sceptic with the other thresholds.

### A10 (2026-11-14, user: "Yes, freeze"): the frozen thresholds
Written after the random-strategy check on engine `1b88e14daa9f` (report `673f1d7`, grid factor `73bd17c`), before any real idea has a
result. From here the thresholds below change only by a later dated addendum, never for an idea whose result is seen.
1. **Bars frozen as the floors in `engine/thresholds.json`** (screen §6.3, walk-forward §6.6, stress §6.7, near-miss lane §6.6a), with A4
   and A9 in force (no G1 drawdown bar; fit risk reported per firm). The check raised none: 0 of 1,000 random strategies reached the
   gatekeeper (one-sided 95% upper bound about 0.3%), against 36% of +0.05 R and 55% of +0.10 R net edges before the luck bar.
2. **Noise reference 0.5%** (`null.target_share` 0.005): the share of random strategies reaching the gatekeeper that the weekly batch test
   (§7) compares real ideas with.
3. **Luck bar (count-adjusted bar, §7) in G1, per news mode:** the daily Sharpe of the stitched unseen log must be
   ≥ μ0 + σ0 · Φ⁻¹(0.95^(1/k)), with μ0 = −0.039 and σ0 = 0.354: the unseen daily Sharpe at mid prices of the 1,000 random strategies
   (zero edge by construction; σ0 = 1/√8.17 unseen years, pure sampling error). No near miss on it. G1 stores k and the bar's value.
   - A route judged from a regime date uses σ0 · √(8.17 / its unseen years).
   - Reference values: k = 1 0.542, 10 0.869, 100 1.122, 1,000 1.334, 3,000 1.426.
4. **k, counted from the ledger when G1 runs.** Only real rows count (lane not null or referee); locked-period opens never count.
   - **Normal ideas:** k = the sum over every real idea with at least one screen row (the judged idea included) of k_eff for each of its
     screened routes (the base and each amber variation). k_eff(N, ρ) is the number of independent zero-edge tries whose best has the
     same 95th percentile as the best of N points at mean pairwise correlation ρ (simulated, `tools/nullstats/grid_factor.py`). ρ is
     the mean pairwise correlation of that route's grid points' unseen daily R at mid prices once its grid rows exist, else 0.688 (the
     null's stop / exit grids: k_eff 2.23 / 4.80 / 5.81 / 9.82 for 3 / 9 / 12 / 27 points).
   - **Data-mined ideas and seen families (§3.7):** k = the number of real test rows in the ledger at that moment, the judged idea's
     included.
   - The card fields "data-mined" and "seen family" must read exactly `yes` or `no`; the pipeline refuses any other value. IDEA-2008's
     "partly" counts as yes.
   - The smallest k an idea faces is the k_eff of its own grid.
5. **Expected power with the luck bar** (calibration, before the stricter counting in items 3–4): +0.05 R net reaches the gatekeeper 30 /
   25 / 18% at k = 10 / 100 / 1,000; +0.10 R net 54 / 51 / 45%; random 0%.
6. **Order:** the engine owner implements items 2–4 (thresholds status "frozen", new engine hash, unit tests), the `oos-sceptic` reviews
   the frozen thresholds (shared rule), its report goes to the user unedited, and only then does the first real idea run.
7. **Correction (2026-11-14, before any real result):** k_eff(N, ρ) is computed exactly by quadrature (engine `ebf01605a2fe`); at ρ
   0.688 it gives 2.26 / 4.82 / 5.83 / 9.80 for 3 / 9 / 12 / 27 points. The values in item 4 came from a 200,000-draw simulation and
   differ only by its noise (a 5,000,000-draw check gives 2.257 and 4.813). Cards carry the strict rows from `ideas/TEMPLATE.md`; the
   explanations moved to "seen family, why" and "data-mined, why" rows, values unchanged in meaning (IDEA-2008 "partly" → yes).

### A11 (2026-11-15, user: "Yes, all three"): the sceptic's gate-1 BLOCK resolved
Written after the `oos-sceptic`'s gate-1 report (`gatekeeper/sceptic/2026-11-14-gate1-thresholds.md`, VERDICT BLOCK), before any real
idea has a result (0 real ledger rows). Two items fix errors (no bar is lowered); the rest only make bars stricter or add reporting.
1. **Amber is judged before costs, as §6.3 says** (objection 1, BLOCK). The amber t ≥ 1.5 test uses R at mid prices (`r_mid`; for the
   synthetic strategies `r_mid` + their planted edge), not R after the spread (`r_gross`). The slice route ("one slice green on its
   own") stays after costs. Consequence for the random-strategy check: the engine owner re-derives every strategy's zone from the
   existing trade files, runs the amber variations, grids, walk-forward and stress for the strategies whose zone changes, and reports
   the amber share, the rescue share and the share reaching the gatekeeper with the A10 luck bar. **Raise-only follow-up:** if more than
   10% of random strategies land amber, the amber cut-off is raised (§6.3); if more than 0.5% reach the gatekeeper, the luck bar is
   raised (§8, one knob). Either goes in a dated addendum before the first real G1. Sceptic's estimate: random amber 0.3% → 4.8%,
   +0.05 R 77% → 92%.
2. **Hold-time fail applied** (objection 2, BLOCK; §4.2 as written): in every G1 news mode, more than 10% of trades held under 2 minutes
   fails the route. It is a safety bar (no near miss), with a unit test. **Walk-forward default** (objection 11): a training window with
   no trades selects the card's default parameters, not the first grid point.
3. **Source-sample overlap** (objection 4). Every card carries two strict rows:
   `| source overlap | yes/no |` and `| source overlap, why | <sources, their sample months inside 2016-11 → 2024-12, defaults from the source yes/no> |`.
   - **yes** when any cited source's sample covers any month of 2016-11 → 2024-12, or the card's defaults or parameter ranges come from
     such a source; also yes when the card cannot say (a source with no stated sample, a public script with no stated test period).
     **no** only for own reasoning that cites no tested sample.
   - **An overlapped idea counts like a data-mined one:** k = the number of real test rows in the ledger at that moment (A10.4).
   - The value must read exactly `yes` or `no`; the pipeline refuses anything else. The ledger and the candidate report carry it.
   - At the locked-period open the sceptic treats an overlapped candidate as "walk-forward = in-sample" and states its locked-period
     power; the go-live decision is the user's with that in view.
4. **Luck bar, stricter** (objections 5–8):
   - **μ0 = 0** (was −0.039): the bar is σ · Φ⁻¹(0.95^(1/k)).
   - **Serial correlation:** σ = σ0 · √(8.17 / the route's unseen years) · max(1, √VR), where VR is the Newey–West long-run variance
     of the stitched unseen daily net R (Bartlett weights, lag ⌊4 (T/100)^(2/9)⌋) divided by its plain variance. Stored with k and the bar.
   - **Re-applied before every locked-period open:** `open_locked.py` refuses to open unless the candidate's stored G1 daily Sharpe
     still clears the bar at the k in the ledger that day (same σ). A candidate that no longer clears is recorded as failing the luck
     bar at open time; its locked period stays closed.
   - **Card fields pinned to the first screen row:** "seen family", "data-mined", "source overlap" and "grid size" are read from the
     idea's first screen row for every k count. A later card change to them has no effect on k.
   - **Stress re-checks** (`swap0`, `fx2015`) use the same k and σ as the route's G1 (unit test).
5. **Weekly batch test** (objection 3): besides the 0.5% random reference, it reports the cost-neutral null (the 1,000 random
   strategies at `r_mid`: green at the screen, at least one green route, through the G1 bars before the luck bar; the sceptic's proxy
   0.9% / 8.7% / 5.6%) next to the real ideas' rates at the same stages, and the number of locked opens per quarter next to the expected
   false finalists.
6. **Before the first G1:** A10 and items 1, 2 and 4 committed with a new engine hash (logged), plus an end-to-end test of the
   real-idea route (screen → tune → G1 with the ledger's k). The sceptic re-checks only these fixes; its report goes to the user unedited.
7. **On record, not adopted as bars:** measured power is optimistic (planted edges are steady and added after the price path; at the
   k a quarter brings, +0.05 R reaches the gatekeeper about 11% of the time, +0.10 R 36–39%); a realistic-edge power run (synthetic
   only) can run any time. Short-history routes (e.g. DE40-only, about 1.3 unseen years) need an active Sharpe near 3.8 at k ≈ 10,000,
   so in effect they cannot pass; the lanes are told. Fit risk from a block bootstrap comes with the firm simulation (§10).

### A12 (2026-11-15, user: "Yes, watch list"): IC-only edges are listed, not advanced
Written after batch 1's screens (13 real rows), where 2001 and 3000 are amber at FTMO's costs and roughly green at IC's. Information
only: no bar, zone, route or count changes, for any idea.
1. **Pass or fail stays on FTMO's costs** (§3.5, decided 2026-11-08). Nothing below moves an idea forward.
2. **IC watch list** (`gatekeeper/IC-WATCH.md`, built by `gatekeeper/ic_watch.py` from the trade files): every real screen and
   amber-variation row whose result would be green by the §6.3 green test on `r_net_ic` (IC's costs) but is not green on FTMO's,
   with both numbers and the note "edge in the market, not deployable at FTMO costs". IC's numbers are approximate: the trades are
   simulated with FTMO's wider spread.
3. **It adds nothing to k** and is not a test (it re-reads existing trade files; no runner job, no ledger row). It is refreshed with each
   batch report.
4. **Use:** if a cheaper venue becomes real (a raw-spread firm or the user's own account, CFD plan §0), its rules come by a new dated
   addendum, written and reviewed by the sceptic before any idea is judged under it. Entries already on the list were seen before that
   rule, so they count as seen results under it (k = real test rows, like data-mined), never as clean.

### A13 (2026-11-17, user: "Commit A13"): volume profiles over a full session are allowed; other tick-volume uses stay parked
Written after the engine owner's two data checks (`data-checks/volume-profile/`, ee21ad3; no ledger rows, engine unchanged) and before
any volume-profile card exists. It narrows §5's "volume-based ideas are parked" for one use only. No bar, zone, route or count changes.
1. **Evidence and its limit.** IC vs FTMO daily tick profiles, 28 FX pairs, 2020-04 → 2021-07 (9,072 days): bin-share correlation 0.992,
   POC in the same bin 85%, the part TPO doesn't explain correlates 0.94 across brokers; where IC's tick POC differs from its TPO POC,
   FTMO's POC sits on IC's tick POC 74% of the time and on the TPO POC 16%. Tick vs TPO on IC (2014–2024): cash session correlation
   0.97–0.98 (POC within one bin 89%), full day 0.87–0.97, week 0.94–0.98. So tick-count profiles measure a market-wide quantity, and
   they differ from TPO mainly over a full day or a week. **Not shown:** that tick count is traded volume (no futures volume to compare),
   or that any level predicts anything.
2. **Allowed:** a **volume profile** (tick count per price bin, from `bars["vol"]`) built over **at least one full session**: a stated
   cash session, a full 24 h day, or a week; composites of whole sessions are fine. The card states: IC tick count is a proxy for
   activity, not traded volume; the session (cash or 24 h, with its clock); the bin size in ATR units; and that a profile is final only
   at its session's last closed bar (a developing profile may be used only as of closed bars, and the card says so).
3. **One family with its TPO twin (k).** Every volume-profile card names its **TPO twin** (the same rule on a price × time profile)
   and picks one of the two as its default. The other may run only as one of the card's at most 3 amber variations (§6.4), never as a
   second card. A twin that already has a screen result is a seen result: a red twin is final (§6.3), so its volume version is not a
   new card; an amber twin may take the volume version as one of its own variations, under its existing budget.
4. **Still parked (§5):** every other use of tick volume: intraday or daily volume levels, volume pace or surges, volume filters, and
   volume-weighted indicators (CCI, MFI, OBV and the like). IDEA-2010, 3007 and 3010 stay held; IDEA-2011 is unblocked only through its
   v2 (volume filter removed). A tick-volume VWAP (weekly or other) is **not** covered here; it is decided with the VWAP discussion.
5. **Checks:** the look-ahead review and the gatekeeper runs treat a module that reads `bars["vol"]` as a hold unless its card is a
   volume-profile card under 2–3; the reviewer checks that the profile uses only closed bars of whole sessions as stated.

### A14 (2026-11-17, user: "yes on the cftc"; context symbols from "I want to do everything you just proposed"): other markets and outside series as inputs
Drafted in `gatekeeper/A14-DRAFT.md`; the sceptic's review (`gatekeeper/sceptic/2026-11-17-A14-draft.md`) passed these two parts with
conditions, all included below. The mining lane (the draft's §3) is **not** part of A14: it was blocked and is decided separately. No bar,
zone, route or count changes for any idea already screened.

**1. Context symbols.**
1. A card may declare up to **3 context symbols** from the research store in the row `| context symbols | … |` (or `none`); none may be a
   traded symbol of the card. They are inputs only, never traded, never a grid axis. The runner refuses a job whose context differs from
   the card's row in either direction.
2. The module gets `ctx["context"][SYM]` arrays aligned to the traded bars at the same timeframe: element i is the last context bar whose
   close time is ≤ traded bar i's close time, with that close time and the staleness age as arrays. Before the context history starts and
   inside its data holes (DE40 2021-09, oil 2017-07, the 2015 and 2017 holes) the value is NaN, never a stale back-fill. No raw context bars.
3. **No re-carding by swapping context:** a card that differs from an idea with a result only in its context symbols is one of that idea's
   amber variations (under its budget) or, if none is left, counts as seen (k = real test rows).
4. **FX context:** an idea with an FX context symbol runs the fx2015 stress test as an FX idea.
5. **Live:** a context symbol must be tradable-data available at every target firm (AUS200, F40, HK50, US2000 are data-only); the firm feed
   check includes the context feed. Before the first finalist with context symbols, one referee comparison with a context symbol (the cBot
   takes the last context bar whose open + timeframe ≤ now).
6. Look-ahead review check 9 (alignment, staleness, declared list). The engine hash changes; rows without context stay byte-identical,
   shown by re-running a sample of committed rows (§4.4).

**2. Outside series (CFTC Commitments of Traders first; rule-derived calendars).**
1. Allowed: public, free series with a **known release time**. Every value carries its release time (UTC) and is visible from the first
   bar that closes after it. COT release = the actual date of each report (holiday shifts, Oct 2013, the 2018–19 catch-up schedule),
   never "the Friday after the as-of date"; the later candidate where unsure. Friday 15:30 New York falls in the pre-weekend entry block,
   so the first usable entry is after the weekend.
2. Research series stop at release time ≤ 2024-12-31 23:59 UTC (unit test on the stored series). The 2024 files' as-of 2024-12-31 report
   (released 2025-01-03) is on disk only, outside the research store. Download and cut are logged.
3. **Vintage, a user-accepted exception (like A2):** CFTC's history files are current versions, re-posted after release (2022–2024 on
   2026-01-15), so they may contain corrections made in 2025–26. No free point-in-time vintage exists. Conditions: (a) before any COT card
   runs, the engine owner bounds the revision size by comparing the history files with point-in-time copies of weekly report pages
   (archived snapshots dated ≤ 2024, a few dozen, read one at a time); (b) cards prefer levels or ≥ 52-week percentiles over week-on-week
   changes near a threshold; (c) a raise-only G2 stress test perturbs COT values by that bound; (d) every COT card states "current vintage".
4. The card fixes, as inputs (not tuned): the report (Legacy / Disaggregated / TFF), trader category, contract mapping, futures-only or
   combined.
5. Not allowed: the news calendar as an entry signal (firm rule), paid or private data, series without release times. Rule-derived
   calendars (monthly options expiry, quarterly index rebalance and roll dates) are computed from published rules, no download.
6. Download approved by the user 2026-11-17: 45 futures-only annual files 2010–2024 (Legacy `deacot<YEAR>.zip`, Disaggregated
   `fut_disagg_txt_<YEAR>.zip`, TFF `fut_fin_txt_<YEAR>.zip`), 57.0 MB, from https://www.cftc.gov/files/dea/history/.
7. **Revision bound measured (2026-11-17, engine owner, `data-checks/cot/README.md`):** 91 point-in-time market-weeks from CFTC's
   own archive pages (7 markets, 10 position fields) are all identical to the stored history, including the 2022–24 files re-posted
   2026-01-15; 95% upper bound on the revised share about 3.3%. The 3(c) stress therefore has no measured size; it is set now, before
   any COT card runs, as a floor: every COT position value perturbed by ±1% (seeded random sign per value), raise-only, in G2.
8. **Also approved (user 2026-11-17, "Approve download"):** CBOE VIX_History, VIX3M_History, VIX9D_History (897,835 bytes, visible
   after 16:15 New York); FRED DGS3MO / DGS2 / DGS10 (refused automated requests on 2026-11-17; not stored yet).

### A15 (2026-11-17, user: "Yes, one sweep", "Yes, full period"): one mining sweep, its own ledger and its own luck bar
Drafted in `gatekeeper/A15-DRAFT.md`. Sceptic: v1 BLOCK (`gatekeeper/sceptic/2026-11-17-A15-draft.md`), v2 PASS WITH CONDITIONS
(`gatekeeper/sceptic/2026-11-17-A15-v2-recheck.md`); every condition is in 10. Nothing in the main pipeline changes.
**1. What it is.** One sweep of **N = 50,000 rules**, drawn once, then stopped and judged. A second sweep needs a new addendum, and then
k counts every mining rule ever drawn and unopened sweep-1 candidates are re-checked at that k.
1. **Spec.** The grammar is written in `mining/SPEC.md`: entry blocks (price-only breakouts, pullbacks, time-of-day, moving-average and
   oscillator conditions, ATR bands; A14 context-symbol and CFTC blocks), each block's parameter values, filters (session, volatility
   third, trend, bloc), stops 1–3 ATR, targets 1–3 R / none / time exit, symbol sets and timeframes from the A3 menu, class. The spec
   states its compliance with A1.5 (nothing chosen from post-2024 behaviour) and §3.7. **The sceptic reviews `SPEC.md` once before the
   draw.**
2. **Non-adaptive and bound.** The 50,000 rules are drawn by a seeded sampler before any result exists; the draw never depends on a
   result. Before the first job, commit the sampler code hash, the seed and the SHA-256 of the full 50,000-rule list (rule id +
   definition hash). The runner refuses any mining job whose rule id and definition hash are not on that list. One engine hash and one
   composer hash for the whole sweep; a change that alters results voids and reruns the whole sweep (k unchanged, 4). **No tuning:** each
   rule is judged at its drawn parameters.
3. **Excluded from the grammar:**
   - unbalanced rules: every block is mirror-symmetric (the short condition is the long condition on negated price); no `side` filter;
   - the `recent` slice and any regime start date;
   - any anchored average or band (session, day, week, intraday dual: the whole §3.7 VWAP family);
   - every use of tick volume (A13); time-of-day values derived from release times;
   - context symbols not tradable at the firms (AUS200, F40, HK50, US2000; A14.1.5);
   - CFTC blocks other than levels or ≥ 52-week percentiles (A14.2.3(b)); CFTC blocks only once the A14.2.3(a) revision bound is done.
4. **Overrides, stated (all for mined rules only):** §7 "one ledger" (own ledger, 2); §6.1 and CLAUDE.md "idea card first" (the
   committed spec and rule list stand in for cards); CLAUDE.md "every test … lands in the ledger" (mined tests land in `ledger-mining/`);
   §6.2 look-ahead review (the reviewer reviews every grammar block, the composer and the spec once, a seeded sample of 50 compiled rules,
   and every rule that reaches judging); §6.6 walk-forward (replaced by in-sample judging at full multiplicity, 3.3); §5 / §11 roles (7).
   The two CLAUDE.md lines are amended with the user's go.

**2. Own ledger.** `ledger-mining/`, written only by the runner (lane `mining`), outside the main git repo (git-ignored). Each day
`mining/LEDGER-HASHES.md` gets one line per file: (byte length, SHA-256); the audit hashes today's file cut to yesterday's length. Mining
rows never enter the main k. Code guards before any mining job, each with a unit test: `is_real` excludes lanes `mining` and
`mining-null`; the runner refuses a `mining` row for `ledger/` and any mining job not on the bound rule list (1.2); `count_k_mining`;
`open_locked.py` uses the mining k for a mined candidate.

**3. Pipeline and storage.**
1. Each rule runs once over 2014-11 → 2024-12 in all four news modes (one row). For every row the runner stores **one compact trade
   array per news mode**: entry_t, exit_t, symbol, side, r_mid, r_net (FTMO). About 8 GB for the sweep (sceptic's estimate). Full trade
   folders only for rules that reach judging.
2. Screen: the §6.3 green test on M0 at FTMO costs. No amber budget.
3. **Judging, in-sample at full multiplicity** (replaces §6.6; nothing is unseen except the locked period). The green rule's own trades,
   judged by every G1 bar (trades, profit factor, yearly blocks, drawdown, hold time) and the mining luck bar (4); no near miss.
   **Window: the full research period 2014-11 → 2024-12** (user, 2026-11-17: "Yes, full period"): σ 0.317, bar about **1.51**; a rule
   with true Sharpe 1.0 / 1.5 / 2.0 passes about 5 / 49 / 94%. G2's fx2015 test applies.
4. **G2 stress** (§6.7) for every rule that passes judging, plus:
   - neighbouring values = its explicit ±1-step neighbours on each parameter (same symbols, timeframe, blocks), run as G2 rows;
   - the long / short bar for mined rules fails a side with under 25% of trades, and an empty side never passes;
   - on symbols whose FTMO add-on is flat or unmeasured (`engine/costs.json` `addon_detail`): a raise-only test at spread × 2 outside the
     cash session, or the G3 firm-feed check on research-period FTMO ticks where they exist, before any locked open.
5. **Nothing is judged until all 50,000 rows exist and the null (5) is reviewed.** Every verdict uses the same frozen k.

**4. Own luck bar.** The A10 / A11.4 bar σ·max(1, √VR)·z with **z = max(z_k, z\*)**:
- z_k = Φ⁻¹(0.95^(1/k)), **k = max(50,000, distinct drawn rules with a screen row) + the main pipeline's real rows** at the time the
  null is reviewed (49 today). k is frozen then. G2 rows, neighbour rows and reruns of the same drawn rules don't change it.
  z_k = 4.748 at k = 50,000 (bar 1.51 at σ 0.317, VR 1).
- z\* from the null (5). **There is no route to a lower bar.** The bar is never lowered, by addendum or otherwise.
- **Expected yield, stated now:** close to zero (pass rates in 3.3). Under zero edge, a mined finalist passes the locked-period median bar
  about 2% of the time at bar 1.51 (normal approximation).

**5. Own null (must pass review before any verdict).**
1. **Replicates:** the same 50,000 rules re-scored from their per-mode compact arrays, with r_mid sign-flipped by one seeded sign per
   (symbol, entry day), the same sign in every mode and every row; costs are not flipped (r_net = flipped r_mid − cost). At least 60
   replicates. No ledger rows; nothing added to k.
2. **Statistic:** per replicate, the maximum over null rules that are green at the screen and pass every judging bar except the luck bar,
   taken over modes M1–M3 (eligibility at any firm), of the standardized Sharpe S / (σ·max(1, √VR)). G2 is not replayed (conservative):
   a null finalist is a null rule that passes screen and judging including the luck bar.
3. **Rule, which only raises:** z\* = the highest standardized Sharpe of any null rule (as in 2) in any replicate, plus 0.01. Then
   z = max(z_k, z\*): no null rule in any replicate is a finalist, by construction, and the bar is at least the formula's.
4. The sceptic reviews the null (counts, z\*, distribution) before any real verdict is computed.

**6. Firewall.**
1. Mining spec, log, null and results live in `mining/` (`SPEC.md`, `LOG.md`, `REPORT.md`), `ledger-mining/` and `runs/mining/`. `LOG.md`,
   `STATUS.md`, `DIGEST.md` and the user's pushes carry counts only (rows, k, how many rules at each stage). Lane briefs list those
   folders as never read. Mined rules are excluded from `ic_watch.py` and the A11.5 batch test (own line).
2. **Reverse direction:** the mining session doesn't read `ledger/`, `runs/`, `results/`, `gatekeeper/IC-WATCH.md` or batch reports;
   the main real rows are in the mining k (4).
3. After the sweep starts, every lane-brief change the gatekeeper makes cites its non-mining reason in `LOG.md`.
4. **Backstop:** a main card that shares any traded symbol, the timeframe and the entry-block family with a mined rule that reached
   judging counts as data-mined (k = all real rows). A card that cites or copies a mining result is invalid. Mined rules are never
   hand-tuned or carded into the main pipeline.

**7. Owners.** A new **mining session** writes `mining/SPEC.md`, the sampler and the composer. The **engine owner** builds the ledger
split, the guards, the per-mode compact arrays, the null re-scoring and the 10,000-rows-a-day cap (real jobs always first). The
**gatekeeper** computes no mined verdict before the null is reviewed; then runs judging and G2 by the pipeline functions; the sceptic
reviews each mined candidate like any other.

**8. Locked period.** One open per mined candidate; at most **2 mined opens a calendar month**, first-come by G2 pass time, no carry-over,
no gatekeeper choice. A mined finalist needs locked-period expectancy at or above the judged period's **median**. For mined opens
`gatekeeper/OPENS.md` records only pass / fail and the bar values; per-symbol and per-direction results go to `mining/REPORT.md` only.

**9. Timing.** The sweep starts after: the A14 context-symbol and CFTC features are in the engine and the CFTC revision bound is done;
the guards in 2 pass their tests; the sceptic has reviewed `SPEC.md`; this addendum is committed. About 5 days at 10,000 rows a day.

**10. Conditions of the sceptic's re-check (`gatekeeper/sceptic/2026-11-17-A15-v2-recheck.md`), fixed now, before any draw.**
1. **One window in every code path:** judging, G2 (including `year_blocks` for "without best year"), the stress re-checks (fx2015,
   swap0), the null's re-scoring and the re-check at the open all use `from_ms` = 2014-11-01. Unit test: a stored mined judging result
   holds years 10.168 and σ 0.3173.
2. **The open's re-check uses the frozen k of §4**, never recounted (unit test).
3. **Null replicates: exactly 60**, seed committed with the sampler hash and rule list (§1.2). If no null rule in any replicate passes
   the non-luck bars, z = z_k. (A flipped stop gap, e.g. the 15 Jan 2015 SNB move, can inflate z\*: conservative, costs power.)
4. **Cost test order, no choice:** the G3 firm-feed check where research-period FTMO ticks exist for the symbol; otherwise spread × 2 at
   all hours outside the symbol's cash session. Cash sessions are listed per symbol in `mining/SPEC.md` (indices: their exchange
   session; metals 08:20–13:30 and oil 09:00–14:30 New York (the former floor sessions); FX: none, so × 2 at all hours).
5. **Mined-only code, on the §2 guard list with unit tests:** the side rules of §3.4 (replacing the empty-side pass for mined rules);
   fx2015 for mined rules = trades inside the quarantine months removed, judged at the same k and σ.
6. **Engine hash pinned:** mining jobs run from a pinned checkout of the engine at one commit for the whole sweep (the main engine may
   keep changing; the sweep doesn't see it).


### A16 (2026-11-17, user: "I agree that I want to add all four"): currency-strength indices; rules for rate series
Drafted in `gatekeeper/A16-DRAFT.md`; the sceptic (`gatekeeper/sceptic/2026-11-17-A16-draft.md`) passed it with conditions, all written
in below. No bar, zone, route or count changes for any idea. A16 inputs are not part of the A15 sweep.

**1. Currency-strength indices (engine feature).**
1. **Definition:** for each of USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD: level_c(t) = (1/7) Σ_d ±log P_cd, using each of the 7 pairs'
   last close ≤ t (sign so that "up" means c strengthened). This equals the cumulated equal-weight per-bar change and needs no start
   date, so a cBot can reproduce it from any start. A module reads `ctx["fx_index"][CCY]` (`level`, `close_ms`, `age_ms`) for the declared
   currencies only, and may use only level[i] − level[i−j] for j ≤ a lookback stated on the card; no nan-skipping reductions (nanmean,
   ffill, rolling with min_periods).
2. **Freshness and NaN:** a constituent is fresh when its close_ms equals the traded bar's close. With fewer than 5 of 7 fresh the level
   is NaN for that bar. Stale constituents otherwise count at their last close (no hole-NaN for constituents, as live). NaN also before
   the history starts and for every currency in the FX quarantine (DESIGN §3.3.2, A14 §1.4: May–Jul 2015), and lookbacks across the
   quarantine are NaN. NaN means no entry, never "filter passes".
3. **Card row and binding:** `| currency indices | USD, JPY |` (or `all`, or `none`). The engine hands only the declared currencies; the
   runner refuses a job whose declaration differs from the card either way; the ledger row carries the declaration and its data_hash
   covers all 28 pairs; rows without indices stay byte-identical (re-run sample, §4.4). Indices are inputs, never traded, never a grid
   axis; the lookback may be one of the at most 3 tuned parameters. The card states that the unnormalised equal-weight index ranks
   volatility (JPY crosses dominate the extremes).
4. **Re-carding:** a card that differs from an idea with a result by adding, removing or swapping currency indices and/or context
   symbols is that idea's variation (A14 §1.3); for a red idea it counts as seen (k = real rows). An index card whose signal uses only the
   currencies of its traded pair(s) is the own-price idea: if an own-price card on the same pair, timeframe and rule shape has a result,
   the same applies. The look-ahead reviewer flags any card whose declared currencies are a subset of its traded pairs' currencies.
5. **Multi-pair cards:** one screen job holds all declared pairs; the runner refuses a second base screen row for the idea; pair subsets
   only through the fixed bloc slice; a hand-picked single pair needs a 2014–2024 reason (A1.5). The card states its conflict rule (what
   happens when a new entry would hold a currency opposite to an open position). The gatekeeper reports the share of trades opened while
   the card holds an opposite position in that currency or bloc; above 1% of trades or 10% of net R, G1 is recomputed without those
   entries before any open. Long / short is also reported per currency exposure, per year.
6. **FX rules:** any card declaring a currency index is an FX idea for the fx2015 stress on every symbol (`fx_idea` takes the index
   declaration; unit test).
7. **Live:** before the first finalist using indices, one referee month (containing a US-only DST week, a holiday and a Sunday open):
   ranks identical on ≥ 99.5% of decision bars, every mismatch explained; G3 builds the index from each target firm's own 28 feeds.
8. **Look-ahead review check 10:** declared currencies only; `level` at index ≤ i; lookback as declared; NaN is no entry; the subset flag
   of 4.

**2. Rate series (FX rate differentials, A14 §2 outside series).** Daily government bond yields only (no policy-rate series). A day's
yield is visible from the next business day of its source (after any news window of that day), never on the release bar; cards use
levels or differences across days, never an entry on the day a value changes. The look-ahead reviewer checks this. Downloads need the
user's approval of the exact file list.

**3. Schedule catalogue (lane theme, not an input):** only clock times and published, rule-derived dates; never an event release.
