# IDEA-1022: PBoC fixing repricing of AUD and NZD (follow the 09:15 Beijing fix-window move through the Asian morning)

| field | value |
|---|---|
| status | inbox |
| lane | market logic |
| source (OPERATIONS §4) | Claude's ideas |
| family | FX fixing flows (information release at a fixed clock time; intraday continuation) |
| seen family (DESIGN §3.7) | no |
| seen family, why | none |
| locked period seen (DESIGN A1) | no (own reasoning; no source read in this run) |
| data-mined | no |
| data-mined, why | no (no results looked at; the window is set by the PBoC's published fixing time, symbols by China exposure, both before any run) |
| source overlap | yes |
| source overlap, why | market commentary on the 2016 and 2018–2019 fixing episodes is inside 2016-11 → 2024-12 (no tested sample); Shu-He-Cheng 2015 ends before 2016-11; defaults from source: no (lane, DESIGN A11.3 migration 2026-11-16, before any result; card version unchanged) |
| grid size | 9 |
| class (DESIGN-CONSTRAINTS §0) | A intraday |
| two-sided | yes (follows the fix-window move either way; nothing fixes the direction) |
| card version | v1 |

> Strategy module: `strategies/idea_1022_pboc_fix_repricing_aud_nzd.py`. No web access in this run; the evidence below is from Claude's
> own knowledge and **unverified**. **Not a duplicate:** the other fixing cards trade the flow into a fix (IDEA-2002 London 4 pm, 2004
> Tokyo 9:55, 2006 ECB 14:15, 1006 NY 10:00 cut); this card trades the **information** a fix releases, after it, in a currency that
> is not the fixed one. IDEA-1015 (AUD / NZD home-hours reversal) holds the same symbols in overlapping hours with the **opposite** logic
> (fade of the prior London–New York move); its card names "China growth shock, the August 2015 CNY devaluation" as the case where the
> home session continues instead; IDEA-1003 lists "PBoC fixing surprises" as information its fade should not trade. This card is that
> case as a rule. The gatekeeper should check daily P&L correlation with IDEA-1015 (expected negative or near zero) and IDEA-1017.

## Why should this exist
1. **Who is on the other side, who pays:** at 09:15 Beijing every Chinese business day the PBoC (via CFETS) publishes the USD/CNY central
   parity. Since the August 2015 reform the fix is the main daily signal of how much yuan weakness or strength Beijing will tolerate, and
   AUD and NZD are the liquid, open-hours proxies for China exposure (CNH is not in this project's symbol list). Fast traders reprice
   AUD in the first minutes; the rest of the repricing is done by slower Asian-hours participants (Australian and Asian real money,
   corporates, macro accounts adjusting China hedges through the morning). Those who pay: passive orders left from before the fix that
   are picked off as the price adjusts, and mean-reversion liquidity providers in thin Asian hours that lean against a move which is
   information, not noise.
2. **Why it persists:** reading the fix needs a model of the "expected" fix (prior close, basket, and in 2017–2018 the undisclosed
   counter-cyclical factor), so its message is ambiguous and is absorbed over hours rather than seconds. The window is 02:15–05:30
   Amsterdam on two mid-size pairs: the capacity is small and the hours unattractive to the funds that could arbitrage it; for them the
   fix is a CNH trade, not an AUD one.
3. **When it should fail:** on days when the fix is in line with expectations (most days; the threshold skips them), when the window
   move is driven by Australian data instead (11:30 Sydney falls at 09:30 Beijing in the Australian winter, 08:30 Beijing in summer) or
   by Chinese data at 09:30–10:00 Beijing (CPI / PPI, PMIs): those are information too but on another clock, and the news modes split the
   Australian ones out; before 2015-08-11 (first nine months of the research period) the fix moved spot little; and in quiet years
   (parts of 2014, 2020–2021) the signal fires rarely. If the market learns to price the fix within minutes, the edge decays in the
   later years.
4. **Evidence before testing (unverified, from memory):**
   - The 11 Aug 2015 fixing reform and devaluation, and the AUD's sell-off with it; the 2016 and 2018–2019 episodes when fixes weaker or
     stronger than models expected moved CNH and the "China proxy" currencies (AUD, NZD, KRW) in the Asian morning (market commentary of
     the time).
   - Shu, He and Cheng (2015, BIS / China Economic Review), "One currency, two markets: the renminbi's growing influence in Asia-Pacific":
     regional currencies co-move with the onshore and offshore renminbi, increasingly after 2010. No paper testing an intraday
     continuation of AUD after the fix is recalled.
   - Own reasoning: information released at a fixed time and interpreted slowly in thin hours continues (as IDEA-1015 and 1003 assume on
     their failure days); the sign and the hold are this card's hypothesis.

## Rules (defaults)
- **Symbols:** **AUDUSD** (the most liquid China-proxy currency; Australia's largest export market is China) and **NZDUSD** (second; dairy
  and China exposure, thinner in Asian hours). Not AUDJPY / NZDJPY (adds a JPY factor and Tokyo flows, IDEA-2004 / 1018); not USDJPY;
  not XAUUSD (sign of the fix's effect on gold is unclear). The two are correlated: count them as about 1.5 exposures.
- **Clock:** Beijing time (Asia/Shanghai, no daylight saving). In Amsterdam: 09:15 Beijing = 02:15 in winter, 03:15 in summer.
- **Decision timeframe:** m15 (the fix lands on a quarter-hour; m15 bars isolate the fix window).
- **Days:** Monday–Friday Beijing dates on which the bar starting 09:15 Beijing exists. Chinese public holidays (no fix) are not
  excluded: their window moves are small and rarely reach the threshold; they stay in `D` and `W` (lowers both a little; noted, not tuned).
- **Fix-window move:** `d` = close of the bar ending 09:30 Beijing − open of the bar starting 09:15 Beijing (one m15 bar).
- **Scales (previous 20 days with a window, today excluded):** `D` = mean |`d`|; `W` = mean range (high − low) of the m15 bars from
  09:30 to 11:30 Beijing. No trade until 20 days exist.
- **Entry:** at the close of the bar ending 09:30 Beijing, if |`d`| ≥ `k` × `D`: market order **in the direction of** `d`. At most one
  trade per symbol per day.
- **Stop:** broker-side at 0.75 × `W` from the fill. 1 R = that distance.
- **Exit / target / time exit:** time exit at `X` Beijing (default 11:30, the end of the Chinese morning session). No target.
- **Expected trades per year:** about 250 days × 2 symbols × share of days with |`d`| ≥ 1.5 `D` (≈ 1.2 σ for a half-normal |`d`|:
  about 23%, fewer if the window is mostly quiet) ≈ **80–115 a year** (≈ 800–1,100 over the research period).
- **Walk-forward:** 24 / 3 (default; below the 100-per-12-months bar for 12 / 2 at the low end).

## Parameters (at most 3 tuned)
| parameter | default | reason | allowed values (grid, declared now) |
|---|---|---|---|
| `k` (fix-window move, × `D`) | 1.5 | only a window move clearly larger than usual marks a fix that surprised; smaller moves are noise | 1.0, 1.5, 2.0 |
| `X` (time exit, Beijing clock) | 11:30 | how long slow repricing lasts: end of the Chinese morning (11:30), into the afternoon session (13:30), Shanghai close / Tokyo afternoon (15:30) | 11:30, 13:30, 15:30 (module: minutes after midnight 690, 810, 930) |

Fixed (not tuned) values with their reasons: reaction window one m15 bar from 09:15 (the fix time; fast repricing is mostly inside it);
scales over 20 days (a month, as in IDEA-1015 / 1021); stop 0.75 × `W` (three-quarters of a normal morning range against the move means
the repricing failed; one value to keep the grid at 9); `W` measured 09:30–11:30 for every `X` (one scale, independent of the exit);
no holiday table (FX trades through Chinese holidays; a missing bar gives no signal).

## Prop fit
- News: Australian releases at 11:30 Sydney fall at the decision bar's close (09:30 Beijing) in the Australian winter and before the
  window (08:30 Beijing) in the Australian summer; RBA decisions (14:30 Sydney) can fall inside a 13:30 / 15:30 Beijing hold. The four
  news modes split those days out. Chinese data (09:30 / 10:00 Beijing) are not in the USD / AUD news blocks: they land inside the hold
  (noise, not a trigger). No entry reads a calendar.
- Hold 2–6 hours, at most one trade per symbol a day, entries 02:30 / 03:30 Amsterdam, flat long before the class A cut-off; no
  overnight, no weekend.
- Costs: Asian-hours spreads are wider than in London. AUDUSD: `W` roughly 15–25 pips, stop ≈ 12–18 pips, spread + commission ≈ 0.6–0.8
  pip ≈ 0.05 R; NZDUSD wider (≈ 0.1 R). NZDUSD is the cost-sensitive leg.

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
