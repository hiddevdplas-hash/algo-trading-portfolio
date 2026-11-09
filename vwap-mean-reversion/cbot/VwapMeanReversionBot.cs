// cTrader Automate cBot — translation of vwap_mean_reversion.pine
// Entries always use completed bars. Open-trade management (break-even, R trails
// and VWAP band trails) uses either completed bars (Pine parity) or ticks,
// selected by the "Trade Management Timing" parameter.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{
    public enum VwapMode { WeeklyVWAP, SessionVWAP, IntradayDualVWAP }
    public enum VwapSource { Open, High, Low, Close, HL2, HLC3, OHLC4, HLCC4 }
    public enum Direction { LongOnly, ShortOnly, Both }
    public enum BothBandAction { SkipBoth, PreferLong, PreferShort }
    public enum PenetrationMeasure { Wick, Close }
    public enum VwapBandTrailTrigger { WickTouch, CandleCloseBeyondBand }
    public enum TradeManagement { FixedTakeProfit, TrailHalfRStepOneRGap, TrailHalfRStepHalfRGap, TrailOneRStepOneRGap, TrailHalfRStepOneRGapSkipFirst, VwapBandTrail, DynamicVwapBandTrail }
    public enum ManagementTiming { BarClose, Tick }
    internal enum TrailVwapSource { None, Weekly, Session, ETH, RTH }
    public enum IntradaySignalSource { Both, ETHOnly, RTHOnly }
    public enum RestartPolicy { StopAndPreservePositions = 0, CloseOwnedPositions = 1, ResumePositions = 2 }
    public enum RiskModel { PercentOfBalance, PercentOfEquity, FixedCashRisk, FixedReferenceAccount }
    public enum ForceCloseOption { No, Yes }
    public enum NewsMode { Off, BlockEntries, BlockEntriesAndCloseTrades }

    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class VwapMeanReversionBot : Robot
    {
        // Group order and labels intentionally mirror the Pine settings panel.
        [Parameter("VWAP View Mode", Group = "👁️ VWAP VIEW", DefaultValue = VwapMode.IntradayDualVWAP)] public VwapMode Mode { get; set; }
        [Parameter("VWAP Source", Group = "👁️ VWAP VIEW", DefaultValue = VwapSource.HL2)] public VwapSource Source { get; set; }

        [Parameter("Trade Direction", Group = "⚙️ TRADE SETTINGS", DefaultValue = Direction.Both)] public Direction TradeDirection { get; set; }
        [Parameter("If Both Bands Are Touched", Group = "⚙️ TRADE SETTINGS", DefaultValue = BothBandAction.SkipBoth)] public BothBandAction BothAction { get; set; }
        // Yes: blocked candles still update the touch/pause state (no signal), so the first
        // candle after a block needs a fresh pause candle like any other signal.
        [Parameter("Track Touches During Blocked Candles", Group = "⚙️ TRADE SETTINGS", DefaultValue = false)] public bool TrackTouchesWhileBlocked { get; set; }
        [Parameter("cBot Label", Group = "⚙️ TRADE SETTINGS", DefaultValue = "VWAP_MR")] public string Label { get; set; }
        [Parameter("When Restarted With Open Positions", Group = "⚙️ TRADE SETTINGS", DefaultValue = RestartPolicy.ResumePositions)] public RestartPolicy RestartHandling { get; set; }
        [Parameter("Allow Hedge Trades", Group = "⚙️ TRADE SETTINGS", DefaultValue = false)] public bool AllowHedgeTrades { get; set; }
        [Parameter("Force Close Safety Net (Broker Hours)", Group = "⚙️ TRADE SETTINGS", DefaultValue = true)] public bool BrokerCloseSafetyNet { get; set; }

        [Parameter("Enable Maximum Signal-to-Entry Distance", Group = "🔍 ENTRY FILTERS", DefaultValue = false)] public bool EnableDistanceFilter { get; set; }
        [Parameter("Maximum Signal-to-Entry Distance (ATR)", Group = "🔍 ENTRY FILTERS", DefaultValue = 1.0, MinValue = 0.0)] public double MaxEntryDistanceAtr { get; set; }
        [Parameter("Enable Maximum Band Penetration", Group = "🔍 ENTRY FILTERS", DefaultValue = false)] public bool EnablePenetrationFilter { get; set; }
        [Parameter("Maximum Band Penetration (ATR)", Group = "🔍 ENTRY FILTERS", DefaultValue = 0.5, MinValue = 0.0)] public double MaxBandPenetrationAtr { get; set; }
        [Parameter("Band Penetration Measurement", Group = "🔍 ENTRY FILTERS", DefaultValue = PenetrationMeasure.Wick)] public PenetrationMeasure Penetration { get; set; }
        [Parameter("Enable ATR Percentile Filter", Group = "🔍 ENTRY FILTERS", DefaultValue = false)] public bool EnableAtrPercentile { get; set; }
        [Parameter("ATR Percentile ATR Length", Group = "🔍 ENTRY FILTERS", DefaultValue = 14, MinValue = 1)] public int PercentileAtrLength { get; set; }
        [Parameter("ATR Percentile Lookback", Group = "🔍 ENTRY FILTERS", DefaultValue = 100, MinValue = 1)] public int PercentileLookback { get; set; }
        [Parameter("Maximum ATR Percentile", Group = "🔍 ENTRY FILTERS", DefaultValue = 90.0, MinValue = 50.0, MaxValue = 100.0)] public double MaxAtrPercentile { get; set; }

        [Parameter("Stop ATR Multiplier", Group = "🎯 TRADE MANAGEMENT", DefaultValue = 1.0, MinValue = 0.1)] public double StopAtrMult { get; set; }
        [Parameter("ATR Length", Group = "🎯 TRADE MANAGEMENT", DefaultValue = 14, MinValue = 1)] public int AtrLength { get; set; }
        [Parameter("Trade Management", Group = "🎯 TRADE MANAGEMENT", DefaultValue = TradeManagement.FixedTakeProfit)] public TradeManagement Management { get; set; }
        [Parameter("VWAP Band Trail Trigger", Group = "🎯 TRADE MANAGEMENT", DefaultValue = VwapBandTrailTrigger.WickTouch)] public VwapBandTrailTrigger BandTrailTrigger { get; set; }
        [Parameter("VWAP Trail ATR Cushion", Group = "🎯 TRADE MANAGEMENT", DefaultValue = 0.0, MinValue = 0.0, Step = 0.05)] public double VwapTrailAtrCushion { get; set; }
        [Parameter("Take Profit (R)", Group = "🎯 TRADE MANAGEMENT", DefaultValue = 0.75, MinValue = 0.05)] public double TargetR { get; set; }
        [Parameter("Enable Break-Even for Fixed Take Profit", Group = "🎯 TRADE MANAGEMENT", DefaultValue = false)] public bool EnableFixedTpBreakEven { get; set; }
        [Parameter("Break-Even Trigger (R)", Group = "🎯 TRADE MANAGEMENT", DefaultValue = 0.5, MinValue = 0.05)] public double FixedTpBreakEvenTriggerR { get; set; }
        [Parameter("Trade Management Timing (Bar Close = Pine)", Group = "🎯 TRADE MANAGEMENT", DefaultValue = ManagementTiming.BarClose)] public ManagementTiming Timing { get; set; }

        [Parameter("Risk Model", Group = "💰 RISK SIZING", DefaultValue = RiskModel.PercentOfBalance)] public RiskModel SelectedRiskModel { get; set; }
        [Parameter("Risk Per Trade (%) — Percentage Models Only", Group = "💰 RISK SIZING", DefaultValue = 1.0, MinValue = 0.01, MaxValue = 100.0)] public double RiskPercent { get; set; }
        [Parameter("Fixed Cash Risk ($) — Fixed Cash Model Only", Group = "💰 RISK SIZING", DefaultValue = 250.0, MinValue = 0.01)] public double FixedCashRisk { get; set; }
        [Parameter("Reference Account Size ($) — Pine Comparison Only", Group = "💰 RISK SIZING", DefaultValue = 100000.0, MinValue = 1.0)] public double ReferenceAccountSize { get; set; }
        [Parameter("Maximum Cash Risk Cap ($, 0 = Disabled)", Group = "💰 RISK SIZING", DefaultValue = 0.0, MinValue = 0.0)] public double MaxCashRiskCap { get; set; }
        [Parameter("Enable Maximum Entry Spread Filter", Group = "💰 RISK SIZING", DefaultValue = true)] public bool EnableMaxEntrySpreadFilter { get; set; }
        [Parameter("Maximum Entry Spread (% of Initial Stop Distance)", Group = "💰 RISK SIZING", DefaultValue = 10.0, MinValue = 0.0, MaxValue = 100.0)] public double MaxEntrySpreadPercentOfStop { get; set; }

        [Parameter("Weekly VWAP Standard Deviations", Group = "🗓️ WEEKLY VWAP", DefaultValue = 3.0, MinValue = 0.5)] public double WeeklyBandMult { get; set; }
        [Parameter("Session VWAP Standard Deviations", Group = "📆 SESSION VWAP", DefaultValue = 3.0, MinValue = 0.5)] public double SessionBandMult { get; set; }
        [Parameter("ETH VWAP Standard Deviations", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = 3.0, MinValue = 0.5)] public double EthBandMult { get; set; }
        [Parameter("RTH VWAP Standard Deviations", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = 3.0, MinValue = 0.5)] public double RthBandMult { get; set; }
        [Parameter("Intraday Dual VWAP Signal Source", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = IntradaySignalSource.Both)] public IntradaySignalSource IntradaySource { get; set; }

        // Each schedule section ends with its daily and Monday-Friday block windows.
        [Parameter("Block First Hours", Group = "🗓️ WEEKLY VWAP", DefaultValue = 0, MinValue = 0, MaxValue = 24)] public int WeeklyFirstHours { get; set; }
        [Parameter("Block Last Hours", Group = "🗓️ WEEKLY VWAP", DefaultValue = 0, MinValue = 0, MaxValue = 24)] public int WeeklyLastHours { get; set; }
        [Parameter("Force Close Friday", Group = "🗓️ WEEKLY VWAP", DefaultValue = ForceCloseOption.No)] public ForceCloseOption WeeklyForceCloseFriday { get; set; }
        [Parameter("Block Daily Window", Group = "🗓️ WEEKLY VWAP", DefaultValue = false)] public bool WeeklyDailyWindowBlock { get; set; }
        [Parameter("Daily Block Window (New York time)", Group = "🗓️ WEEKLY VWAP", DefaultValue = "0000-0001")] public string WeeklyDailyWindow { get; set; }
        [Parameter("Block Monday", Group = "🗓️ WEEKLY VWAP", DefaultValue = false)] public bool WeeklyMondayBlock { get; set; }
        [Parameter("Monday Block Window (New York time)", Group = "🗓️ WEEKLY VWAP", DefaultValue = "0000-0001")] public string WeeklyMondayWindow { get; set; }
        [Parameter("Block Tuesday", Group = "🗓️ WEEKLY VWAP", DefaultValue = false)] public bool WeeklyTuesdayBlock { get; set; }
        [Parameter("Tuesday Block Window (New York time)", Group = "🗓️ WEEKLY VWAP", DefaultValue = "0000-0001")] public string WeeklyTuesdayWindow { get; set; }
        [Parameter("Block Wednesday", Group = "🗓️ WEEKLY VWAP", DefaultValue = false)] public bool WeeklyWednesdayBlock { get; set; }
        [Parameter("Wednesday Block Window (New York time)", Group = "🗓️ WEEKLY VWAP", DefaultValue = "0000-0001")] public string WeeklyWednesdayWindow { get; set; }
        [Parameter("Block Thursday", Group = "🗓️ WEEKLY VWAP", DefaultValue = false)] public bool WeeklyThursdayBlock { get; set; }
        [Parameter("Thursday Block Window (New York time)", Group = "🗓️ WEEKLY VWAP", DefaultValue = "0000-0001")] public string WeeklyThursdayWindow { get; set; }
        [Parameter("Block Friday", Group = "🗓️ WEEKLY VWAP", DefaultValue = false)] public bool WeeklyFridayBlock { get; set; }
        [Parameter("Friday Block Window (New York time)", Group = "🗓️ WEEKLY VWAP", DefaultValue = "0000-0001")] public string WeeklyFridayWindow { get; set; }

        [Parameter("Block First Minutes", Group = "📆 SESSION VWAP", DefaultValue = 0, MinValue = 0, MaxValue = 1380)] public int BlockSessionFirst { get; set; }
        [Parameter("Block Last Minutes", Group = "📆 SESSION VWAP", DefaultValue = 0, MinValue = 0, MaxValue = 1380)] public int BlockSessionLast { get; set; }
        [Parameter("Force Close at Session End", Group = "📆 SESSION VWAP", DefaultValue = ForceCloseOption.No)] public ForceCloseOption SessionForceClose { get; set; }
        // Weekend close for accounts that allow overnight but not weekend holding: with Force Close at Session End = No,
        // trades are held overnight and closed in the Friday session-close window (16:50 NY), like Weekly's Force Close Friday.
        [Parameter("Force Close Friday (Session)", Group = "📆 SESSION VWAP", DefaultValue = ForceCloseOption.No)] public ForceCloseOption SessionForceCloseFriday { get; set; }
        [Parameter("Block Daily Window (Session)", Group = "📆 SESSION VWAP", DefaultValue = false)] public bool SessionDailyWindowBlock { get; set; }
        [Parameter("Daily Block Window (Session, New York time)", Group = "📆 SESSION VWAP", DefaultValue = "0000-0001")] public string SessionDailyWindow { get; set; }
        [Parameter("Block Monday (Session)", Group = "📆 SESSION VWAP", DefaultValue = false)] public bool SessionMondayBlock { get; set; }
        [Parameter("Monday Block Window (Session, New York time)", Group = "📆 SESSION VWAP", DefaultValue = "0000-0001")] public string SessionMondayWindow { get; set; }
        [Parameter("Block Tuesday (Session)", Group = "📆 SESSION VWAP", DefaultValue = false)] public bool SessionTuesdayBlock { get; set; }
        [Parameter("Tuesday Block Window (Session, New York time)", Group = "📆 SESSION VWAP", DefaultValue = "0000-0001")] public string SessionTuesdayWindow { get; set; }
        [Parameter("Block Wednesday (Session)", Group = "📆 SESSION VWAP", DefaultValue = false)] public bool SessionWednesdayBlock { get; set; }
        [Parameter("Wednesday Block Window (Session, New York time)", Group = "📆 SESSION VWAP", DefaultValue = "0000-0001")] public string SessionWednesdayWindow { get; set; }
        [Parameter("Block Thursday (Session)", Group = "📆 SESSION VWAP", DefaultValue = false)] public bool SessionThursdayBlock { get; set; }
        [Parameter("Thursday Block Window (Session, New York time)", Group = "📆 SESSION VWAP", DefaultValue = "0000-0001")] public string SessionThursdayWindow { get; set; }
        [Parameter("Block Friday (Session)", Group = "📆 SESSION VWAP", DefaultValue = false)] public bool SessionFridayBlock { get; set; }
        [Parameter("Friday Block Window (Session, New York time)", Group = "📆 SESSION VWAP", DefaultValue = "0000-0001")] public string SessionFridayWindow { get; set; }

        [Parameter("Block First ETH Minutes", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = 0, MinValue = 0, MaxValue = 930)] public int BlockEthFirst { get; set; }
        [Parameter("Block Last ETH Minutes", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = 0, MinValue = 0, MaxValue = 930)] public int BlockEthLast { get; set; }
        [Parameter("Block First RTH Minutes", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = 0, MinValue = 0, MaxValue = 450)] public int BlockRthFirst { get; set; }
        [Parameter("Block Last RTH Minutes", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = 0, MinValue = 0, MaxValue = 450)] public int BlockRthLast { get; set; }
        [Parameter("Force Close at ETH Close", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool CloseAtEthEnd { get; set; }
        [Parameter("Force Close at RTH Close", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool CloseAtRthEnd { get; set; }
        // Weekend close (Friday session-close window, 16:50 NY) when ETH/RTH trades are otherwise held overnight.
        [Parameter("Force Close Friday (Intraday)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool IntradayForceCloseFriday { get; set; }
        [Parameter("Block Daily Window (Intraday)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool IntradayDailyWindowBlock { get; set; }
        [Parameter("Daily Block Window (Intraday, New York time)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = "0000-0001")] public string IntradayDailyWindow { get; set; }
        [Parameter("Block Monday (Intraday)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool IntradayMondayBlock { get; set; }
        [Parameter("Monday Block Window (Intraday, New York time)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = "0000-0001")] public string IntradayMondayWindow { get; set; }
        [Parameter("Block Tuesday (Intraday)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool IntradayTuesdayBlock { get; set; }
        [Parameter("Tuesday Block Window (Intraday, New York time)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = "0000-0001")] public string IntradayTuesdayWindow { get; set; }
        [Parameter("Block Wednesday (Intraday)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool IntradayWednesdayBlock { get; set; }
        [Parameter("Wednesday Block Window (Intraday, New York time)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = "0000-0001")] public string IntradayWednesdayWindow { get; set; }
        [Parameter("Block Thursday (Intraday)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool IntradayThursdayBlock { get; set; }
        [Parameter("Thursday Block Window (Intraday, New York time)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = "0000-0001")] public string IntradayThursdayWindow { get; set; }
        [Parameter("Block Friday (Intraday)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = false)] public bool IntradayFridayBlock { get; set; }
        [Parameter("Friday Block Window (Intraday, New York time)", Group = "📅 INTRADAY DUAL VWAP", DefaultValue = "0000-0001")] public string IntradayFridayWindow { get; set; }

        // Block entries: a candle that overlaps [release - before, release + after] is blocked like a block-window
        // candle (no signal; touches only tracked when Track Touches During Blocked Candles = Yes).
        // + Close trades: open trades are closed at market "Close Trades Minutes Before News" before the release,
        // and the entry block then starts at least that early. All times New York.
        [Parameter("News Filter", Group = "📰 NEWS FILTER", DefaultValue = NewsMode.Off)] public NewsMode NewsFilterMode { get; set; }
        [Parameter("USD: CPI (08:30 NY)", Group = "📰 NEWS FILTER", DefaultValue = true)] public bool NewsCpi { get; set; }
        [Parameter("USD: NFP (08:30 NY)", Group = "📰 NEWS FILTER", DefaultValue = true)] public bool NewsNfp { get; set; }
        [Parameter("USD: FOMC (14:00 NY)", Group = "📰 NEWS FILTER", DefaultValue = true)] public bool NewsFomc { get; set; }
        // Added 2026-10-14 (FTMO restricted-event list + BoJ): advance GDP and FOMC minutes for USD, and the central bank and
        // key data of every other currency in the symbol. News Currencies "Auto" derives them from the symbol (EURJPY → EUR, JPY;
        // DE40 → EUR; XTIUSD → OIL, USD); or give a list such as "USD,EUR". US events apply only when USD is involved, unless
        // "USD Events On Every Symbol" is on. Other currencies = exactly FTMO's restricted list + BoJ: EUR ECB rate · GBP BoE rate,
        // UK CPI · JPY BoJ · CAD BoC rate, CPI, jobs · AUD RBA rate, jobs, CPI, GDP · NZD RBNZ rate, jobs, CPI, GDP · CHF SNB rate ·
        // OIL EIA crude inventories (no euro-area CPI: FTMO does not restrict it).
        [Parameter("USD: Advance GDP + FOMC Minutes", Group = "📰 NEWS FILTER", DefaultValue = true)] public bool NewsUsdMore { get; set; }
        [Parameter("Other Currencies: FTMO List + BoJ", Group = "📰 NEWS FILTER", DefaultValue = true)] public bool NewsOtherCurrencies { get; set; }
        [Parameter("News Currencies (Auto = from symbol)", Group = "📰 NEWS FILTER", DefaultValue = "Auto")] public string NewsCurrencies { get; set; }
        [Parameter("USD Events On Every Symbol", Group = "📰 NEWS FILTER", DefaultValue = false)] public bool NewsUsdEverywhere { get; set; }
        [Parameter("No Entries: Minutes Before News", Group = "📰 NEWS FILTER", DefaultValue = 5, MinValue = 0, MaxValue = 600)] public int NewsMinutesBefore { get; set; }
        [Parameter("No Entries: Minutes After News", Group = "📰 NEWS FILTER", DefaultValue = 10, MinValue = 0, MaxValue = 600)] public int NewsMinutesAfter { get; set; }
        [Parameter("Close Trades Minutes Before News", Group = "📰 NEWS FILTER", DefaultValue = 5, MinValue = 0, MaxValue = 600)] public int NewsCloseMinutesBefore { get; set; }
        // Yes: band touches inside the news window still update the pause/re-arm state (they never signal), so the
        // first signal after the window needs a fresh pause candle. Fully independent of Track Touches During Blocked Candles
        // (that one covers session/day blocks only), so every combination is possible.
        [Parameter("Track Touches During News Block", Group = "📰 NEWS FILTER", DefaultValue = true)] public bool NewsTrackTouches { get; set; }

        [Parameter("Minimum Trades (Custom Fitness)", Group = "🧪 OPTIMISATION", DefaultValue = 100, MinValue = 1)] public int MinFitnessTrades { get; set; }

        private AverageTrueRange _atr;
        private AverageTrueRange _percentileAtr;
        private TimeZoneInfo _newYork;
        private NewsFilter.NewsSet _news;
        private string[] _newsCurrencies = new string[0];
        private DateTime _newsWarnedDay = DateTime.MinValue;
        private VwapState _weekly = new VwapState(), _daily = new VwapState(), _eth = new VwapState(), _rth = new VwapState();
        private bool _lowerArmed = true, _upperArmed = true;
        private DateTime _lastEthSession = DateTime.MinValue, _lastRthSession = DateTime.MinValue;
        private DateTime _lastTradingDate = DateTime.MinValue, _lastWeekStart = DateTime.MinValue;
        private readonly Dictionary<long, ManagedTrade> _managedTrades = new Dictionary<long, ManagedTrade>();
        private DateTime _lastExitTime = DateTime.MinValue;

        private string _positionLabel;
        private bool _ready;
        private bool _stateWritable, _persistenceFailed;
        private string _lastSavedState;
        private const string RecoveryKey = "Recovery State V3";
        private readonly HashSet<long> _pendingCloses = new HashSet<long>();
        private readonly Dictionary<long, DateTime> _lastCloseAttempt = new Dictionary<long, DateTime>();
        private readonly Dictionary<long, DateTime> _lastProtectionFailure = new Dictionary<long, DateTime>();

        protected override void OnStart()
        {
            _newYork = LoadNewYorkZone();
            string[] newsCurrencies = _newsCurrencies = NewsFilter.Currencies(SymbolName, NewsCurrencies);
            _news = NewsFilter.Build(NewsCpi, NewsNfp, NewsFomc, NewsUsdMore, NewsOtherCurrencies, newsCurrencies, NewsUsdEverywhere);
            if (NewsFilterMode != NewsMode.Off)
            {
                Print("News filter: currencies {0}; events {1}; calendar covered until {2}", string.Join(",", newsCurrencies), _news.Description, NewsCalendar.CoveredUntil);
                string newsWarning = NewsFilter.Warning(newsCurrencies, NewsUsdEverywhere, TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(Server.Time, DateTimeKind.Utc), _newYork));
                if (newsWarning != null) Print(newsWarning);
            }
            // Instance-scoped identity survives a restart and isolates identical labels
            // in real time. Historical runs need no persistent identity.
            if (RunningMode != RunningMode.RealTime)
                _positionLabel = Label + "_H";
            else
            {
                // Preserve the full label even if the display-label parameter changes later.
                _positionLabel = LocalStorage.GetString("Position Label V2", LocalStorageScope.Instance);
                if (string.IsNullOrEmpty(_positionLabel))
                {
                    // Do not create a new identity over positions whose storage may
                    // have been lost (including a restarted cloud container).
                    foreach (var position in Positions)
                        if (position.SymbolName == SymbolName && position.Label != null && position.Label.StartsWith(Label + "_", StringComparison.Ordinal))
                        {
                            Print("Startup stopped: saved identity is missing and matching labelled positions exist. No positions changed. Restore this local instance's storage before resuming.");
                            Stop();
                            return;
                        }
                    _positionLabel = Label + "_" + Guid.NewGuid().ToString("N");
                    LocalStorage.SetString("Position Label V2", _positionLabel, LocalStorageScope.Instance);
                    LocalStorage.Flush(LocalStorageScope.Instance);
                }
            }
            Print("Position ownership label: {0}", _positionLabel);
            // Legacy labels cannot safely identify which instance owns a position.
            if (Positions.FindAll(Label, SymbolName).Length > 0)
            {
                Print("Startup stopped: legacy positions use label {0}. Manage them manually before upgrading; no positions were changed.", Label);
                Stop();
                return;
            }
            Position[] existing = Positions.FindAll(_positionLabel, SymbolName);
            if (existing.Length > 0 && RestartHandling == RestartPolicy.StopAndPreservePositions)
            {
                Print("Startup stopped: {0} owned positions remain open. Broker SL/TP remain active, but cBot trailing is paused. Close them manually or explicitly select CloseOwnedPositions; select ResumePositions to restore saved management state.", existing.Length);
                Stop();
                return;
            }
            // Pine ta.atr() uses Wilder's RMA, not a simple moving average.
            // Matching this smoothing is essential because ATR directly sets
            // the stop distance, target distance, and risk-based position size.
            // Both ATR series always use the current chart Bars.
            _atr = Indicators.AverageTrueRange(Bars, AtrLength, MovingAverageType.WilderSmoothing);
            _percentileAtr = Indicators.AverageTrueRange(Bars, PercentileAtrLength, MovingAverageType.WilderSmoothing);
            // Recovery storage belongs to a persistent live instance. Historical
            // runs start with no broker positions to recover, and reading or
            // writing LocalStorage on every optimization tick only adds work.
            if (RunningMode == RunningMode.RealTime &&
                RestartHandling == RestartPolicy.ResumePositions && !RestoreState(existing))
            {
                Stop();
                return;
            }
            RebuildVwapFromHistory();
            Positions.Closed += OnPositionClosed;
            if (RestartHandling == RestartPolicy.CloseOwnedPositions)
                foreach (var p in existing) _pendingCloses.Add(p.Id);
            _stateWritable = RunningMode == RunningMode.RealTime;
            _ready = true;
            SaveState();
            // Scheduled liquidation still applies if a boundary passed offline.
            ManageBoundaryLiquidation(TradingClock(Server.Time));
            // OnTick already enforces scheduled liquidation in historical runs.
            // Keep the timer for real-time gaps in market ticks only.
            if (RunningMode == RunningMode.RealTime)
                Timer.Start(TimeSpan.FromSeconds(1));
            Print("Recovered {0} managed positions. VWAP trailing resumes only on the next chart-bar close.", _managedTrades.Count);
            Print("{0}: trade management timing = {1} (entries always on bar close). VWAP uses cTrader bar tick volume; sessions follow New York time.", Label, Timing);
        }

        protected override void OnBarClosed()
        {
            if (!_ready) return;
            try { ProcessClosedBar(); }
            finally { SaveState(); }
        }

        private void ProcessClosedBar()
        {
            // Pine uses barstate.isconfirmed and process_orders_on_close=false:
            // evaluate the completed bar, then submit at the next bar's first price.
            // In cTrader's OnBarClosed, Bars excludes the new live bar. The
            // final item is therefore the candle that just closed; using -2
            // delayed the signal and the entry by one complete candle.
            int i = Bars.Count - 1;
            if (i < 0) return;

            DateTime closedBarTime = TradingClock(Bars.OpenTimes[i]);
            UpdateVwapsForClosedBar(i);
            ManageBoundaryLiquidation(TradingClock(Server.Time));
            ManageVwapBandTrails(i);
            ManageBarCloseProtection(i);

            VwapBand band = ClosedBarBand(closedBarTime);
            // Pine updates the pause/re-arm state on every confirmed, eligible
            // calculation candle—even while a position is open or an entry is
            // later rejected by ATR, sizing, or other filters. Do this before
            // every trade gate so repeated touches cannot become fresh signals.
            bool scheduleOk = ScheduleAllows(closedBarTime);
            bool newsBlocked = NewsBlocksCandle(i);
            // Independent switches: Track Touches During Blocked Candles covers session/day blocks only,
            // Track Touches During News Block covers the news window only.
            bool trackTouches = (scheduleOk || TrackTouchesWhileBlocked) && (!newsBlocked || NewsTrackTouches);
            if (!trackTouches) return;

            bool longTouch = band.Valid && Bars.LowPrices[i] <= band.Lower;
            bool shortTouch = band.Valid && Bars.HighPrices[i] >= band.Upper;
            bool lowerArmedBefore = _lowerArmed;
            bool upperArmedBefore = _upperArmed;
            bool longSignal = longTouch && lowerArmedBefore;
            bool shortSignal = shortTouch && upperArmedBefore;

            // A non-touching completed candle is the required pause candle.
            // Long and short band states remain independent, matching Pine.
            // Pine also re-arms when the selected band is unavailable on this
            // candle (e.g. RTH candles in ETH Only mode), so update first.
            _lowerArmed = !longTouch;
            _upperArmed = !shortTouch;
            if (!scheduleOk || newsBlocked) return;
            if (!band.Valid) return;
            if (longSignal && shortSignal)
            {
                if (BothAction == BothBandAction.SkipBoth) return;
                longSignal = BothAction == BothBandAction.PreferLong;
                shortSignal = BothAction == BothBandAction.PreferShort;
            }

            // Position state blocks only execution, never the band pause state.
            // With hedging enabled, an opposite-direction position may coexist,
            // but duplicate entries in the same direction remain blocked.
            // Lock the ATR from the candle that produced the touch signal.
            // The next live quote may set the broker fill, but it must never
            // change the initial stop distance or any R-based trade management.
            // A signal may only enter while its own VWAP period (week, session or
            // ETH/RTH segment) is still open: a touch on the period's last candle
            // must not become an entry at the next period's open on a stale band.
            if (_pendingCloses.Count > 0 || ForceCloseWindowActive(TradingClock(Server.Time)) ||
                TradingClock(Server.Time) >= VwapPeriodEnd(closedBarTime) ||
                BrokerCloseImminent(TradingClock(Server.Time)) ||
                ForceCloseDue(closedBarTime, TradingClock(Server.Time)) ||
                Server.Time <= _lastExitTime.AddSeconds(1) || !AtrReadyForSignal(i)) return;
            double signalAtr = AtrAtSignalClose(i);

            if (longSignal && (TradeDirection == Direction.Both || TradeDirection == Direction.LongOnly) && CanEnter(TradeType.Buy) && Qualifies(true, i, Bars.ClosePrices[i], band.Lower, signalAtr))
                Enter(TradeType.Buy, signalAtr, ActiveTrailSource(closedBarTime));
            else if (shortSignal && (TradeDirection == Direction.Both || TradeDirection == Direction.ShortOnly) && CanEnter(TradeType.Sell) && Qualifies(false, i, Bars.ClosePrices[i], band.Upper, signalAtr))
                Enter(TradeType.Sell, signalAtr, ActiveTrailSource(closedBarTime));
        }

        protected override void OnTick()
        {
            if (!_ready) return;
            try
            {
                ManageBoundaryLiquidation(TradingClock(Server.Time));
                ManageOpenPosition();
            }
            finally { SaveState(); }
        }

        protected override void OnTimer()
        {
            if (!_ready) return;
            try
            {
                ManageBoundaryLiquidation(TradingClock(Server.Time));
                WarnNewsCalendarDaily();
            }
            finally { SaveState(); }
        }

        // Optimisation fitness, used when cTrader's criteria are set to "Custom".
        // Profitable runs score net profit ÷ max equity drawdown (return-to-drawdown).
        // Two guards stop degenerate runs from winning:
        //  - the drawdown is floored at 1% of the ending equity, so a run with a
        //    handful of trades and almost no drawdown cannot produce a huge ratio;
        //  - below the minimum trade count the score is multiplied by (trades/min)^2.
        // Losing runs return their (negative) net profit, so they always rank
        // below every profitable run. (v2: v1 only scaled linearly and floored the
        // drawdown at 1 currency unit, which let 5-trade runs score 60x the best real run.)
        protected override double GetFitness(GetFitnessArgs args)
        {
            if (args.TotalTrades <= 0) return -1e9;
            if (args.NetProfit <= 0) return args.NetProfit;
            double tradeWeight = Math.Min(1.0, (double)args.TotalTrades / MinFitnessTrades);
            double drawdown = Math.Max(args.MaxEquityDrawdown, 0.01 * Math.Abs(args.Equity));
            return args.NetProfit / drawdown * tradeWeight * tradeWeight;
        }

        protected override void OnStop()
        {
            SaveState();
            _ready = false;
            _stateWritable = false;
            Timer.Stop();
            Positions.Closed -= OnPositionClosed;
        }

        private void OnPositionClosed(PositionClosedEventArgs args)
        {
            if (args.Position.Label != _positionLabel || args.Position.SymbolName != SymbolName) return;
            _lastExitTime = Server.Time;
            _managedTrades.Remove(args.Position.Id);
            _pendingCloses.Remove(args.Position.Id);
            _lastCloseAttempt.Remove(args.Position.Id);
            _lastProtectionFailure.Remove(args.Position.Id);
            SaveState();
        }

        private bool CanEnter(TradeType type)
        {
            if (_persistenceFailed || _pendingCloses.Count > 0) return false;
            Position[] openPositions = Positions.FindAll(_positionLabel, SymbolName);
            if (openPositions.Length == 0) return true;
            if (!AllowHedgeTrades) return false;
            foreach (var position in openPositions)
                if (position.TradeType == type) return false;
            return true;
        }

        private void Enter(TradeType type, double signalAtr, TrailVwapSource trailSource)
        {
            double riskDistance = signalAtr * StopAtrMult;
            if (riskDistance <= 0) return;
            // Native cTrader sizing uses the symbol's broker-defined pip value,
            // minimum volume, and volume step. Percentage-of-balance compounds
            // from realized P&L; percentage-of-equity includes open P&L.
            double riskCash = CalculateRiskCash();
            double stopLossPips = riskDistance / Symbol.PipSize;
            if (riskCash <= 0 || stopLossPips <= 0) { Print("Signal skipped: invalid risk-sizing inputs."); return; }
            double volume = Symbol.NormalizeVolumeInUnits(Symbol.VolumeForFixedRisk(riskCash, stopLossPips), RoundingMode.Down);
            if (volume < Symbol.VolumeInUnitsMin) { Print("Signal skipped: calculated volume {0} is below broker minimum {1}.", volume, Symbol.VolumeInUnitsMin); return; }

            // Execution-only gate: the confirmed-bar signal, stop distance, and
            // VWAP management rules remain unchanged. Compare the live executable
            // spread with this trade's existing initial stop distance, so the
            // threshold automatically adapts to volatility and session conditions.
            double liveSpread = Symbol.Ask - Symbol.Bid;
            double liveSpreadPips = liveSpread / Symbol.PipSize;
            double stopDistancePips = riskDistance / Symbol.PipSize;
            double spreadPercentOfStop = 100.0 * liveSpread / riskDistance;
            if (EnableMaxEntrySpreadFilter && spreadPercentOfStop > MaxEntrySpreadPercentOfStop)
            {
                Print("Signal skipped: {0} entry spread {1:F2} pips is {2:F2}% of initial stop distance ({3:F2} pips), exceeding maximum {4:F2}%.", type, liveSpreadPips, spreadPercentOfStop, stopDistancePips, MaxEntrySpreadPercentOfStop);
                return;
            }

            bool trailing = Management != TradeManagement.FixedTakeProfit;
            bool vwapTrailing = Management == TradeManagement.VwapBandTrail || Management == TradeManagement.DynamicVwapBandTrail;
            double trailStepR = Management == TradeManagement.TrailOneRStepOneRGap ? 1.0 : 0.5;
            double trailGapR = Management == TradeManagement.TrailHalfRStepHalfRGap ? 0.5 : 1.0;
            double trailActivationR = Management == TradeManagement.TrailHalfRStepOneRGapSkipFirst ? 1.0 : trailStepR;
            // The signal-to-entry distance filter is evaluated on the signal
            // candle in Qualifies(), matching Pine. The signal's ATR stays locked.
            var result = ExecuteMarketOrder(type, SymbolName, volume, _positionLabel, stopLossPips, trailing ? (double?)null : stopLossPips * TargetR);
            if (!result.IsSuccessful) { Print("Order rejected: {0}", result.Error); return; }

            // Protection is requested with the entry, not in a second request.
            // Defensive fallback: never continue managing an unprotected fill.
            if (!result.Position.StopLoss.HasValue || (!trailing && !result.Position.TakeProfit.HasValue))
            {
                Print("Entry protection missing for position {0}; closing and blocking new entries until confirmed.", result.Position.Id);
                _pendingCloses.Add(result.Position.Id);
                RetryPendingCloses();
                return;
            }
            double fillEntry = result.Position.EntryPrice;
            double stop = type == TradeType.Buy ? fillEntry - riskDistance : fillEntry + riskDistance;
            VwapBand initialBands = TrailBand(trailSource, 2.0, TradingClock(Server.Time));
            double target = vwapTrailing && initialBands.Valid
                ? (type == TradeType.Buy ? initialBands.Lower : initialBands.Upper)
                : (type == TradeType.Buy ? fillEntry + riskDistance * (trailing ? trailActivationR : TargetR) : fillEntry - riskDistance * (trailing ? trailActivationR : TargetR));
            var trade = new ManagedTrade(result.Position.Id, fillEntry, riskDistance, stop, target, trailStepR, trailGapR, trailActivationR, trailSource);
            trade.Stop = result.Position.StopLoss.Value;
            if (!trailing) trade.Target = result.Position.TakeProfit.Value;
            _managedTrades[result.Position.Id] = trade;
            SaveState();
        }

        private double CalculateRiskCash()
        {
            double riskCash;
            switch (SelectedRiskModel)
            {
                case RiskModel.PercentOfBalance:
                    riskCash = Account.Balance * RiskPercent / 100.0;
                    break;
                case RiskModel.PercentOfEquity:
                    riskCash = Account.Equity * RiskPercent / 100.0;
                    break;
                case RiskModel.FixedCashRisk:
                    riskCash = FixedCashRisk;
                    break;
                case RiskModel.FixedReferenceAccount:
                    riskCash = ReferenceAccountSize * RiskPercent / 100.0;
                    break;
                default:
                    riskCash = 0;
                    break;
            }

            if (MaxCashRiskCap > 0) riskCash = Math.Min(riskCash, MaxCashRiskCap);
            return riskCash;
        }

        private void ManageOpenPosition()
        {
            // Bar-close timing manages all open-trade protection in OnBarClosed.
            if (Timing != ManagementTiming.Tick) return;
            foreach (var p in Positions.FindAll(_positionLabel, SymbolName))
            {
                ManagedTrade trade;
                if (_pendingCloses.Contains(p.Id) || !_managedTrades.TryGetValue(p.Id, out trade)) continue;
                if (Management == TradeManagement.FixedTakeProfit)
                {
                    ManageFixedTargetBreakEven(p, trade);
                    continue;
                }
                if (Management == TradeManagement.VwapBandTrail || Management == TradeManagement.DynamicVwapBandTrail)
                {
                    // Live price against the bands of the last completed candle.
                    // A close-beyond-band trigger is a candle-close event by
                    // definition, so it stays in ManageVwapBandTrails.
                    if (BandTrailTrigger == VwapBandTrailTrigger.WickTouch)
                        UpdateVwapTrail(p, trade, p.TradeType == TradeType.Buy ? Symbol.Bid : Symbol.Ask, TradingClock(Server.Time), Bars.Count - 2);
                    continue;
                }
                double favorable = p.TradeType == TradeType.Buy ? Symbol.Bid - trade.Entry : trade.Entry - Symbol.Ask;
                double r = favorable / trade.RiskDistance;
                if (r < trade.TrailActivationR) continue;
                double milestone = Math.Floor(r / trade.TrailStepR) * trade.TrailStepR;
                double proposedStop = RoundToTick(p.TradeType == TradeType.Buy ? trade.Entry + (milestone - trade.TrailGapR) * trade.RiskDistance : trade.Entry - (milestone - trade.TrailGapR) * trade.RiskDistance);
                if (!StopImproves(p.TradeType, proposedStop, trade.Stop)) continue;
                if (TrySetProtection(p, trade, proposedStop, null))
                    trade.Target = p.TradeType == TradeType.Buy ? trade.Entry + (milestone + trade.TrailStepR) * trade.RiskDistance : trade.Entry - (milestone + trade.TrailStepR) * trade.RiskDistance;
            }
        }

        private void ManageFixedTargetBreakEven(Position position, ManagedTrade trade)
        {
            if (!EnableFixedTpBreakEven || trade.BreakEvenActivated) return;
            double favorable = position.TradeType == TradeType.Buy ? Symbol.Bid - trade.Entry : trade.Entry - Symbol.Ask;
            if (favorable / trade.RiskDistance < FixedTpBreakEvenTriggerR) return;

            double breakEvenStop = RoundToTick(trade.Entry);
            bool improves = StopImproves(position.TradeType, breakEvenStop, trade.Stop);
            bool executable = position.TradeType == TradeType.Buy ? breakEvenStop < Symbol.Bid - Symbol.TickSize : breakEvenStop > Symbol.Ask + Symbol.TickSize;
            if (!improves || !executable) return;

            // Commit activation only after the broker accepts protection.
            if (!TrySetProtection(position, trade, breakEvenStop, position.TakeProfit)) return;
            trade.BreakEvenActivated = true;
            Print("{0}: fixed-target break-even activated for position {1} at {2:F5} after {3:F2}R.", Label, position.Id, breakEvenStop, favorable / trade.RiskDistance);
        }

        // Pine parity: break-even and R trails are evaluated once per completed
        // candle from its high/low (close for the break-even guard), and the new
        // stop applies from the next candle.
        private void ManageBarCloseProtection(int barIndex)
        {
            if (Timing != ManagementTiming.BarClose) return;
            if (Management == TradeManagement.VwapBandTrail || Management == TradeManagement.DynamicVwapBandTrail) return;
            double high = Bars.HighPrices[barIndex], low = Bars.LowPrices[barIndex], close = Bars.ClosePrices[barIndex];
            foreach (var p in Positions.FindAll(_positionLabel, SymbolName))
            {
                ManagedTrade trade;
                if (_pendingCloses.Contains(p.Id) || !_managedTrades.TryGetValue(p.Id, out trade)) continue;
                bool isBuy = p.TradeType == TradeType.Buy;
                double reachedR = (isBuy ? high - trade.Entry : trade.Entry - low) / trade.RiskDistance;
                if (Management == TradeManagement.FixedTakeProfit)
                {
                    if (!EnableFixedTpBreakEven || trade.BreakEvenActivated || reachedR < FixedTpBreakEvenTriggerR) continue;
                    // Pine only moves to break-even if the candle closed beyond entry.
                    bool closedBeyondEntry = isBuy ? trade.Entry < close - Symbol.TickSize : trade.Entry > close + Symbol.TickSize;
                    if (!closedBeyondEntry) continue;
                    if (!ApplyBarCloseStop(p, trade, trade.Entry, p.TakeProfit)) continue;
                    trade.BreakEvenActivated = true;
                    Print("{0}: fixed-target break-even activated for position {1} at {2:F5} after {3:F2}R (bar close).", Label, p.Id, trade.Entry, reachedR);
                    continue;
                }
                if (reachedR < trade.TrailActivationR) continue;
                double milestone = Math.Floor(reachedR / trade.TrailStepR) * trade.TrailStepR;
                double proposedStop = isBuy ? trade.Entry + (milestone - trade.TrailGapR) * trade.RiskDistance : trade.Entry - (milestone - trade.TrailGapR) * trade.RiskDistance;
                if (ApplyBarCloseStop(p, trade, proposedStop, null))
                    trade.Target = isBuy ? trade.Entry + (milestone + trade.TrailStepR) * trade.RiskDistance : trade.Entry - (milestone + trade.TrailStepR) * trade.RiskDistance;
            }
        }

        // Pine places the updated stop for the next candle. If the new candle
        // already opened beyond it, Pine's stop fills at that open; mirror this
        // by closing at market instead of sending an invalid stop.
        private bool ApplyBarCloseStop(Position position, ManagedTrade trade, double stop, double? target)
        {
            stop = RoundToTick(stop);
            if (!StopImproves(position.TradeType, stop, trade.Stop)) return false;
            bool executable = position.TradeType == TradeType.Buy ? stop < Symbol.Bid - Symbol.TickSize : stop > Symbol.Ask + Symbol.TickSize;
            if (!executable)
            {
                Print("{0}: updated stop {1:F5} for position {2} is already breached at the candle open; closing at market.", Label, stop, position.Id);
                _pendingCloses.Add(position.Id);
                RetryPendingCloses();
                return false;
            }
            return TrySetProtection(position, trade, stop, target);
        }

        private void ManageVwapBandTrails(int barIndex)
        {
            if (Management != TradeManagement.VwapBandTrail && Management != TradeManagement.DynamicVwapBandTrail) return;
            // Tick timing evaluates the wick trigger on live prices in OnTick.
            if (Timing == ManagementTiming.Tick && BandTrailTrigger == VwapBandTrailTrigger.WickTouch) return;
            DateTime localTime = TradingClock(Bars.OpenTimes[barIndex]);
            foreach (var p in Positions.FindAll(_positionLabel, SymbolName))
            {
                ManagedTrade trade;
                if (_pendingCloses.Contains(p.Id) || !_managedTrades.TryGetValue(p.Id, out trade)) continue;
                // The trigger uses either the completed candle's favorable wick or its close.
                double trailPrice = BandTrailTrigger == VwapBandTrailTrigger.CandleCloseBeyondBand
                    ? Bars.ClosePrices[barIndex]
                    : (p.TradeType == TradeType.Buy ? Bars.HighPrices[barIndex] : Bars.LowPrices[barIndex]);
                // Bar Close timing validates new levels against this candle's
                // close (Pine); Tick timing validates against the live quote.
                double referenceClose = Timing == ManagementTiming.BarClose ? Bars.ClosePrices[barIndex] : double.NaN;
                UpdateVwapTrail(p, trade, trailPrice, localTime, barIndex, referenceClose);
            }
        }

        private void UpdateVwapTrail(Position position, ManagedTrade trade, double trailPrice, DateTime localTime, int atrIndex, double referenceClose = double.NaN)
        {
            if (Management == TradeManagement.DynamicVwapBandTrail)
                UpdateDynamicVwapBandTrail(position, trade, trailPrice, localTime, AtrAtSignalClose(atrIndex), referenceClose);
            else
                UpdateVwapBandTrail(position, trade, trailPrice, localTime, AtrAtSignalClose(atrIndex), referenceClose);
        }

        // With a reference close (Bar Close timing) this mirrors Pine: the level
        // must sit beyond the completed candle's close, and if the new candle
        // already opened past a tightened level, Pine's stop fills at that open,
        // so close at market. Without one (Tick timing) the live quote decides.
        // The static ladder only tightens; the dynamic trail may also loosen.
        private void ApplyVwapTrailStop(Position position, ManagedTrade trade, double candidate, double referenceClose, bool tightenOnly)
        {
            bool isBuy = position.TradeType == TradeType.Buy;
            candidate = RoundToTick(candidate);
            bool improves = StopImproves(position.TradeType, candidate, trade.Stop);
            if (tightenOnly && !improves) return;
            bool executable = isBuy ? candidate < Symbol.Bid - Symbol.TickSize : candidate > Symbol.Ask + Symbol.TickSize;
            if (!double.IsNaN(referenceClose))
            {
                bool validAtClose = isBuy ? candidate < referenceClose - Symbol.TickSize : candidate > referenceClose + Symbol.TickSize;
                if (!validAtClose) return;
                if (!executable)
                {
                    // A looser or unchanged level that is already breached means
                    // the existing broker stop is breached too and will fill.
                    if (!improves) return;
                    Print("{0}: VWAP trail stop {1:F5} for position {2} is already breached at the candle open; closing at market.", Label, candidate, position.Id);
                    _pendingCloses.Add(position.Id);
                    RetryPendingCloses();
                    return;
                }
            }
            else if (!executable) return;
            TrySetProtection(position, trade, candidate, null);
        }

        private void UpdateVwapBandTrail(Position position, ManagedTrade trade, double trailPrice, DateTime localTime, double atr, double referenceClose)
        {
            VwapBand one = TrailBand(trade.VwapSource, 1.0, localTime);
            VwapBand two = TrailBand(trade.VwapSource, 2.0, localTime);
            VwapBand three = TrailBand(trade.VwapSource, 3.0, localTime);
            if (!one.Valid || !two.Valid || !three.Valid) return;
            // The cushion offsets band levels only; stage 1 stays exactly at entry.
            // A missing ATR with a non-zero cushion yields NaN and skips the update.
            double cushion = VwapTrailAtrCushion > 0 ? atr * VwapTrailAtrCushion : 0;

            int stage = trade.VwapStage;
            if (position.TradeType == TradeType.Buy)
            {
                if (trailPrice >= two.Lower) stage = Math.Max(stage, 1);
                if (trailPrice >= one.Lower) stage = Math.Max(stage, 2);
                if (trailPrice >= one.Vwap) stage = Math.Max(stage, 3);
                if (trailPrice >= one.Upper) stage = Math.Max(stage, 4);
                if (trailPrice >= two.Upper) stage = Math.Max(stage, 5);
                if (trailPrice >= three.Upper) stage = Math.Max(stage, 6);
                double candidate = stage == 1 ? trade.Entry : stage == 2 ? two.Lower - cushion : stage == 3 ? one.Lower - cushion : stage == 4 ? one.Vwap - cushion : stage == 5 ? one.Upper - cushion : stage >= 6 ? two.Upper - cushion : double.NaN;
                if (!double.IsNaN(candidate)) ApplyVwapTrailStop(position, trade, candidate, referenceClose, true);
                trade.Target = stage == 0 ? two.Lower : stage == 1 ? one.Lower : stage == 2 ? one.Vwap : stage == 3 ? one.Upper : stage == 4 ? two.Upper : three.Upper;
            }
            else
            {
                if (trailPrice <= two.Upper) stage = Math.Max(stage, 1);
                if (trailPrice <= one.Upper) stage = Math.Max(stage, 2);
                if (trailPrice <= one.Vwap) stage = Math.Max(stage, 3);
                if (trailPrice <= one.Lower) stage = Math.Max(stage, 4);
                if (trailPrice <= two.Lower) stage = Math.Max(stage, 5);
                if (trailPrice <= three.Lower) stage = Math.Max(stage, 6);
                double candidate = stage == 1 ? trade.Entry : stage == 2 ? two.Upper + cushion : stage == 3 ? one.Upper + cushion : stage == 4 ? one.Vwap + cushion : stage == 5 ? one.Lower + cushion : stage >= 6 ? two.Lower + cushion : double.NaN;
                if (!double.IsNaN(candidate)) ApplyVwapTrailStop(position, trade, candidate, referenceClose, true);
                trade.Target = stage == 0 ? two.Upper : stage == 1 ? one.Upper : stage == 2 ? one.Vwap : stage == 3 ? one.Lower : stage == 4 ? two.Lower : three.Lower;
            }

            trade.VwapStage = stage;
            _managedTrades[position.Id] = trade;
        }

        private void UpdateDynamicVwapBandTrail(Position position, ManagedTrade trade, double trailPrice, DateTime localTime, double atr, double referenceClose)
        {
            if (atr <= 0 || double.IsNaN(atr)) return;
            VwapBand one = TrailBand(trade.VwapSource, 1.0, localTime);
            VwapBand two = TrailBand(trade.VwapSource, 2.0, localTime);
            VwapBand three = TrailBand(trade.VwapSource, 3.0, localTime);
            if (!one.Valid || !two.Valid || !three.Valid) return;

            int stage = trade.VwapStage;
            double candidate = double.NaN;
            if (position.TradeType == TradeType.Buy)
            {
                if (trailPrice >= two.Lower) stage = Math.Max(stage, 1);
                if (trailPrice >= one.Lower) stage = Math.Max(stage, 2);
                if (trailPrice >= one.Vwap) stage = Math.Max(stage, 3);
                if (trailPrice >= one.Upper) stage = Math.Max(stage, 4);
                if (trailPrice >= two.Upper) stage = Math.Max(stage, 5);
                if (trailPrice >= three.Upper) stage = Math.Max(stage, 6);
                double band = stage == 1 ? three.Lower : stage == 2 ? two.Lower : stage == 3 ? one.Lower : stage == 4 ? one.Vwap : stage == 5 ? one.Upper : stage >= 6 ? two.Upper : double.NaN;
                // Dynamic mode follows the current selected VWAP band on each
                // completed candle. Unlike the static ladder, it may tighten OR
                // loosen; the original stop remains the maximum permitted risk.
                candidate = !double.IsNaN(band) ? Math.Max(trade.OriginalStop, band - atr * VwapTrailAtrCushion) : double.NaN;
                if (!double.IsNaN(candidate)) ApplyVwapTrailStop(position, trade, candidate, referenceClose, false);
                trade.Target = stage == 0 ? two.Lower : stage == 1 ? one.Lower : stage == 2 ? one.Vwap : stage == 3 ? one.Upper : stage == 4 ? two.Upper : three.Upper;
            }
            else
            {
                if (trailPrice <= two.Upper) stage = Math.Max(stage, 1);
                if (trailPrice <= one.Upper) stage = Math.Max(stage, 2);
                if (trailPrice <= one.Vwap) stage = Math.Max(stage, 3);
                if (trailPrice <= one.Lower) stage = Math.Max(stage, 4);
                if (trailPrice <= two.Lower) stage = Math.Max(stage, 5);
                if (trailPrice <= three.Lower) stage = Math.Max(stage, 6);
                double band = stage == 1 ? three.Upper : stage == 2 ? two.Upper : stage == 3 ? one.Upper : stage == 4 ? one.Vwap : stage == 5 ? one.Lower : stage >= 6 ? two.Lower : double.NaN;
                // The short-side counterpart can also tighten or loosen, but
                // never extends risk beyond the original stop.
                candidate = !double.IsNaN(band) ? Math.Min(trade.OriginalStop, band + atr * VwapTrailAtrCushion) : double.NaN;
                if (!double.IsNaN(candidate)) ApplyVwapTrailStop(position, trade, candidate, referenceClose, false);
                trade.Target = stage == 0 ? two.Upper : stage == 1 ? one.Upper : stage == 2 ? one.Vwap : stage == 3 ? one.Lower : stage == 4 ? two.Lower : three.Lower;
            }

            trade.VwapStage = stage;
            _managedTrades[position.Id] = trade;
        }

        private TrailVwapSource ActiveTrailSource(DateTime localTime)
        {
            if (Mode == VwapMode.WeeklyVWAP) return TrailVwapSource.Weekly;
            if (Mode == VwapMode.SessionVWAP) return TrailVwapSource.Session;
            return InEth(localTime) ? TrailVwapSource.ETH : TrailVwapSource.RTH;
        }

        private VwapBand TrailBand(TrailVwapSource source, double multiplier, DateTime localTime)
        {
            switch (source)
            {
                case TrailVwapSource.Weekly: return _weekly.Band(multiplier);
                case TrailVwapSource.Session: return _daily.Band(multiplier);
                case TrailVwapSource.ETH: return InEth(localTime) ? _eth.Band(multiplier) : VwapBand.None;
                case TrailVwapSource.RTH: return !InEth(localTime) ? _rth.Band(multiplier) : VwapBand.None;
                default: return VwapBand.None;
            }
        }

        private bool Qualifies(bool isLong, int barIndex, double close, double band, double signalAtr)
        {
            double wick = isLong ? Bars.LowPrices[barIndex] : Bars.HighPrices[barIndex];
            bool priceFiltersPass = VwapMeanReversionCore.PassesFilters(isLong, close, wick, band, signalAtr, EnableDistanceFilter, MaxEntryDistanceAtr, EnablePenetrationFilter, Penetration, MaxBandPenetrationAtr);
            // A NaN (not-ready) percentile fails the comparison, as Pine's na does.
            return priceFiltersPass && (!EnableAtrPercentile || AtrPercentileAtSignalClose(barIndex) <= MaxAtrPercentile);
        }

        // ATR is indexed directly to the completed signal candle because the
        // chart timeframe is the sole calculation and ATR timeframe.
        private double AtrAtSignalClose(int signalBarIndex)
        {
            return signalBarIndex >= 0 ? _atr.Result[signalBarIndex] : double.NaN;
        }

        private bool AtrReadyForSignal(int signalBarIndex)
        {
            return signalBarIndex >= VwapMeanReversionCore.RequiredAtrIndex(AtrLength, EnableAtrPercentile, PercentileLookback, PercentileAtrLength) && _atr.Result[signalBarIndex] > 0;
        }

        // Pine ta.percentrank: the share of the PREVIOUS `lookback` values that
        // are less than or equal to the current value. The current bar itself
        // is excluded from the comparison window.
        private double AtrPercentileAtSignalClose(int signalBarIndex)
        {
            int end = signalBarIndex, start = end - PercentileLookback;
            if (start < PercentileAtrLength) return double.NaN;
            double value = _percentileAtr.Result[end], below = 0;
            for (int i = start; i < end; i++) if (_percentileAtr.Result[i] <= value) below++;
            return 100.0 * below / PercentileLookback;
        }

        private void RebuildVwapFromHistory()
        {
            // Rebuild the full current anchor, including bars completed offline.
            // No historical orders or stop changes are replayed.
            DateTime anchor = TimeZoneInfo.ConvertTimeToUtc(
                DateTime.SpecifyKind(NewYorkTime(VwapMeanReversionCore.WeekStart(TradingClock(Server.Time).Date)), DateTimeKind.Unspecified), _newYork);
            while (Bars.Count > 0 && Bars.OpenTimes[0] > anchor)
                if (Bars.LoadMoreHistory() == 0) break;
            int first = 0;
            for (int i = first; i < Bars.Count - 1; i++) UpdateVwapsForClosedBar(i);
        }

        private void UpdateVwapsForClosedBar(int i)
        {
            DateTime t = TradingClock(Bars.OpenTimes[i]);
            DateTime day = t.Date;
            DateTime week = VwapMeanReversionCore.WeekStart(day);
            bool isEth = InEth(t), isRth = !isEth;
            if (day != _lastTradingDate) { _daily.Reset(); _lastTradingDate = day; }
            if (week != _lastWeekStart) { _weekly.Reset(); _lastWeekStart = week; }
            // A VWAP-session boundary resets that session's VWAP accumulator,
            // but it must NOT re-arm the touch/pause state. Pine only re-arms
            // after a completed candle does not touch the relevant band.
            if (isEth && VwapMeanReversionCore.IsNewSession(_lastEthSession, t)) { _eth.Reset(); _lastEthSession = day; }
            if (isRth && VwapMeanReversionCore.IsNewSession(_lastRthSession, t)) { _rth.Reset(); _lastRthSession = day; }
            double source = VwapMeanReversionCore.SourcePrice(Source, Bars.OpenPrices[i], Bars.HighPrices[i], Bars.LowPrices[i], Bars.ClosePrices[i]);
            double volume = Math.Max(0, Bars.TickVolumes[i]);
            _weekly.Add(source, volume); _daily.Add(source, volume);
            if (isEth) _eth.Add(source, volume); else _rth.Add(source, volume);
        }

        private VwapBand ClosedBarBand(DateTime barTime)
        {
            // UpdateVwapsForClosedBar has already incorporated this bar, matching
            // Pine's confirmed-bar VWAP/band values used by low/high touch tests.
            if (Mode == VwapMode.WeeklyVWAP) return _weekly.Band(WeeklyBandMult);
            if (Mode == VwapMode.SessionVWAP) return _daily.Band(SessionBandMult);
            if (InEth(barTime)) return IntradaySource != IntradaySignalSource.RTHOnly ? _eth.Band(EthBandMult) : VwapBand.None;
            return IntradaySource != IntradaySignalSource.ETHOnly ? _rth.Band(RthBandMult) : VwapBand.None;
        }

        // End (trading clock) of the VWAP period that the candle at signalTime belongs to.
        private DateTime VwapPeriodEnd(DateTime signalTime)
        {
            if (Mode == VwapMode.WeeklyVWAP)
                return VwapMeanReversionCore.WeekStart(signalTime.Date).AddDays(4).AddMinutes(VwapMeanReversionCore.SessionCloseMinute);
            if (Mode == VwapMode.IntradayDualVWAP && InEth(signalTime))
                return signalTime.Date.AddMinutes(VwapMeanReversionCore.EthEndMinute);
            return signalTime.Date.AddMinutes(VwapMeanReversionCore.SessionCloseMinute);
        }

        // Live only (timer): repeat the news warning once a day, so an expiring calendar is noticed without a restart.
        private void WarnNewsCalendarDaily()
        {
            if (NewsFilterMode == NewsMode.Off) return;
            DateTime nowNy = NyTime(Server.Time);
            if (nowNy.Date == _newsWarnedDay) return;
            _newsWarnedDay = nowNy.Date;
            string warning = NewsFilter.Warning(_newsCurrencies, NewsUsdEverywhere, nowNy);
            if (warning != null) Print(warning);
        }

        // News filter: the candle [open, close] is blocked when it overlaps the window around a release.
        private bool NewsBlocksCandle(int barIndex)
        {
            if (NewsFilterMode == NewsMode.Off || barIndex < 0) return false;
            DateTime openUtc = Bars.OpenTimes[barIndex];
            return NewsFilter.Blocks(_news, NyTime(openUtc), NyTime(openUtc + CandleSpan(barIndex)), NewsEntryMinutesBefore, NewsMinutesAfter);
        }

        // With closing on, no trade may open after the close moment and before the release.
        private int NewsEntryMinutesBefore
        {
            get { return NewsFilterMode == NewsMode.BlockEntriesAndCloseTrades ? Math.Max(NewsMinutesBefore, NewsCloseMinutesBefore) : NewsMinutesBefore; }
        }

        // True once "release - Close Trades Minutes Before News" lies between the entry and now (UTC in, robust to missed ticks).
        private bool NewsCloseDue(DateTime entryUtc, DateTime nowUtc)
        {
            if (NewsFilterMode != NewsMode.BlockEntriesAndCloseTrades) return false;
            return NewsFilter.CloseDue(_news, NyTime(entryUtc), NyTime(nowUtc), NewsCloseMinutesBefore);
        }

        private DateTime NyTime(DateTime utc) { return TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc, DateTimeKind.Utc), _newYork); }

        // Candle length = the smallest gap between consecutive candle opens seen so far (session and weekend
        // gaps are longer), so it needs no timeframe table. Overlay and Pine use the same candle close.
        private TimeSpan _candleSpan = TimeSpan.MaxValue;
        private TimeSpan CandleSpan(int barIndex)
        {
            for (int k = Math.Max(1, barIndex - 20); k <= barIndex; k++)
            {
                TimeSpan gap = Bars.OpenTimes[k] - Bars.OpenTimes[k - 1];
                if (gap > TimeSpan.Zero && gap < _candleSpan) _candleSpan = gap;
            }
            return _candleSpan == TimeSpan.MaxValue ? TimeSpan.Zero : _candleSpan;
        }

        private bool ScheduleAllows(DateTime now)
        {
            int minute = now.Hour * 60 + now.Minute;
            if (Mode == VwapMode.WeeklyVWAP) return !WeeklyBlockActive(now);
            if (Mode == VwapMode.SessionVWAP)
                return minute >= BlockSessionFirst && minute < VwapMeanReversionCore.SessionCloseMinute - BlockSessionLast &&
                       !SessionDayBlocked(NewYorkTime(now));

            bool isEth = InEth(now);
            // Pine applies only the selected session's blocks: in ETH Only mode
            // RTH candles are always eligible (they can only re-arm), and vice versa.
            if (isEth && IntradaySource == IntradaySignalSource.RTHOnly) return true;
            if (!isEth && IntradaySource == IntradaySignalSource.ETHOnly) return true;
            int within = isEth ? minute : minute - VwapMeanReversionCore.EthEndMinute;
            if (isEth)
                return within >= BlockEthFirst && within < VwapMeanReversionCore.SessionMinutes - BlockEthLast &&
                       !IntradayDayBlocked(NewYorkTime(now));
            return within >= BlockRthFirst && within < VwapMeanReversionCore.RthMinutes - BlockRthLast &&
                   !IntradayDayBlocked(NewYorkTime(now));
        }

        // Monday-Friday block windows, shared by the three schedule sections.
        // Each section's daily window is checked in its *DayBlocked wrapper.
        private bool DayWindowBlocked(DateTime now, bool mon, string monW, bool tue, string tueW, bool wed, string wedW, bool thu, string thuW, bool fri, string friW)
        {
            switch (now.DayOfWeek)
            {
                case DayOfWeek.Monday: return mon && InWindow(monW, now);
                case DayOfWeek.Tuesday: return tue && InWindow(tueW, now);
                case DayOfWeek.Wednesday: return wed && InWindow(wedW, now);
                case DayOfWeek.Thursday: return thu && InWindow(thuW, now);
                case DayOfWeek.Friday: return fri && InWindow(friW, now);
                default: return false;
            }
        }

        private bool WeeklyDayBlocked(DateTime now)
        {
            return (WeeklyDailyWindowBlock && InWindow(WeeklyDailyWindow, now)) ||
                   DayWindowBlocked(now, WeeklyMondayBlock, WeeklyMondayWindow, WeeklyTuesdayBlock, WeeklyTuesdayWindow, WeeklyWednesdayBlock, WeeklyWednesdayWindow, WeeklyThursdayBlock, WeeklyThursdayWindow, WeeklyFridayBlock, WeeklyFridayWindow);
        }

        private bool SessionDayBlocked(DateTime now)
        {
            return (SessionDailyWindowBlock && InWindow(SessionDailyWindow, now)) ||
                   DayWindowBlocked(now, SessionMondayBlock, SessionMondayWindow, SessionTuesdayBlock, SessionTuesdayWindow, SessionWednesdayBlock, SessionWednesdayWindow, SessionThursdayBlock, SessionThursdayWindow, SessionFridayBlock, SessionFridayWindow);
        }

        // Intraday day blocks apply to both ETH and RTH candles.
        private bool IntradayDayBlocked(DateTime now)
        {
            return (IntradayDailyWindowBlock && InWindow(IntradayDailyWindow, now)) ||
                   DayWindowBlocked(now, IntradayMondayBlock, IntradayMondayWindow, IntradayTuesdayBlock, IntradayTuesdayWindow, IntradayWednesdayBlock, IntradayWednesdayWindow, IntradayThursdayBlock, IntradayThursdayWindow, IntradayFridayBlock, IntradayFridayWindow);
        }

        private bool WeeklyBlockActive(DateTime now)
        {
            DateTime weekOpen = VwapMeanReversionCore.WeekStart(now.Date);
            DateTime weeklyClose = weekOpen.AddDays(4).AddMinutes(VwapMeanReversionCore.SessionCloseMinute);
            if (WeeklyFirstHours > 0 && now >= weekOpen && now < weekOpen.AddHours(WeeklyFirstHours)) return true;
            if (WeeklyLastHours > 0 && now >= weeklyClose.AddHours(-WeeklyLastHours) && now < weeklyClose) return true;
            return WeeklyDayBlocked(NewYorkTime(now));
        }

        // Broker stops live on the tick grid. Rounding before every comparison
        // prevents an unrounded level from looking "better" than the broker's
        // rounded stop and resending the same modification on every tick.
        private double RoundToTick(double price)
        {
            return Math.Round(Math.Round(price / Symbol.TickSize) * Symbol.TickSize, Symbol.Digits);
        }

        private bool SamePrice(double? a, double? b)
        {
            return a.HasValue == b.HasValue && (!a.HasValue || Math.Abs(a.Value - b.Value) < Symbol.TickSize / 2);
        }

        private bool StopImproves(TradeType type, double stop, double current)
        {
            return type == TradeType.Buy ? stop > current + Symbol.TickSize / 2 : stop < current - Symbol.TickSize / 2;
        }

        private bool TrySetProtection(Position position, ManagedTrade trade, double stop, double? target)
        {
            DateTime failedAt;
            if (_lastProtectionFailure.TryGetValue(position.Id, out failedAt) && Server.Time < failedAt.AddSeconds(5)) return false;
            stop = RoundToTick(stop);
            if (SamePrice(position.StopLoss, stop) && SamePrice(position.TakeProfit, target))
            {
                trade.Stop = position.StopLoss.Value;
                return true;
            }
            var result = ModifyPosition(position, stop, target, ProtectionType.Absolute);
            if (!result.IsSuccessful)
            {
                _lastProtectionFailure[position.Id] = Server.Time;
                Print("Protection update rejected for {0}: {1}. Previous accepted stop retained; retry remains enabled.", position.Id, result.Error);
                return false;
            }
            if (!result.Position.StopLoss.HasValue)
            {
                Print("Protection missing after update for {0}; requesting close.", position.Id);
                _pendingCloses.Add(position.Id);
                return false;
            }
            _lastProtectionFailure.Remove(position.Id);
            trade.Stop = result.Position.StopLoss.Value;
            return true;
        }

        private bool ForceCloseWindowActive(DateTime now)
        {
            int minute = now.Hour * 60 + now.Minute;
            if (Mode == VwapMode.WeeklyVWAP)
                return WeeklyForceCloseFriday == ForceCloseOption.Yes && now.DayOfWeek == DayOfWeek.Friday &&
                       VwapMeanReversionCore.InSessionClosePeriod(minute);
            if (Mode == VwapMode.SessionVWAP)
                return (SessionForceClose == ForceCloseOption.Yes || SessionForceCloseFriday == ForceCloseOption.Yes && now.DayOfWeek == DayOfWeek.Friday) &&
                       VwapMeanReversionCore.InSessionClosePeriod(minute);
            if (IntradayForceCloseFriday && now.DayOfWeek == DayOfWeek.Friday && VwapMeanReversionCore.InSessionClosePeriod(minute)) return true;
            return (IntradaySource != IntradaySignalSource.RTHOnly && CloseAtEthEnd && minute >= VwapMeanReversionCore.EthForceCloseMinute && minute < VwapMeanReversionCore.EthEndMinute) ||
                   (IntradaySource != IntradaySignalSource.ETHOnly && CloseAtRthEnd && minute >= VwapMeanReversionCore.RthForceCloseMinute && minute < VwapMeanReversionCore.SessionCloseMinute);
        }

        private bool ForceCloseDue(DateTime from, DateTime now)
        {
            if (now < from) return false;
            // Check the entire lifetime, so missed ticks and failed closes do not
            // lose a boundary. A signal spanning it is also ineligible for entry.
            for (DateTime day = from.Date.AddDays(-1); day <= now.Date; day = day.AddDays(1))
            {
                if (Mode == VwapMode.IntradayDualVWAP)
                {
                    if (IntradaySource != IntradaySignalSource.RTHOnly && CloseAtEthEnd &&
                        VwapMeanReversionCore.CrossedBoundary(from, now, day.AddMinutes(VwapMeanReversionCore.EthForceCloseMinute))) return true;
                    if (IntradaySource != IntradaySignalSource.ETHOnly && CloseAtRthEnd &&
                        VwapMeanReversionCore.CrossedBoundary(from, now, day.AddMinutes(VwapMeanReversionCore.RthForceCloseMinute))) return true;
                    if (IntradayForceCloseFriday && day.DayOfWeek == DayOfWeek.Friday &&
                        VwapMeanReversionCore.CrossedBoundary(from, now, VwapMeanReversionCore.SessionForceCloseTime(day))) return true;
                }
                else
                {
                    bool enabled = Mode == VwapMode.SessionVWAP
                        ? SessionForceClose == ForceCloseOption.Yes || SessionForceCloseFriday == ForceCloseOption.Yes && day.DayOfWeek == DayOfWeek.Friday
                        : WeeklyForceCloseFriday == ForceCloseOption.Yes && day.DayOfWeek == DayOfWeek.Friday;
                    if (enabled && VwapMeanReversionCore.CrossedBoundary(from, now, VwapMeanReversionCore.SessionForceCloseTime(day))) return true;
                }
            }
            return false;
        }

        // Safety net for early closes and holidays, which the fixed schedule
        // cannot know: when a force-close option is enabled for the active mode,
        // also close (and block entries) once the broker's own trading hours say
        // the market closes within the force-close window (ForceCloseLeadMinutes). Normal days are unaffected.
        private bool BrokerCloseImminent(DateTime now)
        {
            if (!BrokerCloseSafetyNet || !Symbol.MarketHours.IsOpened() || Symbol.MarketHours.TimeTillClose() > TimeSpan.FromMinutes(VwapMeanReversionCore.ForceCloseLeadMinutes)) return false;
            if (Mode == VwapMode.WeeklyVWAP) return WeeklyForceCloseFriday == ForceCloseOption.Yes && now.DayOfWeek == DayOfWeek.Friday;
            if (Mode == VwapMode.SessionVWAP)
                return SessionForceClose == ForceCloseOption.Yes || SessionForceCloseFriday == ForceCloseOption.Yes && now.DayOfWeek == DayOfWeek.Friday;
            // The ETH close (09:30 NY) is not a market close; RTH ends at the daily close.
            return IntradaySource != IntradaySignalSource.ETHOnly && CloseAtRthEnd || IntradayForceCloseFriday && now.DayOfWeek == DayOfWeek.Friday;
        }

        private void ManageBoundaryLiquidation(DateTime now)
        {
            bool brokerCloseImminent = BrokerCloseImminent(now);
            foreach (var position in Positions.FindAll(_positionLabel, SymbolName))
                if (brokerCloseImminent || ForceCloseWindowActive(now) || ForceCloseDue(TradingClock(position.EntryTime), now) ||
                    NewsCloseDue(position.EntryTime, Server.Time))
                    _pendingCloses.Add(position.Id);
            RetryPendingCloses();
        }

        private void RetryPendingCloses()
        {
            var stillOpen = new HashSet<long>();
            foreach (var position in Positions.FindAll(_positionLabel, SymbolName))
            {
                stillOpen.Add(position.Id);
                if (!_pendingCloses.Contains(position.Id)) continue;
                DateTime last;
                if (_lastCloseAttempt.TryGetValue(position.Id, out last) && Server.Time < last.AddSeconds(5)) continue;
                _lastCloseAttempt[position.Id] = Server.Time;
                var result = ClosePosition(position);
                if (result.IsSuccessful)
                {
                    _pendingCloses.Remove(position.Id);
                    _managedTrades.Remove(position.Id);
                    _lastCloseAttempt.Remove(position.Id);
                    _lastExitTime = Server.Time;
                }
                else Print("Close rejected for {0}: {1}. New entries blocked; will retry.", position.Id, result.Error);
            }
            _pendingCloses.RemoveWhere(id => !stillOpen.Contains(id));
        }

        private bool InEth(DateTime tradingClock) { return VwapMeanReversionCore.IsEth(tradingClock); }
        private bool InWindow(string window, DateTime now) { return VwapMeanReversionCore.InWindow(window, now); }

        private string RecoverySettings()
        {
            // Management must resume under the same rules. Entry sizing/filter
            // parameters may change without reinterpreting an existing trade.
            object[] values = { Bars.TimeFrame, Management, Mode, Source, AtrLength,
                BandTrailTrigger, VwapTrailAtrCushion, EnableFixedTpBreakEven, FixedTpBreakEvenTriggerR,
                Timing, IntradaySource, WeeklyForceCloseFriday,
                SessionForceClose, CloseAtEthEnd, CloseAtRthEnd, SessionForceCloseFriday, IntradayForceCloseFriday };
            return string.Join("|", Array.ConvertAll(values, x => Convert.ToString(x, CultureInfo.InvariantCulture)));
        }

        private void SaveState()
        {
            if (!_stateWritable) return;
            try
            {
                var state = new RecoveryState
                {
                    Version = 3, Account = Convert.ToString(Account.Number, CultureInfo.InvariantCulture),
                    Symbol = SymbolName, Label = _positionLabel, Settings = RecoverySettings(),
                    LowerArmed = _lowerArmed, UpperArmed = _upperArmed, LastExitTime = _lastExitTime,
                    PendingCloses = new List<long>(_pendingCloses), Trades = new List<RecoveryTrade>()
                };
                foreach (var pair in _managedTrades)
                {
                    var t = pair.Value;
                    state.Trades.Add(new RecoveryTrade
                    {
                        Id = pair.Key, Entry = t.Entry, RiskDistance = t.RiskDistance, OriginalStop = t.OriginalStop,
                        Stop = t.Stop, Target = t.Target, TrailStepR = t.TrailStepR, TrailGapR = t.TrailGapR,
                        TrailActivationR = t.TrailActivationR, VwapSource = (int)t.VwapSource,
                        VwapStage = t.VwapStage, BreakEvenActivated = t.BreakEvenActivated
                    });
                }
                string json = JsonSerializer.Serialize(state);
                if (json != _lastSavedState || _persistenceFailed)
                {
                    LocalStorage.SetString(RecoveryKey, json, LocalStorageScope.Instance);
                    LocalStorage.Flush(LocalStorageScope.Instance);
                    _lastSavedState = json;
                }
                _persistenceFailed = false;
            }
            catch (Exception ex)
            {
                if (!_persistenceFailed) Print("Recovery state could not be saved: {0}. Existing trades remain managed; new entries blocked until storage recovers.", ex.Message);
                _persistenceFailed = true;
            }
        }

        private bool RestoreState(Position[] positions)
        {
            try
            {
                string json = LocalStorage.GetString(RecoveryKey, LocalStorageScope.Instance);
                if (string.IsNullOrEmpty(json))
                {
                    if (positions.Length == 0) return true;
                    throw new InvalidOperationException("No saved trade state exists for these open positions.");
                }
                RecoveryState state = JsonSerializer.Deserialize<RecoveryState>(json);
                string account = Convert.ToString(Account.Number, CultureInfo.InvariantCulture);
                if (state == null || state.Version != 3 || state.Account != account || state.Symbol != SymbolName || state.Label != _positionLabel)
                {
                    if (positions.Length == 0) return true;
                    throw new InvalidOperationException("Saved state does not match this account, symbol or instance.");
                }
                if (state.Settings != RecoverySettings())
                {
                    if (positions.Length == 0) return true;
                    throw new InvalidOperationException("Management settings or chart timeframe changed. Restore the previous settings to resume.");
                }
                if (state.Trades == null || state.PendingCloses == null) throw new InvalidOperationException("Saved state is incomplete.");
                var restored = new Dictionary<long, ManagedTrade>();
                foreach (var position in positions)
                {
                    if (state.PendingCloses.Contains(position.Id)) continue;
                    RecoveryTrade saved = state.Trades.Find(t => t.Id == position.Id);
                    if (saved == null) throw new InvalidOperationException("Missing original risk state for position " + position.Id + ".");
                    saved.Reconcile(position.EntryPrice, position.TradeType == TradeType.Buy, position.StopLoss,
                        position.TakeProfit, Management == TradeManagement.FixedTakeProfit, Symbol.TickSize);
                    var trade = new ManagedTrade(position.Id, saved.Entry, saved.RiskDistance, saved.OriginalStop,
                        saved.Target, saved.TrailStepR, saved.TrailGapR, saved.TrailActivationR, (TrailVwapSource)saved.VwapSource);
                    trade.Stop = saved.Stop;
                    trade.VwapStage = saved.VwapStage;
                    trade.BreakEvenActivated = saved.BreakEvenActivated;
                    restored.Add(position.Id, trade);
                }
                foreach (var pair in restored) _managedTrades.Add(pair.Key, pair.Value);
                foreach (var position in positions)
                    if (state.PendingCloses.Contains(position.Id)) _pendingCloses.Add(position.Id);
                _lowerArmed = state.LowerArmed;
                _upperArmed = state.UpperArmed;
                _lastExitTime = state.LastExitTime;
                return true;
            }
            catch (Exception ex)
            {
                Print("Recovery stopped: {0} Positions and broker protections were left unchanged; no guessed state or new entries.", ex.Message);
                return false;
            }
        }

        public sealed class RecoveryState
        {
            public int Version { get; set; }
            public string Account { get; set; }
            public string Symbol { get; set; }
            public string Label { get; set; }
            public string Settings { get; set; }
            public bool LowerArmed { get; set; }
            public bool UpperArmed { get; set; }
            public DateTime LastExitTime { get; set; }
            public List<long> PendingCloses { get; set; }
            public List<RecoveryTrade> Trades { get; set; }
        }

        public sealed class RecoveryTrade
        {
            public long Id { get; set; }
            public double Entry { get; set; }
            public double RiskDistance { get; set; }
            public double OriginalStop { get; set; }
            public double Stop { get; set; }
            public double Target { get; set; }
            public double TrailStepR { get; set; }
            public double TrailGapR { get; set; }
            public double TrailActivationR { get; set; }
            public int VwapSource { get; set; }
            public int VwapStage { get; set; }
            public bool BreakEvenActivated { get; set; }

            public void Reconcile(double brokerEntry, bool isBuy, double? brokerStop, double? brokerTarget, bool fixedTarget, double tickSize)
            {
                if (!IsValid() || Math.Abs(Entry - brokerEntry) > tickSize ||
                    (isBuy ? OriginalStop >= Entry : OriginalStop <= Entry) ||
                    Math.Abs(Math.Abs(Entry - OriginalStop) - RiskDistance) > tickSize)
                    throw new InvalidOperationException("Invalid original risk state for position " + Id + ".");
                if (!brokerStop.HasValue || (fixedTarget && !brokerTarget.HasValue))
                    throw new InvalidOperationException("Broker protection is missing for position " + Id + "; inspect it before resuming.");
                // The broker's accepted protections are authoritative after a
                // crash or a manual edit. Never reset a trailed stop on startup.
                Stop = brokerStop.Value;
                if (brokerTarget.HasValue) Target = brokerTarget.Value;
                BreakEvenActivated = isBuy ? Stop >= Entry : Stop <= Entry;
            }

            public bool IsValid()
            {
                double[] values = { Entry, RiskDistance, OriginalStop, Stop, Target, TrailStepR, TrailGapR, TrailActivationR };
                foreach (double value in values) if (double.IsNaN(value) || double.IsInfinity(value)) return false;
                return Id > 0 && RiskDistance > 0 && TrailStepR > 0 && TrailGapR > 0 && TrailActivationR > 0 &&
                    VwapStage >= 0 && VwapStage <= 6 && Enum.IsDefined(typeof(TrailVwapSource), VwapSource);
            }
        }

        private sealed class ManagedTrade
        {
            public readonly double Entry, RiskDistance, OriginalStop, TrailStepR, TrailGapR, TrailActivationR;
            public readonly TrailVwapSource VwapSource;
            public double Stop, Target;
            public int VwapStage;
            public bool BreakEvenActivated;

            public ManagedTrade(long positionId, double entry, double riskDistance, double stop, double target, double trailStepR, double trailGapR, double trailActivationR, TrailVwapSource vwapSource)
            {
                Entry = entry;
                RiskDistance = riskDistance;
                OriginalStop = stop;
                Stop = stop;
                Target = target;
                TrailStepR = trailStepR;
                TrailGapR = trailGapR;
                TrailActivationR = trailActivationR;
                VwapSource = vwapSource;
                VwapStage = 0;
                BreakEvenActivated = false;
            }
        }

        // Sessions run on a trading clock: New York time + VwapMeanReversionCore.TradingClockOffsetHours.
        private DateTime TradingClock(DateTime utc) { return TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc, DateTimeKind.Utc), _newYork).AddHours(VwapMeanReversionCore.TradingClockOffsetHours); }
        // Block windows are entered in plain New York time.
        private static DateTime NewYorkTime(DateTime tradingClock) { return tradingClock.AddHours(-VwapMeanReversionCore.TradingClockOffsetHours); }
        private static TimeZoneInfo LoadNewYorkZone()
        {
            try { return TimeZoneInfo.FindSystemTimeZoneById("America/New_York"); }
            catch (TimeZoneNotFoundException) { return TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time"); }
        }
    }

    // Shared calculation layer embedded so this cBot is self-contained.
    // It intentionally contains no cBot orders and no chart drawing.
    public struct VwapBand
    {
        public static readonly VwapBand None = new VwapBand(double.NaN, double.NaN, double.NaN);
        public readonly double Vwap;
        public readonly double Upper;
        public readonly double Lower;

        public bool Valid { get { return !double.IsNaN(Vwap); } }

        public VwapBand(double vwap, double upper, double lower)
        {
            Vwap = vwap;
            Upper = upper;
            Lower = lower;
        }
    }

    public sealed class VwapState
    {
        private double _weight;
        private double _weightedValue;
        private double _weightedValueSquared;

        public void Reset()
        {
            _weight = 0;
            _weightedValue = 0;
            _weightedValueSquared = 0;
        }

        public void Add(double source, double volume)
        {
            if (volume <= 0) return;
            _weight += volume;
            _weightedValue += source * volume;
            _weightedValueSquared += source * source * volume;
        }

        public VwapBand Band(double multiplier)
        {
            if (_weight <= 0) return VwapBand.None;
            double vwap = _weightedValue / _weight;
            double variance = Math.Max(0, _weightedValueSquared / _weight - vwap * vwap);
            double deviation = Math.Sqrt(variance);
            return new VwapBand(vwap, vwap + deviation * multiplier, vwap - deviation * multiplier);
        }
    }

    public static class VwapMeanReversionCore
    {
        // Trading clock = New York time + 6 h. The 18:00 NY reopen becomes 00:00,
        // the 09:30 NY cash open 15:30 (EthEndMinute) and the 17:00 NY close
        // 23:00 (SessionCloseMinute), all year round, so US/EU daylight-saving
        // mismatch weeks cannot shift a session, reset or forced close.
        public const int TradingClockOffsetHours = 6;
        public const int EthEndMinute = 930;
        public const int SessionMinutes = 930;
        // RTH runs from the 09:30 NY cash open to the 17:00 NY market close.
        // Every "last" block counts back from that close, never from the reopen.
        public const int RthMinutes = SessionCloseMinute - EthEndMinute;
        public const int SessionCloseMinute = 23 * 60;
        // The forced close is a WINDOW covering the last ForceCloseLeadMinutes before the close: the first
        // price at or after the window start closes the position. A single-minute trigger (the old lead of 1)
        // was often missed in m1 backtests (no price in that minute) and executed after the weekend instead.
        public const int ForceCloseLeadMinutes = 10;
        public const int EthForceCloseMinute = EthEndMinute - ForceCloseLeadMinutes;
        public const int RthForceCloseMinute = SessionCloseMinute - ForceCloseLeadMinutes;

        public static DateTime SessionForceCloseTime(DateTime sessionDate)
        {
            return sessionDate.Date.AddMinutes(SessionCloseMinute - ForceCloseLeadMinutes);
        }

        public static bool InSessionClosePeriod(int minuteOfDay)
        {
            return minuteOfDay >= SessionCloseMinute - ForceCloseLeadMinutes && minuteOfDay < SessionCloseMinute;
        }

        // ETH and RTH each have a distinct accumulator and both belong to
        // their trading date (starting 18:00 NY). Missing intervening bars do not merge sessions.
        public static bool IsNewSession(DateTime lastSessionDate, DateTime barLocalTime)
        {
            return lastSessionDate != barLocalTime.Date;
        }

        public static int RequiredAtrIndex(int atrLength, bool percentileEnabled, int lookback, int percentileLength)
        {
            return percentileEnabled ? Math.Max(atrLength, lookback + percentileLength) : atrLength;
        }

        // Pine measures how far the signal candle CLOSED from the band in the
        // reversion direction only; a close beyond the band counts as zero.
        public static bool SignalWithinDistance(bool isLong, double close, double band, double atr, bool enabled, double multiplier)
        {
            if (!enabled) return true;
            double distance = isLong ? Math.Max(close - band, 0) : Math.Max(band - close, 0);
            return atr > 0 && distance <= atr * multiplier;
        }

        public static bool CrossedBoundary(DateTime from, DateTime now, DateTime boundary)
        {
            return from < boundary && boundary <= now;
        }

        public static bool OverlapsWindow(DateTime from, DateTime now, DateTime day, string window)
        {
            if (string.IsNullOrWhiteSpace(window)) return false;
            string[] parts = window.Split('-');
            TimeSpan start, end;
            if (parts.Length != 2 || !TimeSpan.TryParseExact(parts[0], "hhmm", CultureInfo.InvariantCulture, out start) ||
                !TimeSpan.TryParseExact(parts[1], "hhmm", CultureInfo.InvariantCulture, out end)) return false;
            DateTime begin = day.Date.Add(start), finish = day.Date.Add(end);
            if (end <= start) finish = finish.AddDays(1);
            return from < finish && now >= begin;
        }

        public static double SourcePrice(VwapSource source, double open, double high, double low, double close)
        {
            switch (source)
            {
                case VwapSource.Open: return open;
                case VwapSource.High: return high;
                case VwapSource.Low: return low;
                case VwapSource.Close: return close;
                case VwapSource.HLC3: return (high + low + close) / 3.0;
                case VwapSource.OHLC4: return (open + high + low + close) / 4.0;
                case VwapSource.HLCC4: return (high + low + close + close) / 4.0;
                default: return (high + low) / 2.0;
            }
        }

        public static bool IsEth(DateTime tradingClock)
        {
            return tradingClock.Hour * 60 + tradingClock.Minute < EthEndMinute;
        }

        public static DateTime WeekStart(DateTime date)
        {
            return date.Date.AddDays(-(((int)date.DayOfWeek + 6) % 7));
        }

        public static bool InWindow(string window, DateTime localTime)
        {
            if (string.IsNullOrWhiteSpace(window)) return false;
            string[] parts = window.Split('-');
            TimeSpan start;
            TimeSpan end;
            if (parts.Length != 2 || !TimeSpan.TryParseExact(parts[0], "hhmm", CultureInfo.InvariantCulture, out start) || !TimeSpan.TryParseExact(parts[1], "hhmm", CultureInfo.InvariantCulture, out end)) return false;
            TimeSpan time = localTime.TimeOfDay;
            return start < end ? time >= start && time < end : time >= start || time < end;
        }

        public static bool DirectionAllows(Direction direction, bool isLong)
        {
            return direction == Direction.Both || (isLong && direction == Direction.LongOnly) || (!isLong && direction == Direction.ShortOnly);
        }

        public static bool PassesFilters(bool isLong, double close, double wick, double band, double atr, bool useDistance, double maxDistanceAtr, bool usePenetration, PenetrationMeasure penetrationMeasure, double maxPenetrationAtr)
        {
            if (atr <= 0 || double.IsNaN(atr) || double.IsInfinity(atr) || double.IsNaN(band) || double.IsInfinity(band)) return false;
            if (!SignalWithinDistance(isLong, close, band, atr, useDistance, maxDistanceAtr)) return false;
            double penetrationPrice = penetrationMeasure == PenetrationMeasure.Close ? close : wick;
            double penetration = isLong ? Math.Max(band - penetrationPrice, 0) : Math.Max(penetrationPrice - band, 0);
            return !usePenetration || penetration <= atr * maxPenetrationAtr;
        }
    }
    // News filter shared by the cBot and the overlay (same code in both files; Pine mirrors it).
    // A candle [open, close] in New York time is blocked when it overlaps the window
    // [release - minutesBefore, release + duration + minutesAfter): it closes at or after the window start and opens
    // before the window end. So "5 before / 10 after" blocks the candle whose close (= entry) is at or after
    // 08:25 and every candle that opens before 08:40; with 0/0 only the candle closing at the release is blocked.
    // duration is 0 for releases with a fixed time and the announcement window for the BoJ (no fixed time).
    // Which releases count depends on the symbol's currencies (FTMO restricts an event only on symbols that contain
    // its currency): US CPI / NFP / FOMC and advance GDP + FOMC minutes when USD is involved (or always, on request),
    // and each other involved currency's central bank and key data (EUR, GBP, JPY, CAD, AUD, NZD, CHF; oil: EIA).
    public static class NewsFilter
    {
        public sealed class NewsSet
        {
            internal readonly Dictionary<DateTime, List<KeyValuePair<DateTime, int>>> ByDay = new Dictionary<DateTime, List<KeyValuePair<DateTime, int>>>();
            public string Description = "";
        }

        private static readonly string[] Codes = { "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "NZD", "CHF" };

        // Currencies whose news moves this symbol. "Auto": FX pairs from the two 3-letter codes, indices from their
        // home currency, oil = OIL + USD, metals = USD; otherwise a comma list such as "USD,EUR".
        public static string[] Currencies(string symbol, string setting)
        {
            var list = new List<string>();
            if (!string.IsNullOrWhiteSpace(setting) && !setting.Trim().Equals("Auto", StringComparison.OrdinalIgnoreCase))
            {
                foreach (string part in setting.Split(new[] { ',', ';', ' ', '+' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    string c = part.Trim().ToUpperInvariant();
                    if (!list.Contains(c)) list.Add(c);
                }
                return list.ToArray();
            }
            string s = (symbol ?? "").ToUpperInvariant();
            if (s.Contains("XTI") || s.Contains("XBR") || s.Contains("OIL") || s.Contains("WTI") || s.Contains("BRENT")) return new[] { "OIL", "USD" };
            if (s.StartsWith("US") && !s.StartsWith("USD") || s.StartsWith("NAS") || s.StartsWith("SPX") || s.StartsWith("DJ") || s.StartsWith("WS30")) return new[] { "USD" };
            if (s.StartsWith("DE") || s.StartsWith("GER") || s.Contains("DAX") || s.StartsWith("EU") && !s.StartsWith("EUR") || s.StartsWith("FRA") || s.StartsWith("F40")) return new[] { "EUR" };
            if (s.StartsWith("UK") || s.Contains("FTSE")) return new[] { "GBP" };
            if (s.StartsWith("JP") || s.Contains("NIK")) return new[] { "JPY" };
            if (s.StartsWith("AUS") || s.StartsWith("AU200")) return new[] { "AUD" };
            if (s.StartsWith("XAU") || s.StartsWith("XAG") || s.StartsWith("XPT") || s.StartsWith("XPD")) list.Add("USD");
            for (int i = 0; i + 3 <= s.Length; i += 3)
            {
                string c = s.Substring(i, 3);
                if (Array.IndexOf(Codes, c) >= 0 && !list.Contains(c)) list.Add(c);
            }
            return list.ToArray();
        }

        public static NewsSet Build(bool cpi, bool nfp, bool fomc, bool usdMore, bool otherCurrencies, string[] currencies, bool usdEverywhere)
        {
            var set = new NewsSet();
            var parts = new List<string>();
            bool usd = usdEverywhere || Array.IndexOf(currencies, "USD") >= 0;
            if (usd)
            {
                if (cpi) { Add(set, NewsCalendar.Cpi, 0); parts.Add("US CPI"); }
                if (nfp) { Add(set, NewsCalendar.Nfp, 0); parts.Add("NFP"); }
                if (fomc) { Add(set, NewsCalendar.Fomc, 0); parts.Add("FOMC"); }
                if (usdMore) { Add(set, NewsCalendar.UsdMore, 0); parts.Add("US GDP + FOMC minutes"); }
            }
            if (otherCurrencies)
                foreach (string c in currencies)
                {
                    if (c == "USD") continue;
                    long[] stamps = NewsCalendar.ForCurrency(c);
                    if (stamps.Length == 0) continue;
                    Add(set, stamps, NewsCalendar.DurationFor(c));
                    parts.Add(c);
                }
            set.Description = parts.Count > 0 ? string.Join(", ", parts) : "none";
            return set;
        }

        // Start-up / daily check: a symbol without a recognised currency, or a calendar about to run out, would leave the
        // filter silently inactive. Returns null when all is well.
        public static string Warning(string[] currencies, bool usdEverywhere, DateTime nowNy)
        {
            if (currencies.Length == 0 && !usdEverywhere)
                return "WARNING news filter: no currency recognised in the symbol name; set News Currencies (e.g. USD,EUR) or no news is filtered.";
            DateTime until = DateTime.ParseExact(NewsCalendar.CoveredUntil, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
            if (nowNy.Date > until)
                return "WARNING news filter: the news calendar ended on " + NewsCalendar.CoveredUntil + "; later releases are NOT filtered. Add the new dates and rebuild.";
            if (nowNy.Date > until.AddDays(-30))
                return "WARNING news filter: the news calendar ends on " + NewsCalendar.CoveredUntil + "; add next year's dates and rebuild before then.";
            return null;
        }

        // Compatibility form (US core events only), used by the tests.
        public static bool Blocks(DateTime openNy, DateTime closeNy, bool cpi, bool nfp, bool fomc, int minutesBefore, int minutesAfter)
        {
            return Blocks(Build(cpi, nfp, fomc, false, false, new[] { "USD" }, false), openNy, closeNy, minutesBefore, minutesAfter);
        }

        public static bool CloseDue(DateTime entryNy, DateTime nowNy, bool cpi, bool nfp, bool fomc, int minutesBefore)
        {
            return CloseDue(Build(cpi, nfp, fomc, false, false, new[] { "USD" }, false), entryNy, nowNy, minutesBefore);
        }

        public static DateTime ToTime(long stamp)
        {
            return new DateTime((int)(stamp / 100000000), (int)(stamp / 1000000 % 100), (int)(stamp / 10000 % 100),
                                (int)(stamp / 100 % 100), (int)(stamp % 100), 0);
        }

        private static void Add(NewsSet set, long[] stamps, int duration)
        {
            foreach (long s in stamps)
            {
                DateTime t = ToTime(s);
                List<KeyValuePair<DateTime, int>> list;
                if (!set.ByDay.TryGetValue(t.Date, out list)) set.ByDay[t.Date] = list = new List<KeyValuePair<DateTime, int>>();
                list.Add(new KeyValuePair<DateTime, int>(t, duration));
            }
        }

        public static bool Blocks(NewsSet set, DateTime openNy, DateTime closeNy, int minutesBefore, int minutesAfter)
        {
            if (set == null) return false;
            // A window can reach into the neighbouring day (large before/after or a long duration), so check one day either side.
            for (DateTime day = openNy.Date.AddDays(-1); day <= closeNy.Date.AddDays(1); day = day.AddDays(1))
            {
                List<KeyValuePair<DateTime, int>> releases;
                if (!set.ByDay.TryGetValue(day, out releases)) continue;
                foreach (var r in releases)
                    if (closeNy >= r.Key.AddMinutes(-minutesBefore) && openNy < r.Key.AddMinutes(r.Value + minutesAfter)) return true;
            }
            return false;
        }

        // A trade is closed once the close moment (release - minutesBefore) lies after its entry and at or before now.
        public static bool CloseDue(NewsSet set, DateTime entryNy, DateTime nowNy, int minutesBefore)
        {
            if (set == null || nowNy <= entryNy) return false;
            for (DateTime day = entryNy.Date; day <= nowNy.Date.AddDays(1); day = day.AddDays(1))
            {
                List<KeyValuePair<DateTime, int>> releases;
                if (!set.ByDay.TryGetValue(day, out releases)) continue;
                foreach (var r in releases)
                {
                    DateTime closeAt = r.Key.AddMinutes(-minutesBefore);
                    if (entryNy < closeAt && closeAt <= nowNy) return true;
                }
            }
            return false;
        }
    }

    // NEWS-CALENDAR-BEGIN (generated by tools/gen_news_calendar.py from tools/data/us_news_dates.csv + tools/data/news_dates.csv; do not edit by hand)
    // Release times in New York time as yyyyMMddHHmm. Covered up to 2026-12-04: add next year's dates before then.
    public static class NewsCalendar
    {
        public const string CoveredUntil = "2026-12-04";
        public static readonly long[] Cpi =
        {
            201801120830, 201802140830, 201803130830, 201804110830, 201805100830, 201806120830, 201807120830, 201808100830,
            201809130830, 201810110830, 201811140830, 201812120830, 201901110830, 201902130830, 201903120830, 201904100830,
            201905100830, 201906120830, 201907110830, 201908130830, 201909120830, 201910100830, 201911130830, 201912110830,
            202001140830, 202002130830, 202003110830, 202004100830, 202005120830, 202006100830, 202007140830, 202008120830,
            202009110830, 202010130830, 202011120830, 202012100830, 202101130830, 202102100830, 202103100830, 202104130830,
            202105120830, 202106100830, 202107130830, 202108110830, 202109140830, 202110130830, 202111100830, 202112100830,
            202201120830, 202202100830, 202203100830, 202204120830, 202205110830, 202206100830, 202207130830, 202208100830,
            202209130830, 202210130830, 202211100830, 202212130830, 202301120830, 202302140830, 202303140830, 202304120830,
            202305100830, 202306130830, 202307120830, 202308100830, 202309130830, 202310120830, 202311140830, 202312120830,
            202401110830, 202402130830, 202403120830, 202404100830, 202405150830, 202406120830, 202407110830, 202408140830,
            202409110830, 202410100830, 202411130830, 202412110830, 202501150830, 202502120830, 202503120830, 202504100830,
            202505130830, 202506110830, 202507150830, 202508120830, 202509110830, 202510240830, 202512180830, 202601130830,
            202602130830, 202603110830, 202604100830, 202605120830, 202606100830, 202607140830, 202608120830, 202609110830,
            202610140830, 202611100830, 202612100830, 202701130830, 202702110830, 202703100830, 202704130830, 202705120830,
            202706100830, 202707140830, 202708110830, 202709140830, 202710140830, 202711100830, 202712100830,
        };
        public static readonly long[] Nfp =
        {
            201801050830, 201802020830, 201803090830, 201804060830, 201805040830, 201806010830, 201807060830, 201808030830,
            201809070830, 201810050830, 201811020830, 201812070830, 201901040830, 201902010830, 201903080830, 201904050830,
            201905030830, 201906070830, 201907050830, 201908020830, 201909060830, 201910040830, 201911010830, 201912060830,
            202001100830, 202002070830, 202003060830, 202004030830, 202005080830, 202006050830, 202007020830, 202008070830,
            202009040830, 202010020830, 202011060830, 202012040830, 202101080830, 202102050830, 202103050830, 202104020830,
            202105070830, 202106040830, 202107020830, 202108060830, 202109030830, 202110080830, 202111050830, 202112030830,
            202201070830, 202202040830, 202203040830, 202204010830, 202205060830, 202206030830, 202207080830, 202208050830,
            202209020830, 202210070830, 202211040830, 202212020830, 202301060830, 202302030830, 202303100830, 202304070830,
            202305050830, 202306020830, 202307070830, 202308040830, 202309010830, 202310060830, 202311030830, 202312080830,
            202401050830, 202402020830, 202403080830, 202404050830, 202405030830, 202406070830, 202407050830, 202408020830,
            202409060830, 202410040830, 202411010830, 202412060830, 202501100830, 202502070830, 202503070830, 202504040830,
            202505020830, 202506060830, 202507030830, 202508010830, 202509050830, 202511200830, 202512160830, 202601090830,
            202602110830, 202603060830, 202604030830, 202605080830, 202606050830, 202607020830, 202608070830, 202609040830,
            202610020830, 202611060830, 202612040830, 202701080830, 202702050830, 202703050830, 202704020830, 202705070830,
            202706040830, 202707020830, 202708060830, 202709030830, 202710080830, 202711050830, 202712030830,
        };
        public static readonly long[] Fomc =
        {
            201801311400, 201803211400, 201805021400, 201806131400, 201808011400, 201809261400, 201811081400, 201812191400,
            201901301400, 201903201400, 201905011400, 201906191400, 201907311400, 201909181400, 201910301400, 201912111400,
            202001291400, 202004291400, 202006101400, 202007291400, 202009161400, 202011051400, 202012161400, 202101271400,
            202103171400, 202104281400, 202106161400, 202107281400, 202109221400, 202111031400, 202112151400, 202201261400,
            202203161400, 202205041400, 202206151400, 202207271400, 202209211400, 202211021400, 202212141400, 202302011400,
            202303221400, 202305031400, 202306141400, 202307261400, 202309201400, 202311011400, 202312131400, 202401311400,
            202403201400, 202405011400, 202406121400, 202407311400, 202409181400, 202411071400, 202412181400, 202501291400,
            202503191400, 202505071400, 202506181400, 202507301400, 202509171400, 202510291400, 202512101400, 202601281400,
            202603181400, 202604291400, 202606171400, 202607291400, 202609161400, 202610281400, 202612091400, 202701271400,
            202703171400, 202704281400, 202706091400, 202707281400, 202709151400, 202710271400, 202712081400,
        };
        public static readonly long[] UsdMore =
        {
            201801031400, 201801260830, 201802211400, 201804111400, 201804270830, 201805231400, 201807051400, 201807270830,
            201808221400, 201810171400, 201810250830, 201811291400, 201901091400, 201902201400, 201902280830, 201904101400,
            201904260830, 201905221400, 201907101400, 201907260830, 201908211400, 201910091400, 201910300830, 201911201400,
            202001031400, 202001300830, 202002191400, 202004081400, 202004290830, 202005201400, 202007011400, 202007300830,
            202008191400, 202010071400, 202010290830, 202011251400, 202101061400, 202101280830, 202102171400, 202104071400,
            202104290830, 202105191400, 202107071400, 202107290830, 202108181400, 202110131400, 202110280830, 202111241400,
            202201051400, 202201270830, 202202161400, 202204061400, 202204280830, 202205251400, 202207061400, 202207280830,
            202208171400, 202210121400, 202210270830, 202211231400, 202301041400, 202301260830, 202302221400, 202304121400,
            202304270830, 202305241400, 202307051400, 202307270830, 202308161400, 202310111400, 202310260830, 202311211400,
            202401031400, 202401250830, 202402211400, 202404101400, 202404250830, 202405221400, 202407031400, 202407250830,
            202408211400, 202410091400, 202410300830, 202411261400, 202501081400, 202501300830, 202502191400, 202504091400,
            202504300830, 202505281400, 202507091400, 202507300830, 202508201400, 202510081400, 202511191400, 202512230830,
            202512301400, 202602181400, 202602200830, 202604081400, 202604300830, 202605201400, 202607081400, 202607300830,
            202608191400, 202610071400, 202610290830, 202611181400, 202612301400, 202701280830, 202702171400, 202704071400,
            202704290830, 202705191400, 202706301400, 202707290830, 202708181400, 202710061400, 202710280830, 202711171400,
            202712291400,
        };
        public static readonly long[] Eur =
        {
            201801250745, 201803080745, 201804260745, 201806140745, 201807260745, 201809130745, 201810250745, 201812130745,
            201901240745, 201903070745, 201904100745, 201906060745, 201907250745, 201909120745, 201910240745, 201912120745,
            202001230745, 202003120845, 202004300745, 202006040745, 202007160745, 202009100745, 202010290845, 202012100745,
            202101210745, 202103110745, 202104220745, 202106100745, 202107220745, 202109090745, 202110280745, 202112160745,
            202202030745, 202203100745, 202204140745, 202206090745, 202207210815, 202209080815, 202210270815, 202212150815,
            202302020815, 202303160915, 202305040815, 202306150815, 202307270815, 202309140815, 202310260815, 202312140815,
            202401250815, 202403070815, 202404110815, 202406060815, 202407180815, 202409120815, 202410170815, 202412120815,
            202501300815, 202503060815, 202504170815, 202506050815, 202507240815, 202509110815, 202510300915, 202512180815,
            202602050815, 202603190915, 202604300815, 202606110815, 202607230815, 202609100815, 202610290915, 202612170815,
            202702040815, 202703180915, 202704290815, 202706100815, 202707220815, 202709090815, 202710280815, 202712160815,
        };
        public static readonly long[] Gbp =
        {
            201801160200, 201802080700, 201802130200, 201803200300, 201803220800, 201804180200, 201805100700, 201805230200,
            201806130200, 201806210700, 201807180200, 201808020700, 201808150200, 201809130700, 201809190200, 201810170200,
            201811010800, 201811140200, 201812190200, 201812200700, 201901160200, 201902070700, 201902130200, 201903200300,
            201903210800, 201904170200, 201905020700, 201905220200, 201906190200, 201906200700, 201907170200, 201908010700,
            201908140200, 201909180200, 201909190700, 201910160200, 201911070700, 201911130200, 201912180200, 201912190700,
            202001150200, 202001300700, 202002190200, 202003250300, 202003260800, 202004220200, 202005070700, 202005200200,
            202006170200, 202006180700, 202007150200, 202008060700, 202008190200, 202009160200, 202009170700, 202010210200,
            202011050700, 202011180200, 202012160200, 202012170700, 202101200200, 202102040700, 202102170200, 202103180800,
            202103240300, 202104210200, 202105060700, 202105190200, 202106160200, 202106240700, 202107140200, 202108050700,
            202108180200, 202109150200, 202109230700, 202110200200, 202111040800, 202111170200, 202112150200, 202112160700,
            202201190200, 202202030700, 202202160200, 202203170800, 202203230300, 202204130200, 202205050700, 202205180200,
            202206160700, 202206220200, 202207200200, 202208040700, 202208170200, 202209140200, 202209220700, 202210190200,
            202211030800, 202211160200, 202212140200, 202212150700, 202301180200, 202302020700, 202302150200, 202303220300,
            202303230800, 202304190200, 202305110700, 202305240200, 202306210200, 202306220700, 202307190200, 202308030700,
            202308160200, 202309200200, 202309210700, 202310180200, 202311020800, 202311150200, 202312140700, 202312200200,
            202401170200, 202402010700, 202402140200, 202403200300, 202403210800, 202404170200, 202405090700, 202405220200,
            202406190200, 202406200700, 202407170200, 202408010700, 202408140200, 202409180200, 202409190700, 202410160200,
            202411070700, 202411200200, 202412180200, 202412190700, 202501150200, 202502060700, 202502190200, 202503200800,
            202503260300, 202504160200, 202505080700, 202505210200, 202506180200, 202506190700, 202507160200, 202508070700,
            202508200200, 202509170200, 202509180700, 202510220200, 202511060700, 202511190200, 202512170200, 202512180700,
            202601210200, 202602050700, 202602180200, 202603190800, 202603250300, 202604220200, 202604300700, 202605200200,
            202606170200, 202606180700, 202607220200, 202607300700, 202608190200, 202609160200, 202609170700, 202610210200,
            202611050700, 202611180200, 202612160200, 202612170700, 202701200200, 202702040700, 202702170200, 202703180800,
            202703240300, 202704210200, 202704290700, 202705190200, 202706160200, 202706170700, 202707210200, 202707290700,
            202708180200, 202709150200, 202709160700, 202710200200, 202711040800, 202711170200, 202712150200, 202712160700,
        };
        public static readonly long[] Jpy =
        {
            201801222100, 201803082100, 201804262200, 201806142200, 201807302200, 201809182200, 201810302200, 201812192100,
            201901222100, 201903142200, 201904242200, 201906192200, 201907292200, 201909182200, 201910302200, 201912182100,
            202001202100, 202003152300, 202004262200, 202005212000, 202006152200, 202007142200, 202009162200, 202010282200,
            202012172100, 202101202100, 202103182200, 202104262200, 202106172200, 202107152200, 202109212200, 202110272200,
            202112162100, 202201172100, 202203172200, 202204272200, 202206162200, 202207202200, 202209212200, 202210272200,
            202212192100, 202301172100, 202303092100, 202304272200, 202306152200, 202307272200, 202309212200, 202310302200,
            202312182100, 202401222100, 202403182200, 202404252200, 202406132200, 202407302200, 202409192200, 202410302200,
            202412182100, 202501232100, 202503182200, 202504302200, 202506162200, 202507302200, 202509182200, 202510292200,
            202512182100, 202601222100, 202603182200, 202604272200, 202606152200, 202607302200, 202609172200, 202610292200,
            202612172100, 202701212100, 202703172200, 202704272200, 202706102200, 202707212200, 202709212200, 202710282200,
            202712162100,
        };
        public static readonly long[] Cad =
        {
            201801050830, 201801171000, 201801260830, 201802090830, 201802230830, 201803071000, 201803090830, 201803230830,
            201804060830, 201804181000, 201804200830, 201805110830, 201805180830, 201805301000, 201806080830, 201806220830,
            201807060830, 201807111000, 201807200830, 201808100830, 201808170830, 201809051000, 201809070830, 201809210830,
            201810050830, 201810190830, 201810241000, 201811020830, 201811230830, 201812051000, 201812070830, 201812190830,
            201901040830, 201901091000, 201901180830, 201902080830, 201902270830, 201903061000, 201903080830, 201903220830,
            201904050830, 201904170830, 201904241000, 201905100830, 201905150830, 201905291000, 201906070830, 201906190830,
            201907050830, 201907101000, 201907170830, 201908090830, 201908210830, 201909041000, 201909060830, 201909180830,
            201910110830, 201910160830, 201910301000, 201911080830, 201911200830, 201912041000, 201912060830, 201912180830,
            202001100830, 202001220830, 202001221000, 202002070830, 202002190830, 202003041000, 202003060830, 202003180830,
            202004090830, 202004151000, 202004220830, 202005080830, 202005200830, 202006031000, 202006050830, 202006170830,
            202007100830, 202007151000, 202007220830, 202008070830, 202008190830, 202009040830, 202009091000, 202009160830,
            202010090830, 202010210830, 202010281000, 202011060830, 202011180830, 202012040830, 202012091000, 202012160830,
            202101080830, 202101200830, 202101201000, 202102050830, 202102170830, 202103101000, 202103120830, 202103170830,
            202104090830, 202104210830, 202104211000, 202105070830, 202105190830, 202106040830, 202106091000, 202106160830,
            202107090830, 202107141000, 202107280830, 202108060830, 202108180830, 202109081000, 202109100830, 202109150830,
            202110080830, 202110200830, 202110271000, 202111050830, 202111170830, 202112030830, 202112081000, 202112150830,
            202201070830, 202201190830, 202201261000, 202202040830, 202202160830, 202203021000, 202203110830, 202203160830,
            202204080830, 202204131000, 202204200830, 202205060830, 202205180830, 202206011000, 202206100830, 202206220830,
            202207080830, 202207131000, 202207200830, 202208050830, 202208160830, 202209071000, 202209090830, 202209200830,
            202210070830, 202210190830, 202210261000, 202211040830, 202211160830, 202212020830, 202212071000, 202212210830,
            202301060830, 202301170830, 202301251000, 202302100830, 202302210830, 202303081000, 202303100830, 202303210830,
            202304060830, 202304121000, 202304180830, 202305050830, 202305160830, 202306071000, 202306090830, 202306270830,
            202307070830, 202307121000, 202307180830, 202308040830, 202308150830, 202309061000, 202309080830, 202309190830,
            202310060830, 202310170830, 202310251000, 202311030830, 202311210830, 202312010830, 202312061000, 202312190830,
            202401050830, 202401160830, 202401240945, 202402090830, 202402200830, 202403060945, 202403080830, 202403190830,
            202404050830, 202404100945, 202404160830, 202405100830, 202405210830, 202406050945, 202406070830, 202406250830,
            202407050830, 202407160830, 202407240945, 202408090830, 202408200830, 202409040945, 202409060830, 202409170830,
            202410110830, 202410150830, 202410230945, 202411080830, 202411190830, 202412060830, 202412110945, 202412170830,
            202501100830, 202501210830, 202501290945, 202502070830, 202502180830, 202503070830, 202503120945, 202503180830,
            202504040830, 202504150830, 202504160945, 202505090830, 202505200830, 202506040945, 202506060830, 202506240830,
            202507110830, 202507150830, 202507300945, 202508080830, 202508190830, 202509050830, 202509160830, 202509170945,
            202510100830, 202510210830, 202510290945, 202511070830, 202511170830, 202512050830, 202512100945, 202512150830,
            202601090830, 202601190830, 202601280945, 202602060830, 202602170830, 202603130830, 202603160830, 202603180945,
            202604100830, 202604200830, 202604290945, 202605080830, 202605190830, 202606050830, 202606100945, 202606220830,
            202607100830, 202607150945, 202607200830, 202608070830, 202608170830, 202609020945, 202609040830, 202609140830,
            202610090830, 202610190830, 202610280945, 202611060830, 202611160830, 202612040830, 202612090945, 202612140830,
            202701210830, 202701270945, 202702180830, 202703030945, 202703180830, 202704280945, 202706020945, 202707210945,
            202709080945, 202710270945, 202712080945,
        };
        public static readonly long[] Aud =
        {
            201801171930, 201801301930, 201802052230, 201802141930, 201803052230, 201803061930, 201803212030, 201804030030,
            201804182130, 201804232130, 201805010030, 201805162130, 201806050030, 201806052130, 201806132130, 201807030030,
            201807182130, 201807242130, 201808070030, 201808152130, 201809040030, 201809042130, 201809122130, 201810020030,
            201810172030, 201810302030, 201811052230, 201811141930, 201812032230, 201812041930, 201812191930, 201901231930,
            201901291930, 201902042230, 201902201930, 201903042230, 201903051930, 201903202030, 201904012330, 201904172130,
            201904232130, 201905070030, 201905152130, 201906040030, 201906042130, 201906122130, 201907020030, 201907172130,
            201907302130, 201908060030, 201908142130, 201909030030, 201909032130, 201909182130, 201910010030, 201910162030,
            201910292030, 201911042230, 201911131930, 201912022230, 201912031930, 201912181930, 202001221930, 202001281930,
            202002032230, 202002191930, 202003022230, 202003031930, 202003182030, 202003182330, 202004070030, 202004152130,
            202004282130, 202005050030, 202005132130, 202006020030, 202006022130, 202006172130, 202007070030, 202007152130,
            202007282130, 202008040030, 202008122130, 202009010030, 202009012130, 202009162130, 202010052330, 202010142030,
            202010272030, 202011022230, 202011181930, 202011302230, 202012011930, 202012161930, 202101201930, 202101261930,
            202102012230, 202102171930, 202103012230, 202103021930, 202103172030, 202104060030, 202104142130, 202104272130,
            202105040030, 202105192130, 202106010030, 202106012130, 202106162130, 202107060030, 202107142130, 202107272130,
            202108030030, 202108182130, 202108312130, 202109070030, 202109152130, 202110042330, 202110132030, 202110262030,
            202111012330, 202111101930, 202111301930, 202112062230, 202112151930, 202201191930, 202201241930, 202201312230,
            202202161930, 202202282230, 202203011930, 202203162030, 202204050030, 202204132130, 202204262130, 202205030030,
            202205182130, 202205312130, 202206070030, 202206152130, 202207050030, 202207132130, 202207262130, 202208020030,
            202208172130, 202209060030, 202209062130, 202209142130, 202210032330, 202210192030, 202210252030, 202210312330,
            202211161930, 202211291930, 202212052230, 202212061930, 202212141930, 202301101930, 202301181930, 202301241930,
            202302062230, 202302151930, 202302281930, 202303062230, 202303152030, 202303282030, 202304040030, 202304122130,
            202304252130, 202305020030, 202305172130, 202305302130, 202306060030, 202306062130, 202306142130, 202306272130,
            202307040030, 202307192130, 202307252130, 202308010030, 202308162130, 202308292130, 202309050030, 202309052130,
            202309132130, 202309262130, 202310022330, 202310182030, 202310242030, 202311062230, 202311151930, 202311281930,
            202312042230, 202312051930, 202312131930, 202401091930, 202401171930, 202401301930, 202402052230, 202402141930,
            202402271930, 202403051930, 202403182330, 202403202030, 202403262030, 202404172130, 202404232130, 202405070030,
            202405152130, 202405282130, 202406042130, 202406122130, 202406180030, 202406252130, 202407172130, 202407302130,
            202408060030, 202408142130, 202408272130, 202409032130, 202409182130, 202409240030, 202409242130, 202410162030,
            202410292030, 202411042230, 202411131930, 202411261930, 202412031930, 202412092230, 202412111930, 202501071930,
            202501151930, 202501281930, 202502172230, 202502191930, 202502251930, 202503041930, 202503192030, 202503252030,
            202503312330, 202504162130, 202504292130, 202505142130, 202505200030, 202505272130, 202506032130, 202506182130,
            202506242130, 202507080030, 202507162130, 202507292130, 202508120030, 202508132130, 202508262130, 202509022130,
            202509172130, 202509232130, 202509300030, 202510152030, 202510282030, 202511032230, 202511121930, 202511251930,
            202512021930, 202512082230, 202512101930, 202601061930, 202601211930, 202601271930, 202602022230, 202602181930,
            202602241930, 202603031930, 202603162330, 202603182030, 202603242030, 202604152130, 202604282130, 202605050030,
            202605202130, 202605262130, 202606022130, 202606160030, 202606232130, 202606242130, 202607222130, 202607282130,
            202608110030, 202608192130, 202608252130, 202609012130, 202609232130, 202609290030, 202609292130, 202610142030,
            202610272030, 202611022230, 202611181930, 202611241930, 202612011930, 202612072230, 202612161930, 202701051930,
            202701201930, 202701261930, 202702082230, 202702171930, 202702231930, 202703021930, 202703222330, 202703232030,
            202703242030, 202705040030, 202706220030, 202708100030, 202709280030, 202711012330, 202712132230,
        };
        public static readonly long[] Nzd =
        {
            201801241645, 201802061645, 201802071500, 201803141745, 201803211600, 201804181845, 201805011845, 201805091700,
            201806201845, 201806271700, 201807161845, 201807311845, 201808081700, 201809191845, 201809261700, 201810151745,
            201811061645, 201811071500, 201812191645, 201901221645, 201902061645, 201902122000, 201903201745, 201903262100,
            201904161845, 201904301845, 201905072200, 201906191845, 201906252200, 201907151845, 201908051845, 201908062200,
            201909181845, 201909242200, 201910151745, 201911051645, 201911122000, 201912181645, 202001231645, 202002041645,
            202002112000, 202003181745, 202003242100, 202004191845, 202005051845, 202005122200, 202006171845, 202006232200,
            202007151845, 202008041845, 202008112200, 202009161845, 202009222200, 202010221745, 202011031645, 202011102000,
            202012161645, 202101211645, 202102021645, 202102232000, 202103171745, 202104132200, 202104201845, 202105041845,
            202105252200, 202106161845, 202107132200, 202107151845, 202108031845, 202108172200, 202109151845, 202110052100,
            202110171745, 202111021745, 202111232000, 202112151645, 202201261645, 202202011645, 202202222000, 202203161745,
            202204122200, 202204201845, 202205031845, 202205242200, 202206151845, 202207122200, 202207171845, 202208021845,
            202208162200, 202209141845, 202210042100, 202210171745, 202211011745, 202211222000, 202212141645, 202301241645,
            202301311645, 202302212000, 202303151745, 202304042200, 202304191845, 202305021845, 202305232200, 202306141845,
            202307112200, 202307181845, 202308011845, 202308152200, 202309201845, 202310032100, 202310161745, 202310311745,
            202311282000, 202312131645, 202401231645, 202402061645, 202402272000, 202403201745, 202404092200, 202404161845,
            202404301845, 202405212200, 202406191845, 202407092200, 202407161845, 202408061845, 202408132200, 202409181845,
            202410082100, 202410151745, 202411051645, 202411262000, 202412181645, 202501211645, 202502041645, 202502182000,
            202503191745, 202504082200, 202504161845, 202505061845, 202505272200, 202506181845, 202507082200, 202507201845,
            202508051845, 202508192200, 202509171845, 202510072100, 202510191745, 202511041645, 202511252000, 202512171645,
            202601221645, 202602031645, 202602172000, 202603181745, 202604072200, 202604201845, 202605051845, 202605262200,
            202606171845, 202607072200, 202607201845, 202608041845, 202609012200, 202609161845, 202610211745, 202610272100,
            202611031645, 202612082000, 202612161645, 202701261645, 202702021645, 202702092000, 202703162100, 202703171745,
            202704221845, 202705042200, 202706152200, 202708032200, 202709142200, 202710262100, 202712072000,
        };
        public static readonly long[] Chf =
        {
            201803150430, 201806210330, 201809200330, 201812130330, 201903210430, 201906130330, 201909190330, 201912120330,
            202003190430, 202006180330, 202009240330, 202012170330, 202103250430, 202106170330, 202109230330, 202112160330,
            202203240430, 202206160330, 202209220330, 202212150330, 202303230430, 202306220330, 202309210330, 202312140330,
            202403210430, 202406200330, 202409260330, 202412120330, 202503200430, 202506190330, 202509250330, 202512110330,
            202603190430, 202606180330, 202609240330, 202612100330, 202703180430, 202706240330, 202709230330, 202712160330,
        };
        public static readonly long[] Oil =
        {
            201801041100, 201801101030, 201801181100, 201801241030, 201801311030, 201802071030, 201802141030, 201802221100,
            201802281030, 201803071030, 201803141030, 201803211030, 201803281030, 201804041030, 201804111030, 201804181030,
            201804251030, 201805021030, 201805091030, 201805161030, 201805231030, 201805311100, 201806061030, 201806131030,
            201806201030, 201806271030, 201807051100, 201807111030, 201807181030, 201807251030, 201808011030, 201808081030,
            201808151030, 201808221030, 201808291030, 201809061100, 201809121030, 201809191030, 201809261030, 201810031030,
            201810111100, 201810171030, 201810241030, 201810311030, 201811071030, 201811151100, 201811211030, 201811281030,
            201812061100, 201812121030, 201812191030, 201812281100, 201901041100, 201901091030, 201901161030, 201901241100,
            201901301030, 201902061030, 201902131030, 201902211100, 201902271030, 201903061030, 201903131030, 201903201030,
            201903271030, 201904031030, 201904101030, 201904171030, 201904241030, 201905011030, 201905081030, 201905151030,
            201905221030, 201905301100, 201906051030, 201906121030, 201906191030, 201906261030, 201907031030, 201907101030,
            201907171030, 201907241030, 201907311030, 201908071030, 201908141030, 201908211030, 201908281030, 201909051100,
            201909111030, 201909181030, 201909251030, 201910021030, 201910091030, 201910171100, 201910231030, 201910301030,
            201911061030, 201911141100, 201911201030, 201911271030, 201912041030, 201912111030, 201912181030, 201912271100,
            202001031100, 202001081030, 202001151030, 202001231100, 202001291030, 202002051030, 202002121030, 202002201100,
            202002261030, 202003041030, 202003111030, 202003181030, 202003251030, 202004011030, 202004081030, 202004151030,
            202004221030, 202004291030, 202005061030, 202005131030, 202005201030, 202005281100, 202006031030, 202006101030,
            202006171030, 202006241030, 202007011030, 202007081030, 202007151030, 202007221030, 202007291030, 202008051030,
            202008121030, 202008191030, 202008261030, 202009021030, 202009101100, 202009161030, 202009231030, 202009301030,
            202010071030, 202010151100, 202010211030, 202010281030, 202011041030, 202011121100, 202011181030, 202011251030,
            202012021030, 202012091030, 202012161030, 202012231030, 202012301030, 202101061030, 202101131030, 202101221100,
            202101271030, 202102031030, 202102101030, 202102181100, 202102241030, 202103031030, 202103101030, 202103171030,
            202103241030, 202103311030, 202104071030, 202104141030, 202104211030, 202104281030, 202105051030, 202105121030,
            202105191030, 202105261030, 202106031100, 202106091030, 202106161030, 202106231030, 202106301030, 202107081100,
            202107141030, 202107211030, 202107281030, 202108041030, 202108111030, 202108181030, 202108251030, 202109011030,
            202109091100, 202109151030, 202109221030, 202109291030, 202110061030, 202110141100, 202110201030, 202110271030,
            202111031030, 202111101030, 202111171030, 202111241030, 202112011030, 202112081030, 202112151030, 202112221030,
            202112291030, 202201051030, 202201121030, 202201201100, 202201261030, 202202021030, 202202091030, 202202161030,
            202202241100, 202203021030, 202203091030, 202203161030, 202203231030, 202203301030, 202204061030, 202204131030,
            202204201030, 202204271030, 202205041030, 202205111030, 202205181030, 202205251030, 202206021100, 202206081030,
            202206151030, 202206291030, 202207071100, 202207131030, 202207201030, 202207271030, 202208031030, 202208101030,
            202208171030, 202208241030, 202208311030, 202209081100, 202209141030, 202209211030, 202209281030, 202210051030,
            202210131100, 202210191030, 202210261030, 202211021030, 202211091030, 202211161030, 202211231030, 202211301030,
            202212071030, 202212141030, 202212211030, 202212291100, 202301051100, 202301111030, 202301191100, 202301251030,
            202302011030, 202302081030, 202302151030, 202302231100, 202303011030, 202303081030, 202303151030, 202303221030,
            202303291030, 202304051030, 202304121030, 202304191030, 202304261030, 202305031030, 202305101030, 202305171030,
            202305241030, 202306011100, 202306071030, 202306141030, 202306221100, 202306281030, 202307061100, 202307121030,
            202307191030, 202307261030, 202308021030, 202308091030, 202308161030, 202308231030, 202308301030, 202309071100,
            202309131030, 202309201030, 202309271030, 202310041030, 202310121100, 202310181030, 202310251030, 202311011030,
            202311151030, 202311221030, 202311291030, 202312061030, 202312131030, 202312201030, 202312281100, 202401041100,
            202401101030, 202401181100, 202401241030, 202401311030, 202402071030, 202402141030, 202402221100, 202402281030,
            202403061030, 202403131030, 202403201030, 202403271030, 202404031030, 202404101030, 202404171030, 202404241030,
            202405011030, 202405081030, 202405151030, 202405221030, 202405301100, 202406051030, 202406121030, 202406201100,
            202406261030, 202407031030, 202407101030, 202407171030, 202407241030, 202407311030, 202408071030, 202408141030,
            202408211030, 202408281030, 202409051100, 202409111030, 202409181030, 202409251030, 202410021030, 202410091030,
            202410171100, 202410231030, 202410301030, 202411061030, 202411141100, 202411201030, 202411271030, 202412041030,
            202412111030, 202412181030, 202412271300, 202501021100, 202501081030, 202501151030, 202501231200, 202501291030,
            202502051030, 202502121030, 202502201200, 202502261030, 202503051030, 202503121030, 202503191030, 202503261030,
            202504021030, 202504091030, 202504161030, 202504231030, 202504301030, 202505071030, 202505141030, 202505211030,
            202505291200, 202506041030, 202506111030, 202506181030, 202506251030, 202507021030, 202507091030, 202507161030,
            202507231030, 202507301030, 202508061030, 202508131030, 202508201030, 202508271030, 202509041200, 202509101030,
            202509171030, 202509241030, 202510011030, 202510081030, 202510161200, 202510221030, 202510291030, 202511051030,
            202511131200, 202511191030, 202511261030, 202512031030, 202512101030, 202512171030, 202512291700, 202512311030,
            202601071030, 202601141030, 202601221200, 202601281030, 202602041030, 202602111030, 202602191200, 202602251030,
            202603041030, 202603111030, 202603181030, 202603251030, 202604011030, 202604081030, 202604151030, 202604221030,
            202604291030, 202605061030, 202605131030, 202605201030, 202605281200, 202606031030, 202606101030, 202606171030,
            202606241030, 202607011030, 202607081030, 202607151030, 202607221030, 202607291030, 202608051030, 202608121030,
            202608191030, 202608261030, 202609021030, 202609101200, 202609161030, 202609231030, 202609301030, 202610071030,
            202610151200, 202610211030, 202610281030, 202611041030, 202611121200, 202611181030, 202611251030, 202612021030,
            202612091030, 202612161030, 202612231030, 202612301030, 202701061030, 202701131030, 202701201030, 202701211200,
            202701271030, 202702031030, 202702101030, 202702171030, 202702181200, 202702241030, 202703031030, 202703101030,
            202703171030, 202703241030, 202703311030, 202704071030, 202704141030, 202704211030, 202704281030, 202705051030,
            202705121030, 202705191030, 202705261030, 202706021030, 202706031200, 202706091030, 202706161030, 202706231030,
            202706301030, 202707071030, 202707081200, 202707141030, 202707211030, 202707281030, 202708041030, 202708111030,
            202708181030, 202708251030, 202709011030, 202709081030, 202709091200, 202709151030, 202709221030, 202709291030,
            202710061030, 202710131030, 202710141200, 202710201030, 202710271030, 202711031030, 202711101030, 202711171030,
            202711241030, 202712011030, 202712081030, 202712151030, 202712221030, 202712291030,
        };
        // Releases of one currency's own events (USD core events are switched separately).
        public static long[] ForCurrency(string ccy)
        {
            switch (ccy)
            {
                case "USD": return UsdMore;
                case "EUR": return Eur;
                case "GBP": return Gbp;
                case "JPY": return Jpy;
                case "CAD": return Cad;
                case "AUD": return Aud;
                case "NZD": return Nzd;
                case "CHF": return Chf;
                case "OIL": return Oil;
                default: return new long[0];
            }
        }
        // Window length after the listed time (minutes) for events without a fixed release time.
        public static int DurationFor(string ccy) { return ccy == "JPY" ? 180 : 0; }
    }
    // NEWS-CALENDAR-END
}
