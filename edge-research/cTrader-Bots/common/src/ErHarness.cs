// Edge Research cBot side, cTrader harness: wires a strategy (IErStrategy) into the risk engine, firm config, news filter and restart
// recovery. Event order per tick = cTrader-Bots/CONVENTIONS.md (order engine; housekeeping; bar-close rules; new intent), the rules of
// engine/rules.py + kernel, plus the live-only firm rules. Spec and test list: cTrader-Bots/CBOT-SIDE.md.
// Composition, not inheritance: the finalist's Robot class owns one ErHarness and forwards OnStart / OnTick / OnBarClosed / OnTimer /
// OnStop to it (one algo type per assembly).
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using cAlgo.API;
using cAlgo.API.Internals;

namespace EdgeResearch.Common
{
    public enum ErRunMode { Normal, NoNewEntries, FlattenAndStop }

    public class ErSettings
    {
        public string Firm = "FTMO", Stage = "phase1", ResearchSymbol = "";
        public double InitialBalance = 100000;
        public string DayBaseOverride = "";               // "yyyy-MM-dd=amount": the firm's day-start figure for the reset on that date (firm's zone)
        public int StrategiesOnAccount = 1, InstancesOnAccount = 1;
        public string ConfigFolder = "~/cAlgo/EdgeResearch/firms", CalendarFile = "~/cAlgo/EdgeResearch/calendar/er-calendar.csv";
        public string StateFolder = "~/cAlgo/EdgeResearch/state", LogFolder = "~/cAlgo/EdgeResearch/logs";
        public string SeedDate = "2024-01-02", TradeFrom = "2024-01-02";
        public ErRunMode RunMode = ErRunMode.Normal;
        public double TestRestartEveryHours = 0;          // test cBot only: drop the in-memory state and recover, every N hours
        public string TestForeignAt = "";                 // test cBot only: "yyyy-MM-dd HH:mm" UTC, open an opposite position under another label
    }

    public class ErHarness
    {
        private readonly Robot _bot;
        private readonly IErStrategy _s;
        private readonly ErSettings _p;
        private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        private FirmConfig _cfg;
        private LossLimits _lim;
        private GuardSettings _g;
        private NewsCalendar _cal;
        private List<NewsWindow> _win = new List<NewsWindow>();
        private MarketClock _clock;
        private BreakBook _breaks;
        private Caps _caps = new Caps();
        private StateFile _state;
        private StreamWriter _log;
        private readonly BarSeries _bars = new BarSeries();
        private readonly Dictionary<string, int> _count = new Dictionary<string, int>();
        private readonly Dictionary<int, OrderTag> _tags = new Dictionary<int, OrderTag>();       // position id / order id -> tag
        private readonly Dictionary<int, string> _why = new Dictionary<int, string>();
        private readonly HashSet<string> _sources = new HashSet<string>();

        private string _label, _canon, _mode, _accountKey, _stateFolder;
        private char _maxClass = 'C';
        private long _seedMs, _fromMs, _tfMs, _startMs, _runningSinceMs;
        private double _tick, _p10;
        private bool _calendarOk, _stopping;
        private long _baseReset = -1;
        private double _dayBase = double.NaN;
        private bool _baseUncertain;
        private long _lastHourlyMs, _lastRestartMs;
        private bool _foreignDone;
        private double _farOverride = double.NaN;

        public ErHarness(Robot bot, IErStrategy strategy, ErSettings settings)
        {
            _bot = bot;
            _s = strategy;
            _p = settings;
        }

        // ============================================================ start ============================================================
        public void Start()
        {
            _startMs = Now();
            _runningSinceMs = _startMs;
            _label = "ER-" + _s.Id;
            _tick = _bot.Symbol.TickSize;
            _p10 = Math.Pow(10, _bot.Symbol.Digits);
            _seedMs = Clock.ParseDayUtc(_p.SeedDate);
            _fromMs = Clock.ParseDayUtc(_p.TradeFrom);
            _tfMs = (long)(TfSpan(_bot.Bars.TimeFrame).TotalMilliseconds);
            _bars.TfMs = _tfMs;
            _accountKey = Safe(_bot.IsBacktesting ? "bt" : (_bot.Account.BrokerName + "-" + _bot.Account.Number));
            _stateFolder = Expand(_p.StateFolder);
            if (_bot.IsBacktesting) _stateFolder = Path.Combine(_stateFolder, "backtest", Clock.FromMs(_startMs).ToString("yyyyMMdd-HHmmss", Inv) + "-" + Environment.TickCount);
            Directory.CreateDirectory(_stateFolder);
            string logDir = Expand(_p.LogFolder);
            Directory.CreateDirectory(logDir);
            string logPath = Path.Combine(logDir, string.Format(Inv, "{0}_{1}_{2}_{3}{4}.csv", _accountKey, Safe(_label), _bot.SymbolName,
                Clock.FromMs(_startMs).ToString("yyyyMMdd-HHmmss", Inv), _bot.IsBacktesting ? "_bt" : ""));
            _log = new StreamWriter(logPath, true) { AutoFlush = true };
            _log.WriteLine("utc_ms,utc,amsterdam,event,id,detail");
            Log("start", 0, string.Format(Inv, "label={0} symbol={1} tf={2} firm={3} stage={4} initial={5} strategies={6} instances={7} mode={8} backtest={9} log={10}",
                _label, _bot.SymbolName, _bot.Bars.TimeFrame, _p.Firm, _p.Stage, _p.InitialBalance, _p.StrategiesOnAccount, _p.InstancesOnAccount,
                _p.RunMode, _bot.IsBacktesting, logPath));

            // ---- firm config (refuse to run without one)
            string cfgPath = Path.Combine(Expand(_p.ConfigFolder), _p.Firm + ".cfg");
            try
            {
                _cfg = FirmConfig.Load(cfgPath, _p.Stage);
                _lim = LossLimits.From(_cfg, _p.InitialBalance);
                _g = GuardSettings.From(_cfg);
                _mode = _cfg.Str("news_mode");
                _maxClass = _cfg.Str("max_class", "C")[0];
                foreach (var x in _cfg.Str("news_sources", "").Split(';')) if (x.Trim().Length > 0) _sources.Add(x.Trim());
                if (!_bot.IsBacktesting && _cfg.Flag("test_only", false)) throw new FormatException("a test config runs in the backtester only");
                if (_cfg.Flag("test_only", false)) _farOverride = _cfg.Num("test_far_bp_override", double.NaN);
            }
            catch (Exception e) { Fatal("firm config " + cfgPath + ": " + e.Message); return; }
            Log("config", 0, string.Format(Inv, "file={0} sha256={1} product={2} news_mode={3} max_class={4} daily={5}% of {6} ({7}) reset {8} {9:00}:{10:00} +{11}min max={12}% {13} risk={14}% sources={15}",
                cfgPath, _cfg.Sha256, _cfg.Str("product", "?"), _mode, _maxClass, _lim.DailyPct, _lim.DailyPctOf, _lim.DailyBase, _lim.ResetZone, _lim.ResetH, _lim.ResetM,
                _lim.ResetWindowMin, _lim.MaxPct, _lim.MaxType, _cfg.Num("risk_pct"), string.Join(";", _sources)));

            // ---- symbol and class
            _canon = _p.ResearchSymbol.Trim().Length > 0 ? _p.ResearchSymbol.Trim() : (_cfg.Canonical(_bot.SymbolName));
            if (_canon == null) { Fatal("symbol " + _bot.SymbolName + " has no symbol.<CANONICAL> line in " + _p.Firm + ".cfg; set Research Symbol"); return; }
            if (_s.Class > _maxClass) { Fatal(string.Format(Inv, "strategy class {0} is not allowed at {1} {2} (max class {3}: {4})", _s.Class, _p.Firm, _p.Stage, _maxClass, _cfg.SourceOf("max_class"))); return; }
            if (Math.Abs(_tick * _p10 - 1) > 1e-9) Log("warn", 0, "tick size is not 10^-digits: grid rounding uses the tick size");

            // ---- news calendar (fail closed: no new entries without a valid, current calendar; M0 needs none)
            LoadCalendar();

            // ---- market hours (pre-close entry block, firm break flats)
            var sess = new List<MarketClock.Session>();
            foreach (var s in _bot.Symbol.MarketHours.Sessions)
                sess.Add(new MarketClock.Session { StartDay = s.StartDay, EndDay = s.EndDay, Start = s.StartTime, End = s.EndTime });
            var hol = new List<MarketClock.Closed>();
            try
            {
                foreach (var h in _bot.Symbol.MarketHours.Holidays)
                    hol.Add(new MarketClock.Closed { StartMs = Clock.Ms(h.StartTime), EndMs = Clock.Ms(h.EndTime), Recurring = h.IsRecurring });
            }
            catch (Exception e) { Log("warn", 0, "holidays not readable: " + e.Message); }
            string anchor = _cfg.Str("sessions_tz." + _canon, _cfg.Str("sessions_tz", SessionZones.Default(_canon)));
            Func<long, long> shift = _bot.IsBacktesting ? MarketClock.AnchoredShift(anchor, Clock.Ms(DateTime.UtcNow)) : null;
            _clock = new MarketClock(sess, hol, shift);
            Log("symbol", 0, string.Format(Inv, "name={0} canonical={1} lot_size={2} volume_min={3} volume_step={4} volume_max={5} pip_size={6} tick_size={7} digits={8}",
                _bot.SymbolName, _canon, _bot.Symbol.LotSize, _bot.Symbol.VolumeInUnitsMin, _bot.Symbol.VolumeInUnitsStep, _bot.Symbol.VolumeInUnitsMax,
                _bot.Symbol.PipSize, _bot.Symbol.TickSize, _bot.Symbol.Digits));
            Log("hours", 0, string.Format(Inv, "sessions={0} holidays={1} table shift at start {2:+0.#;-0.#;0} h ({3}, backtest only)", sess.Count, hol.Count,
                shift == null ? 0 : shift(_startMs) / 3600000.0, anchor));
            _breaks = new BreakBook(_cal, _canon, _clock);
            Log("breaks", 0, _breaks.RowCount > 0
                ? string.Format(Inv, "{0} break rows for {1} in the calendar, complete {2} -> {3}; the session table only outside", _breaks.RowCount, _canon, Clock.Iso(_cal.BreaksFromMs), Clock.Iso(_cal.BreaksToMs))
                : "no break rows for " + _canon + " in the calendar: breaks from the session table and holidays");
            if (sess.Count == 0 && _breaks.RowCount == 0) Log("warn", 0, "no trading sessions and no break rows: pre-close block, class B and firm break flats fall back to Friday 22:45");

            // ---- events
            _bot.Positions.Opened += OnOpened;
            _bot.Positions.Closed += OnClosed;
            _bot.PendingOrders.Filled += OnFilled;

            // ---- history for the indicators: every closed bar from the seed bar on
            int guard = 0;
            while (_bot.Bars.Count > 0 && Clock.Ms(_bot.Bars.OpenTimes[0]) > _seedMs && guard++ < 50 && _bot.Bars.LoadMoreHistory() > 0) { }
            for (int k = 0; k < _bot.Bars.Count - 1; k++) AddBar(k);
            Log("bars", 0, string.Format(Inv, "replayed {0} closed bars from the seed bar ({1})", _bars.Count, _p.SeedDate));

            Recover("start");
            if (_p.RunMode == ErRunMode.FlattenAndStop) { FlattenOwn("run_mode"); Log("stop", 0, "Run Mode FlattenAndStop: own positions closed, own orders cancelled"); _bot.Stop(); return; }
            _bot.Timer.Start(TimeSpan.FromSeconds(1));
        }

        private void LoadCalendar()
        {
            _calendarOk = false;
            string path = Expand(_p.CalendarFile);
            if (_mode == "M0" && !System.IO.File.Exists(path)) { _calendarOk = true; Log("calendar", 0, "M0: no calendar needed"); return; }
            try
            {
                _cal = NewsCalendar.Load(path);
                if (!double.IsNaN(_farOverride))
                    foreach (var ev in _cal.Events) _cal.FarBp[_canon + "|" + ev.TypeId] = _farOverride;     // TEST config only
                _win = _cal.Windows(_canon, _mode, _sources, _cfg.Flag("news_whole_talks", false));
                _calendarOk = _cal.Problems.Count == 0;
                Log("calendar", 0, string.Format(Inv, "file={0} sha256={1} commit={2} valid {3} -> {4} events={5} far_entries={6} windows({7},{8})={9} problems={10}",
                    path, _cal.Sha256, _cal.SourceCommit, _cal.ValidFromMs >= 0 ? Clock.Iso(_cal.ValidFromMs) : "?", _cal.ValidToMs >= 0 ? Clock.Iso(_cal.ValidToMs) : "?",
                    _cal.Events.Count, _cal.FarBp.Count, _canon, _mode, _win.Count, string.Join(" | ", _cal.Problems)));
            }
            catch (Exception e) { _cal = null; _win = new List<NewsWindow>(); Log("calendar_error", 0, path + ": " + e.Message); }
            if (!_calendarOk) Alarm("no valid calendar: no new entries (exits and stops keep working)");
        }

        private bool CalendarCurrent(long now)
        {
            if (_mode == "M0") return true;
            if (!_calendarOk || _cal == null) return false;
            return now >= _cal.ValidFromMs && now < _cal.ValidToMs;
        }

        // ============================================================ recovery ============================================================
        /// <summary>Rebuild every piece of state from the account (positions, orders, history) and the state files: never from memory.</summary>
        private void Recover(string why)
        {
            long now = Now();
            _tags.Clear();
            _caps = new Caps();
            string statePath = Path.Combine(_stateFolder, _accountKey + "_" + Safe(_label) + "_" + _bot.SymbolName + ".state");
            _state = new StateFile(statePath);

            var own = OwnPositions();
            var ownOrders = OwnOrders();
            foreach (var p in own)
            {
                var t = OrderTag.Decode(p.Comment) ?? OrderTag.Decode(_state.Get("tag." + p.Id));
                if (t == null)
                {
                    t = new OrderTag { LiveMs = Clock.Ms(p.EntryTime), BarMs = -1, SlDist = p.StopLoss.HasValue ? Math.Abs(p.EntryPrice - p.StopLoss.Value) : double.NaN };
                    Log("warn", p.Id, "position without a readable tag: live time = entry time, no time exit, target distance unknown");
                }
                _tags[p.Id] = t;
                if (!p.StopLoss.HasValue) Alarm("own position " + p.Id + " has no stop loss");
            }
            foreach (var o in ownOrders)
            {
                var t = OrderTag.Decode(o.Comment) ?? OrderTag.Decode(_state.Get("tag.o" + o.Id));
                if (t != null) _tags[-o.Id] = t;
            }
            if (own.Length + ownOrders.Length > 1) Alarm(string.Format(Inv, "{0} own positions and {1} own orders on {2}: one is the rule; new entries stay blocked until it is one", own.Length, ownOrders.Length, _bot.SymbolName));

            // caps: fills today, order events in the last 60 s (entries going live, exits), from the account
            var seen = new HashSet<int>();
            foreach (var h in _bot.History)
            {
                if (h.Label != _label || h.SymbolName != _bot.SymbolName) continue;
                if (seen.Add(h.PositionId)) _caps.AddFill(Clock.Ms(h.EntryTime));
                _caps.AddOrderEvent(Clock.Ms(h.ClosingTime));
            }
            foreach (var p in own) { _caps.AddFill(Clock.Ms(p.EntryTime)); _caps.AddOrderEvent(_tags[p.Id].LiveMs); }
            foreach (var o in ownOrders) { OrderTag t; if (_tags.TryGetValue(-o.Id, out t)) _caps.AddOrderEvent(t.LiveMs); }

            // day base
            _baseReset = -1;
            EnsureDayBase(now, true);
            Log("recovery", 0, string.Format(Inv, "{0}: own positions={1} orders={2} fills today={3} day base={4:F2} ({5}) state={6}",
                why, own.Length, ownOrders.Length, _caps.FillsToday(now), _dayBase, _baseUncertain ? "UNCERTAIN" : "ok", statePath));
        }

        /// <summary>The day base the firm snapshots at its reset. Order of trust: a value recorded at the reset by any instance on this
        /// account; a live observation (running since before the reset); the user's override; reconstruction from history.</summary>
        private void EnsureDayBase(long now, bool startup)
        {
            long r = _lim.LastResetAtOrBefore(now);
            double bal = _bot.Account.Balance, eq = _bot.Account.Equity;
            if (r == _baseReset)
            {
                if (_lim.InResetWindow(now) && _lim.DailyBase != "balance")
                {
                    double b = _lim.BaseOf(bal, eq);
                    if (b > _dayBase) { _dayBase = b; Record(r); }           // BrightFunded: rollover anywhere in the window -> keep the highest
                }
                return;
            }
            string how;
            double recorded = StateFile.MaxRecordedBase(_stateFolder, _accountKey, r);
            _baseUncertain = false;
            // reconstruct the balance at the reset: balance now minus everything closed since
            double closedSince = 0;
            bool acrossReset = false;
            foreach (var h in _bot.History)
            {
                long c = Clock.Ms(h.ClosingTime);
                if (c >= r) { closedSince += h.NetProfit; if (Clock.Ms(h.EntryTime) < r) acrossReset = true; }
            }
            foreach (var p in _bot.Positions) if (Clock.Ms(p.EntryTime) < r) acrossReset = true;
            double balAtReset = bal - closedSince;

            if (!startup && _runningSinceMs <= r)
            {
                _dayBase = _lim.DailyBase == "balance" ? balAtReset : _lim.DailyBase == "equity" ? eq : Math.Max(_lim.BaseOf(bal, eq), balAtReset);
                how = "observed";
            }
            else if (!double.IsNaN(recorded)) { _dayBase = recorded; how = "recorded"; }
            else if (_lim.DailyBase == "balance" || !acrossReset) { _dayBase = balAtReset; how = acrossReset ? "reconstructed (balance base)" : "reconstructed (flat at reset: equity = balance)"; }
            else if (OverrideFor(r) > 0) { _dayBase = OverrideFor(r); how = "override " + _p.DayBaseOverride; }
            else
            {
                _dayBase = Math.Max(balAtReset, Math.Max(bal, eq));
                _baseUncertain = true;
                how = "UNKNOWN: positions were open at the reset; no new entries until the next reset, or enter the firm's figure in Day Base Override";
                Alarm("day base unknown after " + (startup ? "a restart" : "a gap") + "; entries blocked for today");
            }
            _baseReset = r;
            Record(r);
            Log("daybase", 0, string.Format(Inv, "reset {0} ({1} {2:00}:{3:00}) base={4:F2} limit={5:F2} floor={6:F2} max_floor={7:F2} via {8}",
                Clock.Iso(r), _lim.ResetZone, _lim.ResetH, _lim.ResetM, _dayBase, _lim.DailyLimitMoney(_dayBase), _lim.DailyFloor(_dayBase), _lim.MaxFloor(), how));
        }

        /// <summary>The user's day-base figure if it names the date of this reset (in the firm's reset zone), else 0.</summary>
        private double OverrideFor(long r)
        {
            var kv = (_p.DayBaseOverride ?? "").Split('=');
            if (kv.Length != 2) return 0;
            double v;
            if (Clock.Local(r, _lim.ResetZone).ToString("yyyy-MM-dd", Inv) != kv[0].Trim() || !double.TryParse(kv[1].Trim(), NumberStyles.Float, Inv, out v)) return 0;
            return v;
        }

        private void Record(long r)
        {
            if (_baseUncertain) return;
            _state.Set("daybase." + r.ToString(Inv), _dayBase.ToString("R", Inv));
            foreach (var k in _state.Values.Keys.Where(k => k.StartsWith("daybase.")).ToList())
                if (long.Parse(k.Substring(8), Inv) < r - 5 * Clock.DAY) _state.Set(k, null);
            SaveState();
        }

        // ============================================================ per tick ============================================================
        public void OnTick() { if (_cfg != null) Housekeeping(false); }

        public void OnTimer()
        {
            if (_cfg == null) return;
            long now = Now();
            EnsureDayBase(now, false);
            CheckAccountGuards(now);
            if (now - _lastHourlyMs >= Clock.HOUR)
            {
                _lastHourlyMs = now;
                if (_mode != "M0" && _cal != null && _cal.ValidToMs - now < 2 * Clock.DAY)
                    Alarm(now >= _cal.ValidToMs ? "calendar expired: no new entries" : "calendar expires " + Clock.Iso(_cal.ValidToMs) + ": export a new one");
            }
        }

        public void OnBarClosed()
        {
            if (_cfg == null) return;
            Housekeeping(true);
            int k = _bot.Bars.Count - 1;          // in OnBarClosed, Bars excludes the new live bar: the last item is the bar that closed
            if (k < 0) return;
            int before = _bars.Count;
            AddBar(k);
            if (_bars.Count == before) return;
            int i = _bars.Count - 1;
            long closeMs = _bars.CloseMs(i);
            foreach (var p in OwnPositions())
                if (Clock.Ms(p.EntryTime) < closeMs) BarEvent(i, p);          // never on the tick the position was filled on, or later
            if (i >= _s.Warmup && _bars.OpenMs[i] >= _fromMs) TryEnter(i);
        }

        private void AddBar(int k)
        {
            long op = Clock.Ms(_bot.Bars.OpenTimes[k]);
            if (op < _seedMs) return;
            if (_bars.Add(op, _bot.Bars.OpenPrices[k], _bot.Bars.HighPrices[k], _bot.Bars.LowPrices[k], _bot.Bars.ClosePrices[k]))
                _s.OnBar(_bars, _bars.Count - 1);
        }

        public void OnStop()
        {
            _stopping = true;
            if (_log == null) return;
            Log("summary", 0, string.Join(" ", _count.OrderBy(x => x.Key, StringComparer.Ordinal).Select(x => x.Key + "=" + x.Value)) +
                " open_at_end=" + OwnPositions().Length);
            _log.Flush();
        }

        /// <summary>Account guards first (they beat news and hold rules), then the rules of CONVENTIONS step 2 for own positions and orders.</summary>
        private void Housekeeping(bool barClose)
        {
            long now = Now();
            TestHooks(now);
            EnsureDayBase(now, false);
            CheckAccountGuards(now);

            foreach (var p in OwnPositions())
            {
                OrderTag t = TagOf(p);
                long fill = Clock.Ms(p.EntryTime);
                // class flat time
                if (ClassFlatDue(t.LiveMs, now)) { Close(p, "flat", _flatWhy); continue; }
                // firm break flat (e.g. FTMO Standard funded, Instant Funding funded: nothing held through a break of >= the gap)
                if (FirmBreakDue(now)) { Close(p, "firm_break"); continue; }
                // news windows
                if (NewsPosition(p, t, now)) continue;
                // time exit (waits for a window's end)
                if (t.HoldMs > 0 && now >= fill + t.HoldMs)
                {
                    if (InWindow(p)) Defer(p, "time");
                    else Close(p, "time");
                }
            }
            foreach (var o in OwnOrders())
            {
                OrderTag t;
                if (!_tags.TryGetValue(-o.Id, out t)) t = new OrderTag { LiveMs = now, EndMs = -1 };
                if (ClassFlatDue(t.LiveMs, now)) { Cancel(o, "cancelled_flat"); continue; }
                long ns = ClassRules.LastNightStart(now);
                bool block = (ns > t.LiveMs && ns <= now) || NewsCalendar.StartedBetween(_win, t.LiveMs, now) ||
                             (_breaks.PreCloseBlockStart(now, 2 * Clock.HOUR) > t.LiveMs) || FirmBreakDue(now);
                if (block) { Cancel(o, "cancelled_block"); continue; }
                if (t.EndMs > 0 ? now >= t.EndMs : barClose) Cancel(o, "expired");
            }
        }

        // ============================================================ news ============================================================
        private bool InWindow(Position p) { return _state.Get("win." + p.Id) != null; }

        private void Defer(Position p, string kind)
        {
            if (_state.Get("defer." + p.Id) != null) return;          // the first deferred exit wins (kernel)
            _state.Set("defer." + p.Id, kind);
            SaveState();
            Count("news_deferred_" + kind);
            Log("news_defer", p.Id, kind + " exit waits for the window's end");
        }

        /// <summary>Window start / end for one own position (kernel: flatten unless far-stop; hold without target; target back or close
        /// after). Returns true if the position was closed.</summary>
        private bool NewsPosition(Position p, OrderTag t, long now)
        {
            string ws = _state.Get("win." + p.Id);
            bool buy = p.TradeType == TradeType.Buy;
            double px = buy ? _bot.Symbol.Bid : _bot.Symbol.Ask;
            if (ws != null)
            {
                var parts = ws.Split(';');
                long end = long.Parse(parts[1], Inv);
                if (now < end) return false;
                // window over: past the saved target -> close; otherwise the target goes back; then a deferred exit
                string tps = _state.Get("tp." + p.Id);
                double tp = tps != null && tps.Length > 0 ? double.Parse(tps, Inv) : double.NaN;
                _state.Set("win." + p.Id, null);
                _state.Set("tp." + p.Id, null);
                string deferred = _state.Get("defer." + p.Id);
                _state.Set("defer." + p.Id, null);
                _state.Set("done." + p.Id, parts[0]);
                SaveState();
                if (!double.IsNaN(tp))
                {
                    if (buy ? px >= tp : px <= tp) { Count("news_target"); Close(p, "news_target"); return true; }
                    var r = Modify(p, p.StopLoss, tp);
                    Log("news_restore", p.Id, string.Format(Inv, "target {0} back ({1})", R(tp), r ? "ok" : "FAILED"));
                }
                if (deferred != null) { Close(p, deferred); return true; }
                // and, as the kernel, a next window starting on this same tick is handled now
            }
            int w = NewsCalendar.Inside(_win, now);
            if (w < 0) return false;
            var win = _win[w];
            if (_state.Get("done." + p.Id) == win.Start.ToString(Inv)) return false;     // this window was handled already
            bool exempt = win.Kind == 2;
            if (win.Kind == 1)
            {
                double far = win.FarBp / 1e4 * px;
                double sl = p.StopLoss.HasValue ? p.StopLoss.Value : double.NaN;
                if (!double.IsNaN(far) && !double.IsNaN(sl) && (buy ? px - sl > far : sl - px > far))
                {
                    exempt = true;
                    Count("far_stop_used");
                    Log("news_far", p.Id, string.Format(Inv, "{0}: stop {1} is {2:F1} bp away > far {3:F1} bp: held", win.Types, R(sl), Math.Abs(px - sl) / px * 1e4, win.FarBp));
                }
            }
            if (!exempt) { Count("news_flattened"); Close(p, "news_flat", win.Types); return true; }
            if (win.Kind == 2) Count("news_held");
            double savedTp = p.TakeProfit.HasValue ? p.TakeProfit.Value : double.NaN;
            if (p.TakeProfit.HasValue && !Modify(p, p.StopLoss, null)) { Log("error", p.Id, "target removal failed; retry next tick"); return false; }
            _state.Set("win." + p.Id, win.Start.ToString(Inv) + ";" + win.End.ToString(Inv));
            _state.Set("tp." + p.Id, double.IsNaN(savedTp) ? "" : savedTp.ToString("R", Inv));
            SaveState();
            Log("news_hold", p.Id, string.Format(Inv, "{0} [{1} -> {2}] kind={3}: target {4} removed, stop kept, trail paused", win.Types,
                Clock.Iso(win.Start), Clock.Iso(win.End), win.Kind, R(savedTp)));
            return false;
        }

        // ============================================================ bar-close rules ============================================================
        private void BarEvent(int i, Position p)
        {
            bool buy = p.TradeType == TradeType.Buy;
            bool inWin = InWindow(p);
            double cand = buy ? _s.TrailLong(_bars, i) : _s.TrailShort(_bars, i);
            if (!inWin && !double.IsNaN(cand) && Trail(p, Rt(cand))) return;
            if (buy ? _s.ExitLong(_bars, i) : _s.ExitShort(_bars, i))
            {
                if (inWin) Defer(p, "signal");
                else Close(p, "signal");
            }
        }

        private bool Trail(Position p, double cand)   // tighten only, by more than half a tick; already beaten -> close now
        {
            if (!p.StopLoss.HasValue) return false;
            double cur = p.StopLoss.Value;
            bool buy = p.TradeType == TradeType.Buy;
            if (buy ? !(cand > cur + _tick / 2) : !(cand < cur - _tick / 2)) return false;
            if (buy ? _bot.Symbol.Bid <= cand : _bot.Symbol.Ask >= cand) { Close(p, "trail"); return true; }
            if (!RequestOk(false)) { Count("trail_skipped_budget"); return false; }
            if (!Modify(p, cand, p.TakeProfit)) Log("error", p.Id, "trail modify failed");
            else Log("trail", p.Id, string.Format(Inv, "stop {0} -> {1}", R(cur), R(cand)));
            return false;
        }

        // ============================================================ entries ============================================================
        private void TryEnter(int i)
        {
            var it = _s.Decide(_bars, i);
            if (it == null || it.Side == 0) return;
            long now = Now();
            Count("intents");
            // ---- the engine's checks, in the kernel's order
            if (OwnPositions().Length > 0 || OwnOrders().Length > 0) { Refuse("dropped_busy", i); return; }
            if (!(it.SlDist > 0)) { Refuse("refused_no_stop", i); return; }
            if (BlockedAt(now)) { Refuse("blocked_entry", i); return; }
            if (_caps.DayCapHit(now)) { Refuse("dropped_day_cap", i); return; }
            if (_caps.RateCapHit(now)) { Refuse("dropped_order_rate", i); return; }
            bool buy = it.Side > 0;
            double price = Rt(it.Price);
            if (it.OType != OType.Market)
            {
                bool crossed = it.OType == OType.Stop ? (buy ? _bot.Symbol.Ask >= price : _bot.Symbol.Bid <= price)
                                                     : (buy ? _bot.Symbol.Ask <= price : _bot.Symbol.Bid >= price);
                if (crossed) { Refuse("refused_crossed", i); return; }
            }
            // ---- a stop cTrader can set: beyond the spread and the symbol's minimum distance (2026-11-13: at the Sunday open a 1.7-pip
            //      stop sat inside a wider spread; cTrader opened the position and dropped the stop). Live-only refusal.
            double spread = _bot.Symbol.Ask - _bot.Symbol.Bid, minStop = MinStopDistance();
            if (!(it.SlDist > spread + minStop + _tick))
            {
                Refuse("stop_inside_spread", i, string.Format(Inv, "stop distance {0} <= spread {1} + minimum {2} + 1 tick", R(it.SlDist), R(spread), R(minStop)));
                return;
            }
            // ---- live-only checks (logged with their reason; the research result never saw them)
            if (_p.RunMode != ErRunMode.Normal) { Refuse("run_mode_" + _p.RunMode, i); return; }
            if (!CalendarCurrent(now)) { Refuse("no_calendar", i); return; }
            if (_baseUncertain) { Refuse("daybase_unknown", i); return; }
            if (FirmBreakDue(now)) { Refuse("firm_break", i); return; }
            string hb = HedgeOrBloc(it.Side);
            if (hb != null) { Refuse(hb.StartsWith("hedge") ? "hedge_guard" : "bloc_guard", i, hb); return; }
            if (!RequestOk(true)) { Refuse("request_budget", i); return; }

            // ---- sizing and the risk engine
            double fullRisk = Sizing.RiskMoney(_p.InitialBalance, _cfg.Num("risk_pct"), _p.StrategiesOnAccount);
            var tt = buy ? TradeType.Buy : TradeType.Sell;
            double pv = PipValuePerUnit(_bot.Symbol);
            double comm = CommissionRtPerUnit(_bot.Symbol, buy ? _bot.Symbol.Ask : _bot.Symbol.Bid, pv);
            double maxUnits = MaxUnitsForTrade();
            double units = Sizing.Units(fullRisk, it.SlDist, _bot.Symbol.PipSize, pv, comm, _bot.Symbol.VolumeInUnitsMin, _bot.Symbol.VolumeInUnitsStep, maxUnits);
            if (units <= 0) { Refuse("size_below_min", i, string.Format(Inv, "risk {0:F2} over stop {1} gives less than the minimum volume", fullRisk, R(it.SlDist))); return; }
            double uncapped = Sizing.Units(fullRisk, it.SlDist, _bot.Symbol.PipSize, pv, comm, _bot.Symbol.VolumeInUnitsMin, _bot.Symbol.VolumeInUnitsStep, _bot.Symbol.VolumeInUnitsMax);
            if (units < uncapped)
            {
                Count("lot_cap_trade");
                Log("lot_cap", 0, string.Format(Inv, "per-trade cap {0} units ({1} lots): risk {2:F2} would need {3} units", units, _bot.Symbol.VolumeInUnitsToQuantity(units), fullRisk, uncapped));
            }
            double newMargin = SafeMargin(tt, units);
            var view = View(_canon, it.Side);
            var d = Guards.Entry(_g, view, fullRisk, newMargin);
            if (!d.Ok) { Refuse(d.Reason.Split(':')[0], i, d.Reason); return; }
            if (d.Scale < 1)
            {
                units = Sizing.Units(fullRisk * d.Scale, it.SlDist, _bot.Symbol.PipSize, pv, comm, _bot.Symbol.VolumeInUnitsMin, _bot.Symbol.VolumeInUnitsStep, maxUnits);
                Count("half_risk");
                if (units <= 0) { Refuse("size_below_min", i, "half risk below the minimum volume"); return; }
            }
            units = ClassLotCap(units);
            if (units <= 0) { Refuse("class_lot_cap", i); return; }
            double risk = units * (it.SlDist / _bot.Symbol.PipSize * pv + comm);

            // ---- send
            var tag = new OrderTag { BarMs = _bars.OpenMs[i], LiveMs = now, EndMs = it.OType == OType.Market ? now : (it.ExpiryMs > 0 ? now + it.ExpiryMs : -1),
                                     HoldMs = it.HoldMs, SlDist = it.SlDist, TpDist = it.TpDist, Risk = risk };
            double? slPips = it.SlDist / _bot.Symbol.PipSize;
            double? tpPips = it.TpDist > 0 ? it.TpDist / _bot.Symbol.PipSize : (double?)null;
            string comment = tag.Encode();
            _caps.AddOrderEvent(now);
            Request();
            Count("sent");
            if (it.OType == OType.Market)
            {
                var r = _bot.ExecuteMarketOrder(tt, _bot.SymbolName, units, _label, slPips, tpPips, comment);
                if (!r.IsSuccessful) { Log("error", 0, "market order: " + r.Error); Count("errors"); return; }
                _tags[r.Position.Id] = tag;
                _state.Set("tag." + r.Position.Id, comment);
                SaveState();
                _caps.AddFill(Clock.Ms(r.Position.EntryTime));
                Log("entry", r.Position.Id, string.Format(Inv, "{0} market {1} units at {2} sl {3} tp {4} risk {5:F2} ({6:P2} of initial{7}) bar {8}",
                    tt, units, R(r.Position.EntryPrice), R(r.Position.StopLoss), R(r.Position.TakeProfit), risk, risk / _p.InitialBalance,
                    d.Scale < 1 ? ", half" : "", Clock.Iso(tag.BarMs)));
                if (!r.Position.StopLoss.HasValue) { Alarm("position " + r.Position.Id + " opened without a stop: closing it"); Close(r.Position, "no_stop"); }
                return;
            }
            TradeResult res = it.OType == OType.Stop
                ? _bot.PlaceStopOrder(tt, _bot.SymbolName, units, Send(price), _label, slPips, tpPips, ProtectionType.Relative, null, comment)
                : _bot.PlaceLimitOrder(tt, _bot.SymbolName, units, Send(price), _label, slPips, tpPips, ProtectionType.Relative, null, comment);
            if (!res.IsSuccessful) { Log("error", 0, "pending order: " + res.Error); Count("errors"); return; }
            _tags[-res.PendingOrder.Id] = tag;
            _state.Set("tag.o" + res.PendingOrder.Id, comment);
            SaveState();
            Log("order", res.PendingOrder.Id, string.Format(Inv, "{0} {1} {2} units at {3} risk {4:F2} end {5} bar {6}", tt, it.OType == OType.Stop ? "stop" : "limit",
                units, R(price), risk, tag.EndMs > 0 ? Clock.Iso(tag.EndMs) : "next bar close", Clock.Iso(tag.BarMs)));
        }

        private bool BlockedAt(long now)
        {
            if (ClassRules.NightBlockStart(now) >= 0) return true;
            if (_breaks.PreCloseBlockStart(now, 2 * Clock.HOUR) >= 0) return true;
            return NewsCalendar.Inside(_win, now) >= 0;
        }

        /// <summary>Class flat (engine/rules.py, DESIGN A8): 22:45 Amsterdam (A daily, B Fridays) or 5 min before the close of a market break
        /// of >= 2 h if earlier (A and B), from the symbol's sessions and holidays. Sets _flatWhy for the journal.</summary>
        private string _flatWhy = "";
        private bool ClassFlatDue(long liveMs, long now)
        {
            if (_s.Class == 'C') return false;
            var brs = _breaks.Between(liveMs - Clock.DAY, now + Clock.DAY);
            long f = ClassRules.FlatAt(_s.Class, liveMs, now, brs, _breaks.RowCount == 0 && _clock != null && !_clock.HasSessions);
            if (f < 0) return false;
            var b = brs.FirstOrDefault(x => ClassRules.BreakFlat(_s.Class, x.Close, x.Kind) == f);
            _flatWhy = b == null ? "22:45 Amsterdam" : "break: session close " + Clock.Iso(b.Close) + " (" + b.Kind + ", " + (_breaks.RowsCover(liveMs - Clock.DAY, now + Clock.DAY) ? "calendar" : "sessions") + "), flat " + Clock.Iso(f) + " (A8)";
            return true;
        }

        private bool FirmBreakDue(long now)
        {
            if (!_cfg.Has("flat_before_break_gap_min")) return false;
            return _breaks.LeadDue(now, (long)(_cfg.Num("flat_before_break_gap_min") * Clock.MIN), (long)(_cfg.Num("flat_before_break_lead_min") * Clock.MIN));
        }

        /// <summary>CROSS-FIRM-HEDGING R2 (no two directions on one symbol in one account) and R1 inside this account (one direction per bloc).</summary>
        private string HedgeOrBloc(int side)
        {
            bool bloc = _cfg.Flag("bloc_guard", true);
            var mine = Symbols.Blocs(_canon);
            foreach (var p in _bot.Positions)
            {
                int ps = p.TradeType == TradeType.Buy ? 1 : -1;
                string pc = _cfg.Canonical(p.SymbolName) ?? p.SymbolName;
                if (pc == _canon && ps != side) return "hedge: " + p.SymbolName + " " + p.TradeType + " open (" + p.Label + ")";
                if (!bloc) continue;
                foreach (var b in Symbols.Blocs(pc))
                    foreach (var m in mine)
                        if (b.Key == m.Key && b.Value * ps != m.Value * side) return "bloc " + b.Key + ": " + p.SymbolName + " " + p.TradeType + " open (" + p.Label + ")";
            }
            return null;
        }

        private double MaxUnitsForTrade()
        {
            double lots = _cfg.Num("max_lots_trade." + Symbols.AssetClass(_canon), double.NaN);
            if (_cfg.Has("max_lots_trade_symbol." + _canon)) lots = _cfg.Num("max_lots_trade_symbol." + _canon);
            if (_cfg.Has("max_lots_trade")) lots = double.IsNaN(lots) ? _cfg.Num("max_lots_trade") : Math.Min(lots, _cfg.Num("max_lots_trade"));
            double u = double.IsNaN(lots) ? _bot.Symbol.VolumeInUnitsMax : _bot.Symbol.QuantityToVolumeInUnits(lots);
            return Math.Min(u, _bot.Symbol.VolumeInUnitsMax);
        }

        /// <summary>Instant Funding: total lots per asset class over all open positions, by account size.</summary>
        private double ClassLotCap(double units)
        {
            string cls = Symbols.AssetClass(_canon);
            double cap = _cfg.BySize("class_lot_cap." + (cls == "oil" ? "metal" : cls), _p.InitialBalance);
            if (double.IsNaN(cap)) return units;
            double open = 0;
            foreach (var p in _bot.Positions)
            {
                string pc = _cfg.Canonical(p.SymbolName) ?? p.SymbolName;
                string k = Symbols.AssetClass(pc);
                if ((k == "oil" ? "metal" : k) != (cls == "oil" ? "metal" : cls)) continue;
                var sy = _bot.Symbols.GetSymbol(p.SymbolName);
                open += sy != null ? sy.VolumeInUnitsToQuantity(p.VolumeInUnits) : 0;
            }
            double room = cap - open;
            double lots = _bot.Symbol.VolumeInUnitsToQuantity(units);
            if (lots <= room) return units;
            double u = _bot.Symbol.NormalizeVolumeInUnits(_bot.Symbol.QuantityToVolumeInUnits(Math.Max(0, room)), RoundingMode.Down);
            Log("lot_cap", 0, string.Format(Inv, "{0} class cap {1} lots, open {2}: {3} -> {4} units", cls, cap, open, units, u));
            return u >= _bot.Symbol.VolumeInUnitsMin ? u : 0;
        }

        /// <summary>The symbol's minimum stop distance in price units (0 if unknown).</summary>
        private double MinStopDistance()
        {
            try
            {
                double m = _bot.Symbol.MinStopLossDistance;
                if (!(m > 0)) return 0;
                return _bot.Symbol.MinDistanceType == SymbolMinDistanceType.Pips ? m * _bot.Symbol.PipSize : m / 100.0 * _bot.Symbol.Bid;
            }
            catch (Exception) { return 0; }
        }

        private double SafeMargin(TradeType tt, double units)
        {
            try { return _bot.Symbol.GetEstimatedMargin(tt, units); }
            catch (Exception) { return 0; }
        }

        /// <summary>Estimated round-trip commission per unit, in the account currency (from the symbol's commission settings).</summary>
        /// <summary>Account-currency value of one pip for one unit, at today's conversion rate (Symbol.PipValue is frozen at the cBot's
        /// start, so a cross pair running for weeks would be sized on a stale rate). Falls back to Symbol.PipValue.</summary>
        private double PipValuePerUnit(Symbol sy)
        {
            try
            {
                if (sy.QuoteAsset.Name == _bot.Account.Asset.Name) return sy.PipSize;
                double v = sy.QuoteAsset.Convert(_bot.Account.Asset, sy.PipSize);
                if (v > 0 && !double.IsInfinity(v)) return v;
            }
            catch (Exception) { }
            if (!_pvWarned) { _pvWarned = true; Log("warn", 0, "live pip-value conversion unavailable for " + sy.Name + ": using Symbol.PipValue (fixed at start)"); }
            return sy.PipValue;
        }
        private bool _pvWarned;

        private double CommissionRtPerUnit(Symbol sy, double price, double pipValuePerUnit)
        {
            try
            {
                double c = sy.Commission, perPriceUnit = pipValuePerUnit / sy.PipSize, notional = price * perPriceUnit;
                switch (sy.CommissionType)
                {
                    case SymbolCommissionType.UsdPerOneLot: return 2 * c / sy.LotSize;
                    case SymbolCommissionType.UsdPerMillionUsdVolume: return 2 * c / 1e6 * notional;
                    case SymbolCommissionType.PercentageOfTradingVolume: return 2 * c / 100 * notional;
                    case SymbolCommissionType.QuoteCurrencyPerOneLot: return 2 * c / sy.LotSize * perPriceUnit;
                }
            }
            catch (Exception) { }
            return 0;
        }

        // ============================================================ account guards ============================================================
        private AccountView View(string canon, int side)
        {
            var v = new AccountView { Initial = _p.InitialBalance, Balance = _bot.Account.Balance, Equity = _bot.Account.Equity, Margin = _bot.Account.Margin,
                                      DayBase = _dayBase, DayLimit = _lim.DailyLimitMoney(_dayBase), DayFloor = _lim.DailyFloor(_dayBase), MaxFloor = _lim.MaxFloor(),
                                      FloatingPnl = _bot.Account.UnrealizedNetProfit };
            foreach (var p in _bot.Positions)
            {
                var sy = _bot.Symbols.GetSymbol(p.SymbolName);
                double r;
                if (!p.StopLoss.HasValue || sy == null) r = 1e12;          // no stop: unlimited risk, nothing new may open
                else
                {
                    bool buy = p.TradeType == TradeType.Buy;
                    double px = buy ? sy.Bid : sy.Ask;
                    r = Math.Max(0, (buy ? px - p.StopLoss.Value : p.StopLoss.Value - px)) / sy.PipSize * PipValuePerUnit(sy) * p.VolumeInUnits;
                }
                v.OpenRisk += r;
                string pc = _cfg.Canonical(p.SymbolName) ?? p.SymbolName;
                if (pc == canon && (p.TradeType == TradeType.Buy ? 1 : -1) == side) v.OpenRiskSameIdea += r;
            }
            return v;
        }

        private long _lastGuardMs;
        private void CheckAccountGuards(long now)
        {
            if (_lastGuardMs == now) return;
            _lastGuardMs = now;
            if (double.IsNaN(_dayBase)) return;
            string why = Guards.Flatten(_g, View(_canon, 0));
            if (why == null) return;
            if (_bot.Positions.Count == 0 && !_bot.PendingOrders.Any()) return;
            Count("guard_flatten");
            Log("guard", 0, why + ": closing every position and order on the account");
            foreach (var o in _bot.PendingOrders.ToList()) { Request(); _bot.CancelPendingOrder(o); }
            foreach (var p in _bot.Positions.ToList()) Close(p, why.Split(':')[0]);
        }

        // ============================================================ events ============================================================
        private void OnFilled(PendingOrderFilledEventArgs a)
        {
            if (a.PendingOrder.Label != _label || a.PendingOrder.SymbolName != _bot.SymbolName) return;
            OrderTag t;
            if (!_tags.TryGetValue(-a.PendingOrder.Id, out t)) t = OrderTag.Decode(a.PendingOrder.Comment) ?? new OrderTag { LiveMs = Now() };
            _tags.Remove(-a.PendingOrder.Id);
            _tags[a.Position.Id] = t;
            _state.Set("tag.o" + a.PendingOrder.Id, null);
            _state.Set("tag." + a.Position.Id, t.Encode());
            SaveState();
            _caps.AddFill(Clock.Ms(a.Position.EntryTime));
            Count("filled");
            Log("fill", a.Position.Id, string.Format(Inv, "order {0} filled at {1} sl {2} tp {3}", a.PendingOrder.Id, R(a.Position.EntryPrice), R(a.Position.StopLoss), R(a.Position.TakeProfit)));
            if (!a.Position.StopLoss.HasValue) { Alarm("filled position without stop: closing"); Close(a.Position, "no_stop"); }
        }

        private void OnOpened(PositionOpenedEventArgs a) { }

        private void OnClosed(PositionClosedEventArgs a)
        {
            var p = a.Position;
            if (p.Label != _label || p.SymbolName != _bot.SymbolName)
            {
                if (_why.ContainsKey(p.Id)) Log("closed_other", p.Id, p.Label + " " + p.SymbolName + " closed by this instance (" + _why[p.Id] + ")");
                else if (p.SymbolName == _bot.SymbolName) Log("closed_other", p.Id, p.Label + " " + p.SymbolName + " closed: " + a.Reason);
                return;
            }
            long now = Now();
            _caps.AddOrderEvent(now);
            string why;
            string kind = a.Reason == PositionCloseReason.StopLoss ? "StopLoss"
                        : a.Reason == PositionCloseReason.TakeProfit ? "TakeProfit"
                        : a.Reason == PositionCloseReason.Closed ? "Closed:" + (_why.TryGetValue(p.Id, out why) ? why : (_stopping ? "end" : "?"))
                        : a.Reason.ToString();
            OrderTag t = TagOf(p);
            double holdS = (now - Clock.Ms(p.EntryTime)) / 1000.0;
            Count("closed");
            Log("exit", p.Id, string.Format(Inv, "{0} {1} entry {2} exit_ms {3} net {4:F2} R {5} hold {6:F0}s", kind, p.TradeType, R(p.EntryPrice), now, p.NetProfit,
                t != null && t.Risk > 0 ? (p.NetProfit / t.Risk).ToString("F3", Inv) : "", holdS));
            if (_cfg != null && holdS < _cfg.Num("min_hold_s", 0)) { Count("warn_min_hold"); Log("warn_min_hold", p.Id, string.Format(Inv, "held {0:F0}s < {1}s ({2})", holdS, _cfg.Num("min_hold_s"), _cfg.SourceOf("min_hold_s"))); }
            foreach (var k in new[] { "tag.", "win.", "tp.", "defer.", "done." }) _state.Set(k + p.Id, null);
            SaveState();
        }

        // ============================================================ actions ============================================================
        private void Close(Position p, string why, string detail = "")
        {
            _why[p.Id] = why;
            Request();
            var r = _bot.ClosePosition(p);
            if (!r.IsSuccessful)
            {
                if (r.Error == ErrorCode.EntityNotFound) return;      // another instance closed it first (account guard)
                Log("error", p.Id, "close " + why + ": " + r.Error);
                Count("errors");
            }
            else if (detail.Length > 0) Log("close", p.Id, why + " " + detail);
        }

        private void Cancel(PendingOrder o, string why)
        {
            Request();
            var r = _bot.CancelPendingOrder(o);
            Count(why);
            Log("cancel", o.Id, why + (r.IsSuccessful ? "" : " FAILED " + r.Error));
            _tags.Remove(-o.Id);
            _state.Set("tag.o" + o.Id, null);
            SaveState();
        }

        private void FlattenOwn(string why)
        {
            foreach (var o in OwnOrders()) Cancel(o, "cancelled_" + why);
            foreach (var p in OwnPositions()) Close(p, why);
        }

        private bool Modify(Position p, double? sl, double? tp)
        {
            Request();
            var r = _bot.ModifyPosition(p, sl.HasValue ? Send(Rt(sl.Value)) : (double?)null, tp.HasValue ? Send(Rt(tp.Value)) : (double?)null, ProtectionType.Absolute);
            if (!r.IsSuccessful) { Log("error", p.Id, "modify: " + r.Error); Count("errors"); }
            return r.IsSuccessful;
        }

        private void Refuse(string why, int i, string detail = "")
        {
            Count(why);
            Log("refused", 0, why + " bar " + Clock.Iso(_bars.OpenMs[i]) + (detail.Length > 0 ? " " + detail : ""));
        }

        /// <summary>Server-request budget (DESIGN-CONSTRAINTS §5 [P]: <= requests_per_day_account per account, shared by the instances).
        /// Exits never wait for it.</summary>
        private RequestBudget _budget;
        private bool RequestOk(bool entry)
        {
            if (_budget == null) _budget = new RequestBudget(_cfg.Num("requests_per_day_account", 0), _p.InstancesOnAccount);
            return _budget.Ok(Now(), entry);
        }

        private void Request()
        {
            if (_budget == null) _budget = new RequestBudget(_cfg.Num("requests_per_day_account", 0), _p.InstancesOnAccount);
            _budget.Add(Now());
        }

        // ============================================================ test hooks (test cBot only) ============================================================
        private void TestHooks(long now)
        {
            if (_p.TestRestartEveryHours > 0)
            {
                if (_lastRestartMs == 0) _lastRestartMs = now;
                if (now - _lastRestartMs >= (long)(_p.TestRestartEveryHours * Clock.HOUR))
                {
                    _lastRestartMs = now;
                    Count("test_restart");
                    _runningSinceMs = now;              // as after a real restart: the day base must come from records or history
                    _caps = new Caps();
                    _tags.Clear();
                    _state = null;
                    Recover("simulated restart");
                }
            }
            if (!_foreignDone && _p.TestForeignAt.Length > 0)
            {
                long at = Clock.Ms(DateTime.ParseExact(_p.TestForeignAt.Trim(), "yyyy-MM-dd HH:mm", Inv, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal));
                if (now >= at)
                {
                    _foreignDone = true;
                    var own = OwnPositions();
                    var side = own.Length > 0 && own[0].TradeType == TradeType.Buy ? TradeType.Sell : TradeType.Buy;
                    var r = _bot.ExecuteMarketOrder(side, _bot.SymbolName, _bot.Symbol.VolumeInUnitsMin, "ER-FOREIGN", 50, null, "test foreign position");
                    Log("test_foreign", r.IsSuccessful ? r.Position.Id : 0, "opened " + side + " under label ER-FOREIGN: hedge / bloc guards must refuse the opposite side; account guards must close it too");
                }
            }
        }

        // ============================================================ helpers ============================================================
        private Position[] OwnPositions() { return _bot.Positions.FindAll(_label, _bot.SymbolName); }
        private PendingOrder[] OwnOrders() { return _bot.PendingOrders.Where(x => x.Label == _label && x.SymbolName == _bot.SymbolName).ToArray(); }

        private OrderTag TagOf(Position p)
        {
            OrderTag t;
            if (_tags.TryGetValue(p.Id, out t)) return t;
            t = OrderTag.Decode(p.Comment) ?? new OrderTag { LiveMs = Clock.Ms(p.EntryTime) };
            _tags[p.Id] = t;
            return t;
        }

        private void SaveState()
        {
            if (_state == null) return;
            try { _state.Save(); }
            catch (Exception e) { Log("error", 0, "state file: " + e.Message); }
        }

        private void Count(string k) { int v; _count.TryGetValue(k, out v); _count[k] = v + 1; }

        private void Log(string ev, long id, string detail)
        {
            long now = Now();
            string line = string.Join(",", new[] { now.ToString(Inv), Clock.Iso(now), Clock.Ams(now), ev, id.ToString(Inv), "\"" + detail.Replace("\"", "'") + "\"" });
            if (_log != null) _log.WriteLine(line);
            if (ev != "refused" && ev != "entry" && ev != "exit") _bot.Print("{0} {1} {2}", ev, id, detail);
        }

        private void Alarm(string msg) { Count("alarm"); Log("ALARM", 0, msg); }

        private void Fatal(string msg)
        {
            Log("FATAL", 0, msg + " -> the cBot stops");
            _cfg = null;
            _bot.Stop();
        }

        private long Now() { return Clock.Ms(_bot.Server.TimeInUtc); }
        private double Rt(double x) { return Math.Floor(x / _tick + 0.5) / _p10; }                  // onto the tick grid (Python Grid.rt)
        private double Send(double grid) { return (Math.Floor(grid / _tick + 0.5) + 0.25) / _p10; }  // +1/4 tick: cTrader truncation stores n (RULES A20)
        private static string R(double x) { return double.IsNaN(x) ? "" : x.ToString("R", Inv); }
        private static string R(double? x) { return x.HasValue ? R(x.Value) : ""; }
        private static string Safe(string s) { return new string(s.Select(ch => char.IsLetterOrDigit(ch) || ch == '-' ? ch : '_').ToArray()); }

        private static string Expand(string p) { return ErPaths.Expand(p); }

        private static TimeSpan TfSpan(TimeFrame tf)
        {
            if (tf == TimeFrame.Minute) return TimeSpan.FromMinutes(1);
            if (tf == TimeFrame.Minute5) return TimeSpan.FromMinutes(5);
            if (tf == TimeFrame.Minute15) return TimeSpan.FromMinutes(15);
            if (tf == TimeFrame.Minute30) return TimeSpan.FromMinutes(30);
            if (tf == TimeFrame.Hour) return TimeSpan.FromHours(1);
            if (tf == TimeFrame.Hour4) return TimeSpan.FromHours(4);
            if (tf == TimeFrame.Daily) return TimeSpan.FromDays(1);
            throw new ArgumentException("time frame " + tf + " not supported");
        }
    }
}
