"""Short names for cBot settings: the PROTOCOL short code (v1 step 5 naming) and compact labels for reports."""

MODE_CODE = {"Session": "S", "Weekly": "W", "IntradayDual": "ID"}
MGMT_CODE = {"1": "RS1", "2": "RS2", "3": "RS3", "4": "RS4", "5": "ST", "6": "DT"}      # 0 = Fixed TP: FT<TP>
LABEL = {"Timeframe": "tf", "SessionBandMult": "B", "WeeklyBandMult": "B", "EthBandMult": "EthB", "RthBandMult": "RthB",
         "StopAtrMult": "S", "TargetR": "TP", "BlockSessionFirst": "BF", "BlockSessionLast": "BL",
         "BlockEthFirst": "EthBF", "BlockEthLast": "EthBL", "BlockRthFirst": "RthBF", "BlockRthLast": "RthBL",
         "WeeklyFirstHours": "WF", "WeeklyLastHours": "WL", "SessionForceClose": "FC", "WeeklyForceCloseFriday": "FCfri",
         "CloseAtEthEnd": "EthEnd", "CloseAtRthEnd": "RthEnd", "BandTrailTrigger": "trig", "VwapTrailAtrCushion": "cush",
         "EnableFixedTpBreakEven": "BE", "FixedTpBreakEvenTriggerR": "BEat", "BreakEven": "BE", "AllowHedgeTrades": "hedge",
         "TrackTouchesWhileBlocked": "track"}


def num(v):
    """'4.0' -> '4', 6.5 -> '6.5'."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:g}"


def mgmt(values):
    m = str(values.get("Management", "0")).split(".")[0]
    return f"FT{num(values.get('TargetR', '?'))}" if m == "0" else MGMT_CODE.get(m, f"M{m}")


def band(values):
    for k in ("SessionBandMult", "WeeklyBandMult"):
        if k in values:
            return num(values[k])
    parts = [num(values[k]) for k in ("EthBandMult", "RthBandMult") if k in values]
    return "-".join(parts) if parts else "?"     # ETH-RTH; "-" not "/" (the code is also a file name; "/" until 2026-10-26)


def short_code(symbol, mode, values, news="Noff", timing="BC"):
    """<SYM>_<Mode>_<Mgmt>_B<band>_S<stop>_<News>_<Timing>, e.g. US30_S_RS3_B4_S6.5_Noff_BC."""
    core = f"{symbol}_{MODE_CODE.get(mode, mode)}_{mgmt(values)}_B{band(values)}_S{num(values.get('StopAtrMult', '?'))}"
    return core + (f"_{news}" if news else "") + (f"_{timing}" if timing else "")


def label(values, skip=(), known_only=False):
    """Compact 'tf=m5 B=4 S=6.5 BF=840 ...' (Management shown as its code); known_only: only the settings in LABEL."""
    out = []
    for k, v in values.items():
        if k in skip or (known_only and k not in LABEL and k != "Management"):
            continue
        if k == "Management":
            out.append(mgmt(values))
        elif k != "TargetR" or str(values.get("Management", "0")).split(".")[0] != "0":
            out.append(f"{LABEL.get(k, k)}={num(v)}")
    return " ".join(out)
