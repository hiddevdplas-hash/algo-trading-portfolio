"""DESIGN A8.8 guard: which trades of a test were flattened at an unscheduled gap (a market break of >= 2 h that is no weekend, holiday,
early close or regular daily break: data holes, feed outages). Outside engine/ on purpose (no engine hash change); it reads the trade
logs as written and the engine's own break rules (engine.rules.breaks_from_gaps).

  kind of a break   weekend   it starts on a Friday or spans a Saturday (Amsterdam)
                    regular   engine flag (A8.6)
                    holiday   a date from the close to the reopening is in HOLIDAYS (Western calendar: Christmas / New Year, Easter,
                              1 May, US and UK market holidays; Asian and Australian holidays are NOT in it, so for JP225, HK50 and
                              AUS200 the count runs high: conservative for the guard)
                    unscheduled  everything else
  flagged trade     exit "flat" at a class flat that A8 puts before an unscheduled break: exit time within [flat, close], flat =
                    min(close - 5 min, 22:45 Amsterdam that day).

Usage: ~/.venvs/fastbt/bin/python -m tools.gapcheck.unscheduled_flats <test_id | run folder> [--modes M0,M1,M2,M3]
Prints per mode: trades, flagged, share of trades, flagged net R (FTMO), total net R, flagged / |total| net R, and the A8.8 verdict.
Break lists are cached per symbol under runs/_gapcheck/ (git-ignored; delete-free: rebuilt only if missing)."""
import argparse, json, os, sys
from datetime import date, datetime, timedelta

import numpy as np

from engine import rules as RU
from engine import store

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(REPO, "runs", "_gapcheck")
MIN = RU.MIN
PERIOD = ("2014-11", "2024-12")


def _easter(y):
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    n = h + l - 7 * m + 114
    return date(y, n // 31, n % 31 + 1)


def _nth(y, m, wd, n):
    d = date(y, m, 1)
    return d + timedelta((wd - d.weekday()) % 7 + 7 * (n - 1))


def _last(y, m, wd):
    d = (date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)) - timedelta(1)
    return d - timedelta((d.weekday() - wd) % 7)


def holidays(y0=2014, y1=2025):
    out = set()
    for y in range(y0, y1 + 1):
        e = _easter(y)
        out |= {date(y, 1, 1), date(y, 1, 2), date(y, 12, 24), date(y, 12, 25), date(y, 12, 26), date(y, 12, 27), date(y, 12, 28),
                date(y, 12, 31), e - timedelta(2), e + timedelta(1), date(y, 5, 1),
                _nth(y, 1, 0, 3), _nth(y, 2, 0, 3), _last(y, 5, 0), date(y, 7, 3), date(y, 7, 4), date(y, 7, 5), _nth(y, 9, 0, 1),
                _nth(y, 11, 3, 4), _nth(y, 11, 3, 4) + timedelta(1),                          # US
                _nth(y, 5, 0, 1), _last(y, 8, 0)}                                             # UK
        if y >= 2022:
            out |= {date(y, 6, 19), date(y, 6, 20)}                                           # Juneteenth (+ observed)
    out |= {date(2018, 12, 5), date(2025, 1, 9), date(2020, 5, 8), date(2022, 6, 2), date(2022, 6, 3), date(2022, 9, 19),
            date(2023, 5, 8), date(2016, 6, 24)}
    return out


HOLIDAYS = holidays()


def kind(close, reopen, regular):
    d0 = datetime.fromtimestamp(close / 1000, RU.AMS).date()
    d1 = datetime.fromtimestamp(reopen / 1000, RU.AMS).date()
    days = [d0 + timedelta(i) for i in range((d1 - d0).days + 1)]
    if d0.weekday() == 4 or any(d.weekday() == 5 for d in days[:-1]):
        return "weekend"
    if regular:
        return "regular"
    if any(d in HOLIDAYS for d in days):
        return "holiday"
    return "unscheduled"


def gaps(symbol):
    """(close, reopen) of every gap >= RU.DAILY_REF_GAP in the store ticks (raw; the runner drops crossed ticks first, which can only
    widen a gap: rare at >= 30 min). Cached."""
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{symbol}.json")
    if os.path.isfile(p):
        g = json.load(open(p))
        return np.asarray(g["c"], np.int64), np.asarray(g["r"], np.int64)
    meta = store.store_meta(symbol)
    c, r, prev = [], [], None
    for m in sorted(x for x in meta["months"] if PERIOD[0] <= x <= PERIOD[1]):
        z = store.read_month_raw(symbol, m)
        t = z["t"].astype(np.int64)
        cl = np.where(z["close100"] >= 0, z["close100"] // 10_000, -1).astype(np.int64)
        if prev is not None:
            t, cl = np.concatenate([[prev[0]], t]), np.concatenate([[prev[1]], cl])
        for k in np.flatnonzero(np.diff(t) >= RU.DAILY_REF_GAP):
            c.append(RU._close_at(t, cl, k)); r.append(int(t[k + 1]))
        prev = (int(t[-1]), int(cl[-1]))
    json.dump({"c": [int(x) for x in c], "r": r}, open(p, "w"))
    return np.asarray(c, np.int64), np.asarray(r, np.int64)


def unscheduled_flat_windows(breaks):
    """[flat, close] windows of the A8 flats before unscheduled breaks."""
    out = []
    for c, r, reg in breaks:
        if kind(c, r, reg) != "unscheduled":
            continue
        x = c - RU.FLAT_BEFORE_CLOSE
        d = datetime.fromtimestamp(x / 1000, RU.AMS).date()
        out.append((min(x, RU.ams_ms(d, 22, 45)), c))
    return np.asarray(out, np.int64).reshape(-1, 2)


def flag(exit_t, exit_name, windows):
    """True for trades closed by a flat inside one of the windows."""
    exit_t = np.asarray(exit_t, np.int64)
    if not len(windows) or not len(exit_t):
        return np.zeros(len(exit_t), bool)
    i = np.searchsorted(windows[:, 0], exit_t, side="right") - 1
    ok = i >= 0
    inside = ok & (exit_t <= windows[np.maximum(i, 0), 1])
    return inside & (np.asarray(exit_name).astype(str) == "flat")


def check(run_dir, modes=("M0", "M1", "M2", "M3")):
    files = sorted(f for f in os.listdir(run_dir) if f.endswith(".npz"))
    out = {}
    win = {}
    for m in modes:
        n = k = 0
        r_all = r_flag = 0.0
        for f in files:
            sym, mm = f[:-4].rsplit("_", 1)
            if mm != m:
                continue
            if sym not in win:
                win[sym] = unscheduled_flat_windows(RU.breaks_from_gaps(*gaps(sym)))
            z = np.load(os.path.join(run_dir, f), allow_pickle=False)
            fl = flag(z["exit_t"], z["exit_name"], win[sym])
            r = z["r_net_ftmo"].astype(float)
            n += len(r); k += int(fl.sum()); r_all += float(r.sum()); r_flag += float(r[fl].sum())
        if n:
            share_r = abs(r_flag) / abs(r_all) if r_all else float("inf")
            out[m] = {"trades": n, "flagged": k, "share_trades": round(k / n, 5), "flagged_net_r": round(r_flag, 3),
                      "net_r": round(r_all, 3), "flagged_over_net_r": round(share_r, 5),
                      "recompute_walk_forward": bool(k / n > 0.01 or share_r > 0.10)}
    return out


def run_dir_of(x):
    if os.path.isdir(x):
        return x
    for d in sorted(os.listdir(os.path.join(REPO, "runs"))):
        p = os.path.join(REPO, "runs", d, x)
        if os.path.isdir(p):
            return p
    sys.exit(f"no run folder for {x}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("test")
    ap.add_argument("--modes", default="M0,M1,M2,M3")
    a = ap.parse_args()
    print(json.dumps(check(run_dir_of(a.test), tuple(a.modes.split(","))), indent=1))
