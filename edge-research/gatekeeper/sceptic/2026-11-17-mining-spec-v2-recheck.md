VERDICT: PASS WITH CONDITIONS. Findings 1–9 are resolved or written in. v2 and the engine-a15 runner side add two new gaps, both in the cost stress for mined rules (conditions 1 and 2 below). Neither needs a bar, seed, count or the grammar to change, and neither blocks the draw. Both must be fixed before the first mined G2 row.

Scope:
- Read: `mining/SPEC.md` v2 at 8c55fc2, `mining/LOG.md`, and branch `engine-a15` (540e4ed, not merged into main): `engine/mining.py`, the runner's mining hooks and the cash-session stress, `engine/data.py` `in_session`, the names of the tests in `tests/test_mining.py`, `engine/MINING-API.md`. Also `data-checks/cot/coverage.json`.
- I recomputed the §6.2 bloc probabilities.
- Read-only. Nothing after 2024, nothing in `ledger-mining/` or `runs/mining/`. I didn't run the test suite.

## Findings 1–9: status
| # | status | evidence |
|---|---|---|
| 1 expiry calendar | **resolved (filter dropped)** | SPEC §4, §6.5: no calendar series at all |
| 2 filters beyond A15 §1.1 | **resolved** | vix, expiry and the composer trend filter are dropped; `regime` = A15's "trend". The user's decision is recorded in `mining/LOG.md` row 3, and the IDEA-1007 overlap is disclosed in §11 |
| 3 job fields bound | **resolved in code** | `check_job` recomputes `def_hash` from `params`; `derived()` fixes symbols, timeframe, class, context, series, engine filters, period and modes; test `test_every_job_field_comes_from_the_definition`. "Refuses unsorted lists" (§8.2) is enforced only indirectly, because an unsorted def can't match the bound hash. That is effective, but not a separate check |
| 4 zero-trade rows | **resolved in code** | the ZERO INTENTS guard skips `MI.LANES`; test `test_zero_intent_symbol_writes_a_row` |
| 5 locked-open series | **written in** | §13: a loader that is byte-identical for t ≤ 2024, checked on a sample before the first mined open. Only COT and context symbols are left to extend |
| 6 finite inputs | **written in** | §2 "defined and false at i − 1", plus a unit test in §10.2 |
| 7 symbol weights | **resolved** | Bloc weights ∝ m_b / E[min(k, m_b)]. My recomputation: for the 39, weights 2.8 / 2.8 / 1.143 / 1.143 / 8.4 give 0.172 / 0.172 / 0.070 / 0.070 / 0.516 and inclusion 0.0614 for every symbol (0.0641 in `any` mode). For the COT 13: 0.446 / 0.212 / 0.182 / 0.159, inclusion 0.159. All match §6.2 |
| 8 cost test | **written in** | the whole FTMO spread is doubled; pass = every judging bar including the luck bar at the frozen k, in each eligible mode; the G3 window is fixed at 2020-04-01 → 2021-07-02 (weak, and stated as weak); the holiday limit is stated |
| 9 binding details | **resolved** | canonical form shared with `engine.mining`; types fixed by a schema; a duplicate is redrawn within its family slot; numpy 2.0.2 pinned; `spec_sha256` bound; one draw only; PULL ties are ≤; COT coverage shows all 13 codes in every year 2014–2024 (`coverage.json`); a 2014–2024 reason is given for leaving out JP225 |

## Conditions (most serious first)

**1. The ×2 spread test can't do per symbol what SPEC §12 says, and the runner doesn't fix its parameters. (before the first mined G2)**
- **Where:** `engine-a15:engine/runner.py:539`. One `job["stress"]["cash_session"]` applies to every symbol of the job, and `MINING-API.md:42-44` describes one window per job. `check_job` never inspects `stress`.
- **Effect, with SPEC §12.1 ("each symbol takes its own route"):**
  - A rule on US500 + XAUUSD needs two windows. A rule on US500 + EURUSD would double EURUSD's spread outside New York cash hours, even though EURUSD is on the G3 route.
  - Whoever writes the `g2-cost2x` job therefore chooses the window and could set `spread_mult` to anything. That is the free choice §10.4 was written to remove.
- **Smallest fix:**
  - The runner derives the stress of each G2 stage from the def: per symbol, ×2 and that symbol's window from a fixed table in `engine/mining.py` (copied from SPEC §12.4); no ×2 for symbols on the none or G3 routes; ×1.5 for `g2-cost`.
  - `check_job` refuses any other `stress`.
  - Add a unit test with a mixed-route rule.

**2. G3 with few or no trades in its 1.25-year window is undefined. (before the first mined G3)**
- **Where:** SPEC §12.3.
- **Problem:** a rule's FX trades inside 2020-04-01 → 2021-07-02 can number from zero to a handful. "≥ 80% within ±1 bar" then either passes on nothing or is decided by hand.
- **Smallest fix:** state now a minimum number of trades in the window, e.g. 30 per G3 symbol. Below it, that symbol takes the ×2-at-all-hours route instead (FX has no cash session). No choice remains.

**3. The rows of the null's sign tables depend on whatever is in the store when the null runs. (low)**
- **Where:** `mining.py` `null_symbols()` = sorted `listdir(STORE_ROOT)`.
- **Problem:** a symbol added to the store before the null runs shifts every row, so every sign changes. The procedure is fixed, but its input isn't.
- **Fix:** put the symbol list, or its hash, in `BOUND.json`, and have `sign_tables` use that list.

**4. Bind the spec text before the draw. (low)**
- **Typo:** SPEC §9, line 283, says "v2's draft rule"; it should be v1's. Because `spec_sha256` is bound and "any change voids the list", fix it before binding.
- **No check yet:** `bound()` doesn't verify `spec_sha256` or the numpy version. Add both checks so that a SPEC edit after the draw is caught by the runner, not just forbidden by the text.

**5. Merge and pin `engine-a15` before the draw. (procedural)**
- The guards for 3, 4, the null, k and the window exist only on the branch.
- A15 §9 requires them to pass their tests before the sweep, and §10.6 requires one pinned engine commit. Record that commit with `BOUND.json`.

## New in v2, checked clean
- **CTX on m15 and h1 only:** a structural reason (the h4 anchor), not taken from any result.
- **COT exclusions** now carry reasons that hold with 2014–2024 knowledge.
- **The null's signs** are now numpy tables per (symbol, Amsterdam entry day). They are seeded from `[NULL_SEED, r]`, fixed before the draw, the same in every mode and row, with costs not flipped.
- **`judge()` with z\*** scales the bar by the same σ·max(1, √VR) as the statistic, so the units match.
- **`null_statistic`** uses the same G1 bars as judging, minus the luck bar.
- **Exclusions, mirror symmetry, seeds and the 60 replicates:** unchanged from v1 and still clean. The A1.5 statement is more credible now that the weighting is uniform and expiry is gone.

## Files
- <project>/Edge Research/mining/SPEC.md (§9 line 283, §12.1–12.4, §13)
- engine-a15:engine/mining.py (`check_job`, `null_symbols`, `bound`)
- engine-a15:engine/runner.py (line 539, cash_session per job)
- engine-a15:engine/MINING-API.md (lines 42–44)
- <project>/Edge Research/data-checks/cot/coverage.json
