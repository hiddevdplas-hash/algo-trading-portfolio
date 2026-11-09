# Lane: literature

**Job:** turn published research into idea cards. Sources:
- SSRN, arXiv q-fin;
- journal articles and working papers;
- central-bank and BIS research on FX flows.

**Filter:**
- **time-series effects on what we trade:** indices, FX, metals, oil. Not equity cross-section: a CFD account can't hold a sorted stock portfolio;
- an out-of-sample or post-publication check, where the paper has one;
- **decay:** published effects shrink by about half after publication (McLean & Pontiff 2016). The card states the effect size the paper found and the size we'd need after costs to pass;
- **costs:** many intraday papers ignore spreads. Check that the effect survives a worst-firm spread before writing the card;
- futures or ETF effects that depend on the overnight return may vanish on CFDs, because of swap (DESIGN-CONSTRAINTS; RESEARCH-DESIGN-DRAFT §5).

**Output:** cards in `ideas/cards/`, status `inbox`.
- "Evidence before testing" cites the paper: authors, year, link, sample, market, effect size.
- Rebuild the rule from the paper's description; don't copy code.
- About 2–4 cards a day. Check the ledger and existing cards for duplicates.

**You may / may not:** as the market-logic lane (`lanes/MARKET-LOGIC.md`).
- This lane needs only the web and the repo, so it can run as a cloud session once the repo has a GitHub remote.
