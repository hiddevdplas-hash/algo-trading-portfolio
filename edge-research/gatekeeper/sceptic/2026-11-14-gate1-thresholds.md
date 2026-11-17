VERDICT: BLOCK

# oos-sceptic, gate (1): frozen thresholds (DESIGN A3–A10), 2026-11-14

Reviewed at `2f7deaa` (A10 at `e4808cf`). The working tree has the engine owner's A10 implementation **uncommitted** (`engine/pipeline.py`,
`thresholds.json`, `runner.py`, `metrics.py`, `nullcheck.py`, tests). I read that code but did not treat it as frozen. At HEAD,
`thresholds.json` still says `"status": "floor (not frozen)"` and `target_share 0.01`, and G1 has no luck bar.
Ledger: 12,687 rows, all `lane: null`, all with period 2014-11 → 2024-12. No real idea has been tested and no data after 2024 appears.
My scripts are in the scratchpad folder: `proxy.py`, `proxy_mid.py`, `power.py`, `amber.py`, `keff.py`.

**Why BLOCK:** one frozen bar doesn't do what DESIGN says (objection 1). One stated rule isn't applied by the pipeline (objection 2).
Both are cheap to fix, and neither fix loosens anything. Objection 1 has to be settled **before the first real screen**, because the
zone is decided there and can't be redone for an idea whose result has been seen. Everything else below is a condition or a flag.

---

## Answers to the five questions (short)

**Q1. Noise, costs, and the right null.**
- The 0 of 1,000 result mostly measures **costs**:
  - random entries net a median of −0.143 R a trade, and only 4.2% are net positive;
  - 6 were amber and 2 had a green route (N0100, N0200; both failed G1 bars);
  - nothing random ever reached the luck bar, G2 or the near-miss lane. The 0.3% upper bound only says that random entries with costs don't get through.
- I rebuilt a **cost-neutral null** from the same 1,000 screen logs (net R = `r_mid`, the zero-edge R at mid prices that every trade file
  already holds; default path, no grid). It ran through the screen, the lane-style amber choice of `nullcheck.variations`, and the
  PF / years / trades G1 bars on the unseen part:

  | stage | share |
  |---|---|
  | green at the screen | 0.9% |
  | at least one green route (mostly amber filters) | 8.7% |
  | pass the PF, years and trades bars | 5.6% (66 routes) |
  | best route Sharpe | 1.113 |
  | through the luck bar at k = 10 | 1.9% |
  | through the luck bar at k ≥ 100 | 0 of 1,000 |

  So **the luck bar is the only effective statistical guard after the screen.** The PF / years / trades bars passed 65% of the selected
  noise routes. Against pure noise the luck bar holds once k ≥ ~100.
- The random null is **not the right null for the lanes' ideas**, for two reasons:
  1. It doesn't represent break-even ideas whose gross edge roughly equals their costs. The cost-neutral version fixes that, at no compute cost.
  2. No null can represent **hidden selection**: hypotheses, defaults and parameter ranges chosen by authors or by Claude's training,
     on data that overlaps 2016–2024. Those effects can be real in-sample and gone now. They pass every research bar, and only the
     locked period tests them. That test is weak: zero edge passes 9–37% (§9).
- **False candidates per quarter at ~2,250 ideas** (25 cards a day, OPERATIONS §6):
  - **From pure noise:** about 0.05–0.25. The expected number of fresh-noise routes that clear the luck bar is 0.05–0.09 per quarter at
    route weights 4.8–9.8, and up to ~0.4 if amber routes behave like the best of ~8 slices; G2 removes some of those. Half of it comes
    in the first ~50 routes (objection 5).
  - **From in-sample-real but dead effects:** not bounded by the calibration. As an illustration, if 1% of ideas are such effects,
    that is ~22 ideas a quarter. At the planted +0.10 R pass rate (36–39% at k = 10k–30k) about 8 become candidates, and the locked
    period passes 9–37% of them: **about 0.7–3 false finalists a quarter.** That is the real exposure.

**Q2. A9 (no G1 drawdown bar).**
- **No new path for noise.** In the calibration no random strategy reached G1 at all. In my cost-neutral proxy the luck bar at k ≥ 100
  removes every noise route with no drawdown bar. The drawdown bar mostly tracked trade frequency, not whether an edge was real.
- What it weakens (objection 10):
  - more candidates reach the locked period, and each open is a weak test;
  - the fit risk comes from an iid permutation Monte Carlo, which understates clustered drawdowns;
  - it sets a precedent of lowering a floor. It was documented, made before any real result, and is the user's call.

**Q3. The luck bar.**
- **Mostly right.** σ0 = 0.354 matches 1/√8.17 = 0.350, the normal fit matches the observed maximum (largest of 1,000 is 1.068 vs about
  1.11 predicted), and I reproduced the k_eff values exactly.
- Three fixes, all stricter:
  1. Centre the bar at μ0 = 0 rather than −0.039 (objection 6).
  2. Guard σ against serially correlated real P&L (objection 7).
  3. Pin each idea's card flags to its first screen row (objection 8).
- **ρ = 0.688 is fair for stop / exit grids but lenient for entry or lookback axes.** At ρ 0.3 a 27-point grid is k_eff 22, not 9.8.
  Measuring ρ per route is sound. Grid spacing can game it (27 points: k_eff 2.6 at ρ 0.95), but the bar moves only with log k and the
  sum is project-wide, so the effect is small (about −0.08 Sharpe for a 4× smaller k).
- Front-loading needs a fix (objection 5).

**Q4. Power.** The measured power is **optimistic**:
- the planted edge is added to R after the price path, so it can't be hurt by the +1-bar or jitter test;
- it is constant across years, symbols and sides, and doesn't decay;
- the A7 planting (x + the strategy's mean cost) makes cheap slices worth more than x: 27 of 36 of the +0.05 strategies that reached
  the gatekeeper did so through an amber route.

At the k a quarter will bring (10k–30k), recomputed from the calibration state:

| edge | headline (before the luck bar) | at k = 10k–30k (planted) | real edges |
|---|---|---|---|
| +0.05 R net | 36% | 11% | lower, not measured |
| +0.10 R net | 55% | 36–39% | lower, not measured |

**Q5. Errors.**
- Amber is judged on R after the spread, not before costs (objection 1).
- The hold-time fail isn't in the verdict (objection 2).
- A10 isn't in the committed engine yet, and there is no G1 driver for real ideas yet (objection 8).
- The walk-forward tie-break picks the grid corner when a training window has no trades (objection 11).

---

## Objections, most serious first

### 1. [BLOCK] The amber bar's "before costs t ≥ 1.5" is computed after FTMO's spread
- **What:** `pipeline.screen_zone` builds the amber test from `log_m0["r_gross"]` (`engine/pipeline.py:95, 97, 102`). LOG.md:912
  established on 13 Nov that `r_gross` is "R after FTMO's spread, not before costs". The luck bar was moved to `r_mid`; the amber test
  was not. DESIGN §6.3: "Amber: not green, but **before costs** t ≥ 1.5"; and amber is "an edge before costs that costs eat".
- **Evidence:** I recomputed the share with t ≥ 1.5 on the 1,200 calibration screen logs (`amber.py`):

  | group | after the spread (as coded) | before costs (`r_mid`, + plant) |
  |---|---|---|
  | random | 0.3% | 4.8% |
  | +0.05 R | 77% | 92% |
  | +0.10 R | 93% | 95% |

  The spread is 0.097 R a trade (median, random), about two-thirds of all costs.
- **Why it matters:** the zone decides which real ideas get the 3-variation budget, and it is decided at the first screen. An idea
  whose real gross edge is eaten by the spread is amber by the text and red by the code. That's a lost idea, with no second chance.
  The calibration's amber and rescue rates (0.6% / 0.2%) are also for the coded rule, not the written one.
- **What would change my mind:** an addendum before the first real screen that either
  - (a) defines amber on after-spread R (the user's decision, with these numbers in view; the calibration then stands as run), or
  - (b) fixes the code to `r_mid` and re-derives the null's zones from the existing trade files, with the amber variations for about
    45 newly amber random strategies run (cheap). Under (b), amber noise is the place where §6.3's "raise if too much noise gets the
    budget" applies.

### 2. [BLOCK] The hold-time fail isn't applied by the pipeline
- **What:** §4.2 says that if more than 10% of trades are under 2 min, the strategy fails. `metrics.py:101–102` and `rules.py:273`
  compute `fail_under_2min`, but `pipeline.g1` / `g2` / `verdict` (`pipeline.py:206–302`) never read it.
- **Why it matters:** the firms ban it, so a candidate could reach the gatekeeper with a rule breach. Random strategies don't trip it,
  so the calibration is unaffected.
- **What would change my mind:** the bar wired into G1 (or G2) as a safety bar with a unit test before the first G1; or a written
  statement that the gatekeeper checks it by hand on every candidate.

### 3. The calibration shows that costs kill random entries, not that the machinery after the screen is safe
- **Evidence:** `null/REPORT.json` (random: green 0.0, amber 0.006, rescued 0.002, through G1 0.0). Screen median −0.143 R a trade,
  4.2% net positive (LOG.md:881–882). Only 2 random routes ever reached grids and G1 (`power.py` output: N0100 failed on trades and
  years; N0200 on profit factor). The cost-neutral proxy above is the test the machinery actually needed.
- **Why it matters:** the 0.5% noise reference and the weekly batch test ("real vs random reaching the gatekeeper") compare real
  ideas with a population that is 0% by construction. Any real candidate beats it, so the test can't detect a pipeline that lets
  marginal ideas through.
- **What would change my mind:** the gatekeeper's weekly batch test also reports the cost-neutral null rates. They need no new runs:
  `r_mid` is in every trade file. My proxy: green 0.9%, at least one green route 8.7%, through the G1 bars before the luck bar 5.6%.
  These include no grid and no G2, and use the coded amber rule. Real ideas are then compared at the screen and G1-before-luck stages,
  where noise rates aren't zero.

### 4. Hidden selection: literature and LLM ideas are already selected on the walk-forward years
- **What:** the walk-forward's unseen windows (2016-11 → 2024-12) lie inside many sources' samples. Examples:
  - IDEA-2001's source (Concretum) covers 2007 → Aug 2025: the whole walk-forward window, plus "locked period seen";
  - IDEA-2000's sources are dated 2018 and 2021;
  - IDEA-2008 is flagged data-mined and locked period seen.

  All 2000-series cards except 2008 say `data-mined: no`. The market-logic cards are "own reasoning", but Claude's knowledge contains
  which session, flow and calendar effects worked in 2014–2024 (A1.5 already says so).
- **Why it matters:** the luck bar and k count only this project's tests. An effect that was real in 2016–2024 and has since decayed
  (McLean–Pontiff: about −50% after publication) passes G1 and G2 like a real edge. Only the 22-month locked period separates the two,
  and there zero edge passes 37% / 23% / 9% at 60 / 120 / 250 trades a year (§9). This is the dominant source of false finalists
  (Q1: about 0.7–3 a quarter if 1% of ideas are such effects), and the calibration can't measure it.
- **What would change my mind:** an addendum before the first batch runs (it includes 2000, 2001, 2004 and 2006):
  - every card records its **source-sample overlap** (the months of 2016-11 → 2024-12 inside any cited source's sample, and whether
    the default parameters came from the source);
  - the ledger and the candidate report carry it;
  - at the locked-period open the sceptic treats a fully overlapped candidate as "walk-forward = in-sample", with its locked-period
    power stated, and the go-live decision as the user's with that in view.

  A stricter alternative: count overlapped ideas at the data-mined k.

### 5. The k counted as the ledger grows gives the first ideas a much lower bar
- **Evidence:** the first batch's normal-idea cards and grid sizes:

  | grid size | cards | k_eff each (ρ 0.688) |
  |---|---|---|
  | 27 | 1000, 1003, 1006, 2001 | 9.8 |
  | 9 | 1007, 1009, 1013, 2000, 2006 | 4.8 |
  | 12 | 2004 | 5.8 |
  | 3 | 1008 | 2.2 |

  That gives k ≈ 71 before any amber route, so the bar ≈ 1.07. At ~2,250 ideas a quarter the bar is 1.53–1.65 (`keff.py`). The
  cost-neutral null's best route reached 1.113, above 1.07. With a sequential k the expected number of noise clears is
  Σ(1 − 0.95^(1/K_j)), and half of it falls in the first ~50 routes.
- **Why it matters:** a pass found at k = 70 would fail at the k in force when it reaches the locked period a few weeks later.
- **What would change my mind (stricter only, by addendum before the first G1):** before a candidate's locked-period open, re-apply
  the luck bar at the k in the ledger then, or set a floor on k (e.g. 1,000).

### 6. μ0 = −0.039 makes the bar slightly lenient for net Sharpe
- **Evidence:** the mean of 1,000 is −0.039 with SE 0.354/√1000 = 0.011, so 3.5 SE below 0. It comes from execution at mid prices
  (stop gaps, the stop winning ties). The bar is applied to *net* Sharpe, and the null hypothesis "net edge = 0" is centred at 0.
- **Why it matters:** the bar is 0.11 σ0 too low. At k = 10,000 (z ≈ 3.98) that multiplies a noise route's pass chance by about
  e^(0.11·3.98) ≈ 1.5.
- **What would change my mind:** μ0 = max(μ0, 0), a raise, which §8 allows.

### 7. σ0 assumes independent days
- **What:** σ0 = 1/√years is right for the random strategies (P&L booked at exit, independent entries). Real trend or flow strategies
  can have serially correlated daily P&L, so their Sharpe's sampling error is larger, and the bar is too low for them.
- **What would change my mind:** each candidate's luck bar uses max(σ0·√(8.17 / its years), a block-bootstrap or Newey–West SE of its
  stitched daily series), by addendum before the first G1. That is stricter only.

### 8. The A10 implementation is unfinished, and has one gameable detail
- **Evidence:**
  - At HEAD G1 has no luck bar, and `thresholds.json` reads "floor (not frozen)" with `target_share 0.01`.
  - The uncommitted `count_k` takes `flags[r["idea_id"]] = r["card_flags"]  # the latest row's card fields`. A card whose
    `data-mined` flips from yes to no after a result would drop from the test-row count (k ≈ number of rows) to the idea sum, and so
    would a changed `grid size`.
  - No real-idea G1 driver calls `count_k` yet. The `swap0` and `fx2015` re-checks in G2 call `g1` and must get the same k.
  - IDEA-0001 lacks a `grid size` row and has "**yes**: …" (it would be refused, which is correct).
- **What would change my mind:**
  - A10 committed with its engine hash logged;
  - card flags and grid size pinned to the idea's **first** screen row;
  - a test that the stress re-checks use the luck bar at the same k;
  - an end-to-end test of the real-idea route (screen → tune → G1 with `count_k`) before the first G1.

### 9. Measured power overstates what real edges will get
- **Evidence:**
  - The planted edge is added after the path: `tradelog.py:78–79` (`r_gross + synthetic_edge_r`). The noise test therefore can't
    erode it. It is also flat across years, symbols and sides, and doesn't decay.
  - 27 of the 36 +0.05 R strategies that reached the gatekeeper got there through an amber route.
  - My proxy at k = 1,000, same +0.05 net edge:
    - planted as A7 does (x + the strategy's mean cost on every trade): 15.8%;
    - the same net edge on every trade (cost-neutral): 8.8%.

    The gap is amber routes that pick cheap or high-volatility slices, where the A7 plant is worth more than x.
  - The headline 36% / 55% is before the luck bar. At realistic k (10k–30k) the calibration state gives 11% and 36–39%.
  - Short histories: a DE40-only route is judged on about 1.3 unseen years. Its diluted Sharpe is statistically consistent, but it
    needs an active Sharpe of about 3.8 to clear k ≈ 10k. In effect such ideas can't pass, and the lanes should know before writing
    them.
- **Why it matters:** the plan expects 4–8 strategies. With real edges of +0.05 R the pipeline finds about 1 in 10 or fewer, and the
  locked period removes more. "Nothing passes" is a likely outcome, and it doesn't mean the bars are wrong.
- **What would change my mind:** a second power run (synthetic strategies only) with edges that vary by regime or year, depend on
  entry timing, and decay. It can be run any time; it changes no bar.

### 10. A9: what moving drawdown out of G1 shifts downstream
- **Evidence:**
  - G1 pass rates went from 29% to 62% (+0.05 R) and from 26% to 74% (+0.10 R) (A9.3), so there are more locked-period opens.
  - The locked bar has no multiplicity count, and each open passes zero edge 9–37%.
  - `mc_dd95` is an iid permutation (`metrics.py:26–31`). Clustered real losses make the fit risk optimistic: median 0.50–0.67%,
    with 6–9% of the strategies that reached the gatekeeper below 0.25%.
  - The locked-period drawdown check compares about 22 months with an 8-year Monte Carlo 95th percentile, which is lenient. This
    predates A9.
- **What would change my mind:** the firm simulation (§10) uses block-bootstrap or regime-aware drawdowns for fit risk; the
  gatekeeper reports the number of locked opens per quarter next to the expected false finalists.

### 11. Minor
- **Walk-forward tie-break:** when a training window has no trades, `wf_select` takes grid point 0, the corner rather than the
  declared default (`pipeline.py:159–160`; e.g. DE40's first test windows). It should fall back to the default.
- **A10.5 power numbers** didn't scale σ for regime routes: 18% vs my 17% at k = 1,000 for +0.05 R. Immaterial.
- **Uncounted looks (small but not zero):** eligibility in any of 3 firm modes; lanes choosing a regime date (the A3 list binds only
  the null); amber filters chosen from trade-log context beyond the 15 fixed slices (day of week, month, news day).

---

## Clean
- **Leakage / locked period:** every ledger row is 2014-11 → 2024-12, and no real rows exist. The research store holds no data after 2024.
- **A9 reuse check:** 23 of 23 re-run pairs identical (168 files, 79,716 trades).
- **k_eff mathematics:** 2.23 / 4.82 / 5.83 / 9.80 for 3 / 9 / 12 / 27 points at ρ 0.688. I reproduced these exactly.
- **The luck bar's normal fit vs the observed maximum:** consistent.
- **Near miss:** the luck bar and the other safety bars can't be near-missed (uncommitted code: `SAFETY` includes `luck`).

## Conditions, in order
1. **Before the first real screen:**
   - objection 1 resolved (addendum or code fix);
   - objection 4's source-overlap field and rule committed, or the overlapping literature cards held.
2. **Before the first real G1:**
   - objections 2 and 8 done (A10 committed and tested end to end);
   - objections 5, 6 and 7 decided by addendum (all stricter only).
3. **Any time:**
   - the cost-neutral null in the weekly batch test (objection 3);
   - a realistic-edge power run (objection 9);
   - block-bootstrap fit risk (objection 10).
