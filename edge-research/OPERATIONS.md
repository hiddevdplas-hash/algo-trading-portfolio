# OPERATIONS — how the research runs day to day (decided with the user 2026-11-10 / 11)

> **Portfolio copy** (2026-11-17). How the AI sessions, cloud routines and sources are run day to day. Workspace and routine IDs and local paths are replaced by placeholders; nothing else is edited.

`DESIGN.md` is the law for *what* counts; this file is *who does what, from which sources, when*. Changes to the shares or the review rule
below are made only at a review, never mid-batch.

## 1. The shared contract (every idea session)
1. writes an **idea card** (`ideas/TEMPLATE.md`), committed before anything runs;
2. writes the **strategy module** (rebuilt from scratch, no copied code);
3. puts a **job in the queue**.

Then the system takes over: the **runner** on the Mac tests it on the tick data, the **look-ahead reviewer** checks the module, the **ledger**
records it, the **gatekeeper** grades it. Idea sessions never grade their own work. Cloud sessions can't test (the data is on the Mac): their
cards and modules reach the queue through their branch after the gatekeeper merges them.

## 2. Sessions
| # | session | lane brief | where | model | sources |
|---|---|---|---|---|---|
| 1 | **Gatekeeper = the user's main chat** | `lanes/GATEKEEPER.md` | local, daily | Opus 5.5 | ledger, digest, branch merges, sceptic, locked opens |
| 2 | **Engine owner** | `lanes/ENGINE-OWNER.md` | local, build weeks, later on request | Opus 5.5 | builds and keeps the engine |
| 3 | **Claude's ideas** (market logic) | `lanes/MARKET-LOGIC.md` | cloud routine `<routine-id>`, branch `lane/market-logic` | Opus 5.5 | first principles, aimed at small-capacity niches |
| 4 | **Research** (literature) | `lanes/LITERATURE.md` | local on the Mac (from 2026-11-17; was cloud, branch `lane/literature`), commits on main | Sonnet 5.5 to scan and triage, Opus 5.5 for the cards and code of what's selected | papers, Quantpedia, practitioner websites, free whitepapers (§3) |
| 5 | **Public scripts** | `lanes/PUBLIC-SCRIPTS.md` | **local** (TradingView pages need a real browser) | Sonnet 5.5 to scan, Opus 5.5 for cards and code | TradingView open source, GitHub, the user's Strategy inbox |
| 6 | **Your ideas** (sparring, from 2026-11-17) | `lanes/YOUR-IDEAS.md` | local, interactive: the user opens it whenever they have an idea | Opus 5.5 | the user's own ideas, sparred into cards 0001–0999 |
| 7 | **Mining sweep** (one-off, DESIGN A15) | `mining/SPEC.md` (to be written) | local, a mining session + the engine owner | Opus 5.5 | 50,000 machine-drawn rules, own ledger and luck bar |

- **Final checks on Fable 5.2:** the `oos-sceptic` and `lookahead-reviewer` agents, and a one-off review of the engine's fill logic. Fable is
  about 2× Opus per token and uses the Max limits fastest, so it goes where volume is low and quality matters most.
- **Max plan:** usage is measured in week 1; a lane is paused before quality is lowered.
- **Change from DESIGN §11 (user, 2026-11-10):** public scripts runs locally, not in the cloud.

**Notion (set up 2026-11-11):** an Edge Research page, a **Strategy inbox** database and a **Digest** page mirrored from `DIGEST.md` (workspace IDs removed for this public copy).

## 2a. How the idea lanes run (set up 2026-11-11)
- **A fresh run each day, not a standing chat.** Each run starts from the files, writes its batch, commits, pushes and stops. The prompts
  live in the schedulers; each run logs one line in `lanes/run-logs/<LANE>.md`.

  | lane | scheduler | runs (Amsterdam) | cards per run | cards a day |
  |---|---|---|---|---|
  | Claude's ideas | **cloud routine** `<routine-id>`, Default environment (no web), branch `lane/market-logic` (moved from the Mac 2026-11-11; the desktop task `edge-market-logic-daily` is paused as a fallback) | base 07:00, 10:00, 13:00; bonus 16:00, 19:00 (adaptive from 17 Nov) | 3 | 9–15 |
  | Public scripts | desktop app scheduled task `edge-public-scripts-daily` (from Fri 13 Nov; runs while the Mac is on) | base 07:30, 10:30, 13:30, 16:30; bonus 21:30, 23:30 (adaptive from 17 Nov) | 2 | 8–12 |
  | Research | local task `edge-literature-local` on the Mac (built-in browser for SSRN and repositories), on main; the cloud routine `<routine-id>` and the shortlist scan are paused (2026-11-17) | base 11:45, 18:45; bonus 01:45 (adaptive from 17 Nov) | up to 3 | up to 9 |

  **Changes of 2026-11-16 (user: "do it"):** public scripts 4 runs a day, starting from TradingView Popular > Strategies > Open-source
  only; research adds a Sonnet **shortlist scan** (cloud routine, 05:40 and 11:40) writing `lanes/literature-shortlist.md` for the card
  runs; Claude's ideas gets an **open slot** (at most 1 of 3 cards a run without a mechanism, data-mined yes; `lanes/MARKET-LOGIC.md`);
  the gatekeeper's **screen task** `edge-gatekeeper-screen` (local; 14:15 and 21:15, every 3 hours from 17 Nov) merges lane work at midday, runs the look-ahead
  reviews and screens every ready card, so a card is tested the same day.

  **Changes of 2026-11-17 (user: "I want to do everything you just proposed"):** literature card runs move to the Mac (task
  `edge-literature-local`, 11:45 and 18:45, on main), adding SSRN via the built-in browser, central-bank working-paper series and
  individual Quantpedia pages; the cloud card routine and shortlist scan are paused (5 card runs in 48 h gave 0–1 cards). Screen runs
  push the user one line. New inputs (context symbols, CFTC positioning) and a separate **mining lane** with its own ledger and luck
  bar are drafted in `gatekeeper/A14-DRAFT.md` (sceptic review, then the user's yes, before anything runs).

  **Adaptive schedule and 3-hourly screening (user, 2026-11-17: "Yes, set up all three"):** each automatic lane has base runs and
  bonus runs. A bonus run goes on only if the lane's latest real run wrote at least one card; a base run is skipped after two empty runs in
  a row (a skip line in the run log). Claude's ideas: base 07:00, 10:00, 13:00, bonus 16:00, 19:00 (cloud). Public scripts: base 07:30,
  10:30, 13:30, 16:30, bonus 21:30, 23:30. Literature: base 11:45, 18:45, bonus 01:45 (browser runs never overlap). The gatekeeper's
  screen task runs every 3 hours (02:15 … 23:15) behind a cheap gate (`gatekeeper/screen_gate.py`): it works and pushes only when a
  card is new or changed, REVIEW-FIXES changed, or a lane branch has unmerged commits. Full 24/7 lanes are revisited at the week-6 review.

  Runs per day set by the scale-up (below, 2026-11-12). Each run also writes the strategy module of each new card, and backfills up to 3
  of its lane's cards still marked "module pending" (IDEA-0001 moved to the your-ideas lane, 2026-11-17). Lanes don't submit jobs until the bars are frozen.
  **Module rules for the look-ahead review (engine owner, 2026-11-12):** a review is tied to the module's commit, so a module is final
  before it is queued (any later edit means a new review). Modules are **self-contained**: import numpy and `engine.*` only, never
  `strategies/*`, `tests/*` or `tools/*` (a pinned shared helper sends every importer back to pending). A genuinely shared helper is
  asked from the engine owner, who moves it into the engine.

- **Card numbers by lane** (no clashes between parallel runs): user 0001–0999, market logic 1000–1999, literature 2000–2999,
  public scripts 3000–3999.
- **Strategy modules** are written only once the engine owner publishes the strategy interface (`engine/STRATEGY-API.md`); until then the
  lanes write cards only.
- **Lanes never** run backtests, read data, touch `engine/`, the ledger or `DIGEST.md`, or edit cards of another lane.
- **Cloud first** (user, 2026-11-11): lanes that only need the repo and the web run in the cloud, each on its own `lane/*` branch,
  so they run with the Mac closed and never clash. Local stays local only where data or hardware is needed: engine, runner, gatekeeper,
  locked period, cTrader. Public scripts: a cloud access test ran 2026-11-11: TradingView's
  Pine source isn't in the fetched text (0 / 3; it needs a real browser), GitHub and the Notion inbox work. **Decided (user, 2026-11-11):
  the whole lane stays local** (`edge-public-scripts-daily`); revisit at the week-6 review.
- **Gatekeeper set up 2026-11-11 (user):** a fresh local session "Gatekeeper: Edge Research main chat" is the user's main chat from now
  on (the long planning chat retires). The desktop task **`edge-gatekeeper-evening-prep`** (19:30 daily, Auto mode) checks the lane
  branches, merges what passes, has new literature / public-scripts cards' citations spot-checked by a Fable subagent, and writes the
  digest to `DIGEST.md` and Notion before the user's check-in. It never grades, tunes or touches the engine, ledger or data.
- Sidebar: all Edge Research sessions sit in the **Edge Research** section of the Code tab.
- **Status 2026-11-11:** both desktop tasks created (saved in Auto mode; they run while the app is open; a run missed while it was closed
  runs on next launch). The cloud routine was first refused (no GitHub app access); the user granted
  access and it was created: **`<routine-id>`** (claude.ai/code/routines), cron `30 5 * * *` UTC = 06:30 Amsterdam in
  winter, 07:30 in summer; Opus 5.5 with Sonnet subagents for scanning; **no connectors** (removed: it needs none). First test run 2026-11-11.
- **Scale-up, brought forward to 2026-11-12 (user, 20:00: "Let's bring the card scale up forward now"; first decided 2026-11-11: "I
  want to test way more ideas").** The old "until 24 Nov the batches stay small" is void: the engine screens far more than the lanes can write
  (measured: ≈ 20,000 quick screens a day loading ticks, ≈ 14,000 full walk-forwards; LOG 2026-11-11), Max usage was 15% of the week on
  Thu 12 Nov, and the first tests can start Sat 14 – Sun 15 instead of Wed 25 Nov.
  - **Output: about 25 cards a day** from Fri 13 Nov (table above): 9 Claude's ideas, 12 research, 4 public scripts (36 / 48 / 16%; the queue
    still takes cards in the §4 shares, extra cards wait). Expected backlog at Sat 14's 19:30 merge: about 65 cards.
  - The old formula (1.2 × quick-screen throughput) no longer binds: throughput is about 800× the card output. The limits are **Max usage and
    card quality.** Growth stays in **more runs a day** (each fresh, seeing the newest cards), never bigger batches.
  - **Brakes, checked by the gatekeeper at each evening check-in:** (1) weekly all-models usage on course to pass 80% before its reset → the
    lanes lose runs first (research last); (2) a lane whose cards are held as duplicates or re-skins more than 1 in 5 over 3 days → one run
    fewer; (3) Claude's ideas has no web: it starts at 3 runs, not 4, and goes up only if its hold rate stays under 1 in 10.
  - Why more is worth it (unchanged): the count-adjusted bar grows with the log of the test count (900 → 1,800 → 3,600 ideas a quarter
    raises it about 5% → 10%); the cost that grows linearly is false finalists: at a 1% noise rate, 25 cards a day ≈ 2,250 a quarter ≈ 5 false
    finalists a quarter (vs about 2 at 900), each costing roughly one evaluation fee before the locked period and the bot test stop it.
  - Guard: the gatekeeper rejects re-skins of existing or dead cards before they are queued.
- Batch sizes are revisited in the week-1 Max-usage check and at the week-6 review.

## 3. Sources per lane
**Research (literature) lane:**
- **Papers:** arXiv q-fin (its official API allows programmatic access: scan everything new); SSRN (**targeted searches** only, abstracts
  and free full texts read one at a time; its terms forbid automated bulk downloading); NBER; Fed, ECB, BoE and BIS working papers.
- **Quantpedia:** the free strategy descriptions, read one page at a time; they are an index of papers by asset class.
- **Practitioner websites** (read one page at a time, like a person): Quantocracy (daily aggregator of quant blogs), Robert Carver's blog,
  Robot Wealth, Alpha Architect, Ernie Chan's blog, Quantpedia's blog, Concretum Group (intraday index momentum).
- **Free whitepapers:** AQR research library, Man Group research, central-bank and BIS papers.
- **Free PDFs: legal sources only** (open access, released by the author or publisher, public domain). No pirated copies of commercial books.
- **Books:** none bought now (user, 2026-11-11). Claude already knows the main ideas of the popular titles; the websites are fresher and free.
  If one is wanted later: Carver, *Advanced Futures Trading Strategies* (2023).

**Public-scripts lane:**
- **TradingView open-source scripts:** one page at a time, licence checked (usually MPL 2.0), repaint risk flagged, no code copied.
- **GitHub:** repositories with an open licence (search via the official API is allowed); mostly reference implementations, rarely new ideas.
- **Strategy inbox** (Notion): what the user forwards from the phone; the lane reads what each item points to, at its source.
- **Not used:** RoboQuant (its terms forbid automated access and redistribution), Instagram, TikTok, YouTube.

**X: deferred to the week-6 review (user, 2026-11-11).** The compliant route, if chosen then: xAI's API with its `x_search` tool, a weekly
scan of about 30–50 accounts and keyword searches, Grok filtering to at most 5 posts a week, cards built from the exact post text (never Grok's
summary). Cost checked 2026-11-10: $5 per 1,000 posts fetched plus tokens, estimated $5–15 a month. Browsing X with the user's login is not
used: X's terms forbid automated scraping, and the user's account would carry the risk.

## 4. Source shares and the week-6 review (decided 2026-11-11, before any card is tested)
| source | share of cards tested per week |
|---|---|
| Claude's ideas | 40% |
| Papers + Quantpedia | 30% |
| Practitioner websites + free whitepapers | 15% |
| TradingView + GitHub (+ Strategy inbox) | 15% |
| Your ideas (sparring) | outside the shares: screened at the next screen run |

- The gatekeeper takes cards from the queue in these proportions; extra cards from a source wait. Every ledger row carries its source.
- **Week-6 review (about Tue 6 Jan 2027), rule fixed now:**
  1. per source: cards tested, the share reaching amber or better at the quick screen, and the share passing the walk-forward (G1),
     each set beside the random strategies' share at the same stage;
  2. a source with fewer than 20 tested cards keeps its share;
  3. otherwise the new shares are proportional to the amber-or-better share per test, each between 10% and 50%;
  4. a source whose amber-or-better share is not above the random strategies' share is paused;
  5. X is decided at this review, with these base rates in view (the user's call).
- Amber is a low bar: this review measures where promise comes from, not proof. Proof is the walk-forward and the locked period.

## 5. Daily and weekly rhythm (Amsterdam time)
| when | what |
|---|---|
| around the clock | the runner's Python batches (they don't need a Claude session) |
| 11:45, 18:45 (+ 01:45 bonus) | the research lane runs on the Mac (scheduled) and commits on main |
| daytime, while the Mac is on | Claude's ideas and public scripts write cards; they stop for permission prompts and at the end of turns |
| **evening check-in, 15–20 min** | the user and the gatekeeper: digest, merge the lane branch, approvals, answer blocked sessions |
| anytime, phone | the user adds finds to the Strategy inbox |
| **Sunday, 30 min** | weekly review: batch vs random, the count-adjusted bar, Max usage |

## 6. Timeline (replaces the old dates in DESIGN §12; set 2026-11-11)
The engine build hasn't started: 7–11 Nov went into the design decisions, so everything is about a week later than first planned. Each step
starts only when the one before has passed its checks; a referee mismatch is fixed before any real test.

**Dates are latest dates, not start dates (user, 2026-11-12: "I don't want to lose time, I want to win time").** When a step has passed
its checks, the next one starts at once, without waiting for its calendar slot; the user's own steps (referee evening, noise-target pick,
sceptic report) move earlier when their inputs are ready. Gates never move: no step starts before the one it depends on has passed, and no
check or test is shortened to gain time. Lane card output: the scale-up was brought forward on 2026-11-12 (§2a). First case: the engine owner's Thu 12 – Sat 14 block finished on Wed 11, so build list 4–10 started Thu 12, 13:35.

| when | Claude | user |
|---|---|---|
| **Wed 11 Nov** | this plan; Notion inbox and digest | the 7 remaining FTMO exports (CADCHF, CADJPY, CHFJPY, XAGUSD, EU50.cash, JP225.cash, UKOIL.cash) |
| **Thu 12 – Sat 14** | research store (EURUSD and XAUUSD measured first), cost table v1 (IC + FTMO), engine core. **Idea sessions start writing cards.** | evening check-in |
| **Sun 15 – Tue 17** | news rules and the calendar back to 2014, trade log, unit tests, ledger, queue, runner; the 5 referee strategies in Python and as cBots | evening check-in |
| **Wed 18 or Thu 19, evening** | — | **referee evening:** build the 5 cBots and run them in cTrader tick mode (2–3 h) |
| **Fri 20 – Sun 22** | referee comparison; random-strategy check (overnight); look-ahead reviewer test | weekend check-in |
| **Mon 23 – Tue 24** | trade-off table; bars frozen by addendum; sceptic report | **pick the noise target**; read the sceptic report (30 min) |
| **Wed 25 Nov** | **first real ideas tested**, the card backlog first | daily digest (5 min) |
| **Dec** | pipeline running; weekly batch vs random | digest, Sunday review |
| **about Tue 6 Jan 2027** | **week-6 review** (§4) | review (1 h) |
| **Jan – Feb 2027** | candidates → locked-period open → cTrader check → firm feed check → 1-week bot test | cTrader runs; buying decisions per firm |

## 7. Done and not done (2026-11-11)
**Done:** venue (CFD), firms and products, the CFD portfolio plan, firm rulebooks; IC ticks for 42 symbols checked; FTMO ticks for 12 symbols
plus 20 of the 27 new exports; FTMO commission ($5.00 per lot round trip); `DESIGN.md` with all nine proposals decided; project rules, lane
briefs, card template, ledger schema, sceptic and look-ahead agents; the first idea card; the private repo and the public portfolio; this plan.

**Not done:** the 7 FTMO exports; the whole engine (store, costs, kernel, rules, news calendar to 2014, ledger, queue, runner, referees,
random-strategy check); swap history; starting the lane sessions; later the five other firms' feeds (G3) and the live news calendar in the cBot.
