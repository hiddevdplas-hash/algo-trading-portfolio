// Unit tests of the cBot core (ErCore.cs, ErStrategy.cs): plain dotnet, no cTrader. Run: cTrader-Bots/common/tests/run_tests.sh
// Args: <repo cTrader-Bots/common folder> <vectors.json> <calendar.csv>
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using EdgeResearch.Common;

static class T
{
    static int pass, fail;
    static readonly List<string> failures = new List<string>();

    static void Ok(bool c, string what) { if (c) pass++; else { fail++; failures.Add(what); } }
    static void Eq<TV>(TV a, TV b, string what) { Ok(EqualityComparer<TV>.Default.Equals(a, b), what + ": got " + a + ", want " + b); }
    static void Near(double a, double b, string what, double tol = 1e-6) { Ok(Math.Abs(a - b) <= tol, what + ": got " + a + ", want " + b); }
    static long Ms(int y, int mo, int d, int h = 0, int mi = 0) { return Clock.Ms(new DateTime(y, mo, d, h, mi, 0, DateTimeKind.Utc)); }

    static int Main(string[] args)
    {
        string root = args[0], vec = args[1], cal = args[2];
        Configs(Path.Combine(root, "firms"));
        Limits();
        GuardsTests();
        SizingTests();
        CapsTests();
        TagAndState();
        ClockTests();
        SymbolTests();
        CalendarTests(cal);
        Parity(vec, cal);
        Console.WriteLine($"{pass} passed, {fail} failed");
        foreach (var f in failures.Take(40)) Console.WriteLine("  FAIL " + f);
        return fail == 0 ? 0 : 1;
    }

    // ---------------------------------------------------------------------------------------------------------------------------
    static void Configs(string dir)
    {
        foreach (var f in Directory.GetFiles(dir, "*.cfg"))
        {
            foreach (var st in FirmConfig.Parse(File.ReadAllText(f), null).StageList())
            {
                var c = FirmConfig.Load(f, st);
                var l = LossLimits.From(c, 100000);
                var g = GuardSettings.From(c);
                Ok(c.Num("risk_pct") > 0 && c.Num("risk_pct") <= 2.0, Path.GetFileName(f) + " " + st + " risk_pct in (0, 2]");
                Ok(new[] { "M0", "M1", "M2", "M3" }.Contains(c.Str("news_mode")), Path.GetFileName(f) + " " + st + " news_mode");
                Ok("ABC".Contains(c.Str("max_class")), Path.GetFileName(f) + " " + st + " max_class");
                Ok(l.MaxFloor() < 100000 && (c.Flag("test_only", false) || g.FlattenAtOfDaily > g.EntryRoomOfDaily), Path.GetFileName(f) + " " + st + " limits");
                l.LastResetAtOrBefore(Ms(2024, 3, 15, 12));
            }
        }
        var ftmo = FirmConfig.Load(Path.Combine(dir, "FTMO.cfg"), "funded");
        Eq(ftmo.Num("risk_pct"), 0.75, "FTMO funded risk");
        Eq(ftmo.Str("news_mode"), "M3", "FTMO funded mode");
        Eq(ftmo.Str("max_class"), "B", "FTMO funded class");
        Eq(FirmConfig.Load(Path.Combine(dir, "FTMO.cfg"), "phase1").Str("news_mode"), "M2", "FTMO phase1 mode");
        Eq(ftmo.Canonical("US500.cash"), "US500", "FTMO US500 name");
        Eq(ftmo.Canonical("EUR/USD"), "EURUSD", "slash FX name");
        Eq(ftmo.Canonical("XAU/USD"), "XAUUSD", "slash metal name");
        Eq(ftmo.Canonical("NATGAS.cash"), null, "unknown name");
        var inf = FirmConfig.Load(Path.Combine(dir, "INSTANT-FUNDING.cfg"), "funded");
        Eq(inf.Canonical("WTI"), "XTIUSD", "alternative names");
        Eq(inf.BySize("class_lot_cap.metal", 100000), 3.0, "IF metal lots 100K");
        Ok(double.IsNaN(inf.BySize("class_lot_cap.metal", 75000)), "IF size not in table");
        Eq(inf.Num("idea_risk_cap_pct_initial"), 1.5, "IF funded idea cap");
        Ok(!FirmConfig.Load(Path.Combine(dir, "INSTANT-FUNDING.cfg"), "eval").Has("idea_risk_cap_pct_initial"), "IF idea cap funded only");
        Ok(FirmConfig.Load(Path.Combine(dir, "FUNDINGPIPS.cfg"), "funded").Str("max_class") == "A", "FP funded class A");
        Ok(FirmConfig.Load(Path.Combine(dir, "FUNDINGPIPS.cfg"), "eval").Flag("news_whole_talks", false), "FP whole talks");
        bool threw = false;
        try { FirmConfig.Load(Path.Combine(dir, "FTMO.cfg"), "eval"); } catch (FormatException) { threw = true; }
        Ok(threw, "unknown stage refused");
        threw = false;
        try { FirmConfig.Parse("a = 1\na = 2\n", null); } catch (FormatException) { threw = true; }
        Ok(threw, "duplicate key refused");
    }

    static void Limits()
    {
        var ftmo = new LossLimits { DailyPct = 5, MaxPct = 10, Initial = 100000, DailyBase = "balance", DailyPctOf = "initial", ResetZone = "Europe/Prague", MaxType = "static" };
        Near(ftmo.DailyFloor(ftmo.BaseOf(102000, 99000)), 97000, "FTMO floor = balance at reset - 5% of initial");
        Near(ftmo.MaxFloor(), 90000, "FTMO max floor");
        // 00:00 Prague: CET 23:00 UTC the day before; CEST 22:00 UTC
        Eq(ftmo.LastResetAtOrBefore(Ms(2024, 3, 30, 12)), Ms(2024, 3, 29, 23), "FTMO reset CET");
        Eq(ftmo.LastResetAtOrBefore(Ms(2024, 4, 2, 12)), Ms(2024, 4, 1, 22), "FTMO reset CEST");
        var inf = new LossLimits { DailyPct = 3, MaxPct = 8, Initial = 100000, DailyBase = "max_balance_equity", DailyPctOf = "base", ResetZone = "America/New_York", ResetH = 17, MaxType = "static" };
        double b = inf.BaseOf(100000, 101000);
        Near(b, 101000, "IF base = max(balance, equity)");
        Near(inf.DailyFloor(b), 101000 - 3030, "IF floor = base - 3% of base");
        // 17:00 New York in the March DST gap (US summer from 10 Mar, EU winter until 31 Mar) = 21:00 UTC = 22:00 Amsterdam
        Eq(inf.LastResetAtOrBefore(Ms(2024, 3, 20, 12)), Ms(2024, 3, 19, 21), "IF reset in the DST gap");
        Eq(inf.LastResetAtOrBefore(Ms(2024, 3, 5, 12)), Ms(2024, 3, 4, 22), "IF reset in winter");
        var bf = new LossLimits { DailyPct = 5, MaxPct = 10, Initial = 100000, DailyBase = "max_balance_equity", DailyPctOf = "initial", ResetZone = "Europe/Amsterdam", ResetH = 23, ResetM = 30, ResetWindowMin = 29, MaxType = "static" };
        Near(bf.DailyFloor(101000), 96000, "BF floor (S3 example)");
        Ok(bf.InResetWindow(Ms(2024, 1, 10, 22, 45)) && !bf.InResetWindow(Ms(2024, 1, 10, 23, 0)), "BF reset window 23:30-23:59 Amsterdam");
        var aq = new LossLimits { DailyPct = 3, MaxPct = 12, Initial = 100000, DailyBase = "max_balance_equity", DailyPctOf = "base", ResetZone = "UTC", MaxType = "static" };
        Near(aq.DailyFloor(102000), 98940, "Aqua floor (S1 example)");
        var fk = new LossLimits { DailyPct = 5, MaxPct = 10, Initial = 100000, DailyBase = "equity", DailyPctOf = "base", ResetZone = "UTC", MaxType = "static" };
        Near(fk.BaseOf(100000, 98000), 98000, "Fintokei base = equity");
    }

    static AccountView Acct(double eq, double openRisk = 0)
    {
        return new AccountView { Initial = 100000, Balance = 100000, Equity = eq, DayBase = 100000, DayLimit = 5000, DayFloor = 95000, MaxFloor = 90000, OpenRisk = openRisk };
    }

    static void GuardsTests()
    {
        var g = new GuardSettings();
        Ok(Guards.Entry(g, Acct(100000), 2000, 0).Ok, "fresh day: 2% trade allowed");
        Ok(!Guards.Entry(g, Acct(100000, 2000), 2000, 0).Ok, "second 2% trade: worst-case room 1000 < 2500 -> refused");
        Ok(Guards.Entry(g, Acct(100000, 2000), 2000, 0).Reason.StartsWith("daily_guard"), "reason daily_guard");
        Ok(Guards.Entry(g, Acct(100000, 1000), 1000, 0).Ok, "two 1% trades: room 3000 >= 2500");
        var d = Guards.Entry(g, Acct(100000, 2500), 1000, 0);
        Ok(!d.Ok && d.Reason.StartsWith("daily_guard"), "open risk 2.5% + 1%: daily guard first");
        var gcap = new GuardSettings { EntryRoomOfDaily = 0.9 };
        d = Guards.Entry(gcap, Acct(100000, 2500), 1000, 0);
        Ok(!d.Ok && d.Reason.StartsWith("open_risk_cap"), "open-risk cap 60% of the daily limit");
        // max-loss distance (D1.5): 3 risks -> half, 1 risk -> stop
        var a = Acct(92500); a.DayBase = 92000; a.DayFloor = 87000;    // a new day near the max floor (90,000): room 2,500 < 3 risks
        d = Guards.Entry(g, a, 1000, 0);
        Ok(d.Ok && d.Scale == 0.5, "within 3 risks of the max floor: half risk");
        a.Equity = 90900;
        Ok(!Guards.Entry(g, a, 1000, 0).Ok && Guards.Entry(g, a, 1000, 0).Reason.StartsWith("maxloss_near"), "within 1 risk: stop");
        var gi = new GuardSettings { IdeaRiskCapPctInitial = 1.5 };
        var ai = Acct(100000); ai.OpenRiskSameIdea = 600;
        Ok(Guards.Entry(gi, ai, 600, 0).Ok, "IF idea 1.2% < 1.35%");
        ai.OpenRiskSameIdea = 800;
        Ok(!Guards.Entry(gi, ai, 600, 0).Ok, "IF idea 1.4% > 1.35% (1.5% less the slippage buffer)");
        var gb = new GuardSettings { OpenRiskCapPctBalance = 0.75 };
        Ok(Guards.Entry(gb, Acct(100000), 600, 0).Ok && !Guards.Entry(gb, Acct(100000, 300), 600, 0).Ok, "Aqua funded open risk <= 0.75% of balance");
        var gf = new GuardSettings { OpenRiskCapPctInitial = 3 };
        Ok(!Guards.Entry(gf, Acct(100000, 2000), 800, 0).Ok, "Fintokei 3% cap on open trades");
        var gm = new GuardSettings { MarginCap = 0.6 };
        var am = Acct(100000); am.Margin = 50000;
        Ok(!Guards.Entry(gm, am, 500, 15000).Ok && Guards.Entry(gm, am, 500, 5000).Ok, "margin cap");
        // flatten
        Ok(Guards.Flatten(g, Acct(96500)) == null, "loss 3,500 < 80%: no flatten");
        Ok(Guards.Flatten(g, Acct(96000)) != null, "loss 4,000 = 80%: flatten");
        var gx = new GuardSettings { MaxFlattenRoomOfDaily = 0.2 };
        var ax = Acct(90900); ax.DayFloor = 85000;
        Ok(Guards.Flatten(gx, ax) != null && Guards.Flatten(gx, ax).StartsWith("guard_max"), "max-loss flatten (proposal)");
        var gw = new GuardSettings { FloatFlattenPctBalance = 0.9 };
        var aw = Acct(99050); aw.FloatingPnl = -950;
        Ok(Guards.Flatten(gw, aw) != null && Guards.Flatten(gw, aw).StartsWith("guard_float"), "Aqua floating guard");
    }

    static void SizingTests()
    {
        // EURUSD-like, USD account: pip 0.0001, pip value per unit 0.0001 USD; 20-pip stop, $2,000 -> 1,000,000 units
        Near(Sizing.Units(2000, 0.0020, 0.0001, 0.0001, 0, 1000, 1000, 10000000), 1000000, "units from risk");
        Near(Sizing.Units(2000, 0.0020, 0.0001, 0.0001, 0.00005, 1000, 1000, 10000000), 975000, "commission included, rounded down to the step");
        Near(Sizing.Units(2000, 0.0020, 0.0001, 0.0001, 0, 1000, 1000, 500000), 500000, "capped by max units");
        Near(Sizing.Units(0.5, 0.0020, 0.0001, 0.0001, 0, 1000, 1000, 1e9), 0, "below the minimum -> 0");
        Near(Sizing.RiskMoney(100000, 2.0, 4), 1000, "sqrt(n) sizing (D1.2)");
    }

    static void CapsTests()
    {
        var c = new Caps();
        long d = Ms(2024, 3, 12, 8);
        for (int k = 0; k < 10; k++) c.AddFill(d + k * 600000);
        Ok(c.DayCapHit(d + 7 * 3600000), "10 fills today -> day cap");
        Ok(!c.DayCapHit(Ms(2024, 3, 13, 8)), "next Amsterdam day: free");
        // the Amsterdam day starts at 23:00 UTC in winter
        var c2 = new Caps();
        for (int k = 0; k < 10; k++) c2.AddFill(Ms(2024, 3, 12, 22, 0) + k * 60000);
        Ok(!c2.DayCapHit(Ms(2024, 3, 12, 23, 30)), "fills before 00:00 Amsterdam count for the previous day");
        c.AddOrderEvent(d); c.AddOrderEvent(d + 30000);
        Ok(c.RateCapHit(d + 50000) && !c.RateCapHit(d + 60001), "<= 2 order events in 60 s");
        // request budget (the harness's own path): TEST 120 / 3 instances = 40 a day; an entry needs 3 of room, a trail 1
        var rb = new RequestBudget(120, 3);
        long t0 = Ms(2024, 3, 12, 9);
        for (int k = 0; k < 37; k++) rb.Add(t0);
        Ok(rb.Budget == 40 && rb.Ok(t0, true), "budget: 37 used, an entry fits (37 + 3 = 40)");
        rb.Add(t0);
        Ok(!rb.Ok(t0, true) && rb.Ok(t0, false), "budget: 38 used, no entry, a trail still fits");
        rb.Add(t0); rb.Add(t0);
        Ok(!rb.Ok(t0, false), "budget: 40 used, nothing but exits");
        Ok(rb.Ok(Ms(2024, 3, 12, 23, 1), true) && rb.Count == 0, "budget resets at Amsterdam midnight (23:00 UTC in winter)");
        Ok(new RequestBudget(0, 3).Ok(t0, true), "no budget configured: always room");
    }

    static void TagAndState()
    {
        var t = new OrderTag { BarMs = 1710230400000, LiveMs = 1710231300000, EndMs = -1, HoldMs = 86400000, SlDist = 0.00123, TpDist = double.NaN, Risk = 1234.567 };
        string s = t.Encode();
        var u = OrderTag.Decode(s);
        Ok(u != null && u.BarMs == t.BarMs && u.LiveMs == t.LiveMs && u.EndMs == -1 && u.HoldMs == t.HoldMs && u.SlDist == t.SlDist && double.IsNaN(u.TpDist) && Math.Abs(u.Risk - 1234.57) < 1e-9, "tag round trip");
        Ok(s.Length <= 90, "tag fits a comment (" + s.Length + " chars)");
        Ok(OrderTag.Decode("manual trade") == null && OrderTag.Decode("ER1|bx") == null, "foreign comments ignored");
        string dir = Path.Combine(Path.GetTempPath(), "er-state-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var a = new StateFile(Path.Combine(dir, "acc1_A_EURUSD.state")); a.Set("daybase.100", "100000"); a.Save();
        var b = new StateFile(Path.Combine(dir, "acc1_B_XAUUSD.state")); b.Set("daybase.100", "100250.5"); b.Save(); b.Set("x", "1"); b.Save();
        var c = new StateFile(Path.Combine(dir, "acc2_A_EURUSD.state")); c.Set("daybase.100", "999999"); c.Save();
        Near(StateFile.MaxRecordedBase(dir, "acc1", 100), 100250.5, "highest recorded base of the account's instances");
        Ok(double.IsNaN(StateFile.MaxRecordedBase(dir, "acc1", 200)), "no record for another reset");
        Eq(new StateFile(Path.Combine(dir, "acc1_B_XAUUSD.state")).Get("x"), "1", "state survives a reload");
    }

    static void ClockTests()
    {
        // FX week Sun 22:00 -> Fri 22:00 UTC with a daily 21:55-22:05 break; a holiday on Wed 25 Dec 2024
        var sess = new List<MarketClock.Session>();
        for (int d = 0; d < 5; d++)
            sess.Add(new MarketClock.Session { StartDay = (DayOfWeek)d, Start = d == 0 ? new TimeSpan(22, 0, 0) : new TimeSpan(22, 5, 0), EndDay = (DayOfWeek)(d + 1), End = d == 4 ? new TimeSpan(22, 0, 0) : new TimeSpan(21, 55, 0) });
        var hol = new[] { new MarketClock.Closed { StartMs = Ms(2024, 12, 24, 22, 0), EndMs = Ms(2024, 12, 25, 22, 0) } };
        var mc = new MarketClock(sess, hol);
        Ok(mc.PreCloseBlockStart(Ms(2024, 3, 15, 19, 59), 7200000, 7200000) < 0, "Friday 19:59 UTC: not yet");
        Eq(mc.PreCloseBlockStart(Ms(2024, 3, 15, 20, 0), 7200000, 7200000), Ms(2024, 3, 15, 20, 0), "Friday 20:00 UTC: pre-close block");
        Ok(mc.PreCloseBlockStart(Ms(2024, 3, 13, 21, 0), 7200000, 7200000) < 0, "daily 10-min break: no block");
        // the 21:55 daily break runs into the holiday, so the close is 21:55 and the market reopens with Wednesday's 22:05 session
        Eq(mc.PreCloseBlockStart(Ms(2024, 12, 24, 20, 30), 7200000, 7200000), Ms(2024, 12, 24, 19, 55), "holiday close >= 2 h: block");
        long c, r;
        Ok(mc.NextClose(Ms(2024, 12, 24, 12), out c, out r) && c == Ms(2024, 12, 24, 21, 55) && r == Ms(2024, 12, 25, 22, 5), "close and reopen around a holiday");
        Ok(!mc.NextClose(Ms(2024, 3, 16, 12), out c, out r), "Saturday: closed");
        // DESIGN A8 with the backtest table shift: today's (Nov 2026, US winter) FX table Sun 22:00 -> Fri 22:00 UTC, anchored to New York
        var shift = MarketClock.AnchoredShift("America/New_York", Ms(2026, 11, 13, 12));
        var fx = new MarketClock(sess, null, shift);
        Ok(fx.NextClose(Ms(2024, 3, 8, 12), out c, out r) && c == Ms(2024, 3, 8, 22, 0), "shifted table: winter close 22:00 UTC (8 Mar 2024)");
        Ok(fx.NextClose(Ms(2024, 3, 15, 12), out c, out r) && c == Ms(2024, 3, 15, 21, 0), "shifted table: US-summer close 21:00 UTC (15 Mar 2024)");
        Ok(fx.NextClose(Ms(2024, 4, 5, 12), out c, out r) && c == Ms(2024, 4, 5, 21, 0) && r == Ms(2024, 4, 7, 21, 0), "shifted table: summer close and Sunday open");
        Eq(fx.PreCloseBlockStart(Ms(2024, 3, 15, 19, 0), ClassRules.MinBreak, 2 * Clock.HOUR), Ms(2024, 3, 15, 19, 0), "pre-close block from 19:00 UTC in US summer");
        Ok(new MarketClock(sess, null, MarketClock.AnchoredShift("America/New_York", Ms(2024, 3, 15, 12))).NextClose(Ms(2024, 3, 15, 12), out c, out r) && c == Ms(2024, 3, 15, 22, 0), "same offset: no shift (live)");
        // A8 flat times
        Eq(ClassRules.BreakFlat('B', Ms(2024, 3, 8, 22, 0)), Ms(2024, 3, 8, 21, 45), "A8 B, winter Friday: 22:45 Amsterdam is earlier than close - 5");
        Eq(ClassRules.BreakFlat('B', Ms(2024, 3, 15, 21, 0)), Ms(2024, 3, 15, 20, 55), "A8 B, US-only DST Friday: close - 5 min (21:55 Amsterdam)");
        Eq(ClassRules.BreakFlat('A', Ms(2024, 4, 5, 21, 0)), Ms(2024, 4, 5, 20, 45), "A8 A, summer Friday: 22:45 Amsterdam = 20:45 UTC first");
        Eq(ClassRules.BreakFlat('C', Ms(2024, 3, 15, 21, 0)), -1L, "A8: class C never");
        var br = fx.Breaks(Ms(2024, 3, 11), Ms(2024, 3, 22, 23, 0), ClassRules.MinBreak);
        Ok(br.Count == 2 && br[0].Close == Ms(2024, 3, 15, 21, 0) && br[1].Close == Ms(2024, 3, 22, 21, 0) && br.All(x => x.Kind == MarketBreak.Weekend), "breaks: Friday weekends only (daily 10-min breaks ignored)");
        Eq(ClassRules.FlatAt('B', Ms(2024, 3, 15, 18, 30), Ms(2024, 3, 15, 20, 55), br), Ms(2024, 3, 15, 20, 55), "B flat at 20:55 UTC on 15 Mar");
        Eq(ClassRules.FlatAt('B', Ms(2024, 3, 15, 18, 30), Ms(2024, 3, 15, 20, 54), br), -1L, "B not before");
        Ok(ClassRules.FlatAt('A', Ms(2024, 3, 13, 12), Ms(2024, 3, 13, 21, 45), br) == Ms(2024, 3, 13, 21, 45) && ClassRules.FlatAt('C', Ms(2024, 3, 15, 12), Ms(2024, 3, 18, 12), br) < 0, "A daily 22:45 kept; C never");
        Ok(ClassRules.FlatAt('B', Ms(2024, 3, 13, 12), Ms(2024, 3, 13, 23, 0), br) < 0, "B: no 22:45 on a weekday");
        var hb = mc.Breaks(Ms(2024, 12, 23), Ms(2024, 12, 26), ClassRules.MinBreak);
        Ok(hb.Count == 1 && hb[0].Kind == MarketBreak.Holiday && ClassRules.BreakFlat('B', hb[0].Close, hb[0].Kind) == Ms(2024, 12, 24, 21, 45), "holiday close: B flat 22:45 Amsterdam (close 21:55 UTC, -5 = 21:50)");
        // a symbol with a regular daily break of >= 2 h (STOXX50-like: 20:00 -> 06:00 UTC on weekdays): A flattens before it, B doesn't
        var eu = new List<MarketClock.Session>();
        for (int d = 1; d <= 5; d++) eu.Add(new MarketClock.Session { StartDay = (DayOfWeek)d, Start = new TimeSpan(6, 0, 0), EndDay = (DayOfWeek)d, End = new TimeSpan(20, 0, 0) });
        var euc = new MarketClock(eu, null);
        var eb = euc.Breaks(Ms(2024, 3, 11), Ms(2024, 3, 16), ClassRules.MinBreak);
        Ok(eb.Count == 5 && eb.Take(4).All(x => x.Kind == MarketBreak.Daily) && eb[4].Kind == MarketBreak.Weekend, "regular daily breaks and the weekend classified");
        Eq(ClassRules.FlatAt('A', Ms(2024, 3, 12, 10), Ms(2024, 3, 12, 19, 55), eb), Ms(2024, 3, 12, 19, 55), "A: flat before a daily break >= 2 h");
        Eq(ClassRules.FlatAt('B', Ms(2024, 3, 12, 10), Ms(2024, 3, 13, 10), eb), -1L, "B: not before the regular daily break");
        Eq(ClassRules.FlatAt('B', Ms(2024, 3, 15, 10), Ms(2024, 3, 15, 19, 55), eb), Ms(2024, 3, 15, 19, 55), "B: flat before the weekend");
        // per-exchange shift: EU index table (Berlin) in the US-only DST week moves with Berlin, not New York
        var eus = new MarketClock(eu, null, MarketClock.AnchoredShift(SessionZones.Default("STOXX50"), Ms(2026, 11, 13, 12)));
        Ok(eus.NextClose(Ms(2024, 3, 15, 12), out c, out r) && c == Ms(2024, 3, 15, 20, 0), "STOXX50: no shift in the US-only DST week (Berlin still on winter time)");
        Ok(eus.NextClose(Ms(2024, 4, 5, 12), out c, out r) && c == Ms(2024, 4, 5, 19, 0), "STOXX50: shifted 1 h from 31 Mar (Berlin summer time)");
        // break rows from the calendar win where complete
        var calb = NewsCalendar.Parse("#er-calendar,v1\n#valid_to,2024-12-31\n#rules," + NewsCalendar.RulesLine + "\n#breaks_complete,2024-03-01,2024-03-31\n#break,EURUSD," + Ms(2024, 3, 15, 20, 57) + "," + Ms(2024, 3, 17, 21, 3) + ",weekend\nstart_utc_ms,end_utc_ms,type_id,ccy,kind,tier,research,sources,range,end_status,alt_starts\n");
        var bb = new BreakBook(calb, "EURUSD", fx);
        Ok(bb.RowCount == 1 && bb.RowsCover(Ms(2024, 3, 14), Ms(2024, 3, 16)) && bb.Between(Ms(2024, 3, 14), Ms(2024, 3, 16))[0].Close == Ms(2024, 3, 15, 20, 57), "break rows used where complete");
        Ok(bb.Between(Ms(2024, 4, 4), Ms(2024, 4, 6))[0].Close == Ms(2024, 4, 5, 21, 0), "outside the rows: session table");
        Eq(bb.PreCloseBlockStart(Ms(2024, 3, 15, 19, 0), 2 * Clock.HOUR), Ms(2024, 3, 15, 18, 57), "pre-close block from the row's close");
        Ok(bb.LeadDue(Ms(2024, 3, 15, 20, 53), 2 * Clock.HOUR, 5 * Clock.MIN) && !bb.LeadDue(Ms(2024, 3, 15, 20, 51), 2 * Clock.HOUR, 5 * Clock.MIN), "firm break lead from the row");
        // class rules: 22:45 Amsterdam; B on Fridays; nightly block to 00:15
        Eq(ClassRules.LastFlatAtOrBefore('A', Ms(2024, 3, 29, 21, 45)), Ms(2024, 3, 29, 21, 45), "A flat CET");
        Eq(ClassRules.LastFlatAtOrBefore('A', Ms(2024, 4, 1, 21, 0)), Ms(2024, 4, 1, 20, 45), "A flat CEST");
        Eq(ClassRules.LastFlatAtOrBefore('B', Ms(2024, 4, 3, 12)), Ms(2024, 3, 29, 21, 45), "B flat = last Friday");
        Eq(ClassRules.LastFlatAtOrBefore('C', Ms(2024, 4, 3, 12)), -1L, "C never flat");
        Ok(ClassRules.FlatDue('A', Ms(2024, 3, 12, 10), Ms(2024, 3, 12, 21, 45)) && !ClassRules.FlatDue('A', Ms(2024, 3, 12, 21, 50), Ms(2024, 3, 12, 22, 0)), "flat due only after going live");
        Ok(ClassRules.NightBlockStart(Ms(2024, 7, 1, 22, 14)) >= 0 && ClassRules.NightBlockStart(Ms(2024, 7, 1, 22, 15)) < 0, "night block ends 00:15 Amsterdam (summer)");
        Eq(ClassRules.AmsDayStart(Ms(2024, 3, 12, 23, 30)), Ms(2024, 3, 12, 23, 0), "Amsterdam day start");
    }

    static void SymbolTests()
    {
        Ok(Symbols.BlocksSymbol("USD", "EURUSD") && Symbols.BlocksSymbol("USD", "US500") && Symbols.BlocksSymbol("EUR", "DE40") && !Symbols.BlocksSymbol("EUR", "UK100") && Symbols.BlocksSymbol("OIL", "XBRUSD"), "event -> symbols (DESIGN §3.6 item 4)");
        Eq(Symbols.AssetClass("XTIUSD"), "oil", "asset class");
        var b = Symbols.Blocs("EURUSD");
        Ok(b.Count == 1 && b[0].Key == "USD" && b[0].Value == -1, "long EURUSD = short USD");
        var j = Symbols.Blocs("USDJPY");
        Ok(j.Count == 2 && j.Any(x => x.Key == "USD" && x.Value == 1) && j.Any(x => x.Key == "JPY" && x.Value == 1), "USDJPY in USD and JPY");
        Ok(Symbols.Blocs("EURGBP").Count == 0 && Symbols.Blocs("DE40")[0].Key == "EQ", "crosses: no bloc; indices EQ");
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
        Eq(ErPaths.Expand("~/cAlgo/x"), home + "/cAlgo/x", "path ~/ expands to home");
        Eq(ErPaths.Expand("~" + home + "/Projects/a b"), home + "/Projects/a b", "path ~/Users/<me>/... read as absolute (first R1 try)");
        Eq(ErPaths.Expand(" /abs/p "), "/abs/p", "absolute path unchanged");
    }

    static void CalendarTests(string path)
    {
        var cal = NewsCalendar.Load(path);
        Ok(cal.Problems.Count == 0, "test calendar parses: " + string.Join(" | ", cal.Problems));
        Ok(cal.Events.Count > 100 && cal.FarBp.Count > 0, "test calendar has events and far thresholds");
        var talk = cal.Events.FirstOrDefault(e => NewsCalendar.IsTalk(e.Kind) && !e.Range && e.EndMs < 0);
        if (talk != null)
        {
            long o, c;
            NewsCalendar.EventWindow(talk, -1, false, out o, out c);
            Ok(o == talk.StartMs - 6 * Clock.MIN && c == talk.StartMs + 6 * Clock.MIN, "A6: talk with official start -> T-6 / T+6");
            NewsCalendar.EventWindow(talk, -1, true, out o, out c);
            Ok(c == talk.StartMs + NewsCalendar.FpAssumedEnd[talk.Kind] + 5 * Clock.MIN, "A6.4 FundingPips: end + 5 min (assumed length)");
        }
        else Ok(false, "no talk in the test calendar");
        var rng = cal.Events.FirstOrDefault(e => e.Range);
        if (rng != null)
        {
            long o, c;
            NewsCalendar.EventWindow(rng, -1, false, out o, out c);
            Ok(o == rng.StartMs - 6 * Clock.MIN && c == rng.EndMs + (NewsCalendar.IsTalk(rng.Kind) ? 5 : 6) * Clock.MIN, "range event: whole range");
        }
        // the engine's break rows (export --breaks): class B flats on the test Fridays come from them
        var book = new BreakBook(cal, "EURUSD", null);
        Ok(book.RowCount >= 20 && book.RowsCover(Ms(2024, 3, 14), Ms(2024, 3, 16)), "test calendar: EURUSD break rows complete in March");
        long fb = ClassRules.FlatAt('B', Ms(2024, 3, 15, 18, 30), Ms(2024, 3, 15, 21, 0), book.Between(Ms(2024, 3, 14), Ms(2024, 3, 16)));
        Ok(fb >= Ms(2024, 3, 15, 20, 52) && fb < Ms(2024, 3, 15, 20, 53), "B flat 20:52 UTC on 15 Mar (engine close 20:57:xx - 5 min): " + Clock.Iso(fb));
        Eq(ClassRules.FlatAt('B', Ms(2024, 3, 8, 18, 30), Ms(2024, 3, 8, 22, 0), book.Between(Ms(2024, 3, 7), Ms(2024, 3, 9))), Ms(2024, 3, 8, 21, 45), "B flat 21:45 UTC on 8 Mar (22:45 Amsterdam first)");
        var us = new BreakBook(cal, "US500", null);
        Ok(us.Between(Ms(2024, 5, 27), Ms(2024, 5, 28)).Any(b => Math.Abs(b.Close - Ms(2024, 5, 27, 17, 0)) < Clock.MIN && b.Kind == MarketBreak.Holiday), "US500 Memorial Day early close from the rows");
        var bad = NewsCalendar.Parse(File.ReadAllText(path).Replace("#rules,design=A6", "#rules,design=A5"));
        Ok(bad.Problems.Count > 0, "a calendar with other window rules is refused");
        // firm-only events count only with the firm's sources; alt (firm calendar) times widen the window
        var ev = new NewsEvent { StartMs = Ms(2024, 5, 1, 12), TypeId = "X", Ccy = "USD", Kind = "release", Tier = 2, Research = false, Sources = new[] { "FXStreet" } };
        ev.AltStarts.Add(new KeyValuePair<string, long>("FXStreet", Ms(2024, 5, 1, 12, 2)));
        var c1 = new NewsCalendar(); c1.Events.Add(ev);
        Ok(c1.Windows("EURUSD", "M3", null).Count == 0, "firm-only event ignored without the firm's source");
        var w = c1.Windows("EURUSD", "M3", new HashSet<string> { "FXStreet" });
        Ok(w.Count == 1 && w[0].Start == Ms(2024, 5, 1, 11, 54) && w[0].End == Ms(2024, 5, 1, 12, 8) && w[0].Kind == 1, "union with the firm's calendar time");
        Ok(c1.Windows("EURUSD", "M2", new HashSet<string> { "FXStreet" })[0].Kind == 2, "tier 2 in M2: hold without target");
        Ok(NewsCalendar.StartedBetween(w, Ms(2024, 5, 1, 11), Ms(2024, 5, 1, 11, 55)) && !NewsCalendar.StartedBetween(w, Ms(2024, 5, 1, 11, 55), Ms(2024, 5, 1, 12, 30)), "window start between");
    }

    static void Parity(string vecPath, string calPath)
    {
        var v = JsonDocument.Parse(File.ReadAllText(vecPath)).RootElement;
        var brk = v.GetProperty("breaks").EnumerateArray().Select(x => new MarketBreak { Close = x[0].GetInt64(), Reopen = x[1].GetInt64(), Kind = x[2].GetString() }).ToList();
        long f0 = Ms(2024, 2, 1), f1 = Ms(2024, 12, 1);
        foreach (var cls in new[] { 'A', 'B' })
        {
            var want = v.GetProperty("flats_A8_" + cls).EnumerateArray().Select(x => x.GetInt64()).ToList();
            var mine = ClassRules.FlatTimes(cls, f0, f1, brk);
            int diff = want.Except(mine).Count() + mine.Except(want).Count();
            Ok(diff == 0 && want.Count > 0, "parity A8: class " + cls + " flats with " + brk.Count + " breaks (" + want.Count + " engine, " + mine.Count + " cBot, " + diff + " differ)");
        }
        foreach (var cls in new[] { 'A' })
        {
            var flats = v.GetProperty("flats_" + cls).EnumerateArray().Select(x => x.GetInt64()).ToList();
            int bad = 0;
            for (int k = 0; k < flats.Count; k++)
            {
                if (ClassRules.LastFlatAtOrBefore(cls, flats[k]) != flats[k]) bad++;
                if (k > 0 && ClassRules.LastFlatAtOrBefore(cls, flats[k] - 1) != flats[k - 1]) bad++;
            }
            Ok(bad == 0 && flats.Count > 0, "parity: class " + cls + " flats (" + flats.Count + ", " + bad + " differ)");
        }
        int nb = 0, nn = 0;
        foreach (var p in v.GetProperty("night_probes").EnumerateArray())
        {
            nn++;
            if ((ClassRules.NightBlockStart(p[0].GetInt64()) >= 0) != p[1].GetBoolean()) nb++;
        }
        Ok(nb == 0, "parity: nightly block on " + nn + " probes (" + nb + " differ)");
        foreach (var d in v.GetProperty("day_starts").EnumerateArray())
            Ok(ClassRules.AmsDayStart(d.GetInt64()) == d.GetInt64(), "parity: Amsterdam day start " + d.GetInt64());
        foreach (var r in v.GetProperty("resets").EnumerateObject())
        {
            var parts = r.Name.Split(' ');
            var hm = parts[1].Split(':');
            var lim = new LossLimits { ResetZone = parts[0], ResetH = int.Parse(hm[0]), ResetM = int.Parse(hm[1]) };
            int bad = 0, n = 0;
            foreach (var p in r.Value.EnumerateArray()) { n++; if (lim.LastResetAtOrBefore(p[0].GetInt64()) != p[1].GetInt64()) bad++; }
            Ok(bad == 0, "parity: resets " + r.Name + " on " + n + " probes (" + bad + " differ)");
        }
        var cal = NewsCalendar.Load(calPath);
        int wn = 0, wbad = 0;
        foreach (var kv in v.GetProperty("windows").EnumerateObject())
        {
            var key = kv.Name.Split('|');
            var mine = cal.Windows(key[0], key[1], null);
            var want = kv.Value.EnumerateArray().ToList();
            wn += want.Count;
            bool same = mine.Count == want.Count;
            for (int k = 0; same && k < want.Count; k++)
            {
                var w = want[k];
                double f = w[3].ValueKind == JsonValueKind.Null ? double.NaN : w[3].GetDouble();
                same = mine[k].Start == w[0].GetInt64() && mine[k].End == w[1].GetInt64() && mine[k].Kind == w[2].GetInt32() &&
                       ((double.IsNaN(f) && double.IsNaN(mine[k].FarBp)) || Math.Abs(f - mine[k].FarBp) < 1e-9);
                if (!same && mine[k].Kind == 2 && mine[k].Start == w[0].GetInt64() && mine[k].End == w[1].GetInt64() && w[2].GetInt32() == 2)
                    same = true;   // a hold window's threshold is never used (the kernel reads it for flatten windows only)
            }
            if (!same) { wbad++; failures.Add("  windows differ: " + kv.Name + " (mine " + mine.Count + ", engine " + want.Count + ")"); }
        }
        Ok(wbad == 0, "parity: news windows, " + v.GetProperty("windows").EnumerateObject().Count() + " symbol x mode sets, " + wn + " windows (" + wbad + " sets differ)");
    }
}
