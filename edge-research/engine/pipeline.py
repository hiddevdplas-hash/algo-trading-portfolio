"""Pipeline mechanics (DESIGN §6.3 screen, §6.6 walk-forward G1, §6.6a near miss, §6.7 stress G2): pure functions on trade logs.

The bar values live in engine/thresholds.json (part of the engine hash). The same functions judge real ideas and the random
strategies of the null calibration (§8). They compute zones and pass / fail; only the gatekeeper moves an idea to candidate.

Walk-forward mechanics (defaults sent to the gatekeeper for confirmation 2026-11-12):
  - every grid point runs once over the full research period (all four news modes); trades belong to a window by entry time;
  - in each 24-month training window a point's score = net R after FTMO costs, the worst of M0 / M2 / M3; the chosen point has the
    best average score over itself and its +-1-step grid neighbours (ties: the first in grid order);
  - the chosen point's trades in the following 3-month test window are stitched; G1 is judged on the stitched unseen trades only;
  - one parameter path for all modes and firms (rule B); a firm is eligible if the stitched result passes in its mode (rule C).
"""
import hashlib
import json
import math
import os
from statistics import NormalDist

import numpy as np

from engine import metrics as M

ENGINE = os.path.dirname(os.path.abspath(__file__))
TH = json.load(open(os.path.join(ENGINE, "thresholds.json")))
REPO = os.path.dirname(ENGINE)
LEDGER = os.path.join(REPO, "ledger")
KCACHE = os.path.join(REPO, "runs", "_kcache")
DAY = 86_400_000
LOG_KEYS = ("entry_t", "exit_t", "side", "r_mid", "r_gross", "r_net_ftmo", "r_net_ic", "symbol", "session", "vol_third", "regime", "bloc",
            "r_swap_ftmo", "news_flags")


def month_ms(m, plus=0):
    return int((np.datetime64(m, "M") + plus).astype("datetime64[ms]").astype(np.int64))


# ------------------------------------------------------------------ logs
def load_logs(run_dir, symbols, modes):
    """{mode: one log (dict of arrays) over all symbols} from a runner test folder."""
    out = {}
    for m in modes:
        parts = []
        for s in symbols:
            z = np.load(os.path.join(run_dir, f"{s}_{m}.npz"), allow_pickle=False)
            parts.append({k: z[k] for k in LOG_KEYS if k in z.files})
        out[m] = concat(parts)
    return out


def concat(parts):
    """One log from several (symbols, windows). A part without trades adds nothing: it is left out before the columns are matched,
    because a trade file with no trades lacks the context columns (fixed 2026-11-15: one empty symbol dropped 'vol_third' etc.
    from the whole log)."""
    full = [p for p in parts if n_of(p)]
    parts = full or parts[:1]
    keys = set.intersection(*(set(p) for p in parts)) if parts else set(LOG_KEYS)
    return {k: np.concatenate([np.asarray(p[k]) for p in parts]) if parts else np.zeros(0) for k in keys}


def take(log, mask):
    return {k: np.asarray(v)[mask] for k, v in log.items()}


def n_of(log):
    return len(log["entry_t"]) if "entry_t" in log else 0


def tstat(r):
    r = np.asarray(r, float)
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(len(r))) if sd > 0 else 0.0


def pf(r):
    r = np.asarray(r, float)
    neg = -r[r < 0].sum()
    return float(r[r > 0].sum() / neg) if neg > 0 else (np.inf if r.sum() > 0 else 0.0)


# ------------------------------------------------------------------ screen (§6.3)
def slices(log):
    """The fixed slice list: name -> mask (same for every idea and the random strategies)."""
    s = {}
    for v in ("asia", "london", "ny"):
        s[f"session={v}"] = log["session"].astype(str) == v
    for v in ("low", "mid", "high"):
        s[f"vol={v}"] = log["vol_third"].astype(str) == v
    for v in ("trend", "range"):
        s[f"regime={v}"] = log["regime"].astype(str) == v
    s["side=long"], s["side=short"] = log["side"] > 0, log["side"] < 0
    for v in ("equities", "usd", "metals", "oil"):
        s[f"bloc={v}"] = log["bloc"].astype(str) == v
    s["recent"] = log["entry_t"] >= month_ms(TH["screen"]["recent_from"])
    return s


def is_green(r):
    c = TH["screen"]
    r = np.asarray(r, float)
    return len(r) >= c["green_min_trades"] and r.mean() >= c["green_net_r_per_trade"] and tstat(r) >= c["green_t"]


def screen_zone(log_m0, edge_r=0.0):
    """Zone of a quick-screen run, judged on M0. Green and the slice route: after FTMO costs. Amber's t >= 1.5: before costs, at mid
    prices (DESIGN §6.3, A11.1). edge_r: a synthetic strategy's planted edge (the job's synthetic_edge_r), which the trade file's
    r_mid leaves out; 0 for real ideas."""
    net, gross = log_m0["r_net_ftmo"].astype(float), log_m0["r_gross"].astype(float)
    mid = log_m0["r_mid"].astype(float) + float(edge_r or 0.0)
    out = {"trades": len(net), "net_r_per_trade": round(float(net.mean()), 4) if len(net) else None,
           "t_net": round(tstat(net), 3), "t_mid": round(tstat(mid), 3), "t_gross": round(tstat(gross), 3)}
    if is_green(net):
        out.update(zone="green", green_slices=[])
        return out
    gs = [k for k, m in slices(log_m0).items() if is_green(net[m])] if len(net) else []
    amber = tstat(mid) >= TH["screen"]["amber_mid_t"] or bool(gs)
    out.update(zone="amber" if amber else "red", green_slices=gs)
    return out


# ------------------------------------------------------------------ walk-forward (§6.6)
def wf_windows():
    """(train_start, test_start, test_end) in UTC ms: train 24 months, test 3, step 3, first test 2016-11, to 2024-12."""
    w = TH["walk_forward"]
    out = []
    k = 0
    last = month_ms(w["last_month"], 1)
    while True:
        ts = np.datetime64(w["first_test"], "M") + k * w["step_months"]
        a, b = month_ms(str(ts), -w["train_months"]), month_ms(str(ts))
        e = min(month_ms(str(ts), w["test_months"]), last)
        if b >= last:
            break
        out.append((a, b, e))
        k += 1
    return out


def grid_neighbours(shape):
    """For each flat grid index: itself plus its +-1-step neighbours along each axis."""
    idx = np.arange(int(np.prod(shape))).reshape(shape)
    out = []
    for flat in range(idx.size):
        pos = np.unravel_index(flat, shape)
        nb = [flat]
        for ax in range(len(shape)):
            for d in (-1, 1):
                q = list(pos)
                q[ax] += d
                if 0 <= q[ax] < shape[ax]:
                    nb.append(int(idx[tuple(q)]))
        out.append(nb)
    return out


def wf_select(grid_logs, shape, exclude=None, *, default):
    """Chosen grid point per window. grid_logs: list (flat grid order) of {mode: log}. exclude(log) -> mask of trades to leave out
    of the training scores (the FX 2015 stress). default: the flat index of the card's default point, chosen when a training
    window holds no trades at any point (DESIGN A11.2; it was grid point 0)."""
    if not 0 <= int(default) < len(grid_logs):
        raise ValueError(f"wf_select: default {default} outside the grid of {len(grid_logs)}")
    modes = [m for m in TH["walk_forward"]["score_modes"] if m in grid_logs[0]]
    nb = grid_neighbours(shape)
    choices = []
    for a, b, _ in wf_windows():
        score = np.zeros(len(grid_logs))
        n_tr = 0
        for p, gl in enumerate(grid_logs):
            vals = []
            for m in modes:
                lg = gl[m]
                keep = (lg["entry_t"] >= a) & (lg["entry_t"] < b)
                if exclude is not None:
                    keep &= ~exclude(lg)
                vals.append(float(lg["r_net_ftmo"][keep].sum()))
                n_tr += int(keep.sum())
            score[p] = min(vals)
        if n_tr == 0:
            choices.append(int(default))
            continue
        avg = np.array([score[n].mean() for n in nb])
        choices.append(int(np.argmax(avg)))
    return choices


def wf_stitch(grid_logs, choices, mode, offsets=None):
    """The unseen trades: per window, the chosen point's trades entered in the test window. offsets: per-window replacement of
    the chosen point (the parameter-neighbour stress)."""
    parts = []
    for k, (_, b, e) in enumerate(wf_windows()):
        p = choices[k] if offsets is None else offsets[k]
        lg = grid_logs[p][mode]
        parts.append(take(lg, (lg["entry_t"] >= b) & (lg["entry_t"] < e)))
    return concat(parts)


def year_blocks(log, from_ms=None):
    """Net R per 12-month block of the unseen period (from the first test month, or a regime date); a short last block joins the
    one before."""
    w = TH["walk_forward"]
    start = from_ms if from_ms is not None else month_ms(w["first_test"])
    end = month_ms(w["last_month"], 1)
    edges = []
    t = np.datetime64(int(start), "ms").astype("datetime64[M]")
    while month_ms(str(t)) < end:
        edges.append(month_ms(str(t)))
        t = t + w["block_months"]
    if len(edges) > 1 and end - edges[-1] < (edges[1] - edges[0]) * 0.5:
        edges.pop()
    edges.append(end)
    r = log["r_net_ftmo"].astype(float)
    et = log["entry_t"]
    return [float(r[(et >= edges[i]) & (et < edges[i + 1])].sum()) for i in range(len(edges) - 1)]


def dd_bar_r(firm="FTMO"):
    f = TH["firms"][firm]
    return f["max_loss_pct"] / f["funded_risk_pct"] * f["dd_share"]


def fit_risk_pct(mc95_dd_r, firm="FTMO"):
    """DESIGN A9.1: the largest risk per trade (% of the account) at which the Monte Carlo 95th-percentile drawdown stays <= the
    firm's share (dd_share) of its max loss. None when the drawdown is 0 (no limit from drawdown)."""
    f = TH["firms"][firm]
    return round(f["max_loss_pct"] * f["dd_share"] / mc95_dd_r, 4) if mc95_dd_r > 0 else None


def luck_bar(k, from_ms=None, vr=1.0):
    """DESIGN A10.3, A11.4: the count-adjusted (luck) bar on the stitched unseen daily Sharpe at k effective tries:
    mu0 + sigma * Phi^-1(q^(1/k)) with mu0 = 0 and sigma = sigma0 * sqrt(years0 / the route's unseen years) * max(1, sqrt(vr));
    years = years0 for a route judged over the whole unseen period, shorter from a regime date; vr = the Newey-West variance ratio of
    the route's stitched unseen daily net R (variance_ratio)."""
    L = TH["luck_bar"]
    if k is None or not k >= 1:
        raise ValueError(f"luck bar: k must be >= 1, not {k}")
    if vr is None or not np.isfinite(vr):
        raise ValueError(f"luck bar: variance ratio {vr}")
    sd, years = L["sigma0"], None
    if from_ms is not None:
        years = (month_ms(TH["walk_forward"]["last_month"], 1) - from_ms) / (365.25 * DAY)
        sd = L["sigma0"] * math.sqrt(L["years0"] / years)
    sd *= max(1.0, math.sqrt(vr))
    return {"k": round(float(k), 3), "bar": round(L["mu0"] + sd * NormalDist().inv_cdf(L["quantile"] ** (1.0 / k)), 4),
            "sigma": round(sd, 4), "years": None if years is None else round(years, 3), "vr": round(float(vr), 4)}


def unseen_daily(log, from_ms=None):
    """The stitched unseen daily net R (FTMO) of a log, from the first test month (or a regime date) to the end of the period."""
    w = TH["walk_forward"]
    first = from_ms if from_ms is not None else month_ms(w["first_test"])
    k = log["entry_t"] >= first
    r, x = log["r_net_ftmo"][k].astype(float), log["exit_t"][k]
    o = np.argsort(x, kind="stable")
    return M.daily_series(r[o], x[o], first, month_ms(w["last_month"], 1))


def variance_ratio(log, from_ms=None):
    """DESIGN A11.4: Newey-West long-run variance / plain variance of the stitched unseen daily net R."""
    return float(M.nw_variance_ratio(unseen_daily(log, from_ms)))


def short_hold_share(log):
    """Share of trades held under hold_short_minutes (DESIGN §4.2)."""
    if not n_of(log):
        return 0.0
    h = (np.asarray(log["exit_t"], np.int64) - np.asarray(log["entry_t"], np.int64)) / 60_000
    return float((h < TH["walk_forward"]["hold_short_minutes"]).mean())


def g1(log, firm="FTMO", from_ms=None, *, k, luck=None):
    """G1 bars on stitched unseen trades (one news mode). from_ms: a declared regime date (§6.4): judged from that date.
    k (required, keyword): the effective number of tries for the luck bar (DESIGN A10.3-4, `count_k`); None skips the luck bar,
    which only the null calibration does (it applies the bar in its report). The luck bar is a safety bar: never a near miss.
    luck: a route G1's stored luck bar, reused as it is (same k, sigma and bar) by the stress re-checks swap0 / fx2015 (A11.4;
    `stress_g1`). DESIGN A11.2: more than 10% of trades held under 2 min fails ('hold_time', a safety bar).
    DESIGN A9: the Monte Carlo 95% drawdown is no longer a bar (nor decides eligibility); it is reported with each firm's fit risk."""
    w, nm = TH["walk_forward"], TH["near_miss"]
    if from_ms is not None:
        log = take(log, log["entry_t"] >= from_ms)
    r = log["r_net_ftmo"].astype(float)
    order = np.argsort(log["exit_t"], kind="stable")
    blocks = year_blocks(log, from_ms)
    ypos = float(np.mean([b > 0 for b in blocks])) if blocks else 0.0
    mc = M.mc_dd95(r[order]) if len(r) else 0.0
    min_trades = w["regime_min_trades"] if from_ms is not None else w["min_trades"]
    sharpe = M.daily_sharpe(r[order], log["exit_t"][order], from_ms or month_ms(w["first_test"]), month_ms(w["last_month"], 1)) \
        if len(r) > 1 else None
    short = short_hold_share(log)
    vals = {"trades": len(r), "profit_factor": pf(r), "years_positive": ypos, "mc95_dd_r": mc, "short_hold_share": short}
    hold_ok = short <= w["hold_short_max_share"]
    bars = {"hold_time": (hold_ok, hold_ok),                            # a safety bar: no near miss
            "trades": (len(r) >= min_trades, len(r) >= nm["min_trades"]),
            "profit_factor": (vals["profit_factor"] >= w["profit_factor"], vals["profit_factor"] >= nm["profit_factor"]),
            "years_positive": (ypos >= w["years_positive"], ypos >= nm["years_positive"])}
    if luck is not None:
        if k is not None and round(float(k), 3) != luck["k"]:
            raise ValueError(f"g1: k {k} differs from the stored luck bar's k {luck['k']}")
        k = luck["k"]
    elif k is not None:
        luck = luck_bar(k, from_ms, variance_ratio(log, from_ms))
    if k is not None:
        ok = sharpe is not None and sharpe >= luck["bar"]
        bars["luck"] = (ok, ok)                                          # a safety bar: no near miss
    failed = [x for x, (ok, _) in bars.items() if not ok]
    near = len(failed) == 1 and failed[0] not in SAFETY and bars[failed[0]][1]
    return {"values": {x: (round(v, 4) if isinstance(v, float) and np.isfinite(v) else v) for x, v in vals.items()},
            "daily_sharpe": sharpe, "failed": failed, "pass": not failed, "near_miss": bool(near), "regime_from": from_ms,
            "fit_risk_pct": {f: fit_risk_pct(mc, f) for f in TH["firms"]}, "luck": luck}


def stress_g1(g1_res, from_ms=None, firm="FTMO"):
    """The G1 re-check for the swap0 / fx2015 stress logs of a route: the same k, sigma and bar as the route's own G1 (A11.4)."""
    lk = g1_res.get("luck")
    return lambda lg: g1(lg, firm, from_ms, k=None if lk is None else lk["k"], luck=lk)


def eligible_modes(g1_by_mode, allow_near_miss=True):
    """Firm modes (M1-M3) whose stitched result passes G1 (or is a near miss); a strategy eligible at >= 1 firm goes on (rule D)."""
    return [m for m in ("M1", "M2", "M3") if m in g1_by_mode and (g1_by_mode[m]["pass"] or (allow_near_miss and g1_by_mode[m]["near_miss"]))]


# ------------------------------------------------------------------ stress (§6.7)
def g2(base, mode, cls, fx, stressed, neighbours_logs, g1_fn, declared_symbols=None):
    """G2 for one mode. base: stitched unseen log; stressed: {'noise': log, 'cost': log, 'swap0': log, 'fx2015': log} (stitched
    with the same parameter path, or re-selected for fx2015); neighbours_logs: stitched logs one grid step each way.
    Returns per test (pass, near miss) and the overall verdict (near miss allowed on at most one non-safety test, and only if G1
    had none)."""
    s, nm = TH["stress"], TH["near_miss"]
    r = base["r_net_ftmo"].astype(float)
    p0 = float(r.sum())
    out = {}

    def keep(lg):
        return float(lg["r_net_ftmo"].astype(float).sum()) / p0 if p0 > 0 else 0.0

    if "noise" in stressed:
        k = keep(stressed["noise"])
        out["noise"] = (k >= s["noise_keep"], k >= nm["noise_keep"], round(k, 3))
    if "cost" in stressed:
        f = pf(stressed["cost"]["r_net_ftmo"].astype(float))
        out["cost"] = (f >= s["cost_profit_factor"], f >= nm["cost_profit_factor"], round(f, 3))
    if cls in ("B", "C") and "swap0" in stressed:
        ok = g1_fn(stressed["swap0"])["pass"]
        out["swap0"] = (ok, ok, None)                                         # safety: no near miss
    if neighbours_logs:
        k = min(keep(lg) for lg in neighbours_logs)
        out["neighbours"] = (k >= s["neighbour_keep"], k >= nm["neighbour_keep"], round(k, 3))
    yb = year_blocks(base)
    no_best = p0 - max(yb) if yb else p0
    top5 = p0 - float(np.sort(r)[::-1][:5].sum())
    out["without_best_year"] = (no_best > 0, no_best > 0, round(no_best, 3))
    out["without_top5"] = (top5 > 0, top5 > 0, round(top5, 3))
    if fx and "fx2015" in stressed:
        ok = g1_fn(stressed["fx2015"])["pass"]
        out["fx2015"] = (ok, ok, None)
    for name, m in (("long", base["side"] > 0), ("short", base["side"] < 0)):
        v = float(r[m].mean()) if m.any() else 0.0
        out[name] = (v >= s["side_min_r_per_trade"] or not m.any(), v >= s["side_min_r_per_trade"] or not m.any(), round(v, 4))
    # DESIGN A4: without its best symbol the strategy is still net positive after costs (>= 2 declared symbols); a safety bar.
    syms = base["symbol"].astype(str)
    declared = sorted(set(declared_symbols)) if declared_symbols else sorted(set(syms))
    labels = []
    if len(declared) < 2:
        labels.append("single symbol")                                 # test n/a; concentration judged by the portfolio check (§9)
    else:
        per = {x: float(r[syms == x].sum()) for x in declared}
        best = max(per, key=per.get)
        rest = p0 - per[best]
        out["without_best_symbol"] = (rest > 0, rest > 0, round(rest, 3))
    failed = [k for k, v in out.items() if not v[0]]
    return {"tests": {k: {"pass": v[0], "near": v[1], "value": v[2]} for k, v in out.items()}, "failed": failed,
            "pass": not failed, "mode": mode, "labels": labels}


SAFETY = {"luck", "hold_time", "swap0", "fx2015", "long", "short", "without_best_symbol"}


def verdict(g1_res, g2_res):
    """pass, near miss (§6.6a: exactly one G1 / G2 bar failed, within its margin, not a safety bar), or fail."""
    fails = [("g1", k) for k in g1_res["failed"]] + [("g2", k) for k in (g2_res or {}).get("failed", [])]
    if not fails:
        return "pass"
    if len(fails) == 1:
        stage, k = fails[0]
        if k not in SAFETY and ((stage == "g1" and g1_res["near_miss"]) or (stage == "g2" and g2_res["tests"][k]["near"])):
            return "near_miss"
    return "fail"


def fx_quarantine_mask(log, every_symbol=False):
    """Trades entered in the FX quarantine on FX symbols; every_symbol=True: on every symbol (an idea with an FX context symbol,
    whose signals on any traded symbol may read FX prices, DESIGN A14.1.4)."""
    a, b = TH["stress"]["fx_quarantine"]
    lo, hi = month_ms(a), month_ms(b, 1)
    from engine.costs import asset_class
    if every_symbol:
        fx = np.ones(n_of(log), bool)
    else:
        fx = np.array([asset_class(s) == "fx" for s in log["symbol"].astype(str)]) if n_of(log) else np.zeros(0, bool)
    return fx & (log["entry_t"] >= lo) & (log["entry_t"] < hi)


def fx_idea(symbols, context=()):
    """(runs fx2015, every_symbol mask): an idea runs the fx2015 stress test if it trades an FX pair or reads one as a context
    symbol (DESIGN A14.1.4); with an FX context symbol every traded symbol's quarantine trades are left out."""
    from engine.costs import asset_class
    ctx_fx = any(asset_class(s) == "fx" for s in (context or ()))
    return any(asset_class(s) == "fx" for s in symbols) or ctx_fx, ctx_fx


# ------------------------------------------------------------------ cards (DESIGN A10.4)
CARD_FIELDS = {"data-mined": "data_mined", "seen family": "seen_family", "source overlap": "source_overlap", "grid size": "grid_size"}


def card_flags(text):
    """The card's machine-read fields, strictly: 'data-mined', 'seen family' and 'source overlap' (DESIGN A11.3) read exactly yes or
    no; 'grid size' is the declared
    grid's number of points (an integer >= 1). Table rows `| <field> | <value> |`; the field cell may carry a parenthesis after the
    name (e.g. 'seen family (DESIGN §3.7)'). Anything else, a missing field or a field given twice is refused (ValueError)."""
    out = {}
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key = cells[0].lower()
        for name, field in CARD_FIELDS.items():
            if key != name and not key.startswith(name + " ("):
                continue
            if field in out:
                raise ValueError(f"card: '{name}' is given twice")
            v = cells[1]
            if field == "grid_size":
                if not v.isdigit() or int(v) < 1:
                    raise ValueError(f"card: 'grid size' must be a whole number >= 1, not {v!r}")
                out[field] = int(v)
            else:
                if v not in ("yes", "no"):
                    raise ValueError(f"card: '{name}' must read exactly yes or no, not {v!r} (DESIGN A10.4, A11.3)")
                out[field] = v == "yes"
    missing = [n for n, f in CARD_FIELDS.items() if f not in out]
    if missing:
        raise ValueError(f"card lacks {missing} (rows '| data-mined | yes/no |', '| seen family | yes/no |', "
                         "'| source overlap | yes/no |', '| grid size | N |')")
    return out


# ------------------------------------------------------------------ k: effective tries (DESIGN §7, A10.4)
def k_eff(n, rho):
    """The number of independent zero-edge tries whose best has the same 95th percentile as the best of n points with mean
    pairwise correlation rho: k = ln(0.95) / ln(Phi(q)), q the 95th percentile of the max of n equicorrelated standard normals.
    Computed exactly (Gauss-Hermite over the common factor) instead of simulated (tools/nullstats/grid_factor.py agrees)."""
    n = int(n)
    if n < 1:
        raise ValueError(f"k_eff: n must be >= 1, not {n}")
    rho = min(max(float(rho), 0.0), 1.0)
    q = TH["luck_bar"]["quantile"]
    if n == 1 or rho >= 1.0 - 1e-9:
        return 1.0
    if rho <= 1e-12:
        return float(n)
    z, wts = np.polynomial.hermite_e.hermegauss(160)
    wts = wts / wts.sum()
    nd = NormalDist()
    cdf = np.vectorize(nd.cdf)

    def F(x):
        return float(np.sum(wts * cdf((x - math.sqrt(rho) * z) / math.sqrt(1.0 - rho)) ** n))
    lo, hi = -2.0, 8.0
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if F(mid) < q else (lo, mid)
    return float(math.log(q) / math.log(nd.cdf((lo + hi) / 2)))


SCREEN_STAGES = ("screen", "amber-V1", "amber-V2", "amber-V3")
GRID_STAGE = "tune"
ROUTES = ("base", "V1", "V2", "V3")


def is_real(row):
    """A real test: not the null calibration, not a referee, never a locked-period open (DESIGN A10.4)."""
    return row.get("lane") not in ("null", "referee") and row.get("stage") != "locked"


def route_of(row):
    if row.get("route"):
        return row["route"]
    st = row.get("stage", "")
    return "base" if st == "screen" else st[len("amber-"):] if st.startswith("amber-V") else None


def read_ledger(path=None):
    rows = []
    d = path or LEDGER
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith(".jsonl"):
            rows += [json.loads(x) for x in open(os.path.join(d, f)) if x.strip()]
    return rows


def route_rho(grid_rows, n, load=None):
    """Mean pairwise correlation of a route's grid points' unseen daily R at mid prices (M0), once all n points have a row;
    else None (the caller uses the default). Clipped to [0, 1]. Cached in runs/_kcache by the rows' test ids."""
    pts = {}
    for r in grid_rows:
        pts.setdefault(json.dumps(r.get("variant"), sort_keys=True), r)
    if n < 2 or len(pts) < n:
        return None
    rows = sorted(pts.values(), key=lambda r: r["test_id"])
    key = hashlib.sha256("|".join(r["test_id"] for r in rows).encode()).hexdigest()[:16]
    cp = os.path.join(KCACHE, key + ".json")
    if load is None and os.path.isfile(cp):
        return json.load(open(cp))["rho"]
    first, end = month_ms(TH["walk_forward"]["first_test"]), month_ms(TH["walk_forward"]["last_month"], 1)
    ser = []
    for r in rows:
        lg = load(r) if load else load_logs(os.path.join(REPO, r["run_path"]), r["symbols"], ["M0"])["M0"]
        k = lg["entry_t"] >= first
        s = M.daily_series(lg["r_mid"][k].astype(float), lg["exit_t"][k], first, end)
        if s.std() > 0:
            ser.append(s)
    if len(ser) < 2:
        return None
    c = np.corrcoef(np.array(ser))
    rho = float(min(max(c[~np.eye(len(ser), dtype=bool)].mean(), 0.0), 1.0))
    if load is None:
        os.makedirs(KCACHE, exist_ok=True)
        json.dump({"rho": rho, "test_ids": [r["test_id"] for r in rows]}, open(cp, "w"))
    return rho


def first_screen_flags(real):
    """{idea: card_flags of its first real screen row} (ledger order). Every field must be there (A11.3-4)."""
    out = {}
    for r in real:
        if r.get("stage") == "screen" and r["idea_id"] not in out:
            f = r.get("card_flags") or {}
            miss = [x for x in CARD_FIELDS.values() if x not in f]
            if miss:
                raise ValueError(f"{r['idea_id']}: its first screen row lacks card fields {miss}")
            out[r["idea_id"]] = f
    return out


def count_k(rows, idea_id, rho_fn=route_rho):
    """k for the luck bar when an idea's G1 runs (DESIGN A10.4), from the ledger rows written so far.
    Only real rows count (is_real). Data-mined ideas, seen families and source-overlapped ideas (A11.3): k = the number of real test
    rows. Every idea's card fields are read from its FIRST real screen row (A11.4): a later card change has no effect. Normal ideas: k = the sum
    over every real idea with at least one screen row of k_eff(N, rho) for each of its screened routes (base and each amber
    variation), N = the idea's declared grid size (card), rho = that route's grid correlation (route_rho) or the frozen default.
    Never below the k_eff of the judged idea's own base route. Returns {k, method, ...}."""
    real = [r for r in rows if is_real(r)]
    mine = [r for r in real if r.get("idea_id") == idea_id]
    if not any(r.get("stage") == "screen" for r in mine):
        raise ValueError(f"{idea_id}: no real screen row in the ledger")
    flags = first_screen_flags(real)
    if idea_id not in flags:
        raise ValueError(f"{idea_id}: its first screen row carries no card_flags")
    rho0 = TH["luck_bar"]["rho_default"]
    screened = {r["idea_id"] for r in real if r.get("stage") == "screen"}
    routes = sorted({(r["idea_id"], route_of(r)) for r in real if r["idea_id"] in screened and r.get("stage") in SCREEN_STAGES})
    per = {}
    for idea, route in routes:
        if idea not in flags:
            raise ValueError(f"{idea}: its first screen row carries no card_flags")
        n = flags[idea]["grid_size"]
        g = [r for r in real if r["idea_id"] == idea and r.get("stage") == GRID_STAGE and route_of(r) == route]
        rho = rho_fn(g, n) if g else None
        per[f"{idea}/{route}"] = {"n": n, "rho": rho0 if rho is None else round(rho, 4), "measured": rho is not None,
                                  "k_eff": round(k_eff(n, rho0 if rho is None else rho), 3)}
    own = per[f"{idea_id}/base"]["k_eff"] if f"{idea_id}/base" in per else k_eff(flags[idea_id]["grid_size"], rho0)
    f = flags[idea_id]
    if f["data_mined"] or f["seen_family"] or f["source_overlap"]:
        k = max(float(len(real)), own)
        why = [x for x in ("data_mined", "seen_family", "source_overlap") if f[x]]
        return {"k": round(k, 3), "method": "real test rows (" + ", ".join(why) + ")", "real_rows": len(real), "own_k_eff": own,
                "card_flags": f}
    k = max(sum(v["k_eff"] for v in per.values()), own)
    return {"k": round(k, 3), "method": "sum of k_eff over screened routes of real ideas", "ideas": len(screened),
            "routes": len(per), "own_k_eff": own, "per_route": per}
