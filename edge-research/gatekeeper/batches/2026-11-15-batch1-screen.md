# Batch 1: quick screen, 2026-11-15 (engine fb7127a41fd1)

13 real ideas screened, 15:41–15:43 Amsterdam. Each idea ran once at its card defaults, over 2014-11 → 2024-12, in all four news modes.
Zones are judged on M0 at FTMO costs (DESIGN §6.3, amber before costs per A11.1).
Ledger rows T20261115-012850 … 012862; `zero_trade_symbols` is empty on all 13.
Real test count at this point: 13 rows. IDEA-2000 is held (REVIEW-FIXES).

| idea | lane | trades | net R / trade | t after costs | t before costs (mid) | zone | slices green on their own |
|---|---|---|---|---|---|---|---|
| 2001 noise-area intraday momentum | literature | 4,705 | +0.049 | 2.20 | 5.42 | **amber** | vol high, range regime, long side, recent 2021–24 |
| 3000 price-level novelty breakout | public scripts | 2,249 | +0.072 | 1.94 | 3.65 | **amber** | vol low, long side |
| 2006 Europe fix USD reversal | literature | 10,532 | −0.004 | −0.63 | 4.17 | **amber** | — |
| 2004 Tokyo fix gotobi USDJPY | literature | 777 | −0.029 | −1.53 | 3.00 | **amber** | — |
| 1009 oil NY first-hour continuation | market logic | 1,560 | −0.170 | −3.84 | 2.06 | **amber** | — |
| 1008 gold Asia long / NY short | market logic | 5,176 | −0.022 | −2.32 | 1.57 | **amber** | — |
| 3001 EU cash-open breakaway gap | public scripts | 758 | +0.029 | 0.73 | 1.49 | red | — |
| 1007 monthly opex dealer hedge | market logic | 478 | −0.030 | −0.87 | −0.15 | red | — |
| 3003 US IB failed-auction fade | public scripts | 704 | −0.096 | −2.47 | 0.25 | red | — |
| 1013 EU index US-open repricing | market logic | 1,317 | −0.322 | −7.37 | −0.13 | red | — |
| 1006 NY cut strike pin FX | market logic | 2,653 | −0.089 | −5.34 | −0.45 | red | — |
| 1000 LBMA auction reversal | market logic | 2,023 | −0.273 | −11.29 | −1.00 | red | — |
| 1003 Asian-hours dislocation reversal | market logic | 2,755 | −0.349 | −15.09 | −1.68 | red | — |

**Summary:** 0 green, 6 amber, 7 red. Red is final; a genuinely different idea needs a new card.

**Near the line, stated so nobody re-reads it later:**
- 2001 missed green on size: +0.049 R a trade against +0.05 R, with t 2.20.
- 3000 missed green on t: 1.94 against 2.0.
- 3001 missed amber on t before costs: 1.49 against 1.5.

None is rounded up. The bars are fixed.

**Next, for the amber ideas (DESIGN §6.4):**
- The owning lane writes at most 3 variations on the card. Each one carries its reason, is committed before it runs, adds information (not knob-turning), and is reviewed for look-ahead if the module changes.
- Each variation is a ledger test, counted in k.
- A slice that is green on its own earns only the budget, never a pass.
- Any regime date needs an external, dated reason.
