"""Job queue, runner and ledger writer (DESIGN §4.4, §4.6, §7). The only writer of the ledger.

  ~/.venvs/fastbt/bin/python -m engine.runner submit <job.json> [...]   validate and queue (queue/pending/)
  ~/.venvs/fastbt/bin/python -m engine.runner run [--workers 14] [--once] [--poll 30]
  ~/.venvs/fastbt/bin/python -m engine.runner status

Job file (JSON):
  idea_id, card (repo path, committed and unchanged), lane, stage, strategy ("strategies/<file>.py:<function>", committed and
  unchanged), params, grid_id, grid_size, symbols, timeframe ("m5" ... "h4"), period ["YYYY-MM", "YYYY-MM"] inside 2014-11 ... 2024-12,
  class (A / B / C), modes (default all four), stress {spread_mult, swap_mult, zero_positive_swap} (default none), review (look-ahead
  review id, or null until reviewed), note.
One job = one test = one ledger row, with metrics per news mode over all its symbols. Trade logs go to runs/<day>/<test_id>/.

Shared tick memory: the runner loads one symbol's FTMO-venue ticks once (t, bid, ask, the add-on and the conversion rate) into
shared memory for the union of the queued periods; up to 14 workers read it without copies (about 32 bytes a tick: 11 GB for the
largest symbol). Nothing is cached on disk. Work runs symbol by symbol; a job's row is written once all its symbols are done.
"""
import argparse
import fcntl
import glob
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from multiprocessing import shared_memory

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from engine import context as CX, costs as C, data, inputs as IN, kernel as K, metrics as M, rules, store, tradelog  # noqa: E402
import zlib  # noqa: E402
from engine.hash import engine_hash  # noqa: E402

QUEUE = os.path.join(REPO, "queue")
LEDGER = os.path.join(REPO, "ledger")
RUNS = os.path.join(REPO, "runs")
WORKERS = 14
STAGES_FORBIDDEN = ("locked",)          # the locked period is opened only by gatekeeper/open_locked.py
TFS = ("m1", "m5", "m10", "m15", "m30", "h1", "h2", "h4")
DEFAULT_STRESS = {"spread_mult": 1.0, "swap_mult": 1.0, "zero_positive_swap": False}


# ------------------------------------------------------------------ helpers
def _git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)


def committed(path):
    """Commit of a repo file, or None if it is untracked or has uncommitted changes."""
    if _git("ls-files", "--error-unmatch", path).returncode != 0:
        return None
    if _git("diff", "--quiet", "HEAD", "--", path).returncode != 0:
        return None
    return _git("log", "-1", "--format=%H", "--", path).stdout.strip() or None


def month_ms(m, end=False):
    d = np.datetime64(m, "M") + (1 if end else 0)
    return int(d.astype("datetime64[ms]").astype(np.int64))


def cost_hash():
    d = json.load(open(C.COSTS_JSON))
    d.pop("built_utc", None)
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12]


def data_hash(symbols, series=None):
    h = hashlib.sha256()
    for s in sorted(symbols):
        m = store.store_meta(s)
        h.update(json.dumps([s, m["months"], m.get("converted_utc")], sort_keys=True).encode())
    if series:                                            # A14 §2: the series store files the job reads (none: hash unchanged)
        from engine import series as SR
        h.update(b"series\0" + SR.store_hash(series).encode())
    return h.hexdigest()[:12]


def local_imports(path, seen=None):
    """Repo files a strategy module imports, directly or through other repo modules (strategies.*, tests.*, tools.*); the engine is
    covered by the engine hash."""
    import ast
    seen = set() if seen is None else seen
    tree = ast.parse(open(os.path.join(REPO, path)).read())
    for node in ast.walk(tree):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
            ([node.module] + [f"{node.module}.{a.name}" for a in node.names] if isinstance(node, ast.ImportFrom) and node.module else [])
        for n in names:
            if n.split(".")[0] not in ("strategies", "tests", "tools"):
                continue
            for cand in (n.replace(".", "/") + ".py", n.rsplit(".", 1)[0].replace(".", "/") + ".py"):
                if os.path.isfile(os.path.join(REPO, cand)) and cand != path and cand not in seen:
                    seen.add(cand)
                    local_imports(cand, seen)
    return sorted(seen)


def validate(job, require_committed=True):
    """Checks a job before it is queued; returns the job with defaults and provenance filled in."""
    j = dict(job)
    for k in ("idea_id", "card", "lane", "stage", "strategy", "symbols", "timeframe", "period", "class"):
        if k not in j:
            raise ValueError(f"job lacks '{k}'")
    if j["stage"] in STAGES_FORBIDDEN:
        raise ValueError("the locked period is opened only by gatekeeper/open_locked.py")
    if j["class"] not in rules.CLASSES:
        raise ValueError(f"class {j['class']}")
    if j["timeframe"] not in TFS:
        raise ValueError(f"timeframe {j['timeframe']}")
    a, b = j["period"]
    data._month(a), data._month(b)
    if a > b:
        raise ValueError("period runs backwards")
    j.setdefault("modes", list(rules.MODES))
    if not set(j["modes"]) <= set(rules.MODES):
        raise ValueError(f"modes {j['modes']}")
    j["stress"] = {**DEFAULT_STRESS, **(j.get("stress") or {})}
    j.setdefault("params", {})
    j.setdefault("grid_id", None)
    j.setdefault("grid_size", 1)
    j.setdefault("review", None)
    j.setdefault("filters", {})
    CX.filter_mask("EURUSD", np.zeros(0, np.int64), j["filters"])          # refuses names / values outside the menu
    j.setdefault("noise", None)
    if j["noise"] and set(j["noise"]) - {"seed", "jitter_spreads", "shift_bars"}:
        raise ValueError(f"noise {j['noise']}")
    j.setdefault("synthetic_edge_r", 0.0)
    if j["synthetic_edge_r"] and j["lane"] != "null":
        raise ValueError("a synthetic edge is for the null calibration only")
    # DESIGN A10.4: a real idea's card states data-mined / seen family as exactly yes / no and its grid size (the luck bar's k);
    # every real job names its route (base / V1-V3: derived for screen and amber stages, required for the others)
    if j["lane"] not in ("null", "referee"):
        from engine import pipeline as P
        cp = os.path.join(REPO, j["card"])
        if not os.path.isfile(cp):
            raise ValueError(f"card {j['card']} not found")
        j["card_flags"] = P.card_flags(open(cp, encoding="utf-8").read())
        derived = "base" if j["stage"] == "screen" else j["stage"][len("amber-"):] if j["stage"].startswith("amber-V") else None
        j.setdefault("route", derived)
        if j["route"] not in P.ROUTES or (derived and j["route"] != derived):
            raise ValueError(f"route {j.get('route')!r}: one of {P.ROUTES} (stage {j['stage']})")
    # DESIGN A14.1: context symbols, inputs only (never traded, no grid axis); a real job's list equals its card's declared row
    if j.get("context"):
        IN.check_context(j["context"], j["symbols"])
    if j.get("series"):                                    # DESIGN A14 §2: outside series, each known and in the store
        from engine import series as SR
        if not isinstance(j["series"], list) or len(set(j["series"])) != len(j["series"]):
            raise ValueError(f"series must be a list of distinct names, not {j['series']!r}")
        for n in j["series"]:
            if not n.startswith("calendar:"):
                SR.series(n)
    if j["lane"] not in ("null", "referee"):
        text = open(os.path.join(REPO, j["card"]), encoding="utf-8").read()
        declared = IN.card_context(text)
        if sorted(declared or []) != sorted(j.get("context") or []):
            raise ValueError(f"context {j.get('context') or []} differs from the card's '| context symbols |' row "
                             f"{declared if declared is not None else '(no row)'} (A14.1: changing them is a new card)")
        declared = IN.card_series(text)
        if sorted(declared or []) != sorted(j.get("series") or []):
            raise ValueError(f"series {j.get('series') or []} differ from the card's '| outside series |' row "
                             f"{declared if declared is not None else '(no row)'} (A14 §2.4: fixed inputs)")
    j.setdefault("venue", "ftmo")
    if j["venue"] not in ("ftmo", "ic"):
        raise ValueError(f"venue {j['venue']}")
    if j["venue"] == "ic" and j["lane"] != "referee":
        raise ValueError("research is judged on the FTMO venue (DESIGN §3.5); IC runs are for referees only")
    for s in j["symbols"]:
        store.store_meta(s)
    path, _, fn = j["strategy"].partition(":")
    if not fn or not os.path.isfile(os.path.join(REPO, path)):
        raise ValueError(f"strategy {j['strategy']}: expected 'strategies/<file>.py:<function>'")
    if require_committed:
        j["card_commit"] = committed(j["card"])
        j["strategy_commit"] = committed(path)
        if not j["card_commit"]:
            raise ValueError(f"card {j['card']} is not committed or has uncommitted changes (idea card first)")
        if not j["strategy_commit"]:
            raise ValueError(f"strategy {path} is not committed or has uncommitted changes")
        j["strategy_deps"] = {}
        for dep in local_imports(path):                                 # repo code the module imports is pinned too
            c = committed(dep)
            if not c:
                raise ValueError(f"{dep} (imported by {path}) is not committed or has uncommitted changes")
            j["strategy_deps"][dep] = c
        from engine import reviews
        j["review"] = reviews.lookup(path, j["strategy_commit"], j["strategy_deps"])   # on the ledger row; only PASS counts (§6.2)
    return j


def submit(paths, require_committed=True):
    os.makedirs(os.path.join(QUEUE, "pending"), exist_ok=True)
    out = []
    for p in paths:
        j = validate(json.load(open(p)), require_committed)
        j["job_id"] = j.get("job_id") or "J" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        j["submitted_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        dst = os.path.join(QUEUE, "pending", j["job_id"] + ".json")
        json.dump(j, open(dst, "w"), indent=1)
        out.append(dst)
    return out


# ------------------------------------------------------------------ ledger
def _ledger_rows():
    n, ideas = 0, set()
    for f in sorted(glob.glob(os.path.join(LEDGER, "*.jsonl"))):
        for line in open(f):
            if line.strip():
                n += 1
                ideas.add(json.loads(line).get("idea_id"))
    return n, ideas


def append_ledger(row_fn):
    """Appends one row under a lock; row_fn(test_id, count_at_run) builds it. Returns the row."""
    os.makedirs(LEDGER, exist_ok=True)
    with open(os.path.join(LEDGER, ".lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        n, ideas = _ledger_rows()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        test_id = f"T{day.replace('-', '')}-{n + 1:06d}"
        row = row_fn(test_id, {"tests": n + 1, "ideas": len(ideas | {None}) - 1})
        with open(os.path.join(LEDGER, day + ".jsonl"), "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        fcntl.flock(lk, fcntl.LOCK_UN)
    return row


# ------------------------------------------------------------------ shared ticks
class SharedTicks:
    """One symbol's fill-ready ticks in shared memory (created by the runner, attached by workers)."""
    FIELDS = (("t", np.int64), ("bid", np.float64), ("ask", np.float64), ("half_addon", np.float32), ("conv", np.float32))

    def __init__(self, symbol, first_month, last_month, spread_mult, costs, venue="ftmo"):
        tk = data.ticks(symbol, first_month, last_month, venue=venue, costs=costs, spread_mult=spread_mult)
        arrays = {"t": tk.t, "bid": tk.bid, "ask": tk.ask, "half_addon": tk.half_addon,
                  "conv": np.zeros(0) if tk.conv_bid is None else (tk.conv_bid + tk.conv_ask) / 2}
        self.shm, self.spec = [], {}
        for name, dt in self.FIELDS:
            a = np.ascontiguousarray(arrays[name], dtype=dt)
            sm = shared_memory.SharedMemory(create=True, size=max(a.nbytes, 1))
            np.ndarray(a.shape, dt, buffer=sm.buf)[:] = a
            self.shm.append(sm)
            self.spec[name] = (sm.name, a.shape, np.dtype(dt).str)
        self.breaks = rules.market_breaks(tk.t, tk.close_ms)        # A8: closes, regular daily flag
        self.info = {"symbol": symbol, "ticks": int(len(tk.t)), "n_dropped_crossed": tk.n_dropped_crossed,
                     "n_zeroed_crossed": tk.n_zeroed_crossed, "spread_mult": spread_mult, "venue": venue}
        del tk, arrays

    def release(self):
        for sm in self.shm:
            sm.close()
            sm.unlink()


def attach(spec):
    """Worker side: views on the shared arrays (no copies). Returns (arrays, handles)."""
    arrays, handles = {}, []
    for name, (shm_name, shape, dt) in spec.items():
        sm = shared_memory.SharedMemory(name=shm_name)    # workers share the parent's resource tracker: the parent unlinks
        handles.append(sm)
        arrays[name] = np.ndarray(shape, np.dtype(dt), buffer=sm.buf)
    return arrays, handles


class _Ticks:
    """FillTicks-like view for the trade log."""
    def __init__(self, a, lo, hi, symbol, venue):
        self.symbol, self.venue = symbol, venue
        self.t, self.bid, self.ask = a["t"][lo:hi], a["bid"][lo:hi], a["ask"][lo:hi]
        self.half_addon = a["half_addon"][lo:hi]
        conv = a["conv"][lo:hi] if len(a["conv"]) else None
        self.conv_bid = self.conv_ask = conv


# ------------------------------------------------------------------ worker
_MODS = {}
ENTRY_KEYS = ("side", "otype", "price", "sl_dist", "tp_dist", "expiry_ms", "hold_ms")


def shift_signals(I, rng, k):
    """Moves every entry intent k bars later (G2 noise, DESIGN A4.4); a move onto a bar that already has an entry, or past the
    last bar, is dropped. Exits and trails stay where they are. (rng is kept in the signature; the jitter uses it.)"""
    side = np.asarray(I["side"])
    n = len(side)
    out = dict(I)
    for key in ENTRY_KEYS:
        if key in I:
            a = np.asarray(I[key])
            out[key] = np.zeros_like(a) if key in ("side", "otype") else np.full(n, np.nan)
    idx = np.flatnonzero(side != 0)
    dst = idx + k                                   # DESIGN A4.4: later only (an earlier move would use the later bar's levels)
    taken = set()
    for i, d in zip(idx, dst):
        if 0 <= d < n and d not in taken:
            taken.add(d)
            for key in ENTRY_KEYS:
                if key in I:
                    out[key][d] = np.asarray(I[key])[i]
    return out



def _strategy(spec):
    if spec not in _MODS:
        path, _, fn = spec.partition(":")
        s = importlib.util.spec_from_file_location("strat_" + hashlib.md5(path.encode()).hexdigest()[:8], os.path.join(REPO, path))
        mod = importlib.util.module_from_spec(s)
        s.loader.exec_module(mod)
        _MODS[spec] = getattr(mod, fn)
    return _MODS[spec]


class ZeroIntentError(ValueError):
    pass


def work(job, symbol, spec, breaks, out_dir, events, far):
    """One job on one symbol, every news mode. Returns {mode: (log, counters)} with the trade logs saved under out_dir."""
    a, handles = attach(spec)
    try:
        first_ms, end_ms = month_ms(job["period"][0]), month_ms(job["period"][1], end=True)
        lo, hi = np.searchsorted(a["t"], first_ms), np.searchsorted(a["t"], end_ms)
        tk = _Ticks(a, lo, hi, symbol, job["venue"])
        costs = C.load()
        meta = store.store_meta(symbol)
        tick = float(meta["tick_size"])
        b = data.bars(symbol, job["timeframe"])
        keep = b["close_ms"] <= end_ms
        b = {k: v[keep] for k, v in b.items()}
        ctx = {"symbol": symbol, "timeframe": job["timeframe"], "tick": tick,
               "digits": int(meta.get("symbol_digits") or meta["digits"]), "first_ms": first_ms, "end_ms": end_ms}
        if job.get("context"):                             # A14.1: closed context bars aligned to the traded bars' closes
            ctx["context"] = IN.context(job["context"], job["timeframe"], b["close_ms"], end_ms)
        if job.get("series"):                              # A14 §2: values visible from the first bar closing after release
            from engine import series as SR
            ctx["series"] = SR.outside(job["series"], b["close_ms"])
        noise = job.get("noise")
        rng = np.random.default_rng([int(noise["seed"]), zlib.crc32(symbol.encode())]) if noise else None
        if noise and noise.get("jitter_spreads"):          # G2 noise: each bar shifted by up to +-1 spread (one offset per bar)
            sample = (tk.ask[::1000] - tk.bid[::1000]) if hi > lo else np.zeros(1)
            off = rng.uniform(-1, 1, len(b["c"])) * float(np.median(sample)) * float(noise["jitter_spreads"])
            b = dict(b, o=b["o"] + off, h=b["h"] + off, l=b["l"] + off, c=b["c"] + off)
        I = dict(_strategy(job["strategy"])(b, dict(job["params"]), ctx))
        own_flat = np.asarray(I.pop("flat_ms", []), np.int64)
        # Guard (2026-11-15, IDEA-2000 'EU50' vs the store's 'STOXX50'): a real job whose strategy gives no entry intent on a
        # declared symbol over the whole period is refused here, before any trade is simulated (no result exists, no ledger row).
        # Checked before the job's filters: a filter may empty a symbol legitimately (that is flagged on the row, not refused).
        if job["lane"] not in ("null", "referee"):
            live = (np.asarray(b["open_ms"]) >= first_ms) & (np.asarray(b["close_ms"]) <= end_ms)
            if not (np.asarray(I["side"])[live] != 0).any():
                raise ZeroIntentError(f"ZERO INTENTS: {job['strategy']} gives no entry intent on {symbol} over {job['period'][0]} -> "
                                      f"{job['period'][1]} (symbol name the module doesn't know?); job refused before any trade ran")
        if job.get("filters"):                             # amber / random filter menu, at the decision bar's close
            I["side"] = np.where(CX.filter_mask(symbol, b["close_ms"], job["filters"]), np.asarray(I["side"]), 0)
        if noise and noise.get("shift_bars"):              # G2 noise: every entry signal moved one bar later (A4.4)
            I = shift_signals(I, rng, int(noise["shift_bars"]))
        before = np.asarray(b["open_ms"]) < first_ms       # decisions only from the period start (the strategy may not enforce it)
        if before.any():
            I["side"] = np.where(before, 0, np.asarray(I["side"]))
        out = {}
        st = job["stress"]

        def price_at(ms):                                  # mid at the first tick at or after a window opens (far-stop bp -> price)
            k = min(int(np.searchsorted(tk.t, ms)), len(tk.t) - 1)
            return (tk.bid[k] + tk.ask[k]) / 2
        for mode in job["modes"]:
            kw, info = rules.build_parts(symbol, job["class"], mode, tk.t, breaks, events, far, price_at)
            kw["flat_ms"] = np.union1d(kw["flat_ms"], own_flat[(own_flat >= first_ms) & (own_flat < end_ms)])
            tr, cnt = K.run(tk.t, tk.bid, tk.ask, b["close_ms"], min_step=tick / 2,
                            pip_size=float(meta["pip_size"]), **I, **kw)
            log = tradelog.build(tr, tk, symbol, costs, events=events, swap_mult=st["swap_mult"],
                                 zero_positive_swap=st["zero_positive_swap"], synthetic_edge_r=float(job.get("synthetic_edge_r") or 0),
                                 decision_ms=b["close_ms"][tr["bar"]])
            np.savez_compressed(os.path.join(out_dir, f"{symbol}_{mode}.npz"),
                                **{k: (v.astype(str) if v.dtype == object else v) for k, v in log.items()})
            out[mode] = (log, cnt, info)
        return out
    finally:
        for h in handles:
            h.close()


# ------------------------------------------------------------------ runner
def _claim():
    os.makedirs(os.path.join(QUEUE, "running"), exist_ok=True)
    jobs = []
    for p in sorted(glob.glob(os.path.join(QUEUE, "pending", "*.json"))):
        dst = os.path.join(QUEUE, "running", os.path.basename(p))
        os.rename(p, dst)
        jobs.append((dst, json.load(open(dst))))
    return jobs


def _finish(path, job, parts, eh, ch, info):
    """All symbols of a job done: metrics per mode, one ledger row, job file to done/."""
    first_ms, end_ms = month_ms(job["period"][0]), month_ms(job["period"][1], end=True)
    by_mode = {}
    for mode in job["modes"]:
        logs = [parts[s][mode][0] for s in job["symbols"]]
        cnt = {}
        for s in job["symbols"]:
            for k, v in parts[s][mode][1].items():
                cnt[k] = cnt.get(k, 0) + v
        by_mode[mode] = M.compute(logs, cnt, first_ms, end_ms)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # symbols without a single trade in any mode run (e.g. a filter that empties a symbol): flagged on the row (2026-11-15)
    zero = sorted(s for s in job["symbols"] if all(len(parts[s][m][0]["entry_t"]) == 0 for m in job["modes"]))

    def row(test_id, count):
        run_dir = os.path.join(RUNS, day, test_id)
        os.makedirs(os.path.dirname(run_dir), exist_ok=True)
        os.rename(job["_tmp_dir"], run_dir)
        return {"test_id": test_id, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "job_id": job["job_id"],
                "idea_id": job["idea_id"], "card": job["card"], "card_commit": job.get("card_commit"),
                "card_version": job.get("card_version"), "lane": job["lane"], "stage": job["stage"],
                "strategy": job["strategy"], "strategy_commit": job.get("strategy_commit"), "strategy_deps": job.get("strategy_deps"), "variant": job["params"],
                "grid_id": job["grid_id"], "grid_size": job["grid_size"], "symbols": job["symbols"], "timeframe": job["timeframe"],
                "period": job["period"], "class": job["class"], "venue": job["venue"], "stress": job["stress"],
                "filters": job.get("filters"), "noise": job.get("noise"), "synthetic_edge_r": job.get("synthetic_edge_r"),
                "engine_hash": eh, "cost_hash": ch,
                "data_hash": data_hash(job["symbols"] + list(job.get("context") or []), job.get("series")),
                "review": job["review"],
                "metrics": by_mode, "news_flag": M.news_flag(by_mode), "zone": None, "verdict": None,
                "run_path": os.path.relpath(run_dir, REPO), "count_at_run": count, "data_info": info, "note": job.get("note"),
                "route": job.get("route"), "card_flags": job.get("card_flags"),
                "zero_trade_symbols": zero, **({"context": job["context"]} if job.get("context") else {}),
                **({"series": job["series"]} if job.get("series") else {})}
    r = append_ledger(row)
    os.makedirs(os.path.join(QUEUE, "done"), exist_ok=True)
    job.pop("_tmp_dir", None)
    job["test_id"] = r["test_id"]
    json.dump(job, open(path, "w"), indent=1)
    os.rename(path, os.path.join(QUEUE, "done", os.path.basename(path)))
    return r


def _fail(path, job, err):
    os.makedirs(os.path.join(QUEUE, "failed"), exist_ok=True)
    job["error"] = err
    json.dump({k: v for k, v in job.items() if k != "_tmp_dir"}, open(path, "w"), indent=1)
    os.rename(path, os.path.join(QUEUE, "failed", os.path.basename(path)))


def run_batch(workers=WORKERS, log=print):
    jobs = _claim()
    if not jobs:
        return 0
    awake = None
    if os.path.exists("/usr/bin/caffeinate"):     # keep the Mac awake only while a batch runs (idle waiting doesn't)
        awake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())])
    try:
        return _run_claimed(jobs, workers, log)
    finally:
        if awake is not None:
            awake.terminate()


def _run_claimed(jobs, workers, log):
    eh, ch = engine_hash(), cost_hash()
    costs = C.load()
    try:
        from engine import news
        events, far = news.events(), news.far_thresholds()
    except ImportError:
        events, far = [], {}
    # work units grouped by (symbol, spread multiplier); each group shares one copy of the ticks
    groups = {}
    for path, job in jobs:
        job["_tmp_dir"] = os.path.join(RUNS, "_tmp", job["job_id"])
        os.makedirs(job["_tmp_dir"], exist_ok=True)
        for s in job["symbols"]:
            groups.setdefault((s, job["venue"], float(job["stress"]["spread_mult"])), []).append((path, job))
    parts = {job["job_id"]: {} for _, job in jobs}
    infos = {job["job_id"]: {} for _, job in jobs}
    failed = set()
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for (sym, venue, sm), members in sorted(groups.items()):
            first = min(j["period"][0] for _, j in members)
            last = max(j["period"][1] for _, j in members)
            t0 = time.time()
            sh = SharedTicks(sym, first, last, sm, costs, venue)
            log(f"{sym} {venue} x{sm}: {sh.info['ticks']:,} ticks {first}..{last} in shared memory ({time.time() - t0:.0f} s), "
                f"{len(members)} jobs")
            try:
                futs = {pool.submit(work, job, sym, sh.spec, sh.breaks, job["_tmp_dir"], events, far): (path, job)
                        for path, job in members if job["job_id"] not in failed}
                for f in as_completed(futs):
                    path, job = futs[f]
                    try:
                        parts[job["job_id"]][sym] = f.result()
                        infos[job["job_id"]][sym] = sh.info
                    except Exception as e:
                        failed.add(job["job_id"])
                        _fail(path, job, traceback.format_exc())
                        log(f"FAILED {job['job_id']} {job['idea_id']} {job['stage']} on {sym}: {type(e).__name__}: {e}")
                        continue
                    if len(parts[job["job_id"]]) == len(job["symbols"]):
                        pj = {s: {m: parts[job["job_id"]][s][m][:2] for m in job["modes"]} for s in job["symbols"]}
                        r = _finish(path, job, pj, eh, ch, infos[job["job_id"]])
                        done += 1
                        m0 = r["metrics"].get("M0", {})
                        log(f"{r['test_id']} {job['idea_id']} {job['stage']}: M0 {m0.get('trades')} trades, net {m0.get('net_r')} R")
                        if r["zero_trade_symbols"]:
                            log(f"WARNING {r['test_id']} {job['idea_id']}: no trades in any mode on {r['zero_trade_symbols']}")
                        parts[job["job_id"]] = {}
            finally:
                sh.release()
    return done


def status():
    out = {}
    for q in ("pending", "running", "done", "failed"):
        out[q] = len(glob.glob(os.path.join(QUEUE, q, "*.json")))
    n, ideas = _ledger_rows()
    out["ledger_tests"], out["ledger_ideas"] = n, len(ideas)
    out["engine_hash"] = engine_hash()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll", type=int, default=30)
    ap.add_argument("action", choices=("submit", "run", "status"))
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    if a.action == "submit":
        for p in submit(a.files):
            print("queued", os.path.relpath(p, REPO))
    elif a.action == "status":
        print(json.dumps(status(), indent=1))
    else:
        while True:
            n = run_batch(a.workers, log=lambda s: print(datetime.now().strftime("%H:%M:%S"), s, flush=True))
            if a.once:
                break
            if not n:
                time.sleep(a.poll)


if __name__ == "__main__":
    main()
