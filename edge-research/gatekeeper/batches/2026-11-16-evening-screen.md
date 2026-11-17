# Batch 3: quick screen, 2026-11-16 evening (engine 882d0efed853)

1 real idea screened, 22:10–22:11 Amsterdam (run started late, 21:53). It ran once at its card defaults, over 2014-11 → 2024-12, in all
four news modes. Zone judged on M0 at FTMO costs (DESIGN §6.3, amber before costs per A11.1).
Ledger row T20261116-012889; `zero_trade_symbols` is empty.
**Real test count at this point: 40 rows** (13 batch 1, 26 batch 2, 1 here; all screens).

No merge at 21:15 (evening prep merged none; `lane/literature` still held for IDEA-2011's volume default; `lane/market-logic` has nothing
new). Look-ahead review this run: 1 PASS (3014 @ 533cf034cde2), record in `reviews/`.

| idea | lane | trades | net R / trade | t after costs | t before costs (mid) | zone | slices green on their own |
|---|---|---|---|---|---|---|---|
| 3014 equal-level stop-pool magnet (EURUSD, XAUUSD, US500 h1) | public scripts | 1,345 | −0.056 | −2.36 | 1.64 | **amber** | — |

**Summary:** 0 green, 1 amber, 0 red. Running total of real screens: 40 ideas, 1 green, 9 amber, 30 red.

**Near the line, stated so nobody re-reads it later:** 3014 is amber on t before costs 1.64 against the 1.5 bar, and only there: after
FTMO costs it loses 0.056 R a trade (t −2.36), and no slice is green. Costs eat the whole edge at the mid. 1,345 trades over about 10 years
is about 133 a year for the three symbols, a little under the card's estimate of 150–250. It is data-mined and source-overlapped (yes / yes), so any later G1 runs at k = the real test rows in the ledger.

The card was screened as v1. The Fable spot-check's 4 minor citation issues (digest 2026-11-16) change no rule, default or sign; the
digest noted the 21:15 screen may run it as v1.

## Review notes (no fix required; from the PASS report)
- A pool counts as traded once an entry intent is emitted, even if the engine drops the intent (e.g. a 12 h position still open).
- The code allows an opposite pool at exactly 2 × du (card: "within 2 × du"); measure-zero case.

## Held (not screened)
- **lane/literature not merged** (2000 v4, 2011–2015): IDEA-2011's default reads tick volume (DESIGN §5). Unchanged since midday.
- **1021:** look-ahead FAIL, card-only fix still open (lane).
- **1002, 3012:** gatekeeper chat decisions (mostly-long rule; A11.3 source overlap).
- **2010, 3007, 3010:** tick volume, wait for A13. **3002:** open FAIL (v2 rule). **2000:** fix sits on the held branch.
- No module: 0001, 2002, 2003.

## IC watch (A12, information only)
`gatekeeper/ic_watch.py`: 2 entries (2001, 3000), unchanged; rebuilt from 40 rows. 3014 is not on it.

## Amber variations (step 7)
- No amber row is marked `fixed in <commit>` with variations to queue. 1008, 1009 read "none" (budget spent unused). 2001, 2004, 2006,
  3000, 2007, 1010 still open (lane). Nothing queued.
- New amber row for 3014 added to REVIEW-FIXES (`open (lane)`).

## Needs the gatekeeper chat
- **Tune / walk-forward:** IDEA-2008 (green from midday; unchanged; data-mined, source overlap and locked period seen all yes).
- lane/literature merge decision (2011 volume default).
- 1002 and 3012 decisions; 1008, 1009 closure (amber, no variations).
- 3014's amber budget: amber before costs only (t_mid 1.64, net −0.056 R); variations are the lane's call, with that cost gap in view.
