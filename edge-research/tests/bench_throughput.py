"""Throughput benchmark (engine engineering, not a test of any idea): CPU time per idea for the quick screen and the walk-forward.

Prints timings only. No trade result, R or metric is printed or stored: this is not a ledger test.

Typical intraday idea: m15 decisions, 4 symbols (EURUSD, GBPUSD, XAUUSD, US500), a 3 x 3 x 3 grid (channel length, ATR stop
multiple, hold time), 2014-11 -> 2024-12. Quick screen = M0, the 27 grid points. Walk-forward 24 / 3 = the 27 grid points over the
full period in each of the four news modes (train / test windows are then scored from the trade lists: cheap), so its kernel work
is about 4x the screen's. The news modes' flat times and entry blocks are modelled here as an extra flat-time list of the right
size (the rules layer isn't built yet).

  ~/.venvs/fastbt/bin/python -m tests.bench_throughput
"""
import time

import numpy as np

from engine import costs, data, kernel as K

SYMBOLS = ("EURUSD", "GBPUSD", "XAUUSD", "US500")
GRID = [(n, k, h) for n in (20, 40, 80) for k in (1.0, 1.5, 2.0) for h in (4, 8, 24)]
FIRST, LAST = "2014-11", "2024-12"
MIN = 60_000


def wilder_atr(h, l, c, n=14):
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    tr = np.concatenate([[h[0] - l[0]], tr])
    a = np.empty_like(tr)
    a[:n] = np.nan
    a[n - 1] = tr[:n].mean()
    alpha = 1.0 / n
    for i in range(n, len(tr)):        # fine for a benchmark (numba in the real indicator library)
        a[i] = a[i - 1] + alpha * (tr[i] - a[i - 1])
    return a


def rolling_max(x, n):
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full(len(x), np.nan)
    out[n:] = sliding_window_view(x[:-1], n).max(axis=1)[: len(x) - n]
    return out


def rolling_min(x, n):
    from numpy.lib.stride_tricks import sliding_window_view
    out = np.full(len(x), np.nan)
    out[n:] = sliding_window_view(x[:-1], n).min(axis=1)[: len(x) - n]
    return out


def intents(b, atr, n, k, h):
    hi, lo = rolling_max(b["h"], n), rolling_min(b["l"], n)
    side = np.where(b["c"] > hi, 1, np.where(b["c"] < lo, -1, 0))
    return dict(side=side, sl_dist=k * atr, hold_ms=np.full(len(side), h * 3_600_000.0))


def main():
    c = costs.load()
    t_load = t_sig = t_kern = 0.0
    n_ticks = n_runs = 0
    mem = 0
    news_flats = None
    for sym in SYMBOLS:
        t0 = time.perf_counter()
        ft = data.ticks(sym, FIRST, LAST, venue="ftmo", costs=c)
        b = data.bars(sym, "m15", FIRST, LAST)
        t_load += time.perf_counter() - t0
        n_ticks += len(ft)
        mem = max(mem, ft.t.nbytes + ft.bid.nbytes + ft.ask.nbytes)
        t0 = time.perf_counter()
        atr = wilder_atr(b["h"], b["l"], b["c"])
        t_sig += time.perf_counter() - t0
        # ~ 1,500 high-impact windows a year x 10 years as flat times (news-mode stand-in)
        news_flats = np.sort(np.random.default_rng(0).integers(ft.t[0], ft.t[-1], 15_000))
        K.run(ft.t[:1000], ft.bid[:1000], ft.ask[:1000], b["close_ms"][:10], side=np.zeros(10))   # compile
        for (n, k, h) in GRID:
            t0 = time.perf_counter()
            it = intents(b, atr, n, k, h)
            t_sig += time.perf_counter() - t0
            t0 = time.perf_counter()
            K.run(ft.t, ft.bid, ft.ask, b["close_ms"], **it)
            t_kern += time.perf_counter() - t0
            n_runs += 1
        t0 = time.perf_counter()
        for (n, k, h) in GRID[:3]:                       # news-mode cost sample
            K.run(ft.t, ft.bid, ft.ask, b["close_ms"], flat_ms=news_flats, **intents(b, atr, n, k, h))
        t_news = (time.perf_counter() - t0) / 3
        print(f"{sym}: {len(ft):,} ticks, load {t_load:.1f} s cumulative; one news-mode run {t_news:.2f} s", flush=True)
        del ft
    per_run = t_kern / n_runs
    screen = t_sig + t_kern                     # ticks already in memory (runner groups jobs by symbol)
    screen_cold = screen + t_load
    wf = 4 * screen + 1.0                       # four modes, + window scoring (about 1 s)
    day = 86_400 * 14
    print("")
    print(f"ticks {n_ticks / 1e6:,.0f} M over 4 symbols; largest tick set {mem / 1e9:.1f} GB in memory")
    print(f"load all 4 symbols: {t_load:.0f} s; one kernel run (one symbol, 10 years): {per_run:.2f} s; signals {t_sig:.1f} s")
    print(f"quick screen, 27 points x 4 symbols: {screen:.0f} s CPU warm, {screen_cold:.0f} s with loading")
    print(f"walk-forward, 4 modes: {wf:.0f} s CPU warm")
    print(f"14 workers: screen {day / screen:,.0f} ideas/day warm ({day / screen_cold:,.0f} cold); walk-forward {day / wf:,.0f}/day")


if __name__ == "__main__":
    main()
