# Batch 2: quick screen, 2026-11-16 midday (engine 882d0efed853)

26 real ideas screened, 14:36–14:39 Amsterdam (engine time about 3 minutes). Each idea ran once at its card defaults, over 2014-11 → 2024-12,
in all four news modes. Zones are judged on M0 at FTMO costs (DESIGN §6.3, amber before costs per A11.1).
Ledger rows T20261116-012863 … 012888; `zero_trade_symbols` is empty on all 26.
**Real test count at this point: 39 rows** (13 from batch 1, 26 here; all screens).

Merged before the screen: `lane/market-logic` (IDEA-1015–1023 + modules; review fixes 1001, 1002, 1004, 1005, 1010, 1011, 1012, 1014;
amber "none" for 1008, 1009), merge 90d6df6. `lane/literature` held (see below).
Look-ahead reviews this run: 26 PASS, 1 FAIL (1021); records in `reviews/` (40bdc24). 2007 already had a PASS at its module commit.

| idea | lane | trades | net R / trade | t after costs | t before costs (mid) | zone | slices green on their own |
|---|---|---|---|---|---|---|---|
| 2008 RSI(2) pullback, US indices | literature | 213 | +0.079 | 2.45 | 3.41 | **green** | — |
| 2007 EU-open window, US500 | literature | 1,225 | −0.029 | −1.76 | 2.03 | **amber** | — |
| 1010 round-level stop cascade FX | market logic | 2,564 | −0.066 | −2.95 | 1.58 | **amber** | — |
| 1020 gold weekend-hedge demand | market logic | 952 | −0.012 | −0.48 | 1.38 | red | — |
| 1016 US close-auction pressure reversal | market logic | 863 | −0.063 | −3.39 | 1.10 | red | — |
| 2005 turn of the month, index | literature | 138 | +0.002 | 0.04 | 1.00 | red | — |
| 1011 month-end balanced-fund rebalance | market logic | 111 | +0.034 | 0.45 | 0.78 | red | — |
| 1014 oil CTA breakout flow | market logic | 346 | −0.053 | −0.88 | 0.71 | red | — |
| 1018 home-hours currency weakness | market logic | 10,153 | −0.038 | −5.45 | 0.68 | red | — |
| 3013 US open-range acceptance retest | public scripts | 2,514 | −0.055 | −2.13 | 0.56 | red | — |
| 1004 London-open failed sweep | market logic | 3,566 | −0.133 | −7.48 | 0.53 | red | — |
| 3005 US prior-value re-entry (TPO) | public scripts | 448 | −0.060 | −1.30 | 0.51 | red | — |
| 1017 AUDNZD cross dislocation reversal | market logic | 220 | −0.064 | −1.22 | 0.46 | red | — |
| 1019 same-slot intraday persistence | market logic | 5,971 | −0.048 | −6.20 | 0.29 | red | — |
| 1023 oil inventory overreaction fade | market logic | 233 | −0.113 | −1.31 | 0.29 | red | — |
| 3011 distant daily-shelf rejection | public scripts | 474 | −0.027 | −0.72 | 0.01 | red | — |
| 1001 oil settlement-window reversal | market logic | 1,139 | −0.228 | −12.01 | −0.16 | red | — |
| 3006 weekly-open frontier pullback | public scripts | 1,597 | −0.094 | −3.00 | −0.19 | red | — |
| 2009 monthly TSMOM FX / gold / indices | literature | 960 | −0.065 | −2.68 | −0.73 | red | — |
| 3008 variance-ratio regime switch | public scripts | 1,026 | −0.169 | −4.04 | −1.10 | red | — |
| 1012 metals liquidation-day reversal | market logic | 871 | −0.104 | −3.77 | −1.74 | red | — |
| 3004 isolated-shock fade FX | public scripts | 1,674 | −0.051 | −3.81 | −1.98 | red | — |
| 3009 swing-size exhaustion fade | public scripts | 4,030 | −0.127 | −7.15 | −2.06 | red | — |
| 1015 antipodean home-hours reversal | market logic | 969 | −0.088 | −4.00 | −2.20 | red | — |
| 1005 Friday weekend de-risking, oil | market logic | 260 | −0.214 | −4.54 | −2.58 | red | — |
| 1022 PBoC fix repricing AUD / NZD | market logic | 1,191 | −0.188 | −7.78 | −3.47 | red | — |

**Summary:** 1 green, 2 amber, 23 red. Red is final; a genuinely different idea needs a new card.
Running total of real screens: 39 ideas, 1 green, 8 amber, 30 red.

**Near the line, stated so nobody re-reads it later:**
- 2008 is green on 213 trades, just above the 150 floor; +0.079 R against the +0.05 R bar and t 2.45 against 2.0.
- 1020 missed amber on t before costs: 1.38 against 1.5.

None is rounded up. The bars are fixed.

**Reading 2008's green with care:** it is data-mined (yes) and source-overlapped (yes): the source picked RSI(2) as the best of 3 rules in a
2000–2018 search, and its pages show a holdout of 2019-01 → 2026-10, so `locked period seen` is yes (DESIGN A1). Its k at G1 is the real
test count in the ledger (39 now, A10.4 / A11.3), and its locked-period open, if it ever gets that far, is "not independent". 213 trades
over 10 years is thin for a 24 / 3 walk-forward.

## Held (not screened)
- **lane/literature not merged** (IDEA-2000 v4, 2011–2015): IDEA-2011's default rule reads tick volume (`vol_filter = 1`, `bars["vol"]`),
  a failing merge check (evening-prep step 3, DESIGN §5). It already has a HOLD row in REVIEW-FIXES; one bad card holds the branch. The
  rest of the branch passed py_compile and the synthetic-bar mechanics check. Unblocks if the lane makes `vol_filter = 0` the default
  (card v2) or the gatekeeper chat merges with 2011 held at card level.
- **1021:** look-ahead review FAIL (two rules not on the card: barrier warm-up, "session close"); card-only fix in REVIEW-FIXES.
- **1002:** gatekeeper chat decides whether a mostly-long rule may run (card v2 flags it).
- **3012:** `source overlap` no on a public script with a tested (2025–26, crypto) sample; A11.3 says "no" only for own reasoning citing no
  tested sample; gatekeeper chat decides.
- Still held from before: 2000 (fix is on the held literature branch), 2010, 3007, 3010 (tick volume), 3002 (open FAIL).

## Review notes worth knowing before reading dropped counts (no fix required; from the PASS reports)
- 1001: some XBRUSD 19:30 London entries may fall in the engine's pre-close block (Brent's 15:59 NY winter closes, maybe the DST-gap
  weeks); the engine owner could count them.
- 1011: DE40 15:00 NY entries may be blocked wherever DE40's daily break is ≥ 2 h; not stated on the card.
- 1019 (US500 Friday 15:00 / 15:30 NY), 1016 (pre-holiday 16:00 NY), 3004 / 3008 / 3009 / 3011 (entries at any hour): some signals land in
  engine blocks and are dropped and counted, as their cards state.
- 2005: default k = 2.5 is not a grid point ({2.0, 3.0, 4.0}); the walk-forward fallback would use a k the grid never tests.

## IC watch (A12, information only)
`gatekeeper/ic_watch.py`: 2 entries, unchanged (none from this batch).

## Amber variations (step 7)
- 1008, 1009: lane wrote "none" (5882c6e, V1 = none with a reason). Nothing to queue: their budget is spent unused, so they have no
  route left. Closing them is the gatekeeper chat's call.
- 2001, 2004, 2006, 3000: rows still open (lane); nothing queued.

## Needs the gatekeeper chat
- **Tune / walk-forward:** IDEA-2008 (green; data-mined, source overlap yes, locked period seen yes; see above).
- lane/literature merge decision (2011 volume default).
- 1002 (mostly-long rule) and 3012 (A11.3 source overlap) decisions.
- 1008, 1009: amber with no variations; close them.
