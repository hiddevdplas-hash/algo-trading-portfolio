# oos-sceptic — go-live gate, whole VWAP set (2026-11-01) — excerpt

> **Portfolio excerpt.** The report of the independent AI reviewer (`oos-sceptic`, a Claude Code agent that starts cold and has no stake in
> anything passing) at the go-live decision. The original was saved unedited in the private repository. **Removed here:** objections 3 and
> 6 and the deployment section (account-specific operational details), and a local file path. Everything else is as the agent returned it. The project was closed on this report.

Question put to it: deploy the funded and evaluation sets, or stop this family and restart research (ORB, momentum).

---

**Go-live gate review: VWAP MR set (2026-11-01)**

## Verdict: NO-GO for live capital
- **Funded accounts:** none of the 5 funded files should go on.
- **Evaluation / personal real money:** none of the 15 files either.
- **The only thing I would accept** is the locked set, unchanged, on a demo or a tiny personal account. That is a zero-cost check of execution, run alongside ORB / momentum research. It is not a test of whether there is an edge (objection 9).

## Numbers I recomputed myself
All from `tools/report_stats.py --json` on every v3 OOS report I could find: 147 files, against the 142 the main session cited.

- **Whole family OOS: −398 R.** 2024 +63, 2025 −219, 2026 −242. Only 56 of 147 files were positive. This matches the cited −405 R / +76 / −243 / −237.
- **The 17 unique live files: +136 R.** By year +81 / +42 / +13 R. 2026 is 9.8 months, so about 15.5 R a year against 81 R in 2024.
- **Level 9, closed trades:**

| master | OOS per month | OOS by year | max DD | in-sample |
|---|---|---|---|---|
| funded | +1.12% | 2024 +17.6% / 2025 +18.0% / 2026 +2.4% | 7.6%, trough 2026-09-03 | — |
| evaluation | +2.81% | — | 8.9% | 4.03% per month, DD 15.4% (Jun–Aug 2020) |

## Objections, most serious first

**1. The passers' OOS edge cannot be told apart from selection on noise. The family's own data says passing OOS predicts nothing.**
- **No persistence inside OOS, across all 147 files:**
  - Correlation of 2024 net with 2025+26 net: −0.06. Correlation of 2024–25 net with 2026 net: −0.18. Spearman rank −0.04 / −0.10.
  - A pseudo-pass on 2024–25 only (net > 0, PF ≥ 1.15) picks 41 files. They made +311 R in 2024–25, then **lost −88 R in 2026**, and only 13 of 41 were positive. The other 106 files averaged −1.45 R; these 41 did worse, at −2.15 R per file.
  - Files with PF ≥ 1.3 on 2024–25: 27 files, −79 R in 2026, 5 positive.
  - The top quartile by 2024–25 lost −120 R in 2026; the bottom quartile lost −18 R.
- **In-sample predicts nothing either** (143 files that have a tick IS report):
  - Mean R/month: +0.48 in-sample, −0.08 OOS.
  - Median PF: 1.63 in-sample, 0.92 OOS.
  - Correlation of IS with OOS R/month: −0.13. Correlation of PF: 0.02.
  - The top in-sample quartile did worst OOS (−0.18 R/month); the bottom quartile did −0.015.
- **The pass criteria are lenient.** The zero-edge bootstrap expects about 23 of 82 batch files to pass (≈ 28% per file). Observed: 12 (15%). That is below zero edge, so the family's true mean is negative after costs.
  - Even if the in-sample edge were the alternative, one pass is worth at most a likelihood ratio of about 73/23 ≈ 3.2.
  - A rough mixture fit to 15% passes (about 22 of 143 overall) gives at most about 1 in 3 passers being real, and we do not know which ones.
- **The passers' OOS curves are in-sample in the selection sense.** The evaluation set's OOS t-stat of 4.25 (34 months) is what picking 17 of 147 produces; it is not evidence.
- **The honest forward expectation for these files is about the family mean, zero or negative.**
- **What would change my mind:** only new data. Forward months after 24/10/2026 on the locked set (objection 9). Nothing in 2018–2026 can clear this.

**2. AUDUSD Session "3 of 3 clusters, 3.2%" does not survive multiplicity.**
- About 32 cells reached v3 OOS. The chance that at least one shows a ≤ 3.2% event at zero edge is 1 − 0.968^32 ≈ **65%**.
- The 3.2% also treats the three files as independent: same symbol, same months; the pair shares 28% of trades with daily correlation 0.24.
- **The files themselves:**
  - FT0.75_B3.5: net without the top 5 trades −$1.0k; longs −$1.3k, shorts carry it all; 2024 −$0.5k.
  - FT0.75_B3: everything is 2025 (2024 −$90, 2025 +$6.8k, 2026 −$166).
  - FT3.25: 2025+ only +$75; Friday-close exits = 358% of its net.
  - R/month at $1k risk is 0.08 and 0.19.
- **Not cleared** by any check that does not use OOS.

*(Objection 3 removed: account-specific.)*

**4. The planning case (half the OOS edge) is not justified; at zero edge level 9 misses the user's own targets.**
- RISK-SHEET's zero-edge rows: evaluation fail 68% (target 30–40%), funded breach 44% a year (target 20–25%).
- With no persistence (objection 1), the zero-edge row is the planning case. By the sheet's own rule the level must come down.

**5. Protocol steps 10–11 have not run.**
- No `_full.html`, no step-11 prop-spread runs, and `v3_10_portfolio/` holds only `sets/`.
- PROTOCOL top ("One portfolio stage") orders steps 10 → 11 → sceptic → kill switches → step 12. Going live now skips 10 and 11.
- Kill switches are not written (ROADMAP "Before the first strategy goes live"; RISK-SHEET last line).
- Step 11 can still drop files: USTEC at a 20-point spread, US30 at 40, the FX crosses at IC × 1.5.

*(Objection 6 removed: account-specific.)*

**7. Half of the batch passers pass only because of the 2026-10-31 rule change, including 2 of the 5 funded files.**
- These passers have a top trade above 30% of net, so they would fail the original rule:
  - XAUUSD N12: 82% of net; net without top 5 −$8.8k.
  - AUDJPY FT1 N12: 45%; net without top 5 −$2.7k; 2026 −$1.7k.
  - NZDUSD FT2.5: 43%; XAUUSD Noff: 38%; EURJPY RS2: 34%; EURNZD: 31%.
- The change was set before those OOS runs, so it is not leakage. But it came after earlier cells had failed on that criterion (USDJPY W 50%, AUDUSD W 60–66%). Loosening criteria mid-programme raises the pass rate on noise.

**8. File-level artifacts in the funded set.**
- **XAUUSD N12:** every OOS dollar is 2024; 2025 −$0.6k, 2026 −$2.7k; the 2024 gold bull year (beta, not edge); Friday-close exits 260% of net.
- **AUDJPY FT1 N12:** the top 3 months are 162% of net; 1 of 5 funded clusters passed (zero-edge odds 80.8%).
- **US30 ID FT0.375 N12 (⚑):**
  - It shares 67–70% of trades with US30 S FT0.625, whose OOS was seen the day before its pre-registration.
  - The user then dropped the clean US30 S file in favour of this one on its OOS score — selection on OOS among near-copies.
  - Entries in one hour (about 02:00 Amsterdam, 2 h after the 18:00 NY reset, a young band) carry 153% of net.
  - The top 3 months are 91% of net.
- **EURUSD FT1.5 N12:** fading (+$7.2k / +$3.8k / −$0.9k by year); the 11:00 TC entry hour is 53% of net; top 3 months 63%.
- **USTEC ID FT0.5 N12:** the cleanest file — net without top 5 +$13.4k, top trade 3%, both sides positive, top 3 months 34%. But 2024 is only +$0.6k, and its OOS R/month (0.47) is 2.6× its in-sample (0.18), which reads as regime, not a stable edge.

**9. A 4–6 week forward test cannot confirm an edge.**
- Evaluation set: monthly sd 3.86% against a 2.81% mean. Telling the half edge (1.4% a month) from zero at 2 sigma needs about **30 months**.
- Funded set: about **72 months** at half edge, 18 at full edge.
- A forward test of 4–6 weeks, or even 6 months, can only catch broken execution or a gross failure. That is why it belongs on demo or personal micro, not on prop accounts.

**10. Mechanism.**
- The family-wide −398 R says the VWAP band fade, as parameterised, did not carry forward.
- The passers' P&L often comes from somewhere other than reversion: Friday-close exits (NZDUSD FT4.25 411%, FT2.5 245%, EURJPY RS2 290%, XAUUSD 248–260%), young-band entries (NZDUSD FT4.25 106%, US30 ID's 02h hour), or one regime year (XAUUSD 2024, AUDUSD / AUDJPY 2025).
- Nobody has named who is on the other side, or why that would persist.

**Clean:** no Python export after 2023 was found; pre-registration commit times come before the OOS file times per the LOG intake lines; the pass verdicts recompute correctly (XAUUSD N12 and AUDJPY FT1 N12 re-checked: PASS under `--rules 2026-10-31`).

*(Section "Which files, under what conditions" removed: account-specific.)*

## What the in-sample period is worth for the Ergodic stress test
- **For edge or pass / breach odds: about nothing.** 2018–2023 is the selection period, and objection 1 shows it has zero to negative predictive value.
- The passers' in-sample rate is higher still (funded 1.48% vs 1.12% a month; evaluation 4.03% vs 2.81%). Ergodic over 01/01/2018 → 30/10/2026, about 68% in-sample months, will look better than RISK-SHEET's full-OOS-edge row (evaluation pass 93%, funded breach 8%), and that row is itself not credible.
- **It is useful in two ways only:**
  - **As a veto.** If even this inflated curve breaches, stop. The Jun–Aug 2020 evaluation drawdown of 15.4% at level 9 is a real tail point and already says one evaluation account would have failed.
  - **As a rough read of structure** (daily correlation, same-day losses, worst day). Even those come from selected data.
- **Do not let a good Ergodic number argue for go-live.** Plan sizing on the zero-edge case.
