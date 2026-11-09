#!/usr/bin/env python3
"""Stats of one cTrader backtest report (HTML export) — tick IS, OOS, m1 checks — plus the Monte Carlo DD limits of PROTOCOL v2/v3.

Prints symbol, data type, period, trades, trades/month, net, PF, balance DD and equity DD (cTrader's own per-trade values, max over the
history), biggest trade's share of net, net without the 5 biggest trades, long vs short net, per-year net, and net without Feb–May 2020.

--mc N   bootstrap the trade order N times (default 10,000 when given without a number): OOS DD limits for the pre-registration —
         balance limit = 95th-percentile max balance DD of the resampled trade lists; equity limit = that × (report equity DD / balance DD).
--oos-check BAL EQ TPM   apply the OOS pass criteria (net > 0, PF >= 1.15, trades/month within ±50% of TPM, no trade > 30% of net,
         balance DD <= BAL and equity DD <= EQ) and print PASS / FAIL per criterion.
--rules 2026-10-31   the OOS rule set for cells pre-registered from 2026-10-31 on (user): "no trade > 30% of net" is replaced by
         "net > 0 and PF >= 1.0 without the best trade", and trades/month fails only below 50% of TPM (no upper bound).
         Without --rules: the original rule set (cells pre-registered before 2026-10-31).
--json   machine-readable output.

Usage: python3 tools/report_stats.py <report.html> [--mc [N]] [--oos-check BAL EQ TPM [--rules 2026-10-31]] [--json]
"""
import json, random, sys
from collections import defaultdict
from datetime import datetime, timezone


def load(path):
    s = open(path, encoding="utf-8", errors="ignore").read()
    i = s.index('id="backtesting-report">') + len('id="backtesting-report">')
    return json.loads(s[i:s.index("</script>", i)])


def max_dd(nets):
    eq = pk = dd = 0.0
    for x in nets:
        eq += x; pk = max(pk, eq); dd = max(dd, pk - eq)
    return dd


def stats(rep):
    m = rep["main"]
    T = sorted(rep["history"]["items"], key=lambda t: t["closeTime"])
    nets = [t["net"] for t in T]
    net = sum(nets)
    w = sum(x for x in nets if x > 0); l = -sum(x for x in nets if x < 0)
    p = m["testingPeriod"]
    months = (p["endDate"] - p["startDate"]) / (1000 * 86400 * 30.4375)
    yrs, side = defaultdict(float), defaultdict(float)
    covid = 0.0
    for t in T:
        d = datetime.fromtimestamp(t["entryTime"] / 1000, tz=timezone.utc)
        yrs[datetime.fromtimestamp(t["closeTime"] / 1000, tz=timezone.utc).year] += t["net"]
        side[t["direction"].lower()] += t["net"]
        if d.year == 2020 and 2 <= d.month <= 5:
            covid += t["net"]
    top = sorted(nets, reverse=True)
    return {
        "symbol": m["symbol"], "data": m["data"]["type"], "period": p["formatted"], "tf": m["period"],
        "trades": len(T), "tpm": len(T) / months if months else 0.0,
        "net": net, "pf": w / l if l else float("inf"),
        "bal_dd": max((t.get("balanceDrawdownAbsolute") or 0) for t in T) if T else 0.0,
        "eq_dd": max((t.get("equityDrawdownAbsolute") or 0) for t in T) if T else 0.0,
        "seq_dd": max_dd(nets),  # closed-trade DD from the trade order (what the bootstrap resamples)
        "top_share": top[0] / net if T and net > 0 else float("nan"),
        "net_wo_top5": net - sum(x for x in top[:5] if x > 0),
        "long": side["buy"], "short": side["sell"],
        "years": {str(k): v for k, v in sorted(yrs.items())},
        "net_wo_covid": net - covid,
        "_nets": nets,
    }


def monte_carlo(nets, n, seed=1):
    rnd = random.Random(seed)
    dds = sorted(max_dd(rnd.choices(nets, k=len(nets))) for _ in range(n))
    return {"runs": n, "p50": dds[n // 2], "p95": dds[int(0.95 * n) - 1], "p99": dds[int(0.99 * n) - 1]}


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith("-"):
        sys.exit(__doc__)
    s = stats(load(a[0]))
    out = {k: v for k, v in s.items() if not k.startswith("_")}
    if "--mc" in a:
        i = a.index("--mc")
        n = int(a[i + 1]) if i + 1 < len(a) and a[i + 1].isdigit() else 10000
        mc = monte_carlo(s["_nets"], n)
        ratio = s["eq_dd"] / s["bal_dd"] if s["bal_dd"] else 1.0
        mc.update({"bal_limit": mc["p95"], "eq_limit": mc["p95"] * ratio, "eq_bal_ratio": ratio})
        out["mc"] = mc
    if "--oos-check" in a:
        i = a.index("--oos-check")
        bal, eq, tpm = (float(x) for x in a[i + 1:i + 4])
        if "--rules" in a and a[a.index("--rules") + 1] == "2026-10-31":
            rest = sorted(s["_nets"])[:-1]
            g, l = sum(x for x in rest if x > 0), -sum(x for x in rest if x < 0)
            pf_wo = g / l if l else float("inf")
            out["oos"] = {
                "net > 0": s["net"] > 0, "PF >= 1.15": s["pf"] >= 1.15,
                "trades/month >= 50% of IS": s["tpm"] >= 0.5 * tpm,
                "without the best trade: net > 0 and PF >= 1.0": sum(rest) > 0 and pf_wo >= 1.0,
                f"balance DD <= {bal:,.0f}": s["bal_dd"] <= bal, f"equity DD <= {eq:,.0f}": s["eq_dd"] <= eq,
            }
        else:
            out["oos"] = {
                "net > 0": s["net"] > 0, "PF >= 1.15": s["pf"] >= 1.15,
                "trades/month within ±50%": 0.5 * tpm <= s["tpm"] <= 1.5 * tpm,
                "no trade > 30% of net": s["net"] > 0 and s["top_share"] <= 0.30,
                f"balance DD <= {bal:,.0f}": s["bal_dd"] <= bal, f"equity DD <= {eq:,.0f}": s["eq_dd"] <= eq,
            }
        out["oos_verdict"] = "PASS" if all(out["oos"].values()) else "FAIL"
    if "--json" in a:
        print(json.dumps(out, indent=1)); return
    print(f"{s['symbol']} {s['tf']} · {s['data']} · {s['period']}")
    print(f"trades {s['trades']} ({s['tpm']:.1f}/month) · net {s['net']:,.0f} · PF {s['pf']:.2f} · "
          f"balance DD {s['bal_dd']:,.0f} · equity DD {s['eq_dd']:,.0f}")
    print(f"biggest trade {s['top_share']:.0%} of net · net without top 5 {s['net_wo_top5']:,.0f} "
          f"({s['net_wo_top5'] / s['net']:.0%}) · long {s['long']:,.0f} / short {s['short']:,.0f} · without Feb–May 2020 {s['net_wo_covid']:,.0f}"
          if s["net"] > 0 else f"long {s['long']:,.0f} / short {s['short']:,.0f}")
    print("years: " + " · ".join(f"{y} {v:,.0f}" for y, v in s["years"].items()))
    if "mc" in out:
        mc = out["mc"]
        print(f"Monte Carlo ({mc['runs']:,} resamples of the trade order): max balance DD p50 {mc['p50']:,.0f} · p95 {mc['p95']:,.0f} · p99 {mc['p99']:,.0f}")
        print(f"OOS limits: balance DD <= {mc['bal_limit']:,.0f} · equity DD <= {mc['eq_limit']:,.0f} (× {mc['eq_bal_ratio']:.2f} equity/balance)")
    if "oos" in out:
        for k, v in out["oos"].items():
            print(f"  {'PASS' if v else 'FAIL'}  {k}")
        print(f"OOS verdict: {out['oos_verdict']}")


if __name__ == "__main__":
    main()
