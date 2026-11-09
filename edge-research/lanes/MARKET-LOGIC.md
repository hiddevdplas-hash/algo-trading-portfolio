# Lane: market logic

**Job:** write idea cards from first principles: who pays, and why it persists. The first lane in the queue (the best expected quality per test).

**Families to work** (CFD plan §0.1, `DESIGN-CONSTRAINTS.md` §10):
- time-series trend / momentum, two-sided;
- intraday momentum, including into the close (no Friday late entries at FTMO);
- session and opening-range effects;
- short-term reversal after overreaction;
- FX fixing flows;
- calendar and flow effects (turn of month, quarter end, index rebalancing): two-sided or small;
- carry (class C only, low fit);
- price-only levels: prior day, session highs and lows, time-based profiles.

**Not:**
- volume-based logic (IC tick volume isn't real volume);
- entries triggered by upcoming news;
- grids, martingale;
- long-only as the main logic;
- overnight-gap logic.

**Output:** cards in `ideas/cards/` from `ideas/TEMPLATE.md`, status `inbox`.
- Quality over count: about 3–5 well-built cards a day is plenty.
- Check the ledger and `ideas/cards/` first, so you don't repeat a dead idea. A genuinely different mechanism is a new card; a re-skin of a dead one isn't.
- Spread the cards over the four exposures (equities, USD, metals, oil).

**You may:**
- queue jobs for your own cards once the engine is live;
- write amber variations on your cards (with reasons, before they run).

**You may not:** change the engine, edit the ledger, read data after 2024-12-31 or `~/cAlgo/Exports/`, or move a card past `stress`.
