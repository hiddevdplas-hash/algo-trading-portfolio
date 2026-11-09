// cTrader Automate cBot — data export for tools/fastbt (the Python replica of VwapMeanReversionBot).
// It never trades. Run it ONCE per symbol as a normal backtest with exactly the grid's data settings
// (m1 bars from server, same start date, same spread), on the smallest chart timeframe that symbol's grids use.
// It writes what the real cBot sees during such a backtest:
//   ticks.csv.gz   every simulated tick: time (ms UTC), bid, ask, time until the broker's market close in .NET ticks
//                  (100 ns; -1 = market closed); a line "B,<open ms>" marks where OnBarClosed fired for a chart bar.
//                  Symbols not quoted in the account currency (EURGBP, USDJPY, DE40, ...) add per tick: Symbol.TickValue,
//                  AssetConverter's rate quote -> account, and bid/ask of the conversion pair (GBPUSD, USDJPY, EURUSD, ...)
//   chart_<tf>.csv.gz  the chart bars the cBot uses (open ms, O, H, L, C, tick volume), with ATR (Wilder, ATR Length)
//   bars_<tf>.csv.gz   the same for every extra timeframe; bars_m1 = the m1 source bars
//   meta.json      symbol specs (pip/tick size, lot step, swaps, triple-swap day, trading sessions, ...)
// Output: <Output Folder>/<SYMBOL>_<chart tf>_<first day>/ (default ~/cAlgo/Exports/fastbt).
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.FullAccess)]
    public class FastBtExport : Robot
    {
        [Parameter("Output Folder (empty = ~/cAlgo/Exports/fastbt)", DefaultValue = "")] public string OutputFolder { get; set; }
        [Parameter("Extra Timeframes", DefaultValue = "m1,m5,m10,m15,m30,h1,h2,h4")] public string ExtraTimeframes { get; set; }
        [Parameter("ATR Length", DefaultValue = 14, MinValue = 1)] public int AtrLength { get; set; }
        [Parameter("Write Ticks", DefaultValue = true)] public bool WriteTicks { get; set; }

        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
        private static readonly DateTime Epoch = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        private string _dir;
        private StreamWriter _ticks;
        private AverageTrueRange _atr;
        private readonly List<KeyValuePair<string, Bars>> _extra = new List<KeyValuePair<string, Bars>>();
        private int _barsAtStart;
        private long _tickCount, _barCloseCount;
        private DateTime _firstTick = DateTime.MinValue, _lastTick = DateTime.MinValue, _startTime;
        private string _quote, _account, _convName = "";
        private bool _needConv, _convInverted, _converterFailed;
        private Symbol _conv;

        protected override void OnStart()
        {
            string root = string.IsNullOrWhiteSpace(OutputFolder)
                ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "cAlgo", "Exports", "fastbt")
                : OutputFolder.Trim();
            _startTime = Server.Time;
            _dir = Path.Combine(root, string.Format(Inv, "{0}_{1}_{2:yyyyMMdd}", SymbolName, Short(Bars.TimeFrame), Server.Time));
            Directory.CreateDirectory(_dir);
            _atr = Indicators.AverageTrueRange(Bars, AtrLength, MovingAverageType.WilderSmoothing);
            _barsAtStart = Bars.Count;
            foreach (string part in (ExtraTimeframes ?? "").Split(new[] { ',', ';', ' ' }, StringSplitOptions.RemoveEmptyEntries))
            {
                TimeFrame tf = ParseTimeFrame(part.Trim());
                if (tf == null) { Print("Unknown timeframe skipped: {0}", part); continue; }
                _extra.Add(new KeyValuePair<string, Bars>(part.Trim().ToLowerInvariant(), MarketData.GetBars(tf)));
            }
            _quote = Symbol.QuoteAsset.Name;
            _account = Account.Asset.Name;
            _needConv = !string.Equals(_quote, _account, StringComparison.OrdinalIgnoreCase);
            if (_needConv)
            {
                // The pair that converts the quote currency into the account currency: GBPUSD for EURGBP, USDJPY for AUDJPY.
                string direct = _quote + _account, inverse = _account + _quote;
                try
                {
                    if (Symbols.Exists(direct)) { _conv = Symbols.GetSymbol(direct); _convName = direct; }
                    else if (Symbols.Exists(inverse)) { _conv = Symbols.GetSymbol(inverse); _convName = inverse; _convInverted = true; }
                }
                catch (Exception ex) { Print("Conversion pair lookup failed: {0}", ex.Message); _conv = null; }
                if (_conv == null) Print("No conversion pair for {0} -> {1}: only tick value and converter rate are written", _quote, _account);
                else Print("Conversion pair {0} ({1} -> {2})", _convName, _quote, _account);
            }
            if (WriteTicks) _ticks = Open("ticks.csv.gz", _needConv
                ? "time_ms,bid,ask,till_close_100ns,tick_value,convert,conv_bid,conv_ask"
                : "time_ms,bid,ask,till_close_100ns");
            Print("FastBtExport writing to {0}", _dir);
        }

        protected override void OnBarClosed()
        {
            _barCloseCount++;
            if (_ticks != null) _ticks.Write("B," + Ms(Bars.OpenTimes[Bars.Count - 1]) + "\n");
        }

        protected override void OnTick()
        {
            DateTime t = Server.Time;
            if (_firstTick == DateTime.MinValue) _firstTick = t;
            _lastTick = t;
            _tickCount++;
            if (_ticks == null) return;
            long tillClose = Symbol.MarketHours.IsOpened() ? Symbol.MarketHours.TimeTillClose().Ticks : -1;
            if (!_needConv)
            {
                _ticks.Write(Ms(t) + "," + R(Symbol.Bid) + "," + R(Symbol.Ask) + "," + tillClose.ToString(Inv) + "\n");
                return;
            }
            string rate = "";
            if (!_converterFailed)
            {
                try { rate = R(AssetConverter.Convert(1.0, _quote, _account)); }
                catch (Exception ex) { _converterFailed = true; Print("AssetConverter failed, column left empty: {0}", ex.Message); }
            }
            string conv = _conv != null ? R(_conv.Bid) + "," + R(_conv.Ask) : ",";
            _ticks.Write(Ms(t) + "," + R(Symbol.Bid) + "," + R(Symbol.Ask) + "," + tillClose.ToString(Inv) + "," + R(Symbol.TickValue)
                         + "," + rate + "," + conv + "\n");
        }

        protected override void OnStop()
        {
            if (_ticks != null) { _ticks.Flush(); _ticks.Dispose(); _ticks = null; }
            Try("meta.json", WriteMeta);
            Try("chart bars", () => WriteBars("chart_" + Short(Bars.TimeFrame) + ".csv.gz", Bars, _atr));
            foreach (var pair in _extra) Try("bars " + pair.Key, () => WriteBars("bars_" + pair.Key + ".csv.gz", pair.Value, null));
            Print("FastBtExport done: {0} ticks, {1} bar closes, files in {2}", _tickCount, _barCloseCount, _dir);
        }

        private void Try(string what, Action action)
        {
            try { action(); }
            catch (Exception ex) { Print("FastBtExport: writing {0} failed: {1}", what, ex); }
        }

        private void WriteBars(string name, Bars bars, AverageTrueRange atr)
        {
            using (var w = Open(name, atr != null ? "open_ms,open,high,low,close,tick_volume,atr" : "open_ms,open,high,low,close,tick_volume"))
            {
                var sb = new StringBuilder(128);
                for (int i = 0; i < bars.Count; i++)
                {
                    sb.Clear();
                    sb.Append(Ms(bars.OpenTimes[i])).Append(',').Append(R(bars.OpenPrices[i])).Append(',').Append(R(bars.HighPrices[i]))
                      .Append(',').Append(R(bars.LowPrices[i])).Append(',').Append(R(bars.ClosePrices[i])).Append(',').Append(R(bars.TickVolumes[i]));
                    if (atr != null) sb.Append(',').Append(R(atr.Result[i]));
                    sb.Append('\n');
                    w.Write(sb.ToString());
                }
            }
        }

        private void WriteMeta()
        {
            var meta = new Dictionary<string, object>();
            meta["symbol"] = SymbolName;
            meta["chart_timeframe"] = Short(Bars.TimeFrame);
            meta["start_server_time_ms"] = Ms(_startTime);
            meta["atr_length"] = AtrLength;
            meta["chart_bars_at_start"] = _barsAtStart;
            meta["chart_bars_at_stop"] = Bars.Count;
            meta["first_chart_bar_ms"] = Bars.Count > 0 ? Ms(Bars.OpenTimes[0]) : 0;
            meta["first_tick_ms"] = Ms(_firstTick);
            meta["last_tick_ms"] = Ms(_lastTick);
            meta["tick_count"] = _tickCount;
            meta["bar_close_count"] = _barCloseCount;
            meta["account_balance"] = Account.Balance;
            meta["digits"] = Symbol.Digits;
            meta["pip_size"] = Symbol.PipSize;
            meta["tick_size"] = Symbol.TickSize;
            meta["pip_value"] = Symbol.PipValue;
            meta["tick_value"] = Symbol.TickValue;
            meta["lot_size"] = Symbol.LotSize;
            meta["volume_min"] = Symbol.VolumeInUnitsMin;
            meta["volume_max"] = Symbol.VolumeInUnitsMax;
            meta["volume_step"] = Symbol.VolumeInUnitsStep;
            meta["swap_long"] = Symbol.SwapLong;
            meta["swap_short"] = Symbol.SwapShort;
            meta["base_asset"] = Symbol.BaseAsset.Name;
            meta["quote_asset"] = _quote;
            meta["account_asset"] = _account;
            meta["conversion_symbol"] = _convName;
            meta["conversion_inverted"] = _convInverted;
            meta["converter_failed"] = _converterFailed;
            if (_conv != null) { meta["conversion_digits"] = _conv.Digits; meta["conversion_tick_size"] = _conv.TickSize; }
            // Sizing probe: the same calls the strategy cBot makes for FixedCashRisk 1000.
            var probe = new List<string>();
            foreach (double pips in new[] { 1.0, 7.5, 23.16, 100.0, 231.6, 333.3, 1000.0, 2500.0, 12345.6 })
            {
                double raw = Symbol.VolumeForFixedRisk(1000, pips);
                probe.Add(string.Format(Inv, "{0}|{1}|{2}", R(pips), R(raw), R(Symbol.NormalizeVolumeInUnits(raw, RoundingMode.Down))));
            }
            meta["volume_for_fixed_risk_1000"] = probe;
            try { meta["symbol_properties"] = Describe(Symbol, 0); } catch (Exception ex) { meta["symbol_properties"] = "error: " + ex.Message; }
            try { meta["market_hours"] = Describe(Symbol.MarketHours, 0); } catch (Exception ex) { meta["market_hours"] = "error: " + ex.Message; }
            var options = new JsonSerializerOptions { WriteIndented = true, NumberHandling = JsonNumberHandling.AllowNamedFloatingPointLiterals };
            System.IO.File.WriteAllText(Path.Combine(_dir, "meta.json"), JsonSerializer.Serialize(meta, options));
        }

        // Every readable public property (also those of the API interfaces), as text, so no member name is guessed.
        private static Dictionary<string, object> Describe(object obj, int depth)
        {
            var result = new Dictionary<string, object>();
            if (obj == null) return result;
            var types = new List<Type> { obj.GetType() };
            types.AddRange(obj.GetType().GetInterfaces());
            foreach (Type type in types)
                foreach (PropertyInfo p in type.GetProperties(BindingFlags.Public | BindingFlags.Instance))
                {
                    if (p.GetIndexParameters().Length > 0 || result.ContainsKey(p.Name)) continue;
                    object value;
                    try { value = p.GetValue(obj); } catch (Exception ex) { result[p.Name] = "error: " + ex.GetType().Name; continue; }
                    result[p.Name] = Text(value, depth);
                }
            return result;
        }

        private static object Text(object value, int depth)
        {
            if (value == null) return null;
            if (value is string s) return s;
            if (value is double d) return R(d);
            if (value is IFormattable f && (value.GetType().IsPrimitive || value.GetType().IsEnum || value is DateTime || value is TimeSpan || value is decimal))
                return f.ToString(null, Inv);
            if (value is IEnumerable list && depth < 2)
            {
                var items = new List<object>();
                int n = 0;
                foreach (object item in list) { if (n++ >= 500) break; items.Add(item == null || item.GetType().IsPrimitive || item is string ? Text(item, depth + 1) : Describe(item, depth + 1)); }
                return items;
            }
            if (depth < 2 && !value.GetType().IsPrimitive && value.GetType().Namespace != null && value.GetType().Namespace.StartsWith("cAlgo")) return Describe(value, depth + 1);
            return value.ToString();
        }

        private StreamWriter Open(string name, string header)
        {
            var stream = new GZipStream(new FileStream(Path.Combine(_dir, name), FileMode.Create, FileAccess.Write, FileShare.Read, 1 << 20), CompressionLevel.Fastest);
            var w = new StreamWriter(stream, new UTF8Encoding(false), 1 << 20);
            w.Write(header + "\n");
            return w;
        }

        private static TimeFrame ParseTimeFrame(string s)
        {
            switch (s.ToLowerInvariant())
            {
                case "m1": return TimeFrame.Minute;
                case "m2": return TimeFrame.Minute2;
                case "m3": return TimeFrame.Minute3;
                case "m5": return TimeFrame.Minute5;
                case "m10": return TimeFrame.Minute10;
                case "m15": return TimeFrame.Minute15;
                case "m30": return TimeFrame.Minute30;
                case "h1": return TimeFrame.Hour;
                case "h2": return TimeFrame.Hour2;
                case "h4": return TimeFrame.Hour4;
                case "d1": return TimeFrame.Daily;
                default: return null;
            }
        }

        private static string Short(TimeFrame tf)
        {
            foreach (string name in new[] { "m1", "m2", "m3", "m5", "m10", "m15", "m30", "h1", "h2", "h4", "d1" })
                if (ParseTimeFrame(name).Equals(tf)) return name;
            return tf.ToString();
        }

        private static string Ms(DateTime t) { return ((long)(t - Epoch).TotalMilliseconds).ToString(Inv); }
        private static string R(double v) { return v.ToString("R", Inv); }
    }
}
