// Edge Research cBot side: the strategy interface a finalist implements. Mirrors engine/STRATEGY-API.md: one intent per decision bar
// from closed bars only; per-bar trail candidates and exit signals. The class rules, entry blocks, news modes, caps and every firm rule
// are applied by the harness (ErHarness), never by the strategy. Pure C# (no cAlgo types).
using System;
using System.Collections.Generic;

namespace EdgeResearch.Common
{
    public static class OType { public const int Market = 0, Stop = 1, Limit = 2; }

    /// <summary>One order intent, decided at bar i's close (STRATEGY-API "intents" row i). Distances in price units.</summary>
    public class Intent
    {
        public int Side;                     // +1 buy, -1 sell, 0 nothing
        public int OType;                    // OType.Market / Stop / Limit
        public double Price = double.NaN;    // stop / limit level (on the tick grid)
        public double SlDist = double.NaN;   // stop distance from the fill (required)
        public double TpDist = double.NaN;   // target distance from the fill (NaN = none)
        public long ExpiryMs;                // pending order life after going live (0 = until the next bar's close)
        public long HoldMs;                  // time exit after the fill (0 = none)
        public static readonly Intent None = new Intent();
    }

    /// <summary>Closed bars from the seed bar on (bid OHLC, UTC open times), as the referees keep them.</summary>
    public class BarSeries
    {
        public readonly List<long> OpenMs = new List<long>();
        public readonly List<double> O = new List<double>(), H = new List<double>(), L = new List<double>(), C = new List<double>();
        public long TfMs;
        public int Count { get { return C.Count; } }
        public long CloseMs(int i) { return OpenMs[i] + TfMs; }

        public bool Add(long openMs, double o, double h, double l, double c)
        {
            if (OpenMs.Count > 0 && openMs <= OpenMs[OpenMs.Count - 1]) return false;
            OpenMs.Add(openMs); O.Add(o); H.Add(h); L.Add(l); C.Add(c);
            return true;
        }
    }

    public interface IErStrategy
    {
        string Id { get; }                   // idea id + variant, e.g. "IDEA-1001-v1"; part of the order label
        char Class { get; }                  // 'A', 'B' or 'C' (the card's class)
        int Warmup { get; }                  // closed bars after the seed bar before any decision
        /// <summary>Bar i (the bar that just closed) was added: update indicators. Called once per bar, in order.</summary>
        void OnBar(BarSeries b, int i);
        /// <summary>The intent at bar i's close (Intent.None = nothing).</summary>
        Intent Decide(BarSeries b, int i);
        /// <summary>Candidate stop for an open long / short at bar i's close (NaN = none; tighten only, applied by the harness).</summary>
        double TrailLong(BarSeries b, int i);
        double TrailShort(BarSeries b, int i);
        /// <summary>Close an open long / short at market at bar i's close.</summary>
        bool ExitLong(BarSeries b, int i);
        bool ExitShort(BarSeries b, int i);
    }

    /// <summary>Indicator helpers as the referees compute them (plain sequential loops, double precision, from the seed bar).</summary>
    public class ErIndicators
    {
        private readonly List<double> _tr = new List<double>(), _atr = new List<double>();
        public double Atr(int i) { return i < _atr.Count ? _atr[i] : double.NaN; }

        /// <summary>Wilder 14 ATR: first value = mean of the first 14 true ranges; the seed bar's TR = high - low.</summary>
        public void UpdateAtr(BarSeries b, int i, int n = 14)
        {
            double tr = i == 0 ? b.H[i] - b.L[i] : Math.Max(b.H[i] - b.L[i], Math.Max(Math.Abs(b.H[i] - b.C[i - 1]), Math.Abs(b.L[i] - b.C[i - 1])));
            _tr.Add(tr);
            double a = double.NaN;
            if (i == n - 1) { double acc = 0.0; for (int j = 0; j <= i; j++) acc += _tr[j]; a = acc / n; }
            else if (i > n - 1) a = (_atr[i - 1] * (n - 1) + _tr[i]) / n;
            _atr.Add(a);
        }

        public static double Sma(List<double> x, int i, int n)
        {
            if (i < n - 1) return double.NaN;
            double acc = 0.0;
            for (int j = i - n + 1; j <= i; j++) acc += x[j];
            return acc / n;
        }
    }
}
