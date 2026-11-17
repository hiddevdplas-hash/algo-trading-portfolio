"""Real time zones for UTC ms arrays (DESIGN §4.2: Amsterdam and New York change clocks on different dates).
Copied from VWAP tools/fastbt/data.py (ny_offsets), generalised to any zone; the VWAP file is not edited."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np

NY = "America/New_York"
AMS = "Europe/Amsterdam"


@lru_cache(maxsize=None)
def _transitions(zone, lo_year, hi_year):
    z = ZoneInfo(zone)
    edges, offs = [], []
    t = datetime(lo_year, 1, 1, tzinfo=timezone.utc)
    end = datetime(hi_year + 1, 1, 1, tzinfo=timezone.utc)
    prev = None
    while t < end:                      # hourly scan: transitions are on the hour (UTC) for both zones
        off = int(t.astimezone(z).utcoffset().total_seconds() * 1000)
        if off != prev:
            edges.append(int(t.timestamp() * 1000))
            offs.append(off)
            prev = off
        t += timedelta(hours=1)
    return np.array(edges, dtype=np.int64), np.array(offs, dtype=np.int64)


def offset_ms(t_ms, zone):
    """UTC offset (ms) of `zone` at each UTC time."""
    t_ms = np.asarray(t_ms, dtype=np.int64)
    if t_ms.size == 0:
        return t_ms.copy()
    lo = datetime.fromtimestamp(int(t_ms.min()) / 1000, timezone.utc).year - 1
    hi = datetime.fromtimestamp(int(t_ms.max()) / 1000, timezone.utc).year + 1
    edges, offs = _transitions(zone, lo, hi)
    return offs[np.searchsorted(edges, t_ms, side="right") - 1]


def ny_offset_ms(t_ms):
    return offset_ms(t_ms, NY)


def ams_offset_ms(t_ms):
    return offset_ms(t_ms, AMS)


def local_ms(t_ms, zone):
    """UTC ms -> local wall-clock ms (as if UTC) in `zone`."""
    t_ms = np.asarray(t_ms, dtype=np.int64)
    return t_ms + offset_ms(t_ms, zone)
