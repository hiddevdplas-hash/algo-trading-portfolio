# IDEA-2008: RSI(2) pullback in an uptrend, bought at the US cash close (US500, US30, USTEC)

| field | value |
|---|---|
| status | inbox |
| lane | literature |
| source (OPERATIONS §4) | websites + whitepapers (https://kruegeralgorithms.com/en/research/rsi2-dip-buying-index-cfds-holdout ; https://kruegeralgorithms.com/en/research/rsi2-pullbacks-15-markets-search-passed-holdout-0-of-23 ; rule first published by Connors & Alvarez, 2008) |
| family | short-term reversal (daily pullback in an uptrend) |
| seen family (DESIGN §3.7) | no |
| seen family, why | none |
| locked period seen (DESIGN A1) | yes: both Krueger pages show a holdout of 2019-01 → 2026-10 (seen by the scanning subagent; no numbers or direction recorded here, and symbols, direction and parameters are not chosen from it) |
| data-mined | yes |
| data-mined, why | partly: the source picked RSI(2) as the highest-t of 3 related pullback rules in its 2000–2018 search; the symbols are the three where the source's search period shows the effect (not chosen from our data) |
| source overlap | yes |
| source overlap, why | Krueger pages: search 2000-2018 (covers 2016-11 to 2018-12) and holdout 2019-01 to 2026-10 seen; Connors-Alvarez 2008 no sample; defaults from source: yes (rsi_lo, stop) (gatekeeper, DESIGN A11.3, 2026-11-15) |
| grid size | 9 |
| class (DESIGN-CONSTRAINTS §0) | C swing (average hold ≈ 3.6 sessions in the source, over weekends) |
| two-sided | no: long only, as published. It stays small: ≈ 8 trades a year per symbol, ≈ 24 in total, average hold ≈ 3–4 sessions; the short mirror fights the index drift and is not the published rule |
| card version | v2 (look-ahead review 2026-11-13: data-mined field set to yes; same-close exit + entry stated) |

> **Read at source 2026-11-13:** both Krueger Algorithms pages above (dated 5 Oct 2026 and 21 Oct 2026), search-period sections only.
> Not read: Connors & Alvarez, *Short Term Trading Strategies That Work* (2008; commercial book): the rule's original wording is
> **unverified** here and is taken from the Krueger pages' statement of it. The first page carries an "Ask the research" box with an
> instruction to the reader's AI; treated as page text and ignored. **Not a duplicate:** no card in 0001–3001 (main, lane branches) trades
> a daily pullback / short-term reversal; the nearest are momentum or time-of-day cards. Rules rebuilt from the page's description; no code
> copied (the pages show none). Strategy module: `strategies/idea_2008_rsi2_pullback_us_indices.py`.

## Why should this exist
1. **Who is on the other side, who pays:** short-horizon sellers after a sharp 1–3 day drop in a rising market: de-risking flows,
   volatility-targeting and stop-outs that sell after down days, and liquidity demand that pushes the index below its value for a few
   days. The buyer is paid a liquidity premium for absorbing them while the longer trend (close > 200-day average) is intact.
2. **Why it persists:** the edge per trade is small next to the variance of a 3–4 day index hold (a few tenths of a percent against a
   daily SD ≈ 1%), it comes in only ≈ 8 trades a year per index, and it needs a fill at the close: the source finds next-open entry
   loses most of it. Few large players care about a 30 bp edge eight times a year.
3. **When it should fail:** crashes that start inside an uptrend (the 200-day filter lags: 2008-style and Feb–Mar 2020-style falls);
   long trending years with few pullbacks; and in general **after 2015**: the source says its search-period result came "mainly in the
   years before 2015" and the effect was already small from 2015 on. Our research period (2014-11 → 2024-12) is almost all after that.
4. **Evidence before testing:**
   - **Krueger Algorithms, "RSI(2) dip-buying on index CFDs" (5 Oct 2026),**
     https://kruegeralgorithms.com/en/research/rsi2-dip-buying-index-cfds-holdout . Data: daily SPY, QQQ, DIA (Yahoo) as stand-ins for
     US500, NAS100, US30. Search period **2000–2018**: **419 trades, net +34.6 bp a trade (t 3.1)**, average hold 3.6 sessions;
     the same holds entered every day earn +1.0 bp, so **excess +33.6 bp (t 3.0)**; **13 of 19 years** positive (the page's own bar
     was 14); at 1.5× spread still +33.6 bp. Costs: 2 bp round trip spread + slippage; financing interest + 2.5 % a year, tripled at
     weekends, 70 % dividend credit. Per market in R with a 3 × ATR(10) stop, ≈ 8 trades a year each: **US500 +0.14 R (t 4.5),
     US30 +0.09 R (t 2.4), NAS100 +0.07 R (t 1.6)**; worst trades −1.06 / −1.05 / −2.68 R. Stops: the 3-ATR stop was hit on 9–12 % of
     trades and did not raise the mean; a 2-ATR stop (hit 17–20 %) was worse than none in all three. Selection: 3 related pullback
     rules were tried; none met all the page's criteria; RSI(2) had the highest t and went to the holdout as an "observation candidate".
   - **Krueger Algorithms, "RSI(2) pullbacks, 15 markets" (21 Oct 2026),**
     https://kruegeralgorithms.com/en/research/rsi2-pullbacks-15-markets-search-passed-holdout-0-of-23 . Same primary rule on nine other
     indices (IWM, DAX, FTSE 100, CAC 40, SMI, Euro Stoxx 50, Nikkei 225, Hang Seng, ASX 200), 2000–2018: **pooled +22.35 bp net,
     +30.9 bp gross, n 1,066, t 2.27**; random entries with the same hold +0.3 bp (95th percentile +10 bp). **Entry at the next open:
     +8.7 bp net, t 0.9.** DAX, Nikkei and ASX 200 near zero. 240 cells tested (20 rules × long/short × filter × 15 markets): 35 with
     t ≥ 2 vs ≈ 6 by chance. Effect "mainly before 2015". Data warning on the same page: free daily FX candles whose close, high and low
     come from different windows gave a spurious result; this card builds its daily series from h1 bars at one fixed clock time.
   - **Post-publication:** the rule was published in 2008; the 2008–2018 part of the search period is after publication and is
     included in the numbers above, but not split out on the pages. No independent academic test read.
   - **Decay and costs:** published net +34.6 bp a trade (US ETFs, 2000–2018). Halved for decay (McLean & Pontiff) ≈ +17 bp; the
     source's "small from 2015" suggests less, say 0–15 bp in our period. FTMO costs per trade (`data-checks/cost-table.md`): spread
     + add-on ≈ 0.5 bp (US500), ≈ 0.3–0.4 bp (US30, USTEC); **swap ≈ −8.8 % a year long ≈ 2.4 bp a calendar day, ≈ 12 bp for a 3.6-session
     hold that spans ≈ 5 calendar days** (the source charged interest + 2.5 % too, so its net already pays this). 1 R = 3 × daily
     ATR(10) ≈ 300–400 bp on US500. Decayed +17 bp ≈ **+0.05 R**; at the source's per-market size +0.07 to +0.14 R. Needed for green:
     ≥ +0.05 R after costs, i.e. the effect must hold at about half its 2000–2018 size. **Honest prior: weak to marginal.**
   - **Power:** ≈ 24 trades a year, ≈ 240 over the research period. Per-trade SD ≈ 0.5 R; +0.05 R gives t ≈ 1.5. Underpowered: a pass
     needs the effect near its published size; a fail at +0.05 R is not conclusive.

## Rules (defaults)
- **Symbols:** US500, US30, USTEC (the three markets of the source's per-market table; all three positive in its search period). Not
  DE40, JP225, AUS200 (near zero in the source's search period); not UK100, STOXX50, F40, HK50 (in the pooled nine but not shown
  per market; adding them adds tests on a weaker pooled result).
- **Decision timeframe:** h1, New York clock. The daily series is built from the h1 bars: the **cash close** of a day is the close of
  the h1 bar ending **16:00 ET** (every weekday that has one); the day's high / low are the extremes of the h1 bars after the previous
  cash close up to and including this one. The rule is decided on that series.
- **Indicators (on the cash-close series):** RSI(2) with Wilder smoothing; SMA(200) and SMA(5) of the cash closes; ATR(10), Wilder,
  from the day high / low and the previous cash close.
- **Entry:** buy at market at the close of the h1 bar ending 16:00 ET when RSI(2) < `rsi_lo` **and** cash close > SMA(200). The CFD
  trades until 17:00 ET, so the fill is seconds after the cash close (the source's close entry, not its losing next-open variant).
- **Stop:** broker-side, `k` × ATR(10) (daily, above) below the fill. No target.
- **Exit:** at the close of the first h1 bar ending 16:00 ET (after entry) whose cash close is above SMA(5); **time exit 28 calendar
  days** after the fill (≈ the source's 20-session maximum).
  v2: look-ahead review 2026-11-13: when an exit and a new entry fall on the same 16:00 ET close, the open trade exits at that close and
  the new trade enters on the same tick (the exit is never suppressed by an entry).
- **Expected trades per year:** ≈ 8 per symbol, ≈ 24 in total (fewer on Fridays: FTMO's 2-h-before-close rule blocks late Friday
  entries; the engine applies it).
- **Walk-forward:** 24 / 3 (default; far fewer than 100 trades per 12 months).

## Parameters (at most 3 tuned)
| parameter | default | reason | allowed values (grid, declared now) |
|---|---|---|---|
| `rsi_lo` | 10 | the published threshold | {5, 10, 15} |
| `k` (stop, × daily ATR(10)) | 3.0 | the source's emergency stop; 2 × ATR was worse than none in all three markets, so the grid goes wider, not tighter | {3.0, 4.0, 5.0} |

Grid size 9. Fixed (not tuned), with reasons: RSI length 2, SMA(200) trend filter and SMA(5) exit (the published rule); ATR(10) (the
source's stop measure); time exit 28 calendar days (≈ 20 sessions, published); cash close at 16:00 ET (the source used close prices;
the CFD's 23:00 server close is not the cash close).

## Prop fit
- Class C: holds overnight and over weekends (with Mon–Thu entries and 3–4 session holds, most trades span a weekend). Runs at FTMO Swing, E8 Pro, BrightFunded,
  Aqua; not at FTMO Standard funded unless the weekend rule is added (that would be a new card, not a variation).
- Entry at 16:00 ET = 22:00 Amsterdam (21:00 in the DST-gap weeks): before the 22:45–00:15 entry block. Friday entries fall inside
  FTMO's 2 h before the index close (21:50 UTC) and are blocked by the engine.
- News: holds through all US data and FOMC days; the four news modes decide; the strategy never reads the calendar.
- Swap ≈ 2.4 bp a calendar day long on US indices (FTMO): included by the engine; it is a large share of the decayed edge.
- Three long index positions can be open at once after a broad sell-off: one bet on US equities; the portfolio check sees it.
- Low frequency (≈ 2 trades a month across the three): check the inactivity rules at the portfolio level.

## Amber budget (only if the quick screen says amber; each line written and committed before it runs)
| # | change | reason (what information it adds) | written (date) |
|---|---|---|---|
| V1 | | | |
| V2 | | | |
| V3 | | | |

## Results (ledger test ids only; numbers live in the ledger and the digest)
- quick screen:
- amber variations:
- tuning / walk-forward:
- stress:
- gatekeeper:
