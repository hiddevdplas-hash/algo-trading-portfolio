# IDEA-2001: noise-area intraday momentum on US index CFDs

| field | value |
|---|---|
| status | inbox |
| lane | literature |
| source (OPERATIONS §4) | websites + whitepapers (Concretum Group research; Swiss Finance Institute working paper) |
| family | intraday momentum (volatility-band breakout from the open) |
| seen family (DESIGN §3.7) | no |
| seen family, why | none (not a repair of a RoboQuant template; no VWAP in the rules) |
| locked period seen (DESIGN A1) | **yes**: Concretum "Beat the Market" PDF, version of 22 Sep 2025, shows Jan–Aug 2025 (unseen remainder from Sep 2025) |
| data-mined | no |
| data-mined, why | no |
| source overlap | yes |
| source overlap, why | Zarattini-Aziz-Barbon, sample May 2007 - Apr 2024 (covers the whole window to 2024-04), 2025 version also shows Jan-Aug 2025; defaults from source: yes (N 14, m 1.0, grid) (gatekeeper, DESIGN A11.3, 2026-11-15) |
| grid size | 27 |
| class (DESIGN-CONSTRAINTS §0) | A intraday |
| two-sided | yes (paper trades both sides) |
| card version | v3 (2026-11-11: `locked period seen` field added per DESIGN A1; v2 (2026-11-11: evidence verified against the paper; rules unchanged, expectations cut)) |

> **Verified 2026-11-11 against:** Zarattini, Aziz, Barbon, "Beat the Market", full text, version of 22 Sep 2025 (first version
> 10 May 2024), from the Concretum page (https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf), and the
> RePEc record of SFI Research Paper 24-97 (https://ideas.repec.org/p/chf/rpseri/rp2497.html; SSRN 4824172 blocks automated access).
> Rules rebuilt from the description, no code copied. Strategy module: `strategies/idea_2001_noise_area_intraday_momentum.py`.
> The paper uses VWAP in its trailing stop; this card deliberately drops VWAP (band-only exit) to stay outside the VWAP seen family.
> **That choice removes the variant behind the headline numbers** (see Evidence).
> **Locked-period note for the gatekeeper:** the 2025 version of the paper's FAQ (Q24) prints monthly returns of the strategy for
> Jan–Aug 2025, inside our locked period. This lane has seen that table; it is deliberately **not** copied onto this card.

## Why should this exist
1. **Who pays:** when price leaves the range that the usual intraday noise explains at that time of day, it signals an order-flow
   imbalance (institutional execution spread over the day, hedgers, stop cascades). Those flows are price-insensitive and keep pushing;
   the counterparties are liquidity providers and mean-reversion traders who fade the break.
2. **Why it persists:** the edge is a low hit-rate trend payoff (many small losses, a few large wins): uncomfortable to hold, capacity
   limited intraday, and its returns cluster in volatile periods (2008, 2020, 2022), so it looks dead for years between them.
3. **When it should fail:** calm, range-bound years (2017, much of 2019 and 2021): many false breaks, each costing spread. Days dominated
   by one scheduled release where the move reverses.
4. **Evidence before testing:**
   - Zarattini, Aziz, Barbon (2024), "Beat the Market: An Effective Intraday Momentum Strategy for S&P500 ETF (SPY)", Swiss Finance
     Institute Research Paper 24-97, SSRN 4824172. https://ideas.repec.org/p/chf/rpseri/rp2497.html ; full text:
     https://concretumgroup.com/wp-content/uploads/2026/02/Beat-the-Market.pdf . Practitioner paper (Concretum is the first author's
     firm), not peer-reviewed.
   - **Sample:** SPY, 1-min IQFeed bars, **May 2007 – Apr 2024**. Noise area as on this card: σ(t) = mean over the last 14 days of
     |close at t / 09:30 open − 1|; bounds from max/min(open, prior close); decisions and stops only at HH:00 / HH:30; all flat at 16:00.
   - **Costs:** included: $0.0035 per share commission plus $0.001 per share slippage, each side (≈ 1.8 bps a side at SPY's
     2007–2024 average price of $247, more in early years). Slippage from the authors' own 1,000-trade live test in April 2024.
     With the Kissell I-Star impact model instead, the headline Sharpe drops from 1.33 to 1.17 (FAQ Q15).
   - **Effect sizes (net of those costs), by exit variant:**
     | variant | sizing | IRR | vol | Sharpe | max DD | trades (17 y) | source |
     |---|---|---|---|---|---|---|---|
     | opposite band as stop (**no VWAP**) | 1× | 6.2% | 10.9% | **0.61** | 21% | 5,494 (1.3/day) | Table 1 |
     | current band + VWAP | 1× | 9.7% | 7.7% | 1.24 | 12% | 7,668 (1.8/day) | Table 2 |
     | current band + VWAP | vol-target, ≤ 4× | **19.6%** | 14.3% | **1.33** | 25% | 7,668 | Table 3 (headline) |
     | SPY buy & hold | 1× | 7.2% | 20.2% | 0.45 | 56% | — | Table 1 |
     The v1 card quoted the headline row (19.6%, 1.33, −25%): **correct numbers, wrong row for this card.** This card exits on the
     current band **without** VWAP, a variant the paper only illustrates (Fig. 5a) and never tabulates. The tabulated no-VWAP version
     has Sharpe 0.61 at 1×, worst day −10.3%, negative skew (−1.24); the VWAP stop is what moves it to 1.24. Expect this card's
     variant between the two, and closer to 0.61 than the v1 card implied.
   - Robustness in the paper: lookback 10 / 14 / 20 days gives Sharpe 1.23 / 1.35 / 1.33 (headline variant, FAQ Q6): flat, so `N` is
     a cheap parameter. Volatility multiplier: best Sharpe "at approximately 1.5" (Fig. 9), **chosen after seeing results**; the paper
     keeps 1.0. Futures (FAQ Q13, Jan 2007 – Sep 2024, headline variant): S&P 500 Sharpe 1.32, **Nasdaq 1.23**; average over 33
     futures 0.60. Profit is higher when SPY's 5-day RSI is low (proxy for dealer short gamma; Section 4.5), and in high-VIX regimes.
     Calendar years (headline variant, FAQ Q24): **2016 −12.8%, 2017 −6.9%**, 2010 +1.3%, 2019 +6.9%: the calm-year failure in point 3
     is real and lasts years.
   - **Out of sample:** no separate holdout in the paper. First version **10 May 2024** (v1 card said Nov 2024: wrong). Post-publication
     inside our research period, May–Dec 2024 (headline variant, FAQ Q24): ≈ +17% compounded. Our locked open (2025 →) is fully
     post-publication.
   - **Decay and costs (redone in R, v2):** the paper's per-trade **net** edge is ≈ 2.1 bps (no-VWAP: 6.8%/yr arithmetic ÷ 323 trades/yr)
     to 2.2 bps (VWAP: 10.0% ÷ 451); adding back its costs (≈ 3.6–5 bps round trip) gives **≈ 6–7 bps gross per trade** (v1 said 4–8
     bps: consistent). Decayed by half: ≈ 3.25 bps. 1 R = s × band width: the paper's example band is 0.30% at 10:30 and 0.60% at 15:30,
     so **1 R ≈ 30–60 bps** (v1 said 40–80). US500 CFD cost ≈ 1.25 bps.
     | 1 R | decayed gross | cost | net (decayed) | net (published size) |
     |---|---|---|---|---|
     | 30 bps | 0.11 R | 0.04 R | **+0.07 R** | +0.18 R |
     | 45 bps | 0.07 R | 0.03 R | **+0.04 R** | +0.12 R |
     | 60 bps | 0.05 R | 0.02 R | **+0.03 R** | +0.09 R |
     These use the per-trade edge of the **VWAP or opposite-band** variants; the no-VWAP Sharpe of 0.61 says this card's variant may
     earn less. Needed for green: ≥ +0.05 R after costs over ≥ 150 trades with t ≥ 2. Verdict: passes only if the effect holds at
     well over half its published size. Costs are not the binding constraint; the decayed edge of the band-only variant is.
   - Our sizing is 1 R per trade, not volatility targeting, so the Sharpe will not match the paper's even if the effect is real.

## Rules (defaults)
- **Symbols:** US500 (the paper's market), USTEC (Concretum's follow-up applies it to QQQ; same session, higher noise). Two symbols,
  one bloc; fewer tests.
- **Decision timeframe:** m15 bars; decisions only on bars closing at :00 and :30 ET, from 10:00 to 15:30 ET (the paper's 30-min grid).
- **Noise band:** for each time of day t (minutes after the 09:30 ET cash open), σ(t) = mean over the previous N trading days of
  |close at t / that day's 09:30 open − 1|. Today's bounds: Upper(t) = max(Open, prior cash close) × (1 + m·σ(t)),
  Lower(t) = min(Open, prior cash close) × (1 − m·σ(t)). Open = first price at or after 09:30 ET. Only closed bars and past days are used.
- **Entry:** at a decision bar close, if flat: close > Upper(t) → long; close < Lower(t) → short (market order).
  Re-entry allowed the same day after an exit; at most 10 trades a day (engine cap).
- **Stop:** broker-side, entry ∓ s × m·σ(t) × Open (the band width at that time, so the stop scales with the day's usual noise).
- **Exit:** at a decision bar close, if a long closes back below Upper(t) (short: above Lower(t)), close it (exit flag). Time exit at
  the close of the m15 bar ending 16:00 ET. If long and the bar closes below Lower(t), reverse (exit + new short in the same rule).
- **Expected trades per year:** the paper has 1.3 (no VWAP) to 1.8 (VWAP) trades a day → ≈ 650–900 for two symbols.
- **Walk-forward:** 24 / 3 (default).

## Parameters (at most 3 tuned)
| parameter | default | reason | allowed values (grid, declared now) |
|---|---|---|---|
| `N` (σ lookback, days) | 14 | the paper's choice; Sharpe flat over 10–20 in the paper | {10, 14, 20} |
| `m` (band multiplier) | 1.0 | the paper's band (1.5 was the paper's best Sharpe in hindsight; in the grid, not the default) | {1.0, 1.25, 1.5} |
| `s` (stop, × band width) | 1.0 | gives back one noise unit before the broker stop; the exit flag usually acts first | {0.75, 1.0, 1.5} |

Grid size 27. Fixed: 30-min decision grid, first decision 10:00 ET, last entry 15:30 ET, exit at the cash close.

## Prop fit
- Class A, flat by 16:00 ET (22:00 Amsterdam). Holds of 30 min to 6 h; median ≥ 15 min by construction (30-min grid).
- Friday entries after 19:50 UTC blocked by the engine (FTMO 2-h rule): loses the last 1–2 decision points in winter.
- News: 10:00 ET releases (ISM, consumer confidence) and FOMC 14:00 ET fall on decision times; the news modes flatten / block as
  designed. The rule never uses the calendar to enter.
- Trades per day ≤ 10 per strategy; one position per symbol.

## Amber budget (only if the quick screen says amber; each line written and committed before it runs)
| # | change | reason (what information it adds) | written (date) |
|---|---|---|---|
| V1 | | | |
| V2 | | | |
| V3 | | | |

## Results (ledger test ids only; numbers live in the ledger and the digest)
- quick screen:
- amber variations:
- tuning / walk-forward:
- stress:
- gatekeeper:
