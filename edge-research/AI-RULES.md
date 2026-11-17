# Edge Research — working rules for Claude

> **Portfolio copy** of the project's `CLAUDE.md`: the standing rules every Claude Code session in Edge Research reads first. One sentence about specific personal trading accounts is reworded; nothing else is edited.

Finds, tests and hands over strategies for the CFD prop plan: a Python engine on IC tick data, several Claude sessions ("lanes") feeding idea
cards into one pipeline, walk-forward, a locked recent period, and a ledger that counts every test. **`DESIGN.md` is the law**; this file is
how to work. Parent rules: `../CLAUDE.md`. Capital side (decided): `CFD-PORTFOLIO-PLAN.md` §0.
Siblings (read-only, copy from them, never edit): `../VWAP Mean Reversion Strategy (Claude)/` (closed: edge not real; start at `CLOSE-OUT.md`),
`../RoboQuant Templates (Claude)/` (parked: 0 of 10 passed).

## Start of every session
1. Read `STATUS.md`, then the part of `DESIGN.md` your role needs, your row in `OPERATIONS.md`, the tail of `LOG.md`, and your lane brief in `lanes/`.
2. `git status` first: other sessions work in this folder. `git add` only files this session changed; never `git add -A` / `commit -a`.

## Hard rules
- **The locked period (2025-01-01 →) is opened only by the gatekeeper**, once per candidate, with `gatekeeper/open_locked.py`. No other session
  reads data after 2024-12-31, from the research store, from `~/cAlgo/Exports/`, or from anywhere else. Research sessions never read
  `~/cAlgo/Exports/` at all: only the engine loader reads data.
- **Every test goes through the engine and lands in the ledger.** No side runs, no "quick look" outside it. The ledger is written only by the
  runner; never edit it by hand. (Mined rules of the one A15 sweep land in `ledger-mining/`, also written only by the runner; user 2026-11-17.)
- **Idea card first.** No backtest without a committed card. Defaults, parameters, grid, walk-forward length and symbols are on the card
  before the first run. Amber variations are written on the card, with their reason, before they run. At most 3, never topped up. (Exception, DESIGN A15, user 2026-11-17: the one mining sweep's committed spec and rule list
  stand in for cards, for mined rules only.)
- **Never change a bar after a result exists.** Rule changes = a dated addendum in `DESIGN.md`, committed before the run it governs, and never
  for an idea whose result is already seen.
- **No strategy is re-tuned on live data,** and no automatic loop adds filters after seeing results.
- **Lanes don't grade their own work.** Only the gatekeeper moves an idea to "candidate".
- **The engine has one owner.** Other sessions use it; a change gets a new engine hash and is logged.
- **Data:** never `rm`; never permanently delete; never empty the Trash; `mv` to `~/.Trash` only after the user says so in this session.
  `~/cAlgo/Exports` and `../data/` likewise, and exports only after the archive is verified. `../data/` is copy-only.
- **Live prop accounts are never touched** by any session (no scripts, no EAs).
- **`~/cAlgo/Sources`:** copy cBots there only with the user's go and nothing running in cTrader; the user builds.
- **Sceptic gates:** the `oos-sceptic` agent runs (1) on the frozen thresholds before the first real idea is tested, (2) on each candidate
  before its locked-period open, (3) before any go-live. Show the user its report unedited. A BLOCK is resolved by fixing an error or by the
  user's decision with the objection in view, never by loosening the bar.
- **Public scripts are idea sources only:** rebuilt from scratch, changed substantively, licence and URL on the card, no code copied, no bulk
  scraping (read pages one at a time, like a person). Firms require your own strategy.
- **Firms:** rules from their own pages only; no emails or messages to firms; Discord only if the user opens it.
- **Git:** commit after each logged step (message ends with the attribution line), then `git push` once a remote exists. Never force-push,
  rewrite history or change remotes without the user's go.

## How to work with the user
- **Push back** with numbers when evidence is weak, a step is skipped, or an idea adds selection on noise. Agreeing to keep things moving is
  the failure mode. Report failures as plainly as passes. Not a licensed adviser: give the maths; decisions are the user's.
- Times in **Amsterdam time** (NY + 6 most of the year, NY + 5 in the DST-gap weeks); NY time only for settings.
- Final results go in the **last message after all tool calls**.
- Diversification = strategy P&L correlation, not price correlation. Judge balance **and** equity drawdown.
- Every result reports the test count it was found at.

## Layout
| path | what |
|---|---|
| `DESIGN.md` | the design and its addenda (the law) |
| `OPERATIONS.md` | sessions, models, sources per lane, source shares, daily rhythm, timeline |
| `STATUS.md` · `LOG.md` · `DIGEST.md` | where things stand · every logged step · the daily digest (mirrored to Notion) |
| `ideas/TEMPLATE.md` · `ideas/cards/IDEA-NNNN-<slug>.md` | idea card template · one card per idea |
| `lanes/` | one brief per session role |
| `engine/` | data loader, kernel, costs, rules, runner (engine owner only) |
| `queue/` | job files (git-ignored once running) |
| `ledger/` | append-only test ledger (`README.md` = schema) |
| `gatekeeper/` | locked-period opens (`OPENS.md`), batch reports, portfolio checks |
| `tests/` | engine unit tests, determinism, referee comparisons |
| `cTrader-Bots/` | referee cBots and finalist cBots (one self-contained .cs each) |
| `runs/` | trade lists and run outputs (git-ignored) |
| `CFD-PORTFOLIO-PLAN.md`, `venue-decision/`, `rulebook/`, `DATA-PLAN.md`, `data-checks/`, `tools/` | capital plan, firm rules, data checks (done before this project started) |

Data: raw exports `~/cAlgo/Exports/fastbt-ic-tick/` (42 symbols) and `fastbt-ftmo-tick/` (12); research store
`../data/ic-research-2014-2024/` (built by the engine owner). Python: `~/.venvs/fastbt/bin/python` (system python3 has no numpy).
