# IDEA-1021: autocallable dealer-gamma fade in the Nikkei and Euro Stoxx cash sessions (JP225, STOXX50)

| field | value |
|---|---|
| status | inbox |
| lane | market logic |
| source (OPERATIONS §4) | Claude's ideas |
| family | short-term reversal after overreaction (intraday, from the local cash open) |
| seen family (DESIGN §3.7) | no |
| seen family, why | none |
| locked period seen (DESIGN A1) | no (own reasoning; no source read in this run) |
| data-mined | no |
| data-mined, why | no (no results looked at; symbols chosen by where autocallable notes are written, windows fixed by the exchanges' cash hours) |
| source overlap | yes |
| source overlap, why | practitioner / press accounts (bank notes, Risk.net) of autocall dealer gamma cite no tested sample and include the 2018 Kospi episode, inside 2016-11 → 2024-12; defaults from source: no (lane, DESIGN A11.3 migration 2026-11-16, before any result; card version unchanged) |
| grid size | 9 |
| class (DESIGN-CONSTRAINTS §0) | A intraday |
| two-sided | yes (fades a move away from the open either way; nothing fixes the direction) |
| card version | v2 (2026-11-17, look-ahead review 2026-11-16: barrier warm-up and "session close" stated as the module already does; no rule, parameter, grid or symbol changed) |

> Strategy module: `strategies/idea_1021_autocall_dealer_gamma_session_fade.py`. No web access in this run; the evidence below is from
> Claude's own knowledge and **unverified**. **Not a duplicate:** IDEA-2001 (noise-area momentum) and IDEA-3008 (variance-ratio switch)
> trade US500 / USTEC, where index-option dealer positioning is mixed; IDEA-3003 / IDEA-3005 fade US auction and value-area failures
> (market-profile logic, US only); IDEA-3004 fades lone outlier bars in FX. This card's reason (dealers long gamma from structured notes)
> picks the symbols and predicts a **sign opposite** to IDEA-2001's: fade in JP225 / STOXX50 where IDEA-2001 follows in US500.
> **Overlap:** IDEA-1013 trades STOXX50 from 16:00 Frankfurt in the direction of the US open; this card exits STOXX50 at 15:30 Frankfurt,
> before the US open, so the windows do not overlap. IDEA-2007 (US500 through the European open) is a different symbol and window.

## Why should this exist
1. **Who is on the other side, who pays:** autocallable notes on the Nikkei 225 and the Euro Stoxx 50 are sold in large volumes to
   Japanese, Korean and European retail and private-bank clients. The buyer is short a down-and-in put and receives a coupon; the issuing
   dealer is **long that optionality** (long volatility, long gamma while spot is well above the knock-in barriers). A dealer that is
   long gamma re-hedges against the move: sells into intraday rallies and buys intraday dips, mechanically and price-insensitively. The
   note buyers pay (they sold the volatility cheaply in the note); intraday momentum traders who chase moves in these indices pay too.
2. **Why it persists:** issuance is steady (yield-seeking retail in low-rate Japan and Europe, 2014–2021 especially), the hedging is
   driven by risk limits, not by views, and the notes have multi-year lives, so the long-gamma stock is large and renews itself. The
   effect per day is small and confined to two regional index CFDs in their home hours: a capacity too small to matter to the funds
   that sell volatility against it (they mostly trade it in options, not in intraday futures fades).
3. **When it should fail:** after sharp sell-offs that bring outstanding notes near their knock-in barriers (March 2020, parts of 2016
   and 2022): near the barrier the hedge flips and the dealer flow amplifies moves; the card's fixed drawdown filter skips those days,
   but the filter is only a proxy. Also on days of big news (BoJ, ECB) or when US-driven moves dominate the home session. If issuance
   fell after 2022 as rates rose, the effect weakens late in the period.
4. **Evidence before testing (unverified, from memory):**
   - Practitioner and press accounts (bank research notes, Risk.net coverage) describe dealers' long-vol, long-gamma position from
     autocallables in the Nikkei, Euro Stoxx 50, Kospi 200 and HSCEI as a cause of low implied volatility and dampened realised moves,
     and the 2015–2016 HSCEI and 2018 Kospi episodes as the barrier-flip case. No paper testing an intraday fade on it is recalled.
   - Own reasoning: the sign prediction (fade, not follow) and its contrast with the US indices are this card's hypothesis.

## Rules (defaults)
- **Symbols:** **JP225** (Nikkei 225: the largest autocallable underlying in Japan; cash 09:00–15:00 Tokyo) and **STOXX50** (Euro
  Stoxx 50: the main European autocallable underlying; cash 09:00–17:30 Frankfurt, traded here only to 15:30). Not HK50 (Asian notes are
  written on HSCEI, not on the Hang Seng), not DE40 (history from 2021-09 only), not US500 (dealer positioning mixed; would add tests).
- **Decision timeframe:** m15 (moves from the open develop over hours; m15 gives an entry within 15 minutes of a threshold).
- **Session (local clock, DST by zone):** JP225: open = open of the m15 bar starting 09:00 Tokyo; decisions on bars closing 10:00–14:00
  Tokyo; time exit 15:00 Tokyo. STOXX50: open = open of the bar starting 09:00 Frankfurt; decisions on bars closing 10:00–15:00
  Frankfurt; time exit 15:30 Frankfurt. The first hour is left out (opening auction and overnight information).
- **Scale:** R20 = mean over the previous 20 sessions (today excluded) of the session's range (high − low of the m15 bars from the
  session open to the time exit). No trade until 20 sessions exist.
- **Barrier proxy (fixed):** no trade on a day whose open is below 0.80 × the highest session close of the previous 250 sessions.
  **v2 (look-ahead review 2026-11-16):** before 250 sessions exist, the highest close of all previous sessions is used (from the first
  completed session; the first session is not blocked). Session close = close of the last m15 bar ending at or before the time exit
  (15:00 Tokyo / 15:30 Frankfurt), not the exchange's closing price.
- **Entry:** at a decision bar's close, d = close − session open; if |d| ≥ `k` × R20: market order **against** d. At most one trade per
  symbol per day (the first trigger).
- **Stop:** broker-side at `s` × R20 from the fill. 1 R = that distance.
- **Exit / target / time exit:** target at the session open (target distance = |d| at the signal bar); time exit at the session's time
  exit (15:00 Tokyo / 15:30 Frankfurt).
- **Days:** a session exists when its 09:00 bar exists. Japanese holidays on which OSE futures trade (holiday trading from 2022-09) are not
  excluded if the CFD has bars then (few days a year; noted, not tuned).
- **Expected trades per year:** about 245 sessions × 2 symbols × share of days reaching `k` = 0.55 of an average session range away from
  the open inside the window (rough guess 35–50%) ≈ **170–245 a year**.
- **Walk-forward:** 24 / 3 (default; two correlated-by-mechanism symbols in different time zones, ≈ 85–120 a year each).

## Parameters (at most 3 tuned)
| parameter | default | reason | allowed values (grid, declared now) |
|---|---|---|---|
| `k` (move from the open, × R20) | 0.55 | about half an average day's range: beyond the noise of the first hour, early enough to leave room to revert | 0.4, 0.55, 0.7 |
| `s` (stop, × R20) | 0.45 | a further extension of about half a day's range means the move is not being absorbed | 0.3, 0.45, 0.6 |

Fixed (not tuned) values with their reasons: session hours (exchange clocks); first hour excluded (opening auction); STOXX50 exit 15:30
Frankfurt (before the US cash open, when US flow takes over and IDEA-1013 starts); look-back 20 sessions (one month); barrier proxy
0.80 × 250-session high (knock-in barriers are typically 50–70% of the strike and notes are struck over the past year or two, so a 20% fall
from the year's high puts the newest notes within reach of their barriers; not tuned); target = the open (the hedge flow pulls toward
where it started the day; a fixed point, no parameter).

## Prop fit
- News: BoJ decisions land in Tokyo hours on JP225, ECB decisions at 13:45 / 14:30 Frankfurt on STOXX50; the four news modes split those
  days out. No entry is triggered by the calendar.
- Hold minutes to a few hours, at most one trade per symbol a day, no overnight, no weekend. JP225 trades end 07:00–08:00 Amsterdam.
- Costs: JP225 spread about 1.2 points against an average session range of a few hundred points (≈ 0.01 R); STOXX50 about 2 points
  against a range of about 40–50 points (≈ 0.1 R at `s` = 0.45): STOXX50 is the cost-sensitive leg.
- The two symbols trade in different hours: no stacked risk from this card.

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
