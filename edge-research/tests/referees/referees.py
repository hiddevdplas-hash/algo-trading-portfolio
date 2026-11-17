"""The 5 referee strategies (DESIGN §4.5 item 2) in Python: the same rules as the cBots in cTrader-Bots/ER_R*.cs, line for line.

Not engine code: plain strategy modules that hand intents to the kernel. Every indicator is a plain sequential loop in double
precision, seeded at the first bar on or after the seed date, so the cBot (same loops, same seed bar) gets bit-identical values.
Price levels and distances are put on the symbol's tick grid as n / 10**digits (the nearest double), as the cBots do.

  R1 EmaCross      EURUSD m15  EMA 20 / 50 cross, stop-and-reverse at the cross, stop 2 ATR, no target        (market, exit signal)
  R2 DonchianStop  XAUUSD h1   stop order at the 20-bar high (close > SMA 50) or low, re-placed every bar,
                               stop 2 ATR, target 4 ATR, time exit 24 h                                       (stop entry, target, time)
  R3 SessionTimed  US500 m5    10:00 NY: direction of 09:30 -> 10:00, stop 1.5 ATR, target 3 ATR, exit 15:30 NY (NY clock, DST)
  R4 LimitFade     XAUUSD m15  close outside Bollinger 20 / 2: limit 0.5 ATR further, live 60 min, stop 1 ATR,
                               target 1 ATR                                                                    (limit entry, expiry)
  R5 SmaTrail      EURUSD h1   close crosses SMA 50: stop 2 ATR, trailed to close -/+ 2.5 ATR at every bar
                               close, flat Fridays 16:45 NY, no entries Friday from 12:00 NY                  (trail, flat time)
ATR = Wilder 14 (first value = mean of the first 14 true ranges; the seed bar's true range = high - low).
Also part of the rules (look-ahead review 2026-11-12, F4): no decision in the first WARMUP = 100 bars after the seed bar; R2 skips a bar
whose close equals the SMA 50, R3 a day whose 09:55 close equals the 09:30 open; R4's band uses the population standard deviation
(divide by 20); R5's trail candidates exist from the warm-up on (before trade_from), but no position exists before trade_from.

  ~/.venvs/fastbt/bin/python -m tests.referees.referees [R1 ...]     -> runs/referees/<R>_<SYMBOL>_<seed>_python.csv + counters
"""
import csv
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from engine import data, kernel as K, store
from engine.hash import engine_hash
from engine.timeutil import ny_offset_ms

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "runs", "referees")
NY = ZoneInfo("America/New_York")
WARMUP = 100           # bars after the seed bar before any decision
TF_MS = {"m5": 300_000, "m15": 900_000, "h1": 3_600_000}

SPECS = {
    "R1": dict(name="EmaCross", symbol="EURUSD", tf="m15", seed="2023-12-01", trade_from="2024-01-01", end="2024-07-01"),
    "R2": dict(name="DonchianStop", symbol="XAUUSD", tf="h1", seed="2023-06-01", trade_from="2023-07-01", end="2024-01-01"),
    "R3": dict(name="SessionTimed", symbol="US500", tf="m5", seed="2024-01-02", trade_from="2024-02-01", end="2024-06-01"),
    "R4": dict(name="LimitFade", symbol="XAUUSD", tf="m15", seed="2023-12-01", trade_from="2024-01-01", end="2024-05-01"),
    "R5": dict(name="SmaTrail", symbol="EURUSD", tf="h1", seed="2022-08-01", trade_from="2022-09-01", end="2023-03-01"),
}
CSV_FIELDS = ("ref", "symbol", "side", "bar_open_ms", "live_ms", "fill_ms", "entry_ms", "entry_px", "sl0", "tp0", "exit_ms",
              "exit_px", "exit_kind", "volume", "gross", "commission", "swap", "net")
KIND = {1: "StopLoss", 2: "TakeProfit", 3: "Closed:time", 4: "Closed:signal", 5: "Closed:flat", 6: "end", 7: "trail"}


def day_ms(s):
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


class Grid:
    """The symbol's tick grid: n / 10**digits, n = floor(x / tick + 0.5) (cBot: Math.Floor(x / Symbol.TickSize + 0.5) / 10^Digits)."""
    def __init__(self, symbol=None, tick=None, digits=None):
        if symbol is not None:
            m = store.store_meta(symbol)
            digits, tick = int(m.get("symbol_digits") or m["digits"]), float(m["tick_size"])
        self.digits = int(digits)
        self.tick = float(tick)
        self.p10 = 10.0 ** self.digits
        assert abs(self.tick * self.p10 - 1) < 1e-9, "referees assume tick = 10**-digits"

    @classmethod
    def from_ctx(cls, ctx):
        """From the runner's context (strategy modules read no files)."""
        return cls(tick=ctx["tick"], digits=ctx["digits"])

    def rt(self, x):
        return math.floor(x / self.tick + 0.5) / self.p10


# ---- indicators: sequential loops over bars s..n-1 (s = seed bar), NaN before they are ready -------------------------------
def atr(h, l, c, s, n=14):
    out = [math.nan] * len(c)
    tr = [math.nan] * len(c)
    for i in range(s, len(c)):
        if i == s:
            tr[i] = h[i] - l[i]
        else:
            pc = c[i - 1]
            tr[i] = max(h[i] - l[i], max(abs(h[i] - pc), abs(l[i] - pc)))
        if i == s + n - 1:
            acc = 0.0
            for j in range(s, i + 1):
                acc += tr[j]
            out[i] = acc / n
        elif i > s + n - 1:
            out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def ema(c, s, n):
    k = 2.0 / (n + 1)
    out = [math.nan] * len(c)
    for i in range(s, len(c)):
        out[i] = c[i] if i == s else out[i - 1] + k * (c[i] - out[i - 1])
    return out


def sma(c, s, n):
    out = [math.nan] * len(c)
    for i in range(s + n - 1, len(c)):
        acc = 0.0
        for j in range(i - n + 1, i + 1):
            acc += c[j]
        out[i] = acc / n
    return out


def stdev(c, mean, s, n):
    out = [math.nan] * len(c)
    for i in range(s + n - 1, len(c)):
        acc = 0.0
        for j in range(i - n + 1, i + 1):
            d = c[j] - mean[i]
            acc += d * d
        out[i] = math.sqrt(acc / n)
    return out


def ny_parts(ms):
    """(NY local ms, minute of day, NY day number, weekday Mon=0) for UTC ms arrays."""
    loc = ms + ny_offset_ms(ms)
    day = loc // 86_400_000
    return loc, (loc // 60_000) % 1440, day, (day + 3) % 7


def friday_flats(first_ms, end_ms, hh=16, mm=45):
    out = []
    d = datetime.fromtimestamp(first_ms / 1000, timezone.utc).date() - timedelta(days=7)
    while True:
        if d.weekday() == 4:
            t = int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp() * 1000)
            if t >= end_ms:
                break
            if t >= first_ms:
                out.append(t)
        d += timedelta(days=1)
    return out


# ---- the five strategies: bars -> intents ------------------------------------------------------------------------------------
def intents(ref, b, g):
    sp = SPECS[ref]
    o, h, l, c = (b[k].tolist() for k in ("o", "h", "l", "c"))
    op = b["open_ms"]
    n = len(c)
    s = int(np.searchsorted(op, day_ms(sp["seed"])))
    a = atr(h, l, c, s)
    can = np.zeros(n, bool)
    can[s + WARMUP:] = True
    can &= op >= day_ms(sp["trade_from"])
    I = dict(side=np.zeros(n, np.int64), otype=np.zeros(n, np.int64), price=np.full(n, np.nan), sl_dist=np.full(n, np.nan),
             tp_dist=np.full(n, np.nan), expiry_ms=np.full(n, np.nan), hold_ms=np.full(n, np.nan),
             trail_long=np.full(n, np.nan), trail_short=np.full(n, np.nan), exit_long=np.zeros(n, bool), exit_short=np.zeros(n, bool))
    flat = []
    if ref == "R1":
        f, sl_ = ema(c, s, 20), ema(c, s, 50)
        for i in range(s + 1, n):
            if not can[i]:
                continue
            up = f[i] > sl_[i] and f[i - 1] <= sl_[i - 1]
            dn = f[i] < sl_[i] and f[i - 1] >= sl_[i - 1]
            if up or dn:
                I["side"][i] = 1 if up else -1
                I["exit_short" if up else "exit_long"][i] = True
                I["sl_dist"][i] = g.rt(2.0 * a[i])
    elif ref == "R2":
        m50 = sma(c, s, 50)
        for i in range(s + 19, n):
            if not can[i] or math.isnan(m50[i]) or c[i] == m50[i]:
                continue
            hi = h[i]; lo = l[i]
            for j in range(i - 19, i):
                hi = max(hi, h[j]); lo = min(lo, l[j])
            up = c[i] > m50[i]
            I["side"][i] = 1 if up else -1
            I["otype"][i] = K.STOP
            I["price"][i] = hi if up else lo
            I["sl_dist"][i] = g.rt(2.0 * a[i])
            I["tp_dist"][i] = g.rt(4.0 * a[i])
            I["hold_ms"][i] = 86_400_000
    elif ref == "R3":
        _, mins, day, _ = ny_parts(op)
        o930 = {}
        for i in range(s, n):
            if mins[i] == 9 * 60 + 30:
                o930[day[i]] = o[i]
            if not can[i]:
                continue
            if mins[i] == 9 * 60 + 55 and day[i] in o930 and c[i] != o930[day[i]]:
                I["side"][i] = 1 if c[i] > o930[day[i]] else -1
                I["sl_dist"][i] = g.rt(1.5 * a[i])
                I["tp_dist"][i] = g.rt(3.0 * a[i])
            if mins[i] == 15 * 60 + 25:
                I["exit_long"][i] = I["exit_short"][i] = True
    elif ref == "R4":
        m = sma(c, s, 20)
        sd = stdev(c, m, s, 20)
        for i in range(s + 19, n):
            if not can[i]:
                continue
            lo_b, hi_b = m[i] - 2.0 * sd[i], m[i] + 2.0 * sd[i]
            if c[i] < lo_b or c[i] > hi_b:
                buy = c[i] < lo_b
                I["side"][i] = 1 if buy else -1
                I["otype"][i] = K.LIMIT
                I["price"][i] = g.rt(c[i] - 0.5 * a[i]) if buy else g.rt(c[i] + 0.5 * a[i])
                I["sl_dist"][i] = g.rt(1.0 * a[i])
                I["tp_dist"][i] = g.rt(1.0 * a[i])
                I["expiry_ms"][i] = 3_600_000
    elif ref == "R5":
        m50 = sma(c, s, 50)
        _, cmins, _, cwd = ny_parts(op + TF_MS[sp["tf"]])
        for i in range(s + 50, n):
            if i < s + WARMUP:
                continue
            I["trail_long"][i] = g.rt(c[i] - 2.5 * a[i])
            I["trail_short"][i] = g.rt(c[i] + 2.5 * a[i])
            if not can[i] or (cwd[i] == 4 and cmins[i] >= 12 * 60):
                continue
            up = c[i] > m50[i] and c[i - 1] <= m50[i - 1]
            dn = c[i] < m50[i] and c[i - 1] >= m50[i - 1]
            if up or dn:
                I["side"][i] = 1 if up else -1
                I["sl_dist"][i] = g.rt(2.0 * a[i])
        flat = friday_flats(day_ms(sp["trade_from"]), day_ms(sp["end"]))
    return I, flat


def run(ref):
    sp = SPECS[ref]
    g = Grid(sp["symbol"])
    b = data.bars(sp["symbol"], sp["tf"])
    end = day_ms(sp["end"])
    keep = b["close_ms"] <= end
    b = {k: v[keep] for k, v in b.items()}
    I, flat = intents(ref, b, g)
    last_month = (np.datetime64(sp["end"], "M") - 1).astype(str)
    tk = data.ticks(sp["symbol"], sp["trade_from"][:7], last_month, venue="ic")
    k = tk.t < end
    tr, cnt = K.run(tk.t[k], tk.bid[k], tk.ask[k], b["close_ms"], flat_ms=flat, min_step=g.tick / 2,
                         pip_size=float(store.store_meta(sp["symbol"])["pip_size"]), **I)
    os.makedirs(OUT, exist_ok=True)
    base = os.path.join(OUT, f"{ref}_{sp['symbol']}_{sp['seed']}_python")
    with open(base + ".csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_FIELDS)
        lt = tk.t[k]
        for j in range(len(tr["bar"])):
            w.writerow([ref, sp["symbol"], int(tr["side"][j]), int(b["open_ms"][tr["bar"][j]]), int(lt[tr["live_tick"][j]]),
                        int(tr["entry_t"][j]), int(tr["entry_t"][j]), repr(float(tr["entry_px"][j])), repr(float(tr["sl0"][j])),
                        "" if np.isnan(tr["tp"][j]) else repr(float(tr["tp"][j])), int(tr["exit_t"][j]),
                        repr(float(tr["exit_px"][j])), KIND[int(tr["exit_reason"][j])], "", "", "", "", ""])
    info = dict(ref=ref, **sp, trades=int(len(tr["bar"])), counters=cnt, engine_hash=engine_hash(), ticks=int(k.sum()),
                n_dropped_crossed=tk.n_dropped_crossed, n_zeroed_crossed=tk.n_zeroed_crossed,
                exits={KIND[r]: int((tr["exit_reason"] == r).sum()) for r in KIND if (tr["exit_reason"] == r).any()},
                net_r_gross=round(float(tr["r_gross"].sum()), 3))
    json.dump(info, open(base + ".json", "w"), indent=1)
    return info


if __name__ == "__main__":
    for r in (sys.argv[1:] or list(SPECS)):
        print(json.dumps(run(r)), flush=True)
