# Ledger: one row per test (append-only)

**Files:** `ledger/YYYY-MM-DD.jsonl`, one JSON object per line.
- Written **only by the runner** (`engine/runner.py`), never by hand.
- Committed daily by the gatekeeper.
- A correction is a new row with `supersedes: <test_id>`.

| field | meaning |
|---|---|
| `test_id` | unique id (date + sequence) |
| `ts` | UTC time the run finished |
| `idea_id`, `card_version`, `card_commit` | the card and the git commit it was read from (must predate the run) |
| `lane` | market logic · literature · public scripts · null · referee |
| `stage` | screen · amber-V1..V3 · tune · wf · stress-<name> · locked · null-<stage> · referee |
| `variant` | parameter values of this run |
| `grid_id`, `grid_size` | which declared grid this point belongs to, and its size |
| `symbols`, `timeframe`, `period` | as run (period never past 2024-12-31 unless stage = locked) |
| `mode` | funded · evaluation |
| `engine_hash`, `cost_hash`, `data_hash` | reproducibility |
| `review` | look-ahead review id and result |
| `metrics` | trades, net R, R/trade before and after costs, PF, t-stat, daily Sharpe, max DD (R), MC 95th DD, % yearly blocks positive, long / short split, top-5 share, by-year, by-symbol, by-session, cost share, hold-time stats, dropped signals |
| `zone` / `verdict` | green · amber · red, or pass · fail with the rule that decided it |
| `run_path` | trade list in `runs/` (git-ignored) |
| `count_at_run` | total tests and effective ideas in the ledger when this row was written |
