// Edge Research cBot side, pure core (no cAlgo types: unit-tested in common/tests with plain dotnet).
// The same rules as engine/rules.py (classes, entry blocks, news modes M0-M3, far-stop, caps) plus the live-only firm rules
// (daily / max loss per firm formula, guards, sizing, lot and margin caps). Spec: cTrader-Bots/CBOT-SIDE.md.
// Assembled into each finalist cBot by common/assemble.py; never edit an assembled file by hand.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace EdgeResearch.Common
{
    // ------------------------------------------------------------------------------------------------------------------------
    // Clocks: UTC milliseconds everywhere; local times per date with real zones (Amsterdam and New York change on different dates).
    public static class Clock
    {
        public static readonly CultureInfo Inv = CultureInfo.InvariantCulture;
        private static readonly DateTime Epoch = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        private static readonly Dictionary<string, TimeZoneInfo> Cache = new Dictionary<string, TimeZoneInfo>();
        // IANA id -> Windows id (cTrader on a Windows VPS without ICU)
        private static readonly Dictionary<string, string> Win = new Dictionary<string, string>
        {
            { "Europe/Amsterdam", "W. Europe Standard Time" }, { "Europe/Prague", "Central Europe Standard Time" },
            { "America/New_York", "Eastern Standard Time" }, { "Asia/Tokyo", "Tokyo Standard Time" }, { "UTC", "UTC" }
        };
        public const long MIN = 60000L, HOUR = 3600000L, DAY = 86400000L;

        public static long Ms(DateTime utc) { return (DateTime.SpecifyKind(utc, DateTimeKind.Utc).Ticks - Epoch.Ticks) / 10000; }
        public static DateTime FromMs(long ms) { return new DateTime(Epoch.Ticks + ms * 10000, DateTimeKind.Utc); }

        public static TimeZoneInfo Zone(string iana)
        {
            TimeZoneInfo z;
            lock (Cache)
            {
                if (Cache.TryGetValue(iana, out z)) return z;
                if (iana == "UTC") z = TimeZoneInfo.Utc;
                else
                {
                    try { z = TimeZoneInfo.FindSystemTimeZoneById(iana); }
                    catch (Exception)
                    {
                        string w;
                        if (!Win.TryGetValue(iana, out w)) throw new ArgumentException("unknown time zone " + iana);
                        z = TimeZoneInfo.FindSystemTimeZoneById(w);
                    }
                }
                Cache[iana] = z;
                return z;
            }
        }

        public static DateTime Local(long ms, string zone) { return TimeZoneInfo.ConvertTimeFromUtc(FromMs(ms), Zone(zone)); }

        /// <summary>UTC ms of a local wall time (Python: datetime(..., tzinfo=ZoneInfo(zone)); a time skipped by DST maps forward
        /// by the gap, an ambiguous one takes the first occurrence, as zoneinfo with fold=0).</summary>
        public static long LocalToMs(DateTime localDate, int hh, int mm, string zone)
        {
            var z = Zone(zone);
            var t = new DateTime(localDate.Year, localDate.Month, localDate.Day, hh, mm, 0, DateTimeKind.Unspecified);
            if (z.IsInvalidTime(t))
            {
                // zoneinfo (fold=0) uses the offset before the gap: e.g. 02:30 on a spring-forward night -> 03:30 local
                var before = z.GetUtcOffset(t.AddHours(-3));
                return Ms(DateTime.SpecifyKind(t - before, DateTimeKind.Utc));
            }
            if (z.IsAmbiguousTime(t))
            {
                var offs = z.GetAmbiguousTimeOffsets(t);
                var big = offs[0] > offs[1] ? offs[0] : offs[1];      // fold=0 = the earlier instant = the larger offset
                return Ms(DateTime.SpecifyKind(t - big, DateTimeKind.Utc));
            }
            return Ms(TimeZoneInfo.ConvertTimeToUtc(t, z));
        }

        public static string Iso(long ms) { return FromMs(ms).ToString("yyyy-MM-dd HH:mm:ss", Inv) + "Z"; }
        public static string Ams(long ms) { return Local(ms, "Europe/Amsterdam").ToString("yyyy-MM-dd HH:mm:ss", Inv); }

        public static long ParseDayUtc(string day)
        {
            return Ms(DateTime.ParseExact(day.Trim(), "yyyy-MM-dd", Inv, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal));
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    public static class ErPaths
    {
        /// <summary>"~/x" -> home/x. A path pasted as "~/Users/<me>/..." (the home folder written twice: the user's first R1 try) is
        /// read as the absolute path it names.</summary>
        public static string Expand(string p)
        {
            p = (p ?? "").Trim();
            if (!p.StartsWith("~")) return p;
            string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
            string rest = p.Substring(1).TrimStart('/', '\\');
            string abs = "/" + rest;
            if (abs.StartsWith(home + "/")) return abs;
            return System.IO.Path.Combine(home, rest);
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Class rules and entry blocks (engine/rules.py: class_flats, nightly_blocks, day_starts).
    public static class ClassRules
    {
        public const string AMS = "Europe/Amsterdam";
        public const int FlatH = 22, FlatM = 45;          // class A daily, class B Fridays
        public const int NightEndH = 0, NightEndM = 15;   // entries blocked 22:45 -> 00:15 Amsterdam

        /// <summary>The last class flat time at or before nowMs (-1 = none: class C).</summary>
        public static long LastFlatAtOrBefore(char cls, long nowMs)
        {
            if (cls == 'C') return -1;
            if (cls != 'A' && cls != 'B') throw new ArgumentException("class " + cls);
            DateTime d = Clock.Local(nowMs, AMS).Date;
            for (int k = 0; k < 9; k++, d = d.AddDays(-1))
            {
                if (cls == 'B' && d.DayOfWeek != DayOfWeek.Friday) continue;
                long f = Clock.LocalToMs(d, FlatH, FlatM, AMS);
                if (f <= nowMs) return f;
            }
            return -1;
        }

        /// <summary>A flat time fell in [liveMs, nowMs]: close the position / cancel the order (kernel: first flat at or after going live).</summary>
        public static bool FlatDue(char cls, long liveMs, long nowMs)
        {
            long f = LastFlatAtOrBefore(cls, nowMs);
            return f >= 0 && f >= liveMs;
        }

        public const long BreakLead = 5 * Clock.MIN, MinBreak = 2 * Clock.HOUR;   // DESIGN A8

        /// <summary>DESIGN A8: the flat time a market break of >= 2 h adds (closeMs = the session close that starts it): class A and B
        /// flat 5 min before that close, or at 22:45 Amsterdam on that moment's Amsterdam date if that is earlier; class C: -1.
        /// (Class A's daily 22:45 stays; for class B this replaces "Friday 22:45": the last session before a break.)</summary>
        public static long BreakFlat(char cls, long closeMs, string kind = "weekend")
        {
            if (cls == 'C') return -1;
            if (cls == 'B' && kind == MarketBreak.Daily) return -1;      // A8.6: class B ignores the symbol's regular daily break
            long p = closeMs - BreakLead;
            long f = Clock.LocalToMs(Clock.Local(p, AMS).Date, FlatH, FlatM, AMS);     // 22:45 on the Amsterdam date of close - 5 min (engine)
            return f < p ? f : p;
        }

        /// <summary>All flat times in [firstMs, endMs) (engine/rules.py class_flats with the breaks' closes; class B skips daily breaks).</summary>
        public static List<long> FlatTimes(char cls, long firstMs, long endMs, IEnumerable<MarketBreak> breaks)
        {
            var o = new SortedSet<long>();
            if (cls == 'C') return o.ToList();
            if (cls == 'A')
                for (DateTime d = Clock.Local(firstMs, AMS).Date.AddDays(-1); d <= Clock.Local(endMs, AMS).Date.AddDays(1); d = d.AddDays(1))
                    o.Add(Clock.LocalToMs(d, FlatH, FlatM, AMS));
            foreach (var b in breaks) { long p = BreakFlat(cls, b.Close, b.Kind); if (p >= 0) o.Add(p); }
            return o.Where(x => x >= firstMs && x < endMs).ToList();
        }

        /// <summary>DESIGN A8 (amended): class A flat at 22:45 Amsterdam daily and before every break of >= 2 h; class B before every such
        /// break except the regular daily one; C never. Returns the flat time in [liveMs, nowMs] that applies, or -1.</summary>
        public static long FlatAt(char cls, long liveMs, long nowMs, IEnumerable<MarketBreak> breaks, bool fixedFridayForB = false)
        {
            if (cls == 'C') return -1;
            long best = -1;
            if (cls == 'A' || fixedFridayForB) { long f = LastFlatAtOrBefore(cls, nowMs); if (f >= liveMs) best = f; }
            foreach (var b in breaks)
            {
                long p = BreakFlat(cls, b.Close, b.Kind);
                if (p >= 0 && p >= liveMs && p <= nowMs && p > best) best = p;
            }
            return best;
        }

        /// <summary>Start of the nightly block containing nowMs, or -1 (block = [22:45 Amsterdam, 00:15 next day)).</summary>
        public static long NightBlockStart(long nowMs)
        {
            DateTime d = Clock.Local(nowMs, AMS).Date;
            for (int k = 0; k < 2; k++, d = d.AddDays(-1))
            {
                long s = Clock.LocalToMs(d, FlatH, FlatM, AMS), e = Clock.LocalToMs(d.AddDays(1), NightEndH, NightEndM, AMS);
                if (s <= nowMs && nowMs < e) return s;
            }
            return -1;
        }

        /// <summary>The most recent nightly block start at or before nowMs.</summary>
        public static long LastNightStart(long nowMs)
        {
            DateTime d = Clock.Local(nowMs, AMS).Date;
            for (int k = 0; k < 3; k++, d = d.AddDays(-1))
            {
                long s = Clock.LocalToMs(d, FlatH, FlatM, AMS);
                if (s <= nowMs) return s;
            }
            return -1;
        }

        /// <summary>Amsterdam midnight starting the day of nowMs (the day cap's day).</summary>
        public static long AmsDayStart(long nowMs) { return Clock.LocalToMs(Clock.Local(nowMs, AMS).Date, 0, 0, AMS); }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Market hours -> the pre-close entry block (engine/rules.py preclose_blocks: [close - 2 h, close) before a close of >= 2 h).
    /// <summary>A market break of the symbol: [Close, Reopen). Kind: daily (the regular daily break), weekend, holiday (incl. early
    /// closes), gap (unscheduled: data outage in history, A8.7).</summary>
    public class MarketBreak
    {
        public const string Daily = "daily", Weekend = "weekend", Holiday = "holiday", Gap = "gap";
        public long Close, Reopen;
        public string Kind;
        public override string ToString() { return Kind + " " + Clock.Iso(Close) + " -> " + Clock.Iso(Reopen); }
    }

    /// <summary>Where a symbol's sessions are anchored (its exchange's clock): the backtest shift of cTrader's current session table uses
    /// it (DESIGN A8 parity: an hour matters in the weeks only one side has changed its clocks). Overridden by "sessions_tz.<SYMBOL>".</summary>
    public static class SessionZones
    {
        public static string Default(string canon)
        {
            switch (canon)
            {
                case "DE40": case "STOXX50": case "F40": return "Europe/Berlin";
                case "UK100": return "Europe/London";
                case "JP225": return "Asia/Tokyo";
                case "AUS200": return "Australia/Sydney";
                case "HK50": return "Asia/Hong_Kong";
                default: return "America/New_York";      // FX, metals, oil, US indices: the New York 17:00 close
            }
        }
    }

    public class MarketClock
    {
        public struct Session { public DayOfWeek StartDay, EndDay; public TimeSpan Start, End; }
        public struct Closed { public long StartMs, EndMs; public bool Recurring; }
        private readonly List<Session> _sessions;
        private readonly List<Closed> _holidays;
        private long _cacheFrom = long.MaxValue, _cacheTo = long.MinValue;
        private List<long[]> _open = new List<long[]>();
        private readonly Func<long, long> _shift;

        /// <param name="shift">ms added to a session end at a given time (null = none). cTrader backtests serve TODAY's weekly table in UTC
        /// (R1, 2026-11-13: a 22:00 UTC Friday close all through Mar-Apr 2024, though the US-summer close was 21:00); AnchoredShift
        /// moves it with the anchor zone's DST.</param>
        public MarketClock(IEnumerable<Session> sessions, IEnumerable<Closed> holidays, Func<long, long> shift = null)
        {
            _sessions = sessions.ToList();
            _holidays = (holidays ?? Enumerable.Empty<Closed>()).ToList();
            _shift = shift;
        }

        /// <summary>A table written at refMs in UTC, anchored to a zone's wall clock (the broker's server time follows New York):
        /// at time t the sessions move by offset(refMs) - offset(t). Zero when t and refMs share the zone's offset (always live).</summary>
        public static Func<long, long> AnchoredShift(string zone, long refMs)
        {
            var z = Clock.Zone(zone);
            long refOff = (long)z.GetUtcOffset(Clock.FromMs(refMs)).TotalMilliseconds;
            return t => refOff - (long)z.GetUtcOffset(Clock.FromMs(t)).TotalMilliseconds;
        }

        public bool HasSessions { get { return _sessions.Count > 0; } }

        private void Build(long nowMs)
        {
            // open intervals (UTC) for the week before to two weeks after now, holidays removed, merged
            DateTime monday = Clock.FromMs(nowMs).Date;
            while (monday.DayOfWeek != DayOfWeek.Monday) monday = monday.AddDays(-1);
            var raw = new List<long[]>();
            for (int w = -1; w <= 2; w++)
            {
                DateTime wk = monday.AddDays(7 * w);
                foreach (var s in _sessions)
                {
                    long a = Clock.Ms(wk.AddDays(((int)s.StartDay + 6) % 7) + s.Start);
                    long b = Clock.Ms(wk.AddDays(((int)s.EndDay + 6) % 7) + s.End);
                    if (b <= a) b += 7 * Clock.DAY;
                    if (_shift != null) { a += _shift(a); b += _shift(b); }
                    raw.Add(new[] { a, b });
                }
            }
            raw.Sort((x, y) => x[0].CompareTo(y[0]));
            var merged = new List<long[]>();
            foreach (var r in raw)
            {
                if (merged.Count > 0 && r[0] <= merged[merged.Count - 1][1]) merged[merged.Count - 1][1] = Math.Max(merged[merged.Count - 1][1], r[1]);
                else merged.Add(new[] { r[0], r[1] });
            }
            foreach (var h in _holidays)
            {
                var hs = new List<long[]>();
                if (!h.Recurring) hs.Add(new[] { h.StartMs, h.EndMs });
                else
                {
                    var s0 = Clock.FromMs(h.StartMs);
                    for (int y = Clock.FromMs(nowMs).Year - 1; y <= Clock.FromMs(nowMs).Year + 1; y++)
                    {
                        long shift = Clock.Ms(new DateTime(y, s0.Month, Math.Min(s0.Day, DateTime.DaysInMonth(y, s0.Month)), s0.Hour, s0.Minute, 0, DateTimeKind.Utc)) - h.StartMs;
                        hs.Add(new[] { h.StartMs + shift, h.EndMs + shift });
                    }
                }
                foreach (var c in hs) merged = Cut(merged, c[0], c[1]);
            }
            _open = merged;
            _cacheFrom = Clock.Ms(monday.AddDays(-3));
            _cacheTo = Clock.Ms(monday.AddDays(10));
        }

        private static List<long[]> Cut(List<long[]> iv, long a, long b)
        {
            var o = new List<long[]>();
            foreach (var x in iv)
            {
                if (b <= x[0] || a >= x[1]) { o.Add(x); continue; }
                if (x[0] < a) o.Add(new[] { x[0], a });
                if (b < x[1]) o.Add(new[] { b, x[1] });
            }
            return o;
        }

        /// <summary>(close, reopen) of the open interval containing nowMs; false if the market is closed now.</summary>
        public bool NextClose(long nowMs, out long closeMs, out long reopenMs)
        {
            closeMs = reopenMs = -1;
            if (!HasSessions) return false;
            if (nowMs < _cacheFrom || nowMs > _cacheTo) Build(nowMs);
            for (int k = 0; k < _open.Count; k++)
            {
                if (_open[k][0] <= nowMs && nowMs < _open[k][1])
                {
                    closeMs = _open[k][1];
                    reopenMs = k + 1 < _open.Count ? _open[k + 1][0] : long.MaxValue;
                    return true;
                }
            }
            return false;
        }

        /// <summary>Session closes in [fromMs, toMs] that start a break of >= minBreakMs (weekend, holiday, early close).</summary>
        public List<long> BreakCloses(long fromMs, long toMs, long minBreakMs)
        {
            return Breaks(fromMs, toMs, minBreakMs).Select(b => b.Close).ToList();
        }

        /// <summary>Breaks of >= minBreakMs whose close is in [fromMs, toMs], classified: holiday if a holiday overlaps it, weekend if it
        /// spans a Saturday, daily if shorter than 20 h, else holiday.</summary>
        public List<MarketBreak> Breaks(long fromMs, long toMs, long minBreakMs)
        {
            var o = new List<MarketBreak>();
            if (!HasSessions) return o;
            if (toMs < _cacheFrom || toMs > _cacheTo) Build(toMs);
            for (int k = 0; k < _open.Count; k++)
            {
                long c = _open[k][1], r = k + 1 < _open.Count ? _open[k + 1][0] : long.MaxValue;
                if (c < fromMs || c > toMs || r - c < minBreakMs) continue;
                string kind;
                if (_holidays.Any(h => Overlaps(h, c, r))) kind = MarketBreak.Holiday;
                else if (SpansSaturday(c, r)) kind = MarketBreak.Weekend;
                else kind = r - c < 20 * Clock.HOUR ? MarketBreak.Daily : MarketBreak.Holiday;
                o.Add(new MarketBreak { Close = c, Reopen = r, Kind = kind });
            }
            return o;
        }

        private static bool SpansSaturday(long c, long r)
        {
            for (long t = c; t < r; t += Clock.HOUR) if (Clock.FromMs(t).DayOfWeek == DayOfWeek.Saturday) return true;
            return false;
        }

        private static bool Overlaps(Closed h, long c, long r)
        {
            if (!h.Recurring) return h.StartMs < r && h.EndMs > c;
            var s0 = Clock.FromMs(h.StartMs);
            for (int y = Clock.FromMs(c).Year - 1; y <= Clock.FromMs(c).Year + 1; y++)
            {
                long shift = Clock.Ms(new DateTime(y, s0.Month, Math.Min(s0.Day, DateTime.DaysInMonth(y, s0.Month)), s0.Hour, s0.Minute, 0, DateTimeKind.Utc)) - h.StartMs;
                if (h.StartMs + shift < r && h.EndMs + shift > c) return true;
            }
            return false;
        }

        /// <summary>Start of the pre-close block containing nowMs, or -1 (block = [close - before, close) when the break lasts >= minBreak).</summary>
        public long PreCloseBlockStart(long nowMs, long minBreakMs, long beforeMs)
        {
            long c, r;
            if (!NextClose(nowMs, out c, out r)) return -1;
            if (r - c >= minBreakMs && nowMs >= c - beforeMs) return c - beforeMs;
            return -1;
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    /// <summary>The symbol's breaks of >= 2 h, from one source at a time (DESIGN A8 parity): the calendar's break rows where they are
    /// complete (the engine's closes: ticks for history, exchange calendars ahead), otherwise the session table (+ holidays). Class flats,
    /// the pre-close entry block and firm break flats all read it.</summary>
    public class BreakBook
    {
        private readonly List<MarketBreak> _rows;
        private readonly long _rowsFrom, _rowsTo;
        private readonly MarketClock _clock;

        public BreakBook(NewsCalendar cal, string canon, MarketClock clock)
        {
            _clock = clock;
            List<MarketBreak> l;
            if (cal != null && cal.BreaksFromMs >= 0 && cal.Breaks.TryGetValue(canon, out l))
            {
                _rows = l.Where(b => b.Reopen - b.Close >= ClassRules.MinBreak).OrderBy(b => b.Close).ToList();
                _rowsFrom = cal.BreaksFromMs;
                _rowsTo = cal.BreaksToMs;
            }
        }

        public bool RowsCover(long fromMs, long toMs) { return _rows != null && fromMs >= _rowsFrom && toMs < _rowsTo; }
        public int RowCount { get { return _rows == null ? 0 : _rows.Count; } }

        /// <summary>Breaks whose close is in [fromMs, toMs].</summary>
        public List<MarketBreak> Between(long fromMs, long toMs)
        {
            if (RowsCover(fromMs, toMs)) return _rows.Where(b => b.Close >= fromMs && b.Close <= toMs).ToList();
            return _clock == null ? new List<MarketBreak>() : _clock.Breaks(fromMs, toMs, ClassRules.MinBreak);
        }

        /// <summary>Start of the pre-close entry block [close - before, close) containing nowMs, or -1.</summary>
        public long PreCloseBlockStart(long nowMs, long beforeMs)
        {
            foreach (var b in Between(nowMs, nowMs + beforeMs))
                if (nowMs >= b.Close - beforeMs && nowMs < b.Close) return b.Close - beforeMs;
            return -1;
        }

        /// <summary>Within leadMs before the close of a break of >= gapMs?</summary>
        public bool LeadDue(long nowMs, long gapMs, long leadMs)
        {
            foreach (var b in Between(nowMs, nowMs + leadMs))
                if (b.Reopen - b.Close >= gapMs && nowMs >= b.Close - leadMs && nowMs < b.Close) return true;
            return false;
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Symbols: canonical (research store / IC) names, asset class, news blocking (rules.blocks_symbol), blocs (CROSS-FIRM-HEDGING §3).
    public static class Symbols
    {
        public static readonly string[] FxCcys = { "EUR", "USD", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD" };
        // DESIGN §3.6 item 4 (engine/rules.py EXTRA), store names
        public static readonly Dictionary<string, string[]> Extra = new Dictionary<string, string[]>
        {
            { "USD", new[] { "XAUUSD", "XAGUSD", "US30", "US500", "USTEC" } }, { "EUR", new[] { "DE40", "STOXX50" } },
            { "GBP", new[] { "UK100" } }, { "JPY", new[] { "JP225" } }, { "OIL", new[] { "XTIUSD", "XBRUSD" } }
        };

        public static bool IsFx(string s) { return s.Length == 6 && FxCcys.Contains(s.Substring(0, 3)) && FxCcys.Contains(s.Substring(3)); }

        public static bool BlocksSymbol(string ccy, string symbol)
        {
            string[] x;
            if (Extra.TryGetValue(ccy, out x) && x.Contains(symbol)) return true;
            return IsFx(symbol) && (symbol.Substring(0, 3) == ccy || symbol.Substring(3) == ccy);
        }

        /// <summary>fx, metal, oil or index (lot caps per class at Instant Funding, max lots per trade at FTMO).</summary>
        public static string AssetClass(string s)
        {
            if (IsFx(s)) return "fx";
            if (s == "XAUUSD" || s == "XAGUSD") return "metal";
            if (s == "XTIUSD" || s == "XBRUSD") return "oil";
            return "index";
        }

        /// <summary>Blocs and the sign of a long position in each (CROSS-FIRM-HEDGING §3: EQ, USD signed, JPY, METALS, OIL;
        /// crosses without USD or JPY: no bloc, DESIGN A3.5).</summary>
        public static List<KeyValuePair<string, int>> Blocs(string s)
        {
            var o = new List<KeyValuePair<string, int>>();
            if (s == "XAUUSD" || s == "XAGUSD") { o.Add(new KeyValuePair<string, int>("METALS", 1)); return o; }
            if (s == "XTIUSD" || s == "XBRUSD") { o.Add(new KeyValuePair<string, int>("OIL", 1)); return o; }
            if (!IsFx(s)) { o.Add(new KeyValuePair<string, int>("EQ", 1)); return o; }
            string b = s.Substring(0, 3), q = s.Substring(3);
            if (b == "USD") o.Add(new KeyValuePair<string, int>("USD", 1));        // long USDxxx = long USD
            if (q == "USD") o.Add(new KeyValuePair<string, int>("USD", -1));       // long xxxUSD = short USD
            if (q == "JPY") o.Add(new KeyValuePair<string, int>("JPY", 1));        // long xxxJPY = short JPY
            return o;
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Firm config: "key = value   # source" lines; stage-scoped keys "<stage>.<key>" win over plain keys.
    public class FirmConfig
    {
        public readonly Dictionary<string, string> Values = new Dictionary<string, string>();
        public readonly Dictionary<string, string> Sources = new Dictionary<string, string>();
        public string Path, Sha256, Stage;

        public static FirmConfig Parse(string text, string stage)
        {
            var c = new FirmConfig { Stage = stage };
            int n = 0;
            foreach (var raw in text.Replace("\r", "").Split('\n'))
            {
                n++;
                string line = raw.Trim();
                if (line.Length == 0 || line.StartsWith("#")) continue;
                int h = line.IndexOf('#');
                string src = h >= 0 ? line.Substring(h + 1).Trim() : "";
                if (h >= 0) line = line.Substring(0, h).Trim();
                int eq = line.IndexOf('=');
                if (eq <= 0) throw new FormatException("config line " + n + ": no 'key = value'");
                string k = line.Substring(0, eq).Trim(), v = line.Substring(eq + 1).Trim();
                if (c.Values.ContainsKey(k)) throw new FormatException("config line " + n + ": duplicate key " + k);
                c.Values[k] = v;
                c.Sources[k] = src;
            }
            return c;
        }

        public static FirmConfig Load(string path, string stage)
        {
            string text = System.IO.File.ReadAllText(path);
            var c = Parse(text, stage);
            c.Path = path;
            using (var sha = System.Security.Cryptography.SHA256.Create())
                c.Sha256 = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-", "").ToLowerInvariant();
            if (!c.StageList().Contains(stage)) throw new FormatException("stage '" + stage + "' not in " + c.Str("stages"));
            return c;
        }

        public string[] StageList() { return Str("stages").Split(',').Select(x => x.Trim()).Where(x => x.Length > 0).ToArray(); }

        private string Key(string k)
        {
            if (Stage != null && Values.ContainsKey(Stage + "." + k)) return Stage + "." + k;
            return k;
        }

        public bool Has(string k) { return Values.ContainsKey(Key(k)); }
        public string Str(string k)
        {
            string v;
            if (!Values.TryGetValue(Key(k), out v)) throw new KeyNotFoundException("firm config: missing key " + k + (Stage != null ? " (stage " + Stage + ")" : ""));
            return v;
        }
        public string Str(string k, string dflt) { return Has(k) ? Str(k) : dflt; }
        public double Num(string k) { return double.Parse(Str(k), NumberStyles.Float, Clock.Inv); }
        public double Num(string k, double dflt) { return Has(k) ? Num(k) : dflt; }
        public bool Flag(string k, bool dflt)
        {
            if (!Has(k)) return dflt;
            string v = Str(k).ToLowerInvariant();
            return v == "yes" || v == "true" || v == "1";
        }
        public string SourceOf(string k) { string s; return Sources.TryGetValue(Key(k), out s) ? s : ""; }

        /// <summary>Firm symbol name -> canonical name, from "symbol.CANON = FIRMNAME" lines.</summary>
        public string Canonical(string firmName)
        {
            foreach (var kv in Values)
                if (kv.Key.StartsWith("symbol.") && kv.Value.Split('|').Select(x => x.Trim()).Contains(firmName)) return kv.Key.Substring(7);
            string plain = firmName.Replace("/", "");                // FX pairs and metals: "EUR/USD" or "EURUSD" -> EURUSD
            if (Symbols.IsFx(plain) || plain == "XAUUSD" || plain == "XAGUSD") return plain;
            return Flag("symbols_identity", false) ? firmName : null;
        }

        /// <summary>A value from a size table "25000:10, 50000:20" for the account's initial balance (exact size, else NaN).</summary>
        public double BySize(string k, double initial)
        {
            if (!Has(k)) return double.NaN;
            foreach (var part in Str(k).Split(','))
            {
                var kv = part.Split(':');
                if (kv.Length == 2 && Math.Abs(double.Parse(kv[0], Clock.Inv) - initial) < 0.5) return double.Parse(kv[1], Clock.Inv);
            }
            return double.NaN;
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // News calendar: the exported file (cTrader-Bots/CBOT-SIDE.md §3, writer: common/proposals/export_calendar.py).
    public class NewsEvent
    {
        public long StartMs, EndMs = -1;          // EndMs -1 = none; range events: end of the usual range; talks: official end if known
        public string TypeId, Ccy, Kind, EndStatus;
        public int Tier;
        public bool Research, Range;              // Range: no official start, StartMs / EndMs span the usual range (engine/news.py)
        public string[] Sources = new string[0];
        public List<KeyValuePair<string, long>> AltStarts = new List<KeyValuePair<string, long>>();   // firm calendar times
    }

    public class NewsWindow
    {
        public long Start, End;
        public int Kind;                // 1 flatten (unless far-stop), 2 hold without target
        public double FarBp;            // NaN = no exemption
        public string Types;            // event types merged into this window (log)
    }

    public class NewsCalendar
    {
        public const long PRE = 6 * Clock.MIN, POST_RELEASE = 6 * Clock.MIN, POST_TALK = 5 * Clock.MIN;   // engine/rules.py (DESIGN A6)
        // FundingPips' whole-event rule (DESIGN A6.4), live cBot only: talks T-6 -> end + 5 min, official end or these assumed lengths
        public static readonly Dictionary<string, long> FpAssumedEnd = new Dictionary<string, long>
        { { "speech", 90 * Clock.MIN }, { "press_conference", 90 * Clock.MIN }, { "testimony", 210 * Clock.MIN } };
        public const string RulesLine = "design=A6;pre_min=6;post_min=6;range_talk_post_min=5;fp_speech_min=90;fp_press_conference_min=90;fp_testimony_min=210";

        public readonly List<NewsEvent> Events = new List<NewsEvent>();
        public readonly Dictionary<string, double> FarBp = new Dictionary<string, double>();      // "SYMBOL|TYPE" -> bp
        public readonly Dictionary<string, List<MarketBreak>> Breaks = new Dictionary<string, List<MarketBreak>>();   // symbol -> breaks (DESIGN A8)
        public long BreaksFromMs = -1, BreaksToMs = -1;     // [from, to): days the break rows are complete for
        public long ValidFromMs = -1, ValidToMs = -1;       // [from, to) = days the file is complete for
        public string Version, SourceCommit, EngineHash, Rules, Sha256;
        public readonly List<string> Problems = new List<string>();

        public static bool IsTalk(string kind) { return kind == "speech" || kind == "press_conference" || kind == "testimony"; }

        public static NewsCalendar Parse(string text)
        {
            var cal = new NewsCalendar();
            string[] head = null;
            int n = 0;
            foreach (var raw in text.Replace("\r", "").Split('\n'))
            {
                n++;
                string line = raw.Trim();
                if (line.Length == 0) continue;
                if (line.StartsWith("#"))
                {
                    var f = line.Substring(1).Split(',');
                    switch (f[0])
                    {
                        case "er-calendar": cal.Version = f.Length > 1 ? f[1] : ""; break;
                        case "source_commit": cal.SourceCommit = f[1]; break;
                        case "engine_hash": cal.EngineHash = f[1]; break;
                        case "valid_from": cal.ValidFromMs = Clock.ParseDayUtc(f[1]); break;
                        case "valid_to": cal.ValidToMs = Clock.ParseDayUtc(f[1]) + Clock.DAY; break;     // inclusive day
                        case "rules": cal.Rules = string.Join(",", f.Skip(1)); break;
                        case "far": if (f.Length == 4) cal.FarBp[f[1] + "|" + f[2]] = double.Parse(f[3], Clock.Inv); break;
                        case "breaks_complete": if (f.Length >= 3) { cal.BreaksFromMs = Clock.ParseDayUtc(f[1]); cal.BreaksToMs = Clock.ParseDayUtc(f[2]) + Clock.DAY; } break;
                        case "break":
                            if (f.Length >= 5)
                            {
                                List<MarketBreak> l;
                                if (!cal.Breaks.TryGetValue(f[1], out l)) cal.Breaks[f[1]] = l = new List<MarketBreak>();
                                l.Add(new MarketBreak { Close = long.Parse(f[2], Clock.Inv), Reopen = long.Parse(f[3], Clock.Inv), Kind = f[4] });
                            }
                            break;
                    }
                    continue;
                }
                var c = line.Split(',');
                if (head == null) { head = c; continue; }
                if (c.Length != head.Length) { cal.Problems.Add("line " + n + ": " + c.Length + " fields, header has " + head.Length); continue; }
                Func<string, string> g = name => { int i = Array.IndexOf(head, name); return i < 0 ? "" : c[i].Trim(); };
                var ev = new NewsEvent
                {
                    StartMs = long.Parse(g("start_utc_ms"), Clock.Inv),
                    EndMs = g("end_utc_ms").Length > 0 ? long.Parse(g("end_utc_ms"), Clock.Inv) : -1,
                    TypeId = g("type_id"), Ccy = g("ccy"), Kind = g("kind"), Tier = int.Parse(g("tier"), Clock.Inv),
                    Research = g("research") == "1", Range = g("range") == "1", EndStatus = g("end_status"),
                    Sources = g("sources").Split(';').Select(x => x.Trim()).Where(x => x.Length > 0).ToArray()
                };
                foreach (var a in g("alt_starts").Split(';').Where(x => x.Contains("@")))
                {
                    var p = a.Split('@');
                    ev.AltStarts.Add(new KeyValuePair<string, long>(p[0], long.Parse(p[1], Clock.Inv)));
                }
                cal.Events.Add(ev);
            }
            if (cal.Version != "v1") cal.Problems.Add("not an er-calendar v1 file");
            if (cal.Rules != RulesLine) cal.Problems.Add("window rules in the file (" + cal.Rules + ") differ from the cBot's (" + RulesLine + ")");
            if (cal.ValidToMs < 0) cal.Problems.Add("no valid_to line");
            cal.Events.Sort((a, b) => a.StartMs != b.StartMs ? a.StartMs.CompareTo(b.StartMs) : string.CompareOrdinal(a.TypeId, b.TypeId));
            return cal;
        }

        public static NewsCalendar Load(string path)
        {
            string text = System.IO.File.ReadAllText(path);
            var cal = Parse(text);
            using (var sha = System.Security.Cryptography.SHA256.Create())
                cal.Sha256 = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-", "").ToLowerInvariant();
            return cal;
        }

        /// <summary>[open, close) of one event (engine/rules.py event_window, DESIGN A6): official start -> T-6 / T+6, talks included;
        /// no official start (Range) -> the whole usual range, to end + 5 min (talks) or end + 6 min (releases). With fpWholeTalks
        /// (FundingPips live, A6.4) a talk with an official start runs T-6 -> end + 5 min (official end, else the assumed length).
        /// alt >= 0: the window around a firm's calendar time for the same event (CFD plan §0.2: union with the official window).</summary>
        public static void EventWindow(NewsEvent ev, long alt, bool fpWholeTalks, out long open, out long close)
        {
            long s = alt >= 0 ? alt : ev.StartMs;
            open = s - PRE;
            if (ev.Range && alt < 0)
            {
                long end = ev.EndMs >= 0 ? ev.EndMs : s;
                close = end + (IsTalk(ev.Kind) ? POST_TALK : POST_RELEASE);
            }
            else if (fpWholeTalks && IsTalk(ev.Kind) && !ev.Range)
            {
                long dur = ev.EndMs >= 0 ? ev.EndMs - ev.StartMs : FpAssumedEnd[ev.Kind];
                close = s + dur + POST_TALK;
            }
            else close = s + POST_RELEASE;
        }

        /// <summary>Does this event count for an account? Research events always (DESIGN A5.1); firm-only events (FXStreet, Myfxbook,
        /// a firm's own list) when one of the firm's calendar sources tags them (they can only remove trading, never add it).</summary>
        public static bool Counts(NewsEvent ev, ICollection<string> firmSources)
        {
            if (ev.Research) return true;
            return firmSources != null && ev.Sources.Any(firmSources.Contains);
        }

        /// <summary>Merged windows for one symbol and news mode, as engine/rules.py news_windows (flatten wins over hold; the far-stop
        /// threshold of a merged window is the largest of its flatten events, none if any has none). Live additions: firm calendar
        /// times (union with the official window, CFD plan §0.2) and firm-only events.</summary>
        public List<NewsWindow> Windows(string symbol, string mode, ICollection<string> firmSources, bool fpWholeTalks = false)
        {
            if (mode != "M0" && mode != "M1" && mode != "M2" && mode != "M3") throw new ArgumentException("mode " + mode);
            var raw = new List<object[]>();       // open, close, kind, far, type
            foreach (var ev in Events)
            {
                if (!Symbols.BlocksSymbol(ev.Ccy, symbol) || !Counts(ev, firmSources)) continue;
                if (mode == "M0" || (mode == "M1" && ev.Tier == 2)) continue;
                int kind = (ev.Tier == 1 || mode == "M3") ? 1 : 2;
                double f;
                if (!FarBp.TryGetValue(symbol + "|" + ev.TypeId, out f)) f = double.NaN;
                long o, c;
                EventWindow(ev, -1, fpWholeTalks, out o, out c);
                raw.Add(new object[] { o, c, kind, f, ev.TypeId });
                foreach (var a in ev.AltStarts)
                {
                    long o2, c2;
                    EventWindow(ev, a.Value, fpWholeTalks, out o2, out c2);
                    raw.Add(new object[] { o2, c2, kind, f, ev.TypeId + "@" + a.Key });
                }
            }
            raw.Sort((x, y) =>
            {
                int r = ((long)x[0]).CompareTo((long)y[0]);
                if (r != 0) return r;
                r = ((long)x[1]).CompareTo((long)y[1]);
                if (r != 0) return r;
                r = ((int)x[2]).CompareTo((int)y[2]);
                if (r != 0) return r;
                double fx = (double)x[3], fy = (double)y[3];        // as Python's tuple sort: then the threshold (NaN last), then the type
                r = (double.IsNaN(fx) ? double.MaxValue : fx).CompareTo(double.IsNaN(fy) ? double.MaxValue : fy);
                return r != 0 ? r : string.CompareOrdinal((string)x[4], (string)y[4]);
            });
            var o_ = new List<NewsWindow>();
            foreach (var r in raw)
            {
                long o = (long)r[0], c = (long)r[1];
                int kind = (int)r[2];
                double f = (double)r[3];
                if (o_.Count > 0 && o < o_[o_.Count - 1].End)
                {
                    var w = o_[o_.Count - 1];
                    w.End = Math.Max(w.End, c);
                    w.Types += "+" + (string)r[4];
                    if (kind == 1)
                    {
                        w.FarBp = w.Kind == 2 ? f : ((double.IsNaN(w.FarBp) || double.IsNaN(f)) ? double.NaN : Math.Max(w.FarBp, f));
                        w.Kind = 1;
                    }
                }
                else o_.Add(new NewsWindow { Start = o, End = c, Kind = kind, FarBp = f, Types = (string)r[4] });
            }
            return o_;
        }

        /// <summary>Index of the window containing t (sorted, non-overlapping), or -1.</summary>
        public static int Inside(List<NewsWindow> ws, long t)
        {
            int lo = 0, hi = ws.Count;
            while (lo < hi) { int m = (lo + hi) / 2; if (ws[m].End <= t) lo = m + 1; else hi = m; }
            return lo < ws.Count && ws[lo].Start <= t ? lo : -1;
        }

        /// <summary>Any window starting in (afterMs, nowMs]? (a pending order that went live before it is cancelled).</summary>
        public static bool StartedBetween(List<NewsWindow> ws, long afterMs, long nowMs)
        {
            int lo = 0, hi = ws.Count;
            while (lo < hi) { int m = (lo + hi) / 2; if (ws[m].Start <= afterMs) lo = m + 1; else hi = m; }
            return lo < ws.Count && ws[lo].Start <= nowMs;
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Daily and overall loss limits by each firm's own formula (rulebook; DESIGN-CONSTRAINTS §3), in account money.
    public class LossLimits
    {
        public double DailyPct, MaxPct, Initial;
        public string DailyBase;        // balance | max_balance_equity | equity  (value at the reset)
        public string DailyPctOf;       // initial | base
        public string ResetZone;
        public int ResetH, ResetM, ResetWindowMin;
        public string MaxType;          // static

        public static LossLimits From(FirmConfig c, double initial)
        {
            var hm = c.Str("daily_reset_time").Split(':');
            var l = new LossLimits
            {
                DailyPct = c.Num("daily_loss_pct"), MaxPct = c.Num("max_loss_pct"), Initial = initial,
                DailyBase = c.Str("daily_base"), DailyPctOf = c.Str("daily_pct_of"), ResetZone = c.Str("daily_reset_tz"),
                ResetH = int.Parse(hm[0], Clock.Inv), ResetM = int.Parse(hm[1], Clock.Inv),
                ResetWindowMin = (int)c.Num("daily_reset_window_min", 0), MaxType = c.Str("max_loss_type")
            };
            if (l.DailyBase != "balance" && l.DailyBase != "max_balance_equity" && l.DailyBase != "equity") throw new FormatException("daily_base " + l.DailyBase);
            if (l.DailyPctOf != "initial" && l.DailyPctOf != "base") throw new FormatException("daily_pct_of " + l.DailyPctOf);
            if (l.MaxType != "static") throw new FormatException("max_loss_type " + l.MaxType + ": only static is built (the core six products)");
            return l;
        }

        /// <summary>The last daily reset at or before nowMs (firm's own zone and wall time, DST per date).</summary>
        public long LastResetAtOrBefore(long nowMs)
        {
            DateTime d = Clock.Local(nowMs, ResetZone).Date;
            for (int k = 0; k < 3; k++, d = d.AddDays(-1))
            {
                long r = Clock.LocalToMs(d, ResetH, ResetM, ResetZone);
                if (r <= nowMs) return r;
            }
            throw new InvalidOperationException("no reset found");
        }

        public bool InResetWindow(long nowMs)
        {
            long r = LastResetAtOrBefore(nowMs);
            return nowMs < r + ResetWindowMin * Clock.MIN;
        }

        /// <summary>The value the firm snapshots at the reset, from balance and equity at that moment.</summary>
        public double BaseOf(double balance, double equity)
        {
            if (DailyBase == "balance") return balance;
            if (DailyBase == "equity") return equity;
            return Math.Max(balance, equity);
        }

        public double DailyLimitMoney(double dayBase) { return (DailyPctOf == "initial" ? Initial : dayBase) * DailyPct / 100.0; }
        public double DailyFloor(double dayBase) { return dayBase - DailyLimitMoney(dayBase); }
        public double MaxFloor() { return Initial * (1.0 - MaxPct / 100.0); }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Entry and flatten guards (CFD plan D1.3-D1.5, §0.1; DESIGN-CONSTRAINTS §3-4, §8). All money in the account currency.
    public class GuardSettings
    {
        public double EntryRoomOfDaily = 0.50;      // no entries unless worst-case room after the trade >= (1 - this) of the daily limit
        public double FlattenAtOfDaily = 0.80;      // flatten everything when the day's loss reaches this share of the daily limit
        public double OpenRiskCapOfDaily = 0.60;    // total open risk <= this share of the daily limit
        public double MaxHalfRiskTrades = 3, MaxStopTrades = 1;   // D1.5
        public double MaxFlattenRoomOfDaily = double.NaN;         // [P] flatten when room to the max floor <= this share of the daily limit
        public double OpenRiskCapPctInitial = double.NaN;         // firm cap on all open risk (Fintokei 3%)
        public double OpenRiskCapPctBalance = double.NaN;         // Aqua funded 0.75% (WaveStop)
        public double IdeaRiskCapPctInitial = double.NaN;         // Instant Funding funded 1.5%, Fintokei 3%
        public double FloatFlattenPctBalance = double.NaN;        // [P] Aqua funded: flatten before the -1% WaveStop strike
        public double MarginCap = double.NaN;                     // (used + new margin) / equity
        public double SlipBuffer = 0.10;                          // [P] risk caps keep this share free for stop slippage

        public static GuardSettings From(FirmConfig c)
        {
            return new GuardSettings
            {
                EntryRoomOfDaily = c.Num("guard_entry_at_of_daily"), FlattenAtOfDaily = c.Num("guard_flatten_at_of_daily"),
                OpenRiskCapOfDaily = c.Num("open_risk_cap_of_daily"), MaxHalfRiskTrades = c.Num("maxloss_half_risk_trades"),
                MaxStopTrades = c.Num("maxloss_stop_trades"), MaxFlattenRoomOfDaily = c.Num("maxloss_flatten_room_of_daily", double.NaN),
                OpenRiskCapPctInitial = c.Num("open_risk_cap_pct_initial", double.NaN),
                OpenRiskCapPctBalance = c.Num("open_risk_cap_pct_balance", double.NaN),
                IdeaRiskCapPctInitial = c.Num("idea_risk_cap_pct_initial", double.NaN),
                FloatFlattenPctBalance = c.Num("float_flatten_pct_balance", double.NaN),
                MarginCap = c.Num("margin_cap", double.NaN), SlipBuffer = c.Num("risk_cap_slip_buffer", 0.10)
            };
        }
    }

    public class AccountView
    {
        public double Initial, Balance, Equity, Margin;
        public double DayBase, DayLimit, DayFloor, MaxFloor;
        public double OpenRisk;           // sum over open positions of the loss from the current price to the stop (+ closing costs)
        public double OpenRiskSameIdea;   // the same, positions on this symbol and direction (Instant Funding "trade idea")
        public double FloatingPnl;        // Account.UnrealizedNetProfit
    }

    public class Decision
    {
        public bool Ok;
        public double Scale = 1.0;        // 0.5 near the max-loss floor (D1.5)
        public string Reason = "";
        public static Decision No(string why) { return new Decision { Ok = false, Reason = why }; }
    }

    public static class Guards
    {
        private const double Eps = 1e-6;      // money; thresholds exactly at a limit count as reached (0.2 x 5,000 is 999.99... in doubles)

        /// <summary>May a new trade with planned risk (money) be opened? Checks, in order: daily guard (D1.3), open-risk caps (D1.4,
        /// firm caps), max-loss distance (D1.5), trade-idea cap, margin. The caller sizes with Scale.</summary>
        public static Decision Entry(GuardSettings g, AccountView a, double fullRisk, double newMargin)
        {
            double worst = a.Equity - a.OpenRisk;                 // equity if every open stop is hit now
            // D1.5 first: it may halve the risk the later checks see
            double scale = 1.0;
            double maxRoom = worst - a.MaxFloor;
            if (maxRoom < g.MaxStopTrades * fullRisk) return Decision.No(string.Format(Clock.Inv, "maxloss_near: room {0:F2} < {1} x risk {2:F2}", maxRoom, g.MaxStopTrades, fullRisk));
            if (maxRoom < g.MaxHalfRiskTrades * fullRisk) scale = 0.5;
            double risk = fullRisk * scale;
            double dayRoomAfter = worst - risk - a.DayFloor;
            if (dayRoomAfter < (1.0 - g.EntryRoomOfDaily) * a.DayLimit - Eps)
                return Decision.No(string.Format(Clock.Inv, "daily_guard: room after {0:F2} < {1:P0} of limit {2:F2}", dayRoomAfter, 1.0 - g.EntryRoomOfDaily, a.DayLimit));
            if (a.OpenRisk + risk > g.OpenRiskCapOfDaily * a.DayLimit)
                return Decision.No(string.Format(Clock.Inv, "open_risk_cap: {0:F2} > {1:P0} of limit", a.OpenRisk + risk, g.OpenRiskCapOfDaily));
            if (!double.IsNaN(g.OpenRiskCapPctInitial) && a.OpenRisk + risk > (1 - g.SlipBuffer) * g.OpenRiskCapPctInitial / 100 * a.Initial)
                return Decision.No("firm_open_risk_cap_initial");
            if (!double.IsNaN(g.OpenRiskCapPctBalance) && a.OpenRisk + risk > (1 - g.SlipBuffer) * g.OpenRiskCapPctBalance / 100 * a.Balance)
                return Decision.No("firm_open_risk_cap_balance");
            if (!double.IsNaN(g.IdeaRiskCapPctInitial) && a.OpenRiskSameIdea + risk > (1 - g.SlipBuffer) * g.IdeaRiskCapPctInitial / 100 * a.Initial)
                return Decision.No("firm_idea_risk_cap");
            if (!double.IsNaN(g.MarginCap) && a.Equity > 0 && (a.Margin + newMargin * scale) / a.Equity > g.MarginCap)
                return Decision.No(string.Format(Clock.Inv, "margin_cap: {0:P1} > {1:P0}", (a.Margin + newMargin * scale) / a.Equity, g.MarginCap));
            return new Decision { Ok = true, Scale = scale };
        }

        /// <summary>Flatten the whole account now? Returns the reason, or null.</summary>
        public static string Flatten(GuardSettings g, AccountView a)
        {
            double dayLoss = a.DayBase - a.Equity;         // the day's loss on the firm's base (floating included)
            if (a.Equity - a.DayFloor <= (1.0 - g.FlattenAtOfDaily) * a.DayLimit + Eps)
                return string.Format(Clock.Inv, "guard_daily: equity {0:F2}, floor {1:F2}, loss {2:F2} >= {3:P0} of limit {4:F2}", a.Equity, a.DayFloor, dayLoss, g.FlattenAtOfDaily, a.DayLimit);
            if (!double.IsNaN(g.MaxFlattenRoomOfDaily) && a.Equity - a.MaxFloor <= g.MaxFlattenRoomOfDaily * a.DayLimit)
                return string.Format(Clock.Inv, "guard_max: equity {0:F2}, max floor {1:F2}", a.Equity, a.MaxFloor);
            if (!double.IsNaN(g.FloatFlattenPctBalance) && a.FloatingPnl <= -g.FloatFlattenPctBalance / 100 * a.Balance)
                return string.Format(Clock.Inv, "guard_float: floating {0:F2} <= -{1}% of balance", a.FloatingPnl, g.FloatFlattenPctBalance);
            return null;
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Sizing: volume from risk money, the stop distance and the symbol's pip value (DESIGN-CONSTRAINTS §8: from the symbol spec at run time).
    public static class Sizing
    {
        /// <summary>Units for a risk (money): loss at the stop = units x slDist/pipSize x pipValuePerUnit + units x commissionRtPerUnit.
        /// Rounded down to the step; 0 if below the minimum.</summary>
        public static double Units(double riskMoney, double slDist, double pipSize, double pipValuePerUnit, double commissionRtPerUnit,
                                   double minUnits, double stepUnits, double maxUnits)
        {
            if (!(riskMoney > 0) || !(slDist > 0) || !(pipValuePerUnit > 0)) return 0;
            double perUnit = slDist / pipSize * pipValuePerUnit + Math.Max(0, commissionRtPerUnit);
            double u = riskMoney / perUnit;
            if (maxUnits > 0 && u > maxUnits) u = maxUnits;
            u = Math.Floor(u / stepUnits + 1e-9) * stepUnits;
            return u + 1e-9 < minUnits ? 0 : u;
        }

        /// <summary>Risk-per-trade money (CFD plan §0.1 ladder, D1.2 sqrt(n) for n strategies on the account).</summary>
        public static double RiskMoney(double initial, double riskPct, int strategiesOnAccount)
        {
            return initial * riskPct / 100.0 / Math.Sqrt(Math.Max(1, strategiesOnAccount));
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Trade caps (engine/rules.py MAX_PER_DAY, MAX_ORDERS_60S; kernel ring): <= 10 fills per Amsterdam day, <= 2 order events in 60 s.
    public class Caps
    {
        public const int MaxPerDay = 10, MaxOrders60s = 2;
        private readonly List<long> _fills = new List<long>(), _events = new List<long>();

        public void AddFill(long ms) { _fills.Add(ms); }
        public void AddOrderEvent(long ms) { _events.Add(ms); if (_events.Count > 64) _events.RemoveAt(0); }

        public int FillsToday(long nowMs)
        {
            long d0 = ClassRules.AmsDayStart(nowMs);
            return _fills.Count(x => x >= d0 && x <= nowMs);
        }

        public bool DayCapHit(long nowMs) { return FillsToday(nowMs) >= MaxPerDay; }
        public bool RateCapHit(long nowMs) { return _events.Count(x => x > nowMs - 60000 && x <= nowMs) >= MaxOrders60s; }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Server-request budget (DESIGN-CONSTRAINTS §5 [P]: <= requests_per_day_account per account a day, shared by its cBot instances;
    // Amsterdam days). Entries and trail moves wait for it; exits never do.
    public class RequestBudget
    {
        public readonly double Budget;      // per instance; 0 = no budget
        public int Count;
        private long _day = -1;

        public RequestBudget(double perAccount, int instances) { Budget = perAccount > 0 ? perAccount / Math.Max(1, instances) : 0; }

        private void Roll(long nowMs) { long d = ClassRules.AmsDayStart(nowMs); if (d != _day) { _day = d; Count = 0; } }

        /// <summary>Room for one more request (entry: 3, room for its own exit and a modify).</summary>
        public bool Ok(long nowMs, bool entry) { Roll(nowMs); return Budget <= 0 || Count + (entry ? 3 : 1) <= Budget; }

        public void Add(long nowMs) { Roll(nowMs); Count++; }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // Order tag: the intent's facts carried in the order / position comment, so a restart rebuilds them from the account.
    public class OrderTag
    {
        public long BarMs, LiveMs, EndMs = -1, HoldMs;   // decision bar open, went live, pending order end (-1 = next bar close), time exit
        public double SlDist, TpDist = double.NaN, Risk;  // distances in price; planned risk money
        public const string Prefix = "ER1";

        public string Encode()
        {
            return string.Join("|", new[] { Prefix, "b" + BarMs.ToString(Clock.Inv), "l" + LiveMs.ToString(Clock.Inv), "e" + EndMs.ToString(Clock.Inv),
                "h" + HoldMs.ToString(Clock.Inv), "s" + SlDist.ToString("R", Clock.Inv), "t" + (double.IsNaN(TpDist) ? "" : TpDist.ToString("R", Clock.Inv)),
                "r" + Math.Round(Risk, 2).ToString(Clock.Inv) });
        }

        public static OrderTag Decode(string s)
        {
            if (string.IsNullOrEmpty(s) || !s.StartsWith(Prefix + "|")) return null;
            var t = new OrderTag();
            try
            {
                foreach (var f in s.Split('|').Skip(1))
                {
                    if (f.Length == 0) continue;
                    string v = f.Substring(1);
                    switch (f[0])
                    {
                        case 'b': t.BarMs = long.Parse(v, Clock.Inv); break;
                        case 'l': t.LiveMs = long.Parse(v, Clock.Inv); break;
                        case 'e': t.EndMs = long.Parse(v, Clock.Inv); break;
                        case 'h': t.HoldMs = long.Parse(v, Clock.Inv); break;
                        case 's': t.SlDist = double.Parse(v, Clock.Inv); break;
                        case 't': t.TpDist = v.Length == 0 ? double.NaN : double.Parse(v, Clock.Inv); break;
                        case 'r': t.Risk = double.Parse(v, Clock.Inv); break;
                    }
                }
            }
            catch (FormatException) { return null; }
            return t;
        }
    }

    // ------------------------------------------------------------------------------------------------------------------------
    // State file: small key=value file per cBot instance (day base records, news state per position). Written atomically.
    public class StateFile
    {
        public readonly string Path;
        public readonly Dictionary<string, string> Values = new Dictionary<string, string>();

        public StateFile(string path)
        {
            Path = path;
            if (System.IO.File.Exists(path))
                foreach (var line in System.IO.File.ReadAllLines(path))
                {
                    int eq = line.IndexOf('=');
                    if (eq > 0) Values[line.Substring(0, eq)] = line.Substring(eq + 1);
                }
        }

        public string Get(string k) { string v; return Values.TryGetValue(k, out v) ? v : null; }
        public void Set(string k, string v) { if (v == null) Values.Remove(k); else Values[k] = v; }

        public void Save()
        {
            string tmp = Path + ".tmp";
            System.IO.File.WriteAllLines(tmp, Values.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => kv.Key + "=" + kv.Value));
            if (System.IO.File.Exists(Path)) System.IO.File.Replace(tmp, Path, null);
            else System.IO.File.Move(tmp, Path);
        }

        /// <summary>The largest day base recorded for this reset by any instance on the account (files "<account>_*.state" in the folder).</summary>
        public static double MaxRecordedBase(string folder, string accountPrefix, long resetMs)
        {
            double best = double.NaN;
            if (!Directory.Exists(folder)) return best;
            foreach (var f in Directory.GetFiles(folder, accountPrefix + "_*.state"))
            {
                var s = new StateFile(f);
                string v = s.Get("daybase." + resetMs.ToString(Clock.Inv));
                double x;
                if (v != null && double.TryParse(v, NumberStyles.Float, Clock.Inv, out x) && (double.IsNaN(best) || x > best)) best = x;
            }
            return best;
        }
    }
}
