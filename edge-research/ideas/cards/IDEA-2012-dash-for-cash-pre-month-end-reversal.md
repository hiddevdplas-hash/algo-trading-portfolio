# IDEA-2012: Dash-for-cash pre-month-end reversal in indices (buy when the month-end selling window ends, sell before the month's last day)

| field | value |
|---|---|
| status | inbox |
| lane | literature |
| source (OPERATIONS §4) | papers + Quantpedia (Etula, Rinne, Suominen & Vaittinen, "Dash for Cash: Monthly Market Impact of Institutional Liquidity Needs", Review of Financial Studies 33(1), 75–111, 2020; open access CC BY, https://acris.aalto.fi/ws/portalfiles/portal/40965155/hhz054.pdf) |
| family | calendar and flow effects (monthly payment-cycle liquidity: reversal of pre-month-end selling pressure) |
| seen family (DESIGN §3.7) | no |
| seen family, why | none |
| locked period seen (DESIGN A1) | no (the paper's sample ends 2013-12; nothing after 2024 seen for this card) |
| data-mined | no |
| data-mined, why | no: the windows (selling pressure T−8…T−4, reversal T−3…T−1 under 3-day settlement), their shift with the settlement cycle, the 5-day conditioning window and the symbols' evidence are the paper's; the grid is declared here before any run |
| source overlap | no |
| source overlap, why | Etula et al. 2020: US 1995-07 → 2013-12, other markets to 2013 (no month inside 2016-11 → 2024-12); footnote 16 names the US T+2 switch of Sep 2017 as a date only, no sample; defaults from source: yes, pre-window (literature lane, DESIGN A11.3 migration, 2026-11-16, values unchanged) |
| grid size | 9 |
| class (DESIGN-CONSTRAINTS §0) | C swing (holds 1–3 nights, often over a weekend) |
| two-sided | no: long only, as the paper's reversal; the selling-pressure leg (short T−8…T−4) is not traded: its raw return in the paper is −3 to −4 bp a day, below an index short's costs and risk |
| card version | v1 |

> **Read at source 2026-11-15:** the RFS article (Aalto open-access copy, full text read for §1 incl. Fig. 4 text and footnote 19,
> Tables 1, 2 and 3 with notes, footnotes 20–22, and the text on the 2017 US move to 2-day settlement, footnote 16). Later sections
> (institutional trade data, fund flows, Treasuries) and the Internet Appendix were not read. **Not a duplicate:** **IDEA-2005**
> (turn of month) holds from the close of T−1 to the first days of the new month: this card exits exactly where 2005 enters, so the
> two never hold the same day. **IDEA-1011** (month-end balanced-fund rebalancing) trades T−D…T on the *month-to-date* return
> against the pension rebalance; this card trades a fixed settlement-timed window on the *last-5-day* return, in one direction (long),
> with the opposite exit day (T−1, before the rebalance day T). Partial overlap with 1011 in months with a large down move late in
> the month: the gatekeeper's portfolio check should look at the P&L correlation with 1011 and 2005. Rule rebuilt from the paper's
> description; the paper has no trading rule and no code. Strategy module: `strategies/idea_2012_dash_for_cash_pre_month_end_reversal.py`.

## Why should this exist
1. **Who is on the other side, who pays:** institutions (pension funds, mutual funds, insurers) with monthly cash payments (pensions,
   redemptions, salaries) sell equities so that the cash *settles* by the month's last day T. With s-day settlement the last sale that
   settles in time is on T−s, so the selling peaks on the days before (T−8…T−4 under 3-day settlement; their own trade data show net
   selling significant on T−5, T−4 and the morning of T−3, footnote 19). Liquidity providers who absorb the forced selling are paid
   by the reversal on T−s…T−1. The seller pays a few basis points of price pressure for certainty of settlement.
2. **Why it persists:** the flows are contractual and calendar-driven (payment cycles, settlement rules); the effect is a few basis
   points a day, only on 2–3 days a month, and needs holding equity risk overnight into month-end; the authors report the patterns
   became more pronounced over time, not weaker.
3. **When it should fail:** months where news dominates the last week (index moves of several % swamp a ≈ 25 bp effect); when
   settlement shortens the reversal window (US T+1 from 2024-05-28 leaves only T−1); if the selling-pressure window moves with the
   rule change but our window does not (handled below by the settlement table, from the paper's own mechanism and its Table 3).
4. **Evidence before testing:**
   - **Etula et al. (2020),** RFS, CC BY. T = last trading day of the month. US sample July 1995 (start of 3-day settlement) to
     December 2013; 22 other developed markets from 1980 or later (settlement ≤ 3 days) to 2013.
   - **Text (§1, Fig. 4):** CRSP value-weighted holding-period return −17 bp for T−8…T−4 and +77 bp for T−3…T+3; abnormal (minus the
     sample's average daily return) **−37 bp for T−8…T−4** (significant), **+25 bp for T−3…T−1**, +48 bp for T−3…T+3.
   - **Table 1 (average daily return; T−8…T−4 / T−3…T−1 / average day):** **S&P 500 −0.04 % / +0.11 % / 0.04 %**; **FTSE 100
     −0.04 % / +0.11 % / 0.03 %**; **DAX −0.03 % / +0.06 % / 0.05 %** (2-day settlement, fixed T−8…T−4 windows); all non-US
     indices −0.03 % / +0.10 % / 0.04 %. So T−3…T−1 earns ≈ +0.33 % on the S&P 500 and FTSE 100 (≈ +21–24 bp above the average day).
   - **Table 2 (correlation of T−8…T−4 and T−3…T−1 returns):** **S&P 500 −0.38**, FTSE 100 −0.33, DAX −0.15; negative in all 23
     markets, significant in 20: the weaker the selling window, the larger the reversal.
   - **Table 3 (settlement experiment):** when 13 European markets moved from 3- to 2-day settlement on 2014-10-06, the T−2
     autocorrelation fell by −0.777 (t −3.66) against the 3-day control group: the reversal moved one day closer to T. The paper
     notes (footnote 16) the US moved to 2-day settlement in September 2017.
   - **Robustness (footnote 21):** the US pattern around T−4 survives dropping quarter- and year-ends, FOMC days and macro
     announcement days. No out-of-sample test and no costs in the paper (it is not a trading paper).
   - **Decay and costs (ours):** S&P 500 reversal ≈ +24 bp abnormal over 3 days; halved for decay ≈ +12 bp abnormal, ≈ +20 bp raw with
     drift (+4 bp a day). FTMO round trip US500 ≈ 0.5 bp, DE40 ≈ 0.6 bp, UK100 ≈ 1.1 bp, plus 1–3 nights' long swap (≈ 1–2.5 bp a
     night at our period's policy rates; ≈ 7–9 %/yr now). **Decayed net ≈ +12–15 bp a trade**; 1 R = 1.5 × daily ATR(20) ≈ 150–200 bp
     ⇒ **≈ +0.07 R a trade**. Needed for green: the effect at or above that after costs.
   - **Power: thin.** 12 months × 3 symbols ≈ 36 trades a year (≈ 360 over the period) at the default (unconditional); ≈ 18 a year at
     `thr` = 0. Per-trade SD ≈ 0.7 R: +0.07 R gives t ≈ 1.9 over the period at the default. A real effect at the decayed size is
     borderline detectable; the gatekeeper should judge it on the 10-year total, not on single walk-forward windows.

## Rules (defaults)
- **Symbols:** US500 (the paper's main market), UK100 (FTSE 100: same Table 1 pattern as the S&P 500, correlation −0.33), DE40
  (DAX: weaker, −0.15, but the cheapest European index and in the 2-day-settlement group the paper discusses). Not US30 / USTEC
  (same US flow as US500), not STOXX50 / F40 (France in Table 1 but higher costs), not JP225 / AUS200 / HK50 (weaker or data-only).
- **Decision timeframe:** h1. Each symbol's **daily close** = the close of its last full h1 cash-session bar: US500 bar ending
  **16:00 New York**, UK100 bar ending **16:00 London** (LSE closes 16:30), DE40 bar ending **17:00 Frankfurt** (Xetra closes 17:30;
  as IDEA-2005).
- **Business days** (per exchange, fixed rules computed from the date, no calendar file): Mon–Fri minus
  - NYSE (US500): New Year (Sun → Mon; a Saturday New Year gives no weekday holiday), MLK (3rd Mon Jan), Presidents (3rd Mon Feb),
    Good Friday, Memorial (last Mon May), Juneteenth from 2022 (observed), Independence (observed), Labor (1st Mon Sep), Thanksgiving
    (4th Thu Nov), Christmas (observed);
  - LSE (UK100): New Year (observed Mon), Good Friday, Easter Monday, first Mon May, last Mon May, last Mon Aug, Christmas and Boxing
    Day (observed);
  - Xetra (DE40): 1 Jan, Good Friday, Easter Monday, 1 May, 24, 25, 26 and 31 Dec.
  One-off closures (2018-12-05 NYSE; 2020-05-08, 2022-06-02/03, 2022-09-19, 2023-05-08 UK moves) are not removed: in those months T or
  the entry day is off by one day (≤ 1 month a year per symbol).
- **T** = the last business day of the calendar month. **Settlement days s** (fixed, the markets' rules): US500 3 before
  2017-09-05, 2 from 2017-09-05, 1 from 2024-05-28; UK100 and DE40 2 (since 2014-10-06, before our data). **Entry day** E = T − (s+1)
  business days (the last day of the selling window; US 3-day: T−4 as the paper). **Selling window** = the 5 business days ending at
  E (T−8…T−4 at s = 3, the paper's window).
- **Signal (at E's daily close):** R_sp = ln(close(E) / close(E − 5 business days)); σ = standard deviation of the last 60 daily
  log returns (business-day closes, E included). Long if R_sp < `thr` × σ × √5. `thr` = 99 means always (the unconditional
  reversal, the paper's Table 1 and text).
- **Entry:** market buy at the close of E's daily-close bar. US500 entries on a Friday or before a NYSE holiday fall in FTMO's 2-h
  pre-close block and are dropped by the engine (≈ 1 month in 5; not filtered in the module).
- **Stop:** broker-side, `k` × ATR(20) from the fill; ATR(20) = simple mean of the last 20 business days' true range (high / low of
  the h1 bars after the previous daily close up to this one, previous daily close). No target.
- **Exit:** at the first bar whose close is at or after T−1's daily-close time (the bar ending 16:00 NY / 16:00 London / 17:00
  Frankfurt on T−1). Backstop time exit 7 days after the fill. If s = 1 (US500 from 2024-05-28) the hold is one night (E = T−2).
  NYSE early-close days (13:00) have no 16:00 bar: an E on such a day (24 Dec, day after Thanksgiving) gives no trade; a T−1 on such
  a day exits at the first bar after 16:00 (the CFD's next open, e.g. Sunday evening after a Friday 27 Nov): ≤ 1 month a year.
- **Expected trades per year:** 12 per symbol, ≈ 36 in total at `thr` = 99 (≈ 32 after US500 Friday drops); ≈ 18 at `thr` = 0.
- **Walk-forward:** 24 / 3 (default; far fewer than 100 trades per 12 months).

## Parameters (at most 3 tuned)
| parameter | default | reason | allowed values (grid, declared now) |
|---|---|---|---|
| `thr` (enter only if the selling-window return < thr × σ√5) | 99 (always) | the paper's headline: the T−3…T−1 reversal on average | {99, 0.0, −0.5} (Table 2: reversal larger after a weak selling window; 0 = any down window, −0.5 = a clearly weak one) |
| `k` (stop, × daily ATR(20)) | 1.5 | the paper has no stop; a 1–3-night hold needs a stop rarely hit by noise (3-day SD ≈ 1.4 ATR) | {1.5, 2.0, 3.0} |

Grid size 9. Fixed (not tuned), with reasons: windows T−(s+5)…T−(s+1) and T−s…T−1 (the paper, shifted with settlement by the paper's
own mechanism and Table 3); the settlement table (market rules); 5-day selling window (the paper); σ over 60 days (a scale for `thr`
only); ATR(20) (stop measure); daily-close bars as IDEA-2005 (cash closes).

## Prop fit
- Class C: holds 1–3 nights; the entry day is often a Wednesday–Friday, so many trades hold over a weekend. Runs at FTMO Swing,
  E8 Pro, BrightFunded, Aqua.
- Entries 16:00 NY = 22:00 Amsterdam (US500), 17:00 Amsterdam (UK100, DE40): outside the 22:45–00:15 block.
- News: month-end weeks carry US data (PCE, JOLTS, ISM, payrolls when T−1 is near the 1st Friday) and ECB / FOMC meetings in some
  months; the four news modes decide. The strategy never reads the calendar.
- Up to 3 positions at once, all long equity on the same days: one bet. The portfolio check sees it, and the overlap with 2005 /
  1011 (adjacent month-end windows).
- Swap: long index swap is a charge, 1–3 nights (≈ 10–20 % of the decayed edge); included by the engine.

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
