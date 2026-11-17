"""IDEA-1025: narrow-range day breakout, held one to three days (open-slot card v1,
ideas/cards/IDEA-1025-narrow-range-day-breakout.md).

- h1 bars. Trading day = 17:00 New York -> 17:00 New York (a bar belongs to the day in which it closes, shifted so 17:00 NY starts the
  next day). A day is complete once a bar of a later day has arrived; it is counted (narrow-day candidate and look-back member) only
  if it has >= 12 h1 bars.
- Day d is NR-N if its range is strictly smaller than each of the previous N - 1 counted days' ranges.
- Day d + 1 (the next day that has bars, whatever its length; a short day is never a narrow day): at the close of each h1 bar,
  the first close above day d's high buys at market, the first close below
  day d's low sells at market; after the first close outside, no further entry on this signal.
- Stop at day d's opposite extreme (distance from the decision close). No target. Time exit H x 24 h.
params (card defaults): N = 7, H = 2. Class B weekend flat, news modes and caps are applied by the engine.
"""
import numpy as np

from engine.timeutil import local_ms

_TZ = "America/New_York"
_DAY = 86_400_000
_SHIFT = 7 * 3_600_000          # 17:00 NY + 7 h = 24:00: the day boundary
_MIN_BARS = 12


def intents(bars, params, ctx):
    N = int(params.get("N", 7))
    H = float(params.get("H", 2))
    h = np.asarray(bars["h"], float)
    l = np.asarray(bars["l"], float)
    c = np.asarray(bars["c"], float)
    om = np.asarray(bars["open_ms"], np.int64)
    cm = np.asarray(bars["close_ms"], np.int64)
    n = len(c)
    side = np.zeros(n, np.int64)
    sl = np.full(n, np.nan)
    hold = np.full(n, np.nan)
    out = {"side": side, "sl_dist": sl, "hold_ms": hold}
    if n == 0:
        return out
    if ctx.get("timeframe", "h1") != "h1":
        raise ValueError("IDEA-1025 is defined on h1 bars")
    first_ms = int(ctx.get("first_ms", om[0]))
    # day key of each bar from its close time (the bar closing at 17:00 NY belongs to the day that ends then)
    day = (local_ms(cm - 1, _TZ) + _SHIFT) // _DAY

    ranges = []          # ranges of counted days, oldest first
    armed = None         # (hi, lo) of the previous day if it was a counted NR-N day
    done = False         # first close outside already seen on the current day
    cur_key = None
    cur_hi = cur_lo = 0.0
    cur_cnt = 0

    for i in range(n):
        k = int(day[i])
        if k != cur_key:
            armed = None
            done = False
            if cur_key is not None and cur_cnt >= _MIN_BARS:
                r = cur_hi - cur_lo
                if len(ranges) >= N - 1 and all(r < x for x in ranges[len(ranges) - (N - 1):]):
                    armed = (cur_hi, cur_lo)
                ranges.append(r)
                if len(ranges) > 64:
                    ranges = ranges[-64:]
            cur_key = k
            cur_hi = h[i]
            cur_lo = l[i]
            cur_cnt = 1
        else:
            cur_hi = max(cur_hi, h[i])
            cur_lo = min(cur_lo, l[i])
            cur_cnt += 1
        if armed is None or done:
            continue
        hi, lo = armed
        if c[i] > hi:
            done = True
            if om[i] >= first_ms and c[i] - lo > 0:
                side[i] = 1
                sl[i] = c[i] - lo
                hold[i] = H * _DAY
        elif c[i] < lo:
            done = True
            if om[i] >= first_ms and hi - c[i] > 0:
                side[i] = -1
                sl[i] = hi - c[i]
                hold[i] = H * _DAY
    return out
