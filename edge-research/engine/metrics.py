"""Ledger metrics of one test (ledger/README.md): computed from the trade logs of all its symbols, per news mode, on FTMO's
net R (judged) with IC's shown. Deterministic: the Monte Carlo drawdown uses a fixed seed.
"""
import numpy as np

from engine.timeutil import ams_offset_ms

DAY = 86_400_000
MC_RUNS = 1000
MC_SEED = 20261112


def _cat(logs, key):
    parts = [np.asarray(l[key]) for l in logs if len(l["bar"])]
    return np.concatenate(parts) if parts else np.zeros(0)


def max_dd(r):
    """Largest peak-to-trough fall of the cumulative R (closed trades in order), as a positive number."""
    if not len(r):
        return 0.0
    eq = np.concatenate([[0.0], np.cumsum(r)])
    return float(np.max(np.maximum.accumulate(eq) - eq))


def mc_dd95(r, runs=MC_RUNS, seed=MC_SEED):
    """95th percentile of the max drawdown over random reorderings of the trades."""
    if len(r) < 2:
        return max_dd(r)
    rng = np.random.default_rng(seed)
    return float(np.percentile([max_dd(rng.permutation(r)) for _ in range(runs)], 95))


def daily_series(r, exit_t, first_ms, end_ms):
    """Daily R on the Amsterdam weekdays of the period (days without exits are 0). An exit on an Amsterdam Saturday or Sunday
    (e.g. at the Sunday-evening reopen) counts on the next Monday (fixed 2026-11-13: such exits were dropped)."""
    loc = np.asarray(exit_t, np.int64) + ams_offset_ms(exit_t)
    d = loc // DAY
    wd = (d + 3) % 7                                                   # 0 = Monday (day 0 of the epoch is a Thursday)
    d = d + np.where(wd == 5, 2, np.where(wd == 6, 1, 0))
    d0 = (first_ms + int(ams_offset_ms([first_ms])[0])) // DAY
    d1 = (end_ms + int(ams_offset_ms([end_ms])[0])) // DAY
    days = np.arange(d0, d1 + 1)
    days = days[((days + 3) % 7) < 5]
    s = np.zeros(len(days))
    i = np.searchsorted(days, d)
    ok = (i < len(days)) & (days[np.minimum(i, len(days) - 1)] == d)
    np.add.at(s, i[ok], np.asarray(r, float)[ok])
    return s


def nw_lag(t):
    """Newey-West lag for a series of t days: floor(4 (t / 100)^(2/9)) (DESIGN A11.4)."""
    return int(np.floor(4.0 * (t / 100.0) ** (2.0 / 9.0))) if t > 0 else 0


def nw_variance_ratio(s):
    """Newey-West long-run variance (Bartlett weights, lag nw_lag) of a daily series divided by its plain variance (DESIGN A11.4).
    1 for independent days; above 1 when daily P&L is positively autocorrelated. 1.0 when the series is too short or flat."""
    x = np.asarray(s, float)
    t = len(x)
    if t < 3:
        return 1.0
    x = x - x.mean()
    g0 = float(np.sum(x * x)) / t                                      # not @: Accelerate matmul warns spuriously
    if g0 <= 0:
        return 1.0
    lr = g0
    for lag in range(1, min(nw_lag(t), t - 1) + 1):
        lr += 2.0 * (1.0 - lag / (nw_lag(t) + 1.0)) * float(np.sum(x[lag:] * x[:-lag])) / t
    return lr / g0


def daily_sharpe(r, exit_t, first_ms, end_ms):
    """Annualised Sharpe of daily R (daily_series)."""
    if not len(r):
        return None
    s = daily_series(r, exit_t, first_ms, end_ms)
    sd = s.std(ddof=1)
    return round(float(s.mean() / sd * np.sqrt(252)), 3) if sd > 0 else None


def _group(r, keys):
    out = {}
    for k in np.unique(keys):
        m = keys == k
        out[str(k)] = {"n": int(m.sum()), "r": round(float(r[m].sum()), 3)}
    return out


def compute(logs, counters, first_ms, end_ms, venue="ftmo"):
    """Metrics for one news mode. logs: trade logs (engine.tradelog.build) of every symbol; counters: summed kernel counters."""
    r = _cat(logs, f"r_net_{venue}")
    n = len(r)
    out = {"trades": n, "dropped": {k: v for k, v in counters.items() if v}}
    if not n:
        return out
    exit_t = _cat(logs, "exit_t").astype(np.int64)
    o = np.argsort(exit_t, kind="stable")
    r, exit_t = r[o], exit_t[o]
    gross = _cat(logs, "r_gross")[o]
    ic = _cat(logs, "r_net_ic")[o]
    side = _cat(logs, "side")[o]
    sym = _cat(logs, "symbol")[o].astype(str)
    sess = _cat(logs, "session")[o].astype(str)
    hold = _cat(logs, "hold_min")[o]
    year = exit_t.astype("datetime64[ms]").astype("datetime64[Y]").astype(int) + 1970
    pos, neg = r[r > 0].sum(), -r[r < 0].sum()
    sd = r.std(ddof=1) if n > 1 else 0.0
    by_year = _group(r, year)
    top5 = np.sort(r)[::-1][:5].sum()
    out.update({
        "net_r": round(float(r.sum()), 3), "r_per_trade_gross": round(float(gross.mean()), 4), "r_per_trade_net": round(float(r.mean()), 4),
        "r_per_trade_net_ic": round(float(ic.mean()), 4), "profit_factor": round(float(pos / neg), 3) if neg > 0 else None,
        "t_stat": round(float(r.mean() / sd * np.sqrt(n)), 3) if sd > 0 else None,
        "daily_sharpe": daily_sharpe(r, exit_t, first_ms, end_ms), "max_dd_r": round(max_dd(r), 3), "mc95_dd_r": round(mc_dd95(r), 3),
        "years_positive_pct": round(100 * float(np.mean([v["r"] > 0 for v in by_year.values()])), 1),
        "long": {"n": int((side > 0).sum()), "r": round(float(r[side > 0].sum()), 3)},
        "short": {"n": int((side < 0).sum()), "r": round(float(r[side < 0].sum()), 3)},
        "top5_share": round(float(top5 / r.sum()), 3) if r.sum() > 0 else None,
        "by_year": by_year, "by_symbol": _group(r, sym), "by_session": _group(r, sess),
        "cost_share": round(float((gross.sum() - r.sum()) / abs(gross.sum())), 3) if gross.sum() != 0 else None,
        "hold": {"share_under_2min": round(float((hold < 2).mean()), 4), "median_min": round(float(np.median(hold)), 2),
                 "fail_under_2min": bool((hold < 2).mean() > 0.10)},
    })
    for c in ("spread", "comm", "swap", "slip"):
        out[f"{c}_r_per_trade"] = round(float(_cat(logs, f"r_{c}_{venue}").mean()), 4)
    fl = _cat(logs, "news_flags").astype(np.int64)
    out["news"] = {"held": int(((fl & 1) > 0).sum()), "far_stop": int(((fl & 2) > 0).sum()), "closed": int(((fl & 4) > 0).sum())}
    return out


def news_flag(by_mode):
    """DESIGN §3.6 flag (6): a strategy keeping less than half its M0 profit in M3 is a news strategy."""
    m0, m3 = by_mode.get("M0", {}).get("net_r"), by_mode.get("M3", {}).get("net_r")
    if m0 is None or m3 is None or m0 <= 0:
        return None
    return bool(m3 < 0.5 * m0)
