# Lane: public scripts

**Job:** use open-source TradingView scripts and public strategies as **idea sources** for strategies we rebuild and make our own.

**Why this lane faces the highest bar:**
- many public scripts repaint, are tuned showcases, or use future data;
- RoboQuant: 0 of 10 passed;
- many traders run the same scripts, so their trades can match other traders' trades, which the firms flag.

**Rules:**
1. **Read pages one at a time, like a person.** No bulk scraping and no scripts against the site.
   - Check the script's licence (often MPL 2.0) and TradingView's terms.
   - Put the URL, author and licence on the card. **Never copy code** into the repo.
2. **Extract the core concept, then change it substantively:**
   - our own entry and exit logic, stop, timeframe and filters, with reasons;
   - the card says what is new versus the source.
   - Prop firms require your own strategy (`rulebook/DESIGN-CONSTRAINTS.md` §10; FundingPips accepts git history as proof).
3. **Flag repaint risk** on the card: higher-timeframe calls, `security()` look-ahead, pivots confirmed later, `barstate` tricks.
4. **Decayed public strategies** can be revived only through the amber budget: at most 3 variations, each with a stated reason, written before they run.

**Output:** cards in `ideas/cards/`, status `inbox`, data-mined = **yes** unless a real mechanism is stated (who pays, why it persists). About 2–4 cards a day.

**You may / may not:** as the market-logic lane. It can run as a cloud session once the repo has a GitHub remote.
