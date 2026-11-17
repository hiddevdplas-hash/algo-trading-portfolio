"""IDEA-3006: weekly-open acceptance with an ATR-paced frontier pullback (card v1, ideas/cards/IDEA-3006-weekly-open-frontier-pullback.md).

Rebuilt from the card's description of the idea source (TradingView "Higher Timeframe Trend Frontier (Zeiierman)" by Zeiierman);
no code copied.
- h1 bars. Week = from Sunday 17:00 NY; WO = open of the week's first bar.
- A = mean true range (vs the prior week's close) of the last 4 completed weeks. Zone = WO +- z x A.
- ATR(i) = mean true range of the last 24 bars up to i. Frontier: F starts at WO on the week's first bar;
  F(i) = F(i-1) + sign(c(i) - F(i-1)) x min(|c(i) - F(i-1)|, v x ATR(i)).
- Long at bar i's close: bar opens Mon 17:00 ... Wed 16:59 NY; c > WO + z A; F(i-1) > F(i-2) (same week); l(i) <= F(i-1) < c(i).
  Short mirrors. At most 2 signals per week. Stop l(i) - 0.5 ATR / h(i) + 0.5 ATR. Trail candidates F(i) -+ t x ATR(i) on every bar.
params (card defaults): z = 0.2, v = 0.25, t = 0.5. Class B rules (Friday flat), news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

_TZ = "America/New_York"
_DAY = 86_400_000
_SHIFT = 7 * 3_600_000          # Sunday 17:00 NY -> Monday 00:00 on the shifted clock
_N_WEEKS = 4
_ATR_N = 24
_STOP_ATR = 0.5
_MAX_SIGNALS = 2


def intents(bars, params, ctx):
    z = float(params.get("z", 0.2))
    v = float(params.get("v", 0.25))
    t = float(params.get("t", 0.5))
    o = np.asarray(bars["o"], float)
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    trl = np.full(n, np.nan)
    trs = np.full(n, np.nan)
    out = {"side": side, "sl_dist": sl, "trail_long": trl, "trail_short": trs}
    if n == 0:
        return out

    sday = (local_ms(om, _TZ) + _SHIFT) // _DAY        # shifted day number (epoch day 0 = Thursday)
    week = (sday - 4) // 7                              # weeks start on shifted Monday = Sunday 17:00 NY
    wday = (sday - 4) % 7                               # 0 = Sun 17:00 -> Mon 17:00, 1 = Mon 17:00 -> Tue 17:00, ...
    first_ms = int(ctx["first_ms"])

    # h1 ATR (closed bars, trailing 24)
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h, pc) - np.minimum(l, pc)
    tr[0] = h[0] - l[0]
    cs = np.cumsum(tr)
    atr = np.full(n, np.nan)
    if n >= _ATR_N:
        atr[_ATR_N - 1:] = (cs[_ATR_N - 1:] - np.r_[0.0, cs[:-_ATR_N]]) / _ATR_N

    wtr = []            # true ranges of completed weeks
    prev_wclose = None
    cur_w = None
    wo = whi = wlo = np.nan
    F = Fp = Fpp = np.nan
    nsig = 0
    for i in range(n):
        if week[i] != cur_w:
            if cur_w is not None:
                if prev_wclose is not None:
                    wtr.append(max(whi, prev_wclose) - min(wlo, prev_wclose))
                prev_wclose = c[i - 1]
            cur_w = week[i]
            wo = o[i]
            whi = h[i]
            wlo = l[i]
            F = wo
            Fp = Fpp = np.nan
            nsig = 0
        else:
            whi = max(whi, h[i])
            wlo = min(wlo, l[i])
        a = atr[i]
        Fpp, Fp = Fp, F                     # Fp = F(i-1), Fpp = F(i-2) within this week (NaN if not)
        if not np.isnan(a):
            d = c[i] - F
            F = F + np.sign(d) * min(abs(d), v * a)
            trl[i] = F - t * a
            trs[i] = F + t * a
        else:
            trl[i] = np.nan
            trs[i] = np.nan
        if len(wtr) < _N_WEEKS or np.isnan(a) or np.isnan(Fpp) or nsig >= _MAX_SIGNALS:
            continue
        if wday[i] not in (1, 2) or om[i] < first_ms:
            continue
        A = float(np.mean(wtr[-_N_WEEKS:]))
        if c[i] > wo + z * A and Fp > Fpp and l[i] <= Fp < c[i]:
            side[i] = 1
            sl[i] = c[i] - (l[i] - _STOP_ATR * a)
            nsig += 1
        elif c[i] < wo - z * A and Fp < Fpp and h[i] >= Fp > c[i]:
            side[i] = -1
            sl[i] = (h[i] + _STOP_ATR * a) - c[i]
            nsig += 1
    return out
