# Ledger: one row per test (append-only)

**Files:** `ledger/YYYY-MM-DD.jsonl` (UTC day), one JSON object per line.
- Written **only by the runner** (`engine/runner.py`, under a file lock), never by hand.
- Committed daily by the gatekeeper.
- A correction is a new row with `supersedes: <test_id>`.

| field | meaning |
|---|---|
| `test_id` | `T<yyyymmdd>-<n>`, n = the row's number in the whole ledger |
| `ts` | UTC time the row was written |
| `job_id` | the queue job |
| `idea_id`, `card`, `card_commit`, `card_version` | the card and the commit it was read from (the runner refuses a card that is uncommitted or changed) |
| `lane` | market logic · literature · public scripts · null · referee |
| `stage` | screen · amber-V1..V3 · tune · wf · stress-<name> · null-<stage> · referee (never `locked`: that is `gatekeeper/open_locked.py`) |
| `strategy`, `strategy_commit` | the strategy module and its commit (refused if uncommitted or changed) |
| `variant` | parameter values of this run |
| `grid_id`, `grid_size` | which declared grid this point belongs to, and its size |
| `symbols`, `timeframe`, `period`, `class`, `venue` | as run (period inside 2014-11 … 2024-12; venue `ftmo` for research, `ic` only for referees) |
| `stress` | `spread_mult`, `swap_mult`, `zero_positive_swap` (G2) |
| `engine_hash`, `cost_hash`, `data_hash` | reproducibility (`engine/hash.py`; cost table; store month counts of the symbols) |
| `review` | look-ahead review id and result (null = not reviewed: the result doesn't count yet) |
| `metrics` | per news mode `M0`…`M3`: trades, net R, R per trade gross / net (FTMO) / net (IC), profit factor, t-stat, daily Sharpe, max DD (R), Monte Carlo 95th DD, % years positive, long / short, top-5 share, by year / symbol / session, cost share, spread / commission / swap / slippage per trade, hold-time stats (fail if > 10% under 2 min), news handling counts, dropped / blocked signals |
| `news_flag` | DESIGN §3.6 flag 6: true if M3 keeps less than half of M0's profit |
| `zone` / `verdict` | set by the pipeline stage that judges (green · amber · red, or pass · fail with the rule); null when written by the runner |
| `run_path` | trade logs in `runs/` (git-ignored): one `.npz` per symbol and mode |
| `count_at_run` | total tests and distinct ideas in the ledger when this row was written (all lanes; the luck bar's k is NOT this: `engine.pipeline.count_k`, DESIGN A10.4) |
| `route` | real lanes: base · V1 · V2 · V3 (the screened route this test belongs to); null for null / referee rows written before A10 |
| `card_flags` | real lanes: the card's `data_mined`, `seen_family`, `source_overlap` (true / false; A11.3) and `grid_size` as the runner read them (DESIGN A10.4); k uses the idea's first screen row (A11.4) |
| `zero_trade_symbols` | symbols of the job with no trade in any mode run (e.g. emptied by a filter); [] when all traded. Rows before 2026-11-15 (engine fb7127a41fd1) lack it. A real job whose module gives no intent at all on a symbol is refused by the runner instead (no row) |
| `data_info` | per symbol: ticks, crossed ticks dropped / zeroed by the loader, venue, spread multiplier |
