# Algorithmic trading research, built with AI coding agents

I'm not a trained programmer. Everything here was built by directing AI coding agents, mainly **Claude Code**, from plain-language goals.
That covers the Python, the C#, the statistics and the agents that review the work. My part is the trading knowledge, the decisions, and
insisting that every claim survives a test designed to break it.

This repository is a curated portfolio. The working repositories are private: they contain personal finances, account details and
third-party material. What's here is real code and real documents from those projects, with personal details removed where marked.

## The short story
1. **VWAP Mean Reversion (Sep–Nov 2026, 533 commits):** a portfolio of mean-reversion strategies on 26 markets.
   - I built a Python replica of the cTrader trading platform's backtester. It matched the platform **trade for trade** (59 of 64 checks at
     ≥ 99%; one check: 22,384 of 22,400 parameter sets identical) and searched about **100× faster**.
   - It went through optimisation, pre-registered out-of-sample tests, and an **independent AI reviewer** at every decision.
   - **The result: the edge was not real.** 147 out-of-sample tests lost −398 R in total, and in-sample success predicted nothing
     (correlation −0.13). The process caught this **before any money was at risk**, and I closed the project.
2. **RoboQuant templates (Nov 2026):** ten public strategy templates, converted to cTrader and tested exactly as published on years the vendor
   never showed. **0 of 10 passed.** The code isn't included, because the vendor's terms forbid redistributing it.
3. **Edge Research (Nov 2026 →):** what the first two projects taught me, turned into a stricter, mostly automated research pipeline.
   - Several AI sessions generate ideas.
   - A generic engine tests them on 12 years of tick data.
   - Every test is counted in a ledger.
   - Random strategies are run through the same pipeline to measure how often noise "passes".
   - A locked recent period is opened only once per candidate.

## What's in here
| folder | what it shows |
|---|---|
| [`vwap-mean-reversion/CLOSE-OUT.md`](vwap-mean-reversion/CLOSE-OUT.md) | the project's result and lessons, in one page |
| [`vwap-mean-reversion/SCEPTIC-GO-LIVE-excerpt.md`](vwap-mean-reversion/SCEPTIC-GO-LIVE-excerpt.md) | the AI reviewer's go-live report that stopped the project: it recomputed every number itself and found no persistence |
| [`vwap-mean-reversion/engine/`](vwap-mean-reversion/engine/) | the Python / numba backtest engine, the cTrader data exporter (C#), and the documents that prove it matches the platform (`REPORT.md`, `RULES.md`, `REFEREES.md`) |
| [`vwap-mean-reversion/cbot/`](vwap-mean-reversion/cbot/) | the trading bot itself (C#, cTrader): sizing, New York time and DST handling, a news filter, restart recovery |
| [`vwap-mean-reversion/tools/report_stats.py`](vwap-mean-reversion/tools/report_stats.py) | report parser, statistics, Monte Carlo drawdown limits, out-of-sample pass check |
| [`edge-research/DESIGN.md`](edge-research/DESIGN.md) | the full design of the new pipeline: data, costs, news rules for prop firms, test counting, walk-forward, the locked period |
| [`edge-research/agents/`](edge-research/agents/) | the two reviewer agents: `oos-sceptic` (red-teams every candidate) and `lookahead-reviewer` (checks code for future-data leaks) |
| [`edge-research/lanes/`](edge-research/lanes/) | the briefs for the parallel AI sessions: idea lanes, a gatekeeper, an engine owner |
| [`edge-research/data-checks/`](edge-research/data-checks/), [`edge-research/tools/`](edge-research/tools/) | the quality check of 193 GB of tick data (42 markets, 2014–2026), and the broker-vs-prop-firm feed comparison |
| [`edge-research/ideas/`](edge-research/ideas/), [`edge-research/ledger/`](edge-research/ledger/) | the idea card every strategy starts from, and the test-ledger format |

## How I work with AI
- **Rules first, results second.** Every project has a written rulebook for the AI. Pass bars are fixed before results exist, and changed
  only by a dated addendum.
- **Independent review.** A separate agent that starts cold reviews every pre-registration and every go-live decision. Its report goes to me
  unedited, and a "no" is resolved by fixing the problem, never by lowering the bar.
- **Verification over trust.** The fast Python engine was only used after it matched the real platform trade for trade, and every
  difference was explained.
- **Parallel sessions with clear roles.** In Edge Research, idea sessions can't grade their own work: only a gatekeeper session can, and
  only through the ledger.
- **Honest failure.** Two projects ended without a tradable strategy, and the documents say so plainly. Finding that out cheaply is the point
  of the process.

## Stack
Python (numpy, numba, pandas) · C# for cTrader cBots · cTrader · Claude Code (agents, sub-agents, parallel sessions) · Git / GitHub · TradeZella and Ergodic Labs for
journalling and stress tests.

---
*Research and engineering work, shared for viewing. Not investment advice, and nothing here is a recommendation to trade.*
