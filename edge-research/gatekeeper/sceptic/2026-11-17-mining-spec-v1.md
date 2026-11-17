VERDICT: BLOCK (narrow). Two items in SPEC v1 don't do what the spec says, and the grammar goes beyond the filter list that A15 §1.1 approved. All three are fixed by editing the spec text or getting the user's decision, before anything is drawn. No bar, seed, count or replicate number needs to move. The rest of the spec passes, with the conditions below.

Scope:
- Read: `mining/SPEC.md` at 5ee52c4; DESIGN §3.2–3.7, A1, A3, A4.5, A12–A15; both A15 sceptic reports; `engine/STRATEGY-API.md`, `costs.json` `addon_detail`, `context.py`, `series.py`, `metrics.py`, `gatekeeper/open_locked.py`; the strategies/ listing; main ledger row counts.
- I wrote nothing in the repo, read no data after 2024, and didn't touch `ledger-mining/` or `runs/mining/`.
- Recomputed: the three seeds (all match their SHA-256 strings), the cost-route table, the symbol inclusion rates (simulated), and the mirror algebra of every family.

## Findings, most serious first

**1. The expiry filter is wired to the wrong calendar, and that calendar stops at 2024. (BLOCK)**
- **Where:** SPEC §4 (`expiry`), §6.5; `engine/series.py:295-302` and `calendar_dates`.
- **Evidence:** `calendar()` labels the Mar/Jun/Sep/Dec expiries `quarterly_expiry`. So `calendar:monthly_expiry` holds only months 1, 2, 4, 5, 7, 8, 10, 11 (I ran `calendar_dates('calendar:monthly_expiry')`: 120 dates for 2010–24, months [1, 2, 4, 5, 7, 8, 10, 11]).
- **Effect:** "in" as declared leaves out every quarterly (triple-witching) week, which contradicts the §4 definition ("the week containing a monthly equity-options expiry"). The calendar is also hard-coded to `calendar(2010, 2024)`, so at a locked open "in" can never be true.
- **Smallest fix (either one):**
  - (a) Drop the expiry filter. This also clears finding 2's overlap.
  - (b) Declare both `calendar:monthly_expiry` and `calendar:quarterly_expiry`, define "in" as their union, and define the week as Mon–Fri in New York dates, saying where a Sunday-evening bar belongs.

**2. The grammar goes beyond A15 §1.1's filter list. (BLOCK until the user decides)**
- **Where:** SPEC §4 against A15 §1.1, which lists "filters (session, volatility third, trend, bloc)" and, from A14, only "context-symbol and CFTC blocks".
- **What the spec adds:** `vix` (an A14 outside series that A15 does not list), `expiry` (a calendar), and a second trend filter. The composer's with/against SMA 200 comes on top of the engine's `regime` trend/range, which is the "trend" of the A3 menu.
- **Firewall angle:** the mining session saw the file name `idea_1007_monthly_opex_dealer_hedge_flow.py` (SPEC §11 discloses that it listed strategies/), and `expiry` is exactly the one input added outside A15's list. That is the reverse-firewall channel finding H of the v1 report warned about. It weakens the claim in §11 that nothing was shaped by those names.
- **Effect on multiplicity:** k is fixed at 50,000 whatever the grammar, so this is about scope and the firewall, not multiplicity.
- **Smallest fix:** drop `vix` and `expiry` (and the composer `trend` if "trend" means `regime`). Otherwise the user OKs them with this objection in view, and it is recorded in `mining/LOG.md` before the draw.

**3. Job fields aren't bound to the definition. (BLOCK: text fix in §13)**
- **Where:** SPEC §13 says "the runner checks `rule_id` + `def_hash`".
- **Problem:** the job also carries `symbols`, `timeframe`, `class`, `filters`, `context`, `series` and `period` as separate fields. A job could keep a bound id and hash and run different symbols or filters. This reopens finding E of the v1 report.
- **Fix:** the runner recomputes `def_hash` from `params`, and derives every other job field from `def` or refuses any difference. `period` is fixed at 2014-11 → 2024-12. Add a unit test.

**4. A rule that fires no entries on a symbol leaves a hole in the sweep. (condition)**
- **Where:** STRATEGY-API: a real job with no entry intent on a symbol is refused (queue/failed, no ledger row).
- **Problem:** filters applied by the composer (trend, vix, expiry) empty the intents and trigger that refusal. Filters applied by the engine (session, vol, regime) don't, and still write a row.
- **Why it matters:**
  - A15 §3.5 needs "all 50,000 rows exist".
  - A rare combination, e.g. TOD + vix high + expiry in + DE40 alone, can produce zero intents.
- **Fix:** mining jobs write a zero-trade row (red) instead of being refused, and the spec says so.

**5. The locked open will see outside series frozen at 2024. (condition, needed before the first mined open)**
- **Where:** `series.align` drops releases ≥ `RESEARCH_END_MS` (hard-coded), the calendar stops at 2024, and the sweep's engine is pinned (A15 §10.6).
- **Effect:** run on 2025+, a COT rule's state would freeze at its last 2024 value, and VIX would too. The open itself isn't built yet (`open_locked.py` docstring).
- **Fix:** SPEC states now that the open runs the same composer with series, calendars and context symbols extended past 2024 by a loader that is byte-identical for t ≤ 2024. It is checked on a sample of mined rows.

**6. An event can fire just after warm-up or a data hole. (condition)**
- **Where:** SPEC §2, "true at i, false at i−1".
- **Problem:** in numpy a NaN comparison gives False. On the first bar after warm-up or a hole (context hole, FX quarantine, the 2014 hole), a condition that has been true all along fires as a fresh cross.
- **Not look-ahead, but:** spurious entries clustered at the ends of holes.
- **Fix:** an event needs finite inputs at both i and i−1. Add a unit test for this case.

**7. The bloc draw weights symbols unevenly; A1.5 should state why. (condition)**
- **Simulation of §6.2:** each metal or oil symbol appears in about 12% of rules, an index or USD pair in about 6.8%, a cross in about 4.4%. That is 2.7× the weight for metals and oil over crosses.
- **Why it matters:** the weighting is structural (the §3.2 exposures, not results). But metals and oil moved strongly in 2025–26, which the author knows, and the mined open's bar is the median expectancy, which helps trend rules in a trending year.
- **Fix (either one):**
  - (a) Give the reason in §11 in 2014–2024 terms (one weight per exposure, §3.2).
  - (b) Weight blocs by their size, which makes symbol inclusion uniform.

**8. The cost test leaves two free choices. (condition)**
- **Where:** SPEC §12.
- **Open points:**
  - "spread × 2": of the whole FTMO spread (IC tick spread + add-on), or of the add-on alone? US500's add-on is 0.078 bp, so doubling only the add-on would be a non-test.
  - The pass criterion is not stated. Fix it now, e.g. "every judging bar, the luck bar at the frozen k included, in each eligible mode".
- **Smaller points:**
  - The G3 window: §12 quotes 2020-04 → 2021-06, which is the add-on's measurement window. Say which FTMO ticks G3 uses.
  - Exchange holidays and US half-days count as in-session (spread not doubled). This is a stated limit, worth a few days a year; Xetra and LSE holidays are rule-derivable.
- **Checked correct:**
  - The routes match `costs.json`: none 16 (15 hourly FX + JP225), G3 13, ×2 10.
  - The cash sessions are sensible: US 09:30–16:00 NY, Xetra 09:00–17:30, LSE 08:00–16:30, TSE with the 15:30 close from 2024-11-05, gold 08:20–13:30 and oil 09:00–14:30 NY. Silver's floor session was 08:25–13:25, so using gold's window is slightly more conservative. FX is never on the ×2 route, so its row is moot.

**9. Smaller binding gaps. (conditions)**
- Canonical form: arrays (symbols, context, series) must be sorted, and floats written in one fixed form. Otherwise the same rule can appear twice under two hashes.
- A redrawn duplicate is drawn again within the same family slot.
- Pin the numpy version: Generator streams aren't guaranteed stable across versions (2.0.2 here).
- Bind SPEC.md's own hash with the list, and allow one draw only: any spec or sampler change after the draw needs a new review.
- PULL: say whether "lowest close" includes ties.
- COT:
  - The engine owner confirms each code has rows in every year 2014–24, not just that it is "in the store".
  - Give a reason for excluding JP225: CME Nikkei (USD) exists. The exclusion is harmless, but it is a choice.

**10. Information only (no change needed):**
- The `regime` filter's k_symbol is the median over 2014-11 → 2016-10, which is now inside the in-sample judged window. It doesn't depend on direction, so the effect is small.
- P52 is computed from the aligned bars, so COT rules start about 2015-01 (oil about 2018-07). Catch-up weeks can merge releases. It is causal.
- Mirror symmetry doesn't make the realised trades balanced: trend "with" on US500, USTEC or XAUUSD will be about 70–75% long. A15's 25% side rule is the only guard; A15 already decided this.
- CTX on h4: if h4 anchors differ between a pair of symbols, `age_ms = 0` never holds and that rule is dead. Synthetic tests can't show this. A timestamp-only check of the share of `age_ms = 0` per pair on the store (≤ 2024, no prices) would.
- There are now 62 main real rows, not 49. At the freeze, k = 50,000 + that count; the bar stays about 1.507.

## Clean
- **Mirror symmetry:** checked algebraically for every family.
  - BRK: HH ↔ LL.
  - PULL, MAX, BAND: rolling means negate; ATR is unchanged under the mirror.
  - OSC: RSI on negated prices is 100 − RSI.
  - CTX: both price series negated.
  - COT: P52 of −x counts ≥, which is symmetric.
  - Nothing is a side parameter.
- **A15 exclusions:** no side filter; no `recent` slice or regime date; no anchored average, VWAP, opening range or prior-session levels (BAND is a rolling SMA band, which A15 §1.1 allows); no tick volume (with a unit test); TOD on a uniform 01–22 whole-hour grid; context only from the 39 firm symbols; COT only as a 52-release percentile of the level.
- **No look-ahead in any block's definition** apart from finding 6. HH/LL exclude bar i, the engine filters use the last closed h4 bar, series are taken strictly before the bar's close, and context only from closed bars.
- **Seeds:** sampler 7029058316196824278, null 2028128550524854714 and review sample 9375309906280918020 all reproduce from their strings.
- **Null:** exactly 60 replicates, seed fixed, the sign rule fully defined and order-free, costs not flipped, and z = z_k when no null rule qualifies. Matches A15 §5 and §10.3.
- **Sampler:** non-adaptive, exactly 50,000 distinct rules, rejections listed.
- **Every block is short enough for the look-ahead reviewer.** COT P52 and CTX alignment are the longest.
- **§3.7 and RoboQuant:** the VWAP family is excluded in full, and no block repairs a template.

## What would change this to PASS WITH CONDITIONS
- SPEC v2 fixes 1 (or drops expiry) and 3.
- Finding 2 is resolved by dropping the extra filters or by the user's recorded OK.
- Findings 4–9 are written in.
- None of these needs the locked period.

## Files
- <project>/Edge Research/mining/SPEC.md (§2, §4, §6.2, §6.5, §8, §11, §12, §13)
- <project>/Edge Research/DESIGN.md (A15 §1.1 line 831–835)
- <project>/Edge Research/engine/series.py (lines 126–146, 287–302, calendar_dates)
- <project>/Edge Research/engine/context.py (lines 1–10, 98–121)
- <project>/Edge Research/engine/STRATEGY-API.md (ZERO INTENTS guard, lines 101–103)
- <project>/Edge Research/gatekeeper/open_locked.py (docstring: the open is not built)
- <scratchpad>/symw.py (symbol-weight simulation)
