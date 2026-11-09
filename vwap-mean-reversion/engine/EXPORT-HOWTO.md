# Running the data exports (once per symbol, all 26 in one evening)

`FastBtExport.cs` is a cBot that never trades. One normal cTrader backtest of it records exactly what the strategy cBot sees
in an m1-bar backtest: every price, the bars of every timeframe (m1 to h4) with tick volume, the symbol's specs and trading
hours, and for symbols not quoted in USD the currency conversion at every price. The Python replica needs one export per
symbol. Version of 2026-10-21 (adds the currency conversion); US30's export of 20 October is still valid.

## Once: update the cBot in cTrader
1. Replace the code of the `FastBtExport` cBot with the new `tools/fastbt/FastBtExport.cs` (paste it in cTrader, or let Claude
   copy it into `~/cAlgo/Sources` while cTrader runs nothing).
2. Press **Build**. It asks for **Full access**: it needs that to write the files; it places no orders.

## Per symbol: one backtest (Backtesting tab of FastBtExport, not Optimisation)
The same for every symbol:
- timeframe **m5** · period **01/01/2018 → 31/12/2023** · data **m1 bars from server** · capital **100,000**
- spread **Fixed**, commission **USD per million USD volume**: the values in the table (the same as the v2 maps)
- **Download historical data for additional symbols … convert profit and margin: ON** (the box under Data) for every symbol — required: with it off, cTrader converts all history at today's rate (EURGBP test 2026-10-21).
- parameters: leave the defaults

Start it and wait for the log line `FastBtExport done: … ticks, … bar closes, files in …/cAlgo/Exports/fastbt/<SYMBOL>_m5_20180101`.
Each run takes a few minutes and writes ~100–200 MB.

**Start with EURGBP and USDJPY** (the two kinds of currency conversion) and tell Claude when they are done: Claude checks
them in a few minutes. Carry on with the others in the meantime. For symbols marked "conversion", the log also shows
`Conversion pair …` at the start. If it says `No conversion pair` instead, note it and carry on.

| # | symbol | spread (fixed) | commission ($ per million) | conversion |
|---|---|---|---|---|
| 1 | EURGBP | 0.4 | 30 | GBPUSD |
| 2 | USDJPY | 0.2 | 30 | USDJPY |
| 3 | US30 | 9 | 0 | — · **already done (20 Oct), skip** |
| 4 | USTEC | 8 | 0 | — |
| 5 | US500 | 6 | 0 | — |
| 6 | US2000 | 6 | 0 | — |
| 7 | DE40 | 10 | 0 | EURUSD |
| 8 | UK100 | 20 | 0 | GBPUSD |
| 9 | JP225 | 125 | 0 | USDJPY |
| 10 | EURUSD | 0.2 | 30 | — |
| 11 | GBPUSD | 0.5 | 30 | — |
| 12 | AUDUSD | 0.3 | 30 | — |
| 13 | NZDUSD | 0.4 | 30 | — |
| 14 | USDCAD | 0.5 | 30 | USDCAD |
| 15 | USDCHF | 1.1 | 30 | USDCHF |
| 16 | AUDJPY | 0.9 | 30 | USDJPY |
| 17 | EURJPY | 0.6 | 30 | USDJPY |
| 18 | AUDNZD | 1.0 | 30 | NZDUSD |
| 19 | EURAUD | 1.0 | 30 | AUDUSD |
| 20 | EURCHF | 0.8 | 30 | USDCHF |
| 21 | EURNZD | 1.7 | 30 | NZDUSD |
| 22 | GBPCAD | 1.4 | 30 | USDCAD |
| 23 | NZDCHF | 0.9 | 30 | USDCHF |
| 24 | XAUUSD | 10 | 30 | — |
| 25 | XAGUSD | 4 | 30 | — |
| 26 | XTIUSD | 5 | 0 | — |

Spread and commission come from each symbol's v2 map (`optimisation/<SYMBOL>/<Mode>/00_map/results.optres`); they must match,
because those maps are the referee results the replica is checked against.

**When: before Sunday 25 October 2026.** That night EU clocks change, and in the week after, the broker may shift its
trading-hours schedule. cTrader's backtests apply today's schedule to all of history (it decides the 22:49 Amsterdam winter
closes), so exports and the maps they are checked against should run under the same schedule.
**It happened (2026-10-28):** after the change the broker's UK100 table closes at 21:00 UTC Mon–Fri (the exports recorded 22:00; Friday found by the m1 check, Mon–Thu from the market-hours screenshot 2026-10-29), so cTrader
now closes UK100 trades open on a winter Friday at 20:50 UTC (BrokerCloseSafetyNet). `tools/fastbt/broker_hours.json` holds such moved
closes; `data.load()` applies them by default (`schedule="now"`, every new cTrader run), referee replays of older runs use
`schedule="export"` (`fullgrid.py` / `compare.py` / `step5_check.py compare-archive` default). The 47 m1 checks run after the change show no
other symbol's close moved earlier (a 1 h earlier close would have changed 2–364 trades in 45 of them; US2000 is not testable). Re-check after
the next clock change (29 March 2027).

Several FastBtExport instances (one per symbol) may run at the same time if cTrader allows it; each writes its own folder.
Nothing has to be sent anywhere: Claude reads the folders in `~/cAlgo/Exports/fastbt/`.
