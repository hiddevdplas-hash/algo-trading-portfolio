# Algorithmic trading research, built with AI coding agents

I'm not a trained programmer. Everything here was built by directing AI coding agents, mainly **Claude Code**, from plain-language goals.
That covers the Python, the C#, the statistics and the agents that review the work. My part is the trading knowledge, the decisions, and
insisting that every claim survives a test designed to break it.

This repository is a curated portfolio. The working repositories are private: they contain personal finances, account details and
third-party material. What's here is real code and real documents from those projects, with personal details removed where marked.
The code is here to read; running it needs the market-data exports, which aren't included.

## The short story
1. **VWAP Mean Reversion (Sep–Nov 2026, 533 commits):** a portfolio of mean-reversion strategies on 26 markets.
   - I built a Python replica of the cTrader trading platform's backtester. It matched the platform **trade for trade** (59 of 64 checks at
     ≥ 99%; one check: 22,384 of 22,400 parameter sets identical) and searched about **100× faster**.
   - It went through optimisation, pre-registered out-of-sample tests, and an **independent AI reviewer** at every decision.
   - **The result: the edge was not real.** 147 out-of-sample tests lost −398 R in total, and in-sample success predicted nothing
     (correlation −0.13). The process caught this **before any money was at risk**, and I closed the project.
2. **RoboQuant templates (Nov 2026):** ten public strategy templates, converted to cTrader and tested exactly as published on years the vendor
   never showed. **0 of 10 passed.** The code isn't included, because the vendor's terms forbid redistributing it.
3. **Edge Research (Nov 2026 →, 297 commits in 11 days):** what the first two projects taught me, turned into a stricter, mostly automated
   research pipeline, run by several AI sessions with fixed roles.
   - **The engine:** a generic Python tick engine on 10 years of data (42 markets, 8.3 billion ticks). Its fills match cTrader **trade for
     trade on 5 of 5 reference strategies** (1,009 trades; four at 100%, one at 99.3%). The last differences came down to how cTrader stores
     stop prices as raw doubles, and that rule is now in the engine. 102 automated tests.
   - **The noise check, done before any real idea was tested:** 1,000 random strategies went through the full pipeline and **none reached
     the final gate**. Strategies with a planted edge of +0.05 R per trade after costs reached it 36% of the time, and +0.10 R 55% of the time.
     So the bars stop noise without stopping everything.
   - **Ideas at scale:** three AI idea lanes (cloud routines and scheduled local runs) write idea cards from first principles, academic
     papers and public scripts. Each card becomes a strategy module, gets an automatic look-ahead code review, and runs through the
     engine into an append-only ledger. So far: **65 idea cards, 60 strategy modules, 53 real ideas screened: 1 green, 10 amber, 42 red.**
     That is a normal hit rate for honest testing, and every test counts toward the bar the next one has to clear.
   - **Governance:** a gatekeeper session merges the lanes' work, and only it can advance an idea. The rules changed 16 times, each time by
     a dated addendum written before the results it governs. An independent reviewer agent blocked three drafts until they were fixed.
   - **A news calendar built from official sources:** 4,336 central-bank and macro events from 2014 to 2024, for the prop-firm news rules.

## What's in here
| folder | what it shows |
|---|---|
| [`vwap-mean-reversion/CLOSE-OUT.md`](vwap-mean-reversion/CLOSE-OUT.md) | the project's result and lessons, in one page |
| [`vwap-mean-reversion/SCEPTIC-GO-LIVE-excerpt.md`](vwap-mean-reversion/SCEPTIC-GO-LIVE-excerpt.md) | the AI reviewer's go-live report that stopped the project: it recomputed every number itself and found no persistence |
| [`vwap-mean-reversion/engine/`](vwap-mean-reversion/engine/) | the Python / numba backtest engine, the cTrader data exporter (C#), and the documents that prove it matches the platform (`REPORT.md`, `RULES.md`, `REFEREES.md`) |
| [`vwap-mean-reversion/cbot/`](vwap-mean-reversion/cbot/) | the trading bot itself (C#, cTrader): sizing, New York time and DST handling, a news filter, restart recovery |
| [`vwap-mean-reversion/tools/report_stats.py`](vwap-mean-reversion/tools/report_stats.py) | report parser, statistics, Monte Carlo drawdown limits, out-of-sample pass check |
| [`edge-research/DESIGN.md`](edge-research/DESIGN.md) | the full design of the new pipeline (data, costs, news rules for prop firms, test counting, walk-forward, the locked period), with its 16 dated addenda |
| [`edge-research/AI-RULES.md`](edge-research/AI-RULES.md), [`edge-research/OPERATIONS.md`](edge-research/OPERATIONS.md) | the standing rules every AI session reads first, and how the sessions, cloud routines, models and sources are run day to day |
| [`edge-research/lanes/`](edge-research/lanes/) | the briefs for the parallel AI sessions: idea lanes, a gatekeeper, an engine owner |
| [`edge-research/agents/`](edge-research/agents/), [`edge-research/gatekeeper/sceptic/`](edge-research/gatekeeper/sceptic/), [`edge-research/reviews/`](edge-research/reviews/) | the two reviewer agents, their reports exactly as returned (including the BLOCKs), and two look-ahead code reviews (one PASS, one FAIL) |
| [`edge-research/engine/`](edge-research/engine/), [`edge-research/tests/`](edge-research/tests/) | the tick engine: kernel, costs, news rules, runner, pipeline, random-strategy check, and its 102 tests |
| [`edge-research/data-checks/referees/REFEREES-RESULT.md`](edge-research/data-checks/referees/REFEREES-RESULT.md), [`edge-research/cTrader-Bots/`](edge-research/cTrader-Bots/) | the engine-vs-cTrader comparison and the five reference cBots (C#) |
| [`edge-research/null/`](edge-research/null/) | the random-strategy calibration: 1,000 random strategies and 200 with a planted edge |
| [`edge-research/ideas/`](edge-research/ideas/), [`edge-research/strategies/`](edge-research/strategies/) | the idea-card template, five example cards, and all 60 strategy modules the lanes wrote |
| [`edge-research/gatekeeper/batches/`](edge-research/gatekeeper/batches/), [`edge-research/ledger/`](edge-research/ledger/) | the gatekeeper's screen reports, the ledger format, and 13 real ledger rows |
| [`edge-research/news/`](edge-research/news/), [`edge-research/mining/SPEC.md`](edge-research/mining/SPEC.md) | the news calendar from official sources, and the spec for the next step: one fixed sweep of 50,000 generated rules, judged against its own noise bar |
| [`edge-research/data-checks/`](edge-research/data-checks/), [`edge-research/tools/`](edge-research/tools/) | the quality check of 193 GB of tick data (42 markets, 2014–2026), the broker-vs-prop-firm feed comparison, and data builders |

## How I work with AI
- **Rules first, results second.** Every project has a written rulebook for the AI. Pass bars are fixed before results exist, and changed
  only by a dated addendum.
- **Independent review.** A separate agent that starts cold reviews every pre-registration and every go-live decision. Its report goes to me
  unedited, and a "no" is resolved by fixing the problem, never by lowering the bar.
- **Verification over trust.** The fast Python engine was only used after it matched the real platform trade for trade, and every
  difference was explained.
- **Parallel sessions with clear roles.** In Edge Research, idea sessions can't grade their own work: only a gatekeeper session can, and
  only through the ledger.
- **Automation with checkpoints.** The idea lanes run on schedules, some in the cloud and some on my Mac. Every evening, one session
  checks their branches, has a second model spot-check the citations, merges what passes, and writes a digest I read on my phone.
- **Honest failure.** Two projects ended without a tradable strategy, and the documents say so plainly. Finding that out cheaply is the point
  of the process.

## Stack
Python (numpy, numba, pandas) · C# for cTrader cBots · cTrader · Claude Code (agents, sub-agents, parallel sessions, cloud routines, scheduled tasks) · Notion · Git / GitHub · TradeZella and Ergodic Labs for
journalling and stress tests.

---
*Research and engineering work, shared for viewing. Not investment advice, and nothing here is a recommendation to trade.*
