# IC tick exports: data check and IC vs FTMO feed comparison (2026-11-06)

Data: `~/cAlgo/Exports/fastbt-ic-tick/` (42 symbols, FastBtExport, "Tick data from server", 193 GB). Per-symbol results:
`data-checks/ic-tick/<folder>.json` (`tools/datacheck/data_check.py`); feed comparisons: `tools/feedcheck/reports/IC-vs-FTMO-*.md`.

## 1. Completeness
- **Every tick file matches its own meta.json count.** Bar-close markers match too, except GBPAUD (953,015 vs 953,016: one bar, the run started without chart history).
- No timestamps running backwards, no unreadable prices.
- **Start dates:** FX, metals 2014-01-19; indices 2014-09-21 (STOXX50 2014-12-01, DE40 **2021-09-19**); oil 2017-07-16. All run to 2026-11-04/05.

## 2. Holes and thin data
- **One hole shared by 36 symbols: 10–19 October 2014** (about 9 days, no data). Research periods should start in **November 2014**.
- Other silences over 4 days are holidays (Easter, Christmas, Lunar New Year on HK50). Weekday silences over 6 h on F40, HK50, STOXX50, AUS200 are their normal overnight closes.
- Thin months (under 40% of the neighbouring months' ticks): AUS200 and JP225 2017-12; F40 2025-02; STOXX50 2016-04, 2016-05, 2022-04, 2025-02, 2025-07; XAGUSD 2014-10. Check before using those symbols.

## 3. Crossed prices (ask below bid)
- **FX, 2014–2019 only; none on any FX pair from 2020.** A broker-feed episode in **May–July 2015** hit every FX pair: EURUSD 36% of ticks in June 2015, crossings up to 74 pips; USDJPY 6% of ticks in 2015, about 1% a year 2016–2019. Later FX crossings are tiny (0.1 pip).
- Indices, oil: almost none.
- **Engine rule:** drop crossed ticks; treat FX May–July 2015 as suspect (exclude, or check that results don't depend on it).

## 4. Spreads (IC raw; median / 95th percentile, Aug–Oct 2026, in pips: FX 0.0001, JPY 0.01, gold 0.01, indices 0.1, oil 0.01)
EURUSD 0.1 / 0.1 (57% of ticks at zero spread; commission comes on top) · GBPUSD 0.2 / 0.4 · USDJPY 0.1 / 0.2 · crosses 0.2–0.8 / 0.4–2.7 · XAUUSD 8 / 12 · US500 5 / 5 · USTEC 10 / 10 · US30 12 / 12 · DE40 5 / 40 · UK100 9 / 50 · XTIUSD 2 / 2.
2014–2015 spreads were wider (crosses 1–4 pips).

## 5. IC vs FTMO
Windows: 2020-04 → 2021-06 (FX) and 2025-07 → 2026-10 (all; UK100 from 2025-09). FTMO has no data from 2021-07 to 2025-06.
- **Clocks identical** (shift 0 h) on all 16 comparisons; about 99% of m5 bars in both feeds.
- **FTMO's spreads are wider**, before commission (median, latest window, IC vs FTMO): AUDUSD 0.1 vs 0.4 · GBPUSD 0.2 vs 0.5 · USDJPY 0.1 vs 0.5 · EURJPY 0.5 vs 1.4 · **XAUUSD 8 vs 43** · **XTIUSD 2.0 vs 8.2** · US30 12 vs 21 · USTEC 10 vs 15 · DE40 5 vs 13.9 · US500 5.0 vs 5.6 · UK100 9 vs 8.5.
- **Prices:** median m5 close difference within 0.1–1× IC's spread on indices, about 1–3× on FX and gold.
- **Signals transfer well on slower timeframes, less on fast ones** (same bar / within ±1 bar): h1 Donchian break 94–98% / 96–100%; m15 fractals 84–95% / 91–97%; m15 EMA20/50 cross 66–93% / 91–99% (UK100 lowest).

## 6. What this means for the research
1. **Research on IC prices, but never on IC costs.** Use the worst firm's costs from the first run: on gold, oil, US30 and DE40, FTMO's spread is 2–5× IC's.
2. **Start research periods in November 2014;** keep the October 2014 hole and FX May–July 2015 out, or show results don't depend on them.
3. **Prefer m15 / h1 decisions.** m5 crossover logic matches between feeds only about 70–90% of the time on the same bar; such strategies need a strict firm-feed check (G3).
4. DE40 has only about 5 years; oil about 9.
5. The EURUSD 2020–2021 comparison is the earlier one (IC side from the 2018–2023 m1-bar export, fixed spread); the IC tick export now covers that window if a re-run is wanted.
