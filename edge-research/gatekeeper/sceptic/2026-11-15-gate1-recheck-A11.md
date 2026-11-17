VERDICT: PASS WITH CONDITIONS

# oos-sceptic, gate (1) re-check of the A11 fixes only, 2026-11-15

I reviewed at HEAD `6fa4993` (engine `041e0e5a8990`). The ledger has 12,849 rows: 0 real and 162 new null-lane rows. Every row's period is 2014-11 → 2024-12. I read nothing after 2024 and ran nothing that writes the ledger.

**Numbers I recomputed** (scripts: `<scratchpad>/a11chk.py` and `a11chk2.py`; I rebuilt each zone from the trade files):
- **Zones:** match `runs/null/state.json` on all 1,200 strategies, 0 mismatches.
- **Random amber 5.0%:** 50 of 1,000. 48 come through the before-costs t-route and 2 through the after-costs slice route.
- **Engine owner's figures confirmed:**
  - 54 strategies moved red → amber: 44 random, 9 at +0.05 R, 1 at +0.10 R.
  - Random rescued 0.2%; random reaching the gatekeeper 0 at k = 10 / 100 / 1,000.
  - +0.05 R: 36% before the luck bar, then 28 / 20 / 17%. +0.10 R: 55%, then 54 / 50 / 45%.
  - VR over 732 route-modes: median 1.023, p95 1.311, max 1.581.
  - Hold-time fails: 0. The largest share of trades under 2 min is 4.2%.
- **Walk-forward default:**
  - 15 routes changed their choices.
  - 4 mode verdicts changed, on 3 strategies (N1035, N1088, N1125). Counted per strategy, that is the engine owner's "3 verdicts".
  - The set of strategies reaching the gatekeeper is 91 before and after, so none was added or lost.
- **Cost-neutral null:** the file values match the brief (amber 11.2%, green 0.9%, green route 8.7%, through G1 before luck 5.6%, best Sharpe 1.198, luck 1.6% / 0 / 0).

I ran the 8 pure A11 unit tests: all pass. I did not run the end-to-end test, because it writes under `runs/_e2e`. The working tree is still clean.

## (1) Objections 1–8 and 11: what the code and text now do

| # | status | where |
|---|---|---|
| 1 amber before costs | **resolved** | `engine/pipeline.py:105–117` (t on `r_mid` + planted edge; the slice route stays after costs); `thresholds.json` `amber_mid_t`. My recomputation agrees exactly. |
| 2 hold-time fail | **resolved** | `pipeline.py:291` (a safety bar in every G1 mode; `hold_time` is in `SAFETY`); unit test `tests/test_luck_k.py:223`. |
| 3 cost-neutral null in the batch test | **resolved, with a labelling flag** | `engine/ideas.py` `batch_test`; `null/COST-NEUTRAL.json`. See flag C. |
| 4 source overlap | **resolved in code; the rule used to fill the cards departs from A11.3** | `card_flags`/`count_k` (overlap → k = real rows). See condition A. |
| 5 k front-loading | **resolved** | `gatekeeper/open_locked.py`: the luck bar is re-applied at that day's k with the stored σ, tested end to end. Gap: see flag B. |
| 6 μ0 = 0 | **resolved** | `thresholds.json` `mu0 0.0`; test at `test_luck_k.py:173`. |
| 7 serial correlation | **resolved** | `metrics.nw_variance_ratio` (Bartlett, lag ⌊4(T/100)^(2/9)⌋); σ uses max(1, √VR), so it never goes below σ0. |
| 8 A10 committed, card fields pinned, stress k, end-to-end test | **resolved** | `pipeline.py:523` `first_screen_flags`; `stress_g1` reuses the stored bar and refuses another k (test at `test_luck_k.py:197`); `tests/test_e2e_route.py`. Minor gap: see flag D. |
| 11 walk-forward tie-break | **resolved** | `wf_select(..., default=)`: when a training window has no trades it takes the card defaults (real ideas: the screen row's parameters, `ideas.py`). |

## Conditions and flags, most serious first

**A. The overlap rule the subagent used is not A11.3, and IDEA-1013 depends on it.**
- **What A11.3 says** (`DESIGN.md:715–717`):
  - yes when "the card cannot say (a source with no stated sample …)";
  - **no** "only for own reasoning that cites no tested sample".
- **What the subagent's line changed:**
  - It allows **no** for cards citing pre-2016-11 tested samples. That case fits neither clause of the text.
  - It narrows "a source with no stated sample" to sources that "claim the traded pattern".
- **The five "no" calls:**
  - **1001, 1010:** pre-window cases or papers only. No is defensible on the rule's purpose, even if not on its letter.
  - **1013 (in the first batch):** it cites "exchange statistics, 2010s" on the closing-auction share. That is an in-window source with no stated sample, and it carries the card's mechanism. Under the text that is yes; under the subagent's line it is no. This is a real close call.
  - **1005:** it offers the 2019, 2020 and 2022 oil weekend events to show the risk is real. 1003 was marked yes for in-window episodes offered as evidence, so 1005 is inconsistent with that call. It also cites "desk lore" with no sample. **Yes** under both the text and the subagent's own line.
  - **1014:** "bank CTA positioning notes, 2010s", no sample. 1006 and 1007 were marked yes for unsampled desk or practitioner notes, so 1014 is inconsistent with those calls. **Yes** under the text.
- **How much it matters:**
  - The fields are pinned to the first screen row, so the value 1013 carries at its screen is final.
  - For 1013 the difference is k = Σk_eff (about 150 at its likely G1) versus real rows (about 300). The bar moves from 1.20 to 1.27 Sharpe. That is modest, and it persists, because rows grow about 3× faster than Σk_eff.
- **What resolves it, before each card's first screen:**
  - either set 1013, 1005 and 1014 to `yes` ("when in doubt: yes", which is stricter);
  - or a one-line dated addendum by the user that states the subagent's line as the rule.

  1005 and 1014 are not in this batch, but they need the same fix before their screens.

**B. The open guard drops near-miss modes** (`gatekeeper/open_locked.py:34`, `not g.get("pass")`).
- §6.6a lets a mode through G1 as a near miss, and `eligible_modes` counts it. The guard skips such modes, so a candidate eligible only through a near miss is refused and logged as "refused: luck bar", even when it clears the bar.
- The error is in the strict direction and touches no screen or G1.
- Fix before the first locked-period open.

**C. The batch-test comparison mixes stages.**
- The cost-neutral "G1 before luck" figure is a proxy: default path, M0, no grid, no walk-forward (`engine/nullcheck.py:361–395`).
- The real ideas' figure is the walk-forward G1 in M1–M3.
- The weekly report should label it as a proxy. No change to any bar.

**D. The pinned grid size is not checked against the axes `route_g1` receives** (`engine/ideas.py:65` and `:92`).
- A card grid edited after the screen would be tuned on the new axes while k uses the old size.
- The rules already forbid that edit, and the card's git history shows it. A one-line assert would close it. Low priority.

## (2) The raise trigger: cost-included or cost-neutral population?

**The engine owner's reading is right.**
- §6.3 and A11.1 refer to the §8 random strategies, which are the cost-included population.
- Decomposed, the two populations differ only in the slice route:

  | population | t-route (before costs) | slice route | total amber |
  |---|---|---|---|
  | cost-included | 4.8% | 0.2% (after costs) | 5.0% |
  | cost-neutral | 3.9% (9 more become green) | 7.3% (at zero cost) | 11.2% |

- The t-route component is the same in both populations, because it is computed before costs by definition.
- The pipeline never judges slices at zero cost, so the extra 6% does not exist in the real pipeline.
- The only knob the trigger turns is the amber t cut-off, and it would not touch that 7.3% anyway.
- 5.0% is close to the chance rate of one-sided t ≥ 1.5 for zero gross edge (about 6.7%, a little less with the small negative drift at mid prices). The 95% upper bound for 50 of 1,000 is about 6.4%, well under 10%.

**It does not matter for safety.** Break-even ideas do reach the amber budget more often. That is by design ("an edge before costs that costs eat"), and the luck bar is what stops them: the cost-neutral null clears it 1.6% at k = 10 and 0% at k ≥ 100.

## (3) The first batch

**No reason not to screen it,** subject to condition A for IDEA-1013:
- All 14 cards parse strictly.
- Overlap flags: 13 yes and only 1013 no. 3000, 3001 and 3003 are also data-mined.
- No real result exists, so no card was written after a result.
- The code paths the batch uses are in place: screen zone, real-idea route, ledger k, fields pinned at the screen.

On 1013, hold it out of the batch, mark it yes, or have the user decide it by addendum before it screens. It cannot be fixed later.

**Expectations to keep in view (A11.7, not blockers):**
- The order in which G1s run gives early ideas a lower k. The open guard re-checks that.
- Oil (from about mid-2017) and DE40 have short histories, which caps the power of 1009 and 1013. Their diluted Sharpe is statistically consistent, so this is about power, not validity.

**Clean:**
- leakage and the locked period: nothing after 2024 was read or written;
- the k_eff values and luck-bar arithmetic: σ0·Φ⁻¹(0.95^(1/k)) gives 0.909 / 1.162 / 1.375 at k = 10 / 100 / 1,000, VR 1;
- the null re-derivation bookkeeping: 162 rows, re-attached without being run twice;
- the A11 thresholds are frozen with their sources recorded.

Files: `<project>/Edge Research/DESIGN.md` (A11 at lines 699+), `<project>/Edge Research/engine/pipeline.py`, `<project>/Edge Research/engine/ideas.py`, `<project>/Edge Research/gatekeeper/open_locked.py`, `<project>/Edge Research/null/REPORT.json`, `<project>/Edge Research/null/COST-NEUTRAL.json`, `<project>/Edge Research/ideas/cards/IDEA-1013-eu-index-us-open-repricing-into-close.md`, `<project>/Edge Research/ideas/cards/IDEA-1005-friday-weekend-derisking-oil.md`, `<project>/Edge Research/ideas/cards/IDEA-1014-oil-cta-breakout-flow.md`.
