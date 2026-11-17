# IDEA-NNNN: <short name>

<!-- Copy to ideas/cards/IDEA-NNNN-<slug>.md. Number ranges per lane (OPERATIONS §2a): user 0001–0999, market logic 1000–1999,
     literature 2000–2999, public scripts 3000–3999; take the next free number in your range. Everything above "Results" is written and committed BEFORE the first run.
     After the first run, only "Status", the amber budget (before each variation runs) and "Results" links change. -->

| field | value |
|---|---|
| status | inbox · queued · review · screen · green · amber · tuning · wf · stress · gatekeeper · candidate · dead (reason) |
| lane | market logic · literature · public scripts · user |
| source (OPERATIONS §4) | Claude's ideas · papers + Quantpedia · websites + whitepapers · TradingView + GitHub · Strategy inbox (+ URL) |
| family | e.g. intraday momentum, session breakout, time-series trend, short-term reversal, carry, calendar |
| seen family (DESIGN §3.7) | exactly `yes` or `no` (DESIGN A10.4: the runner refuses anything else) |
| seen family, why | none · VWAP-derived (strict) · RoboQuant repair of <template> (strict) |
| locked period seen (DESIGN A1) | no · yes (source, months covered; no numbers, no direction) |
| data-mined | exactly `yes` or `no` ("partly" is yes) |
| data-mined, why | the reason |
| source overlap (DESIGN A11.3) | exactly `yes` or `no`: yes if any cited source's sample covers any month of 2016-11 → 2024-12, or the defaults come from such a source, or the card can't say |
| source overlap, why | sources, their sample months inside 2016-11 → 2024-12, defaults from the source yes/no |
| grid size | N: the declared grid's number of points (product of the allowed values below) |
| class (DESIGN-CONSTRAINTS §0) | A intraday · B overnight, flat for weekend · C swing |
| two-sided | yes · no (why, and how it stays small) |
| card version | v1 (bump on any change before the first run; never after) |

## Why should this exist
1. **Who is on the other side, who pays:**
2. **Why it persists** (why it isn't arbitraged away):
3. **When it should fail** (regimes, periods):
4. **Evidence before testing** (paper, script URL + licence, own reasoning):

## Rules (defaults)
- **Symbols** (and reason; fewer is better):
- **Decision timeframe** (m15 / h1 preferred; m5 needs a reason):
- **Entry** (on bar close; order type):
- **Stop** (always a broker-side stop):
- **Exit / target / time exit:**
- **Expected trades per year** (all symbols):
- **Walk-forward:** 24 / 3 (default) · 12 / 2 (only if ≥ 100 trades per 12 months expected)

## Parameters (at most 3 tuned)
| parameter | default | reason | allowed values (grid, declared now) |
|---|---|---|---|
| | | | |

Fixed (not tuned) values with their reasons:

## Prop fit
News sensitivity, hold time, trades per day, weekend / overnight, anything near a firm rule (`rulebook/DESIGN-CONSTRAINTS.md`).

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
