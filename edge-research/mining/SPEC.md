# Mining sweep 1: the grammar and the draw (DESIGN A15 §1.1)

Status: **v2 (2026-11-17), answering the sceptic's review of v1** (`gatekeeper/sceptic/2026-11-17-mining-spec-v1.md`, narrow BLOCK).
Nothing is drawn, compiled or run until the gatekeeper says the review is resolved.
Author: the mining session. Law: `DESIGN.md` A15 (with §10, the sceptic's re-check conditions), A14, A13, A1, §3.7.

One sweep of exactly **N = 50,000 rules**, drawn once by a seeded, non-adaptive sampler from the grammar below, then compiled by one
composer (`mining/composer.py`, `intents(bars, params, ctx)` per `engine/STRATEGY-API.md`) and run once each over
2014-11 → 2024-12 in all four news modes. No tuning: every rule is judged at its drawn values.

The grammar is deliberately small: **8 entry families, 3 filters (all from the engine's existing menu), 1 stop rule, 3 exit types.**
Each family is a few lines of code the look-ahead reviewer can read on its own.

### Changes from v1 (the sceptic's findings)
| finding | change |
|---|---|
| 1, 2 | **Filters cut to A15 §1.1's list:** session, volatility third and trend (= the engine's `regime`, the A3 menu's trend / range). The `vix` and `expiry` filters and the composer's SMA-200 trend filter are **dropped** (the user's decision, 2026-11-17: "yes" to dropping all three; §4). The only outside series left are the COT columns. |
| 3 | Every job field is derived from `def`; the runner recomputes `def_hash` and refuses any difference; period fixed (§13). |
| 4 | A mining job whose rule fires no entry on a symbol writes a zero-trade row (red), never a refusal (§13). |
| 5 | The locked open runs the same composer with COT and context symbols extended past 2024 by a loader that is byte-identical for t ≤ 2024, checked on a sample of mined rows (§13). |
| 6 | An event needs finite inputs at both i and i − 1; unit test across warm-up and holes (§2, §10). |
| 7 | Blocs are weighted so that every symbol is equally likely to be in a rule (§6.2). |
| 8 | × 2 applies to the whole FTMO spread; the pass criterion, the G3 ticks and the holiday limit are stated (§12). |
| 9 | Canonical form, redraw within the family slot, numpy pinned, SPEC hash bound, one draw only, PULL ties, COT per-year coverage, the JP225 reason (§3.8, §6.4, §8). |
| — | Aligned to the engine owner's runner side (branch `engine-a15`): `engine.mining.job_for` builds every job, `BOUND.json` format, canonical / `def_hash` from `engine.mining`, the null's sign tables, the `cash_session` window format (§8.2, §8.4, §9, §12.4, §13). |
| 10 (info) | CTX runs on m15 and h1 only (h4 anchors may differ between symbols, §3.3.4); main real rows are 62, not 49 (§14). |

---

## 1. A rule

A rule is one JSON object; its canonical form is defined in §8.2:

```json
{"block":{"mode":"follow","n":20},"class":"B","context":[],"exit":{"r":1.5,"type":"tp"},"family":"BRK",
 "filters":{"session":"london"},"series":[],"stop_atr":2.0,"symbols":["EURUSD","XAUUSD"],"timeframe":"h1"}
```

- **one entry block** (§3) with its parameters;
- **0, 1 or 2 filters** (§4);
- **one stop** (§5), **one exit** (§5);
- **1–4 traded symbols** (§6), **one timeframe**, **one class**;
- `context` (one context symbol for family CTX, else empty) and `series` (the COT columns for family COT, else empty) follow from the
  block; they are part of the definition and of its hash.

Every entry is a **market order** decided at a bar's close (`otype` 0); the engine makes it live on the first tick after that close.
No stop or limit entry orders, no trailing stops, no pyramiding (the engine's one position per strategy and symbol).

## 2. Conventions used by every block (the reviewer checks these once)

- **Closed bars only.** The value at bar i uses bars ≤ i. Indicators are causal recursions or trailing windows; nothing is normalised
  over the whole period; nothing is centred.
- **Indicators (all on bid OHLC of the job's timeframe):**
  - `ATR(14)`: Wilder, seeded with the mean true range of the first 14 bars (the same code as `strategies/null_random.py`);
  - `SMA(n)`: trailing mean of the last n closes;
  - `EMA(n)`: α = 2 / (n + 1), seeded with SMA(n) at bar n − 1;
  - `RSI(n)`: Wilder, seeded with the mean gain / loss of the first n changes;
  - `HH(n)[i]` = max of `h` over bars i − n … i − 1; `LL(n)[i]` = min of `l` over bars i − n … i − 1 (bar i excluded).
- **Finite inputs (finding 6).** A condition at bar i is **undefined** (no event, no state) when any input it reads at i is NaN
  (warm-up, a context hole, the FX quarantine of a context symbol, a COT percentile with fewer than 52 releases). An **event** at i
  needs the condition **defined at both i and i − 1**: true at i and *defined and false* at i − 1. So nothing fires as a fresh cross
  on the first bar after warm-up or a hole. Unit test (§10).
- **Differences only, never ratios to price.** Every condition compares prices, price differences and ATR multiples. This keeps the
  mirror construction (next point) exact and avoids any price-level dependence.
- **Mirror symmetry by construction (A15 §1.3).** Each family is written once, as a **long** condition `L(bars, inputs)`. The short
  condition is the same function applied to mirrored inputs: `S = L(mirror(bars), mirror(inputs))` with
  `mirror(o, h, l, c) = (−o, −l, −h, −c)` for the traded symbol and for a context symbol, and `mirror(x) = −x` for the signed COT
  net position. ATR, sessions, the volatility third and the regime (|close − SMA| > k·ATR) are unchanged by the mirror. So no
  block, filter or parameter can prefer a side, and there is **no `side` parameter anywhere**. Unit test (§10): for every family,
  `intents` on mirrored bars returns exactly `−side` and swaps `exit_long` / `exit_short`.
  (Mirror symmetry of the rule does not make its realised trades balanced; A15 §3.4's 25% side rule is the guard for that.)
- **Events, not states** (except COT, §3.8): an entry fires on the bar where the long condition becomes true (as defined above).
  Signals while a position is open are dropped by the engine (counted).
- **Decision window:** `side` is non-zero only on bars with `ctx["first_ms"] ≤ open_ms < ctx["end_ms"]`.
- **Never read:** `bars["vol"]` (tick volume, A13), the news calendar, any calendar series, VIX, files, the network, random numbers.
  The composer has no randomness at all.
- **The engine, not the composer,** applies the filters (§4), class rules, entry blocks, the four news modes, caps and costs.

## 3. Entry families (8), each with its parameter values

Families are drawn in **equal quotas: 6,250 rules each** (§8). "mode" values: `follow` trades in the direction of the move, `fade`
against it; for `fade` the long condition is the `follow` short condition (and vice versa), i.e. the same event with the side
negated.

| # | family | long condition at bar i (follow) | parameters (ordered values) | timeframes |
|---|---|---|---|---|
| 3.1 | **BRK** channel breakout | `c[i] > HH(n)[i]`; event | n ∈ {10, 20, 55, 100}; mode ∈ {follow, fade} | m15, h1, h4 |
| 3.2 | **PULL** pullback in trend | `c[i] > SMA(t)[i]` and `c[i] ≤ min(c[i−p+1] … c[i−1])`; event | t ∈ {50, 100, 200}; p ∈ {3, 5, 10} | m15, h1, h4 |
| 3.3 | **TOD** time of day | bar i closes at hh:00 Amsterdam with hh = H, and `c[i] − c[i−m] > 0` | H ∈ {1, 2, …, 22} (whole hours); m ∈ {1, 4, 12}; mode ∈ {follow, fade} | m15, h1 |
| 3.4 | **MAX** moving-average cross | `EMA(fast)[i] > EMA(slow)[i]`; event | fast ∈ {5, 10, 20}; slow ∈ {50, 100, 200}; mode ∈ {follow, fade} | m15, h1, h4 |
| 3.5 | **OSC** RSI extreme | revert: `RSI(n)[i] ≤ T`; momentum: `RSI(n)[i] ≥ 100 − T`; event | n ∈ {2, 5, 14}; T ∈ {10, 20, 30}; mode ∈ {revert, momentum} | m15, h1, h4 |
| 3.6 | **BAND** ATR band around a rolling mean | `c[i] > SMA(t)[i] + w·ATR(14)[i]`; event | t ∈ {20, 50, 100}; w ∈ {1, 2, 3}; mode ∈ {follow, fade} | m15, h1, h4 |
| 3.7 | **CTX** context-symbol breakout (A14 §1) | context symbol X: `cx[i] > HHx(n)[i]` and `age_ms[i] = 0`; event | X (§6.3); n ∈ {10, 20, 55}; relation ∈ {same, opposite} | m15, h1 |
| 3.8 | **COT** speculators' positioning (A14 §2) | **state**: `P52(sign·net)[i] ≥ T` (mode follow) | T ∈ {70, 80, 90}; mode ∈ {follow, fade} | m15, h1, h4 |

"event" = the condition is true at i and defined and false at i − 1 (§2).

Notes per family:
- **3.2 PULL** has no mode: it always buys a dip in an up-trend (mirror: sells a rally in a down-trend). **Ties count as lowest**
  (`≤`): a close equal to the lowest of the previous p − 1 closes qualifies. The opposite reading (sell the dip in an up-trend) is
  covered by BRK fade and OSC.
- **3.3 TOD** is an event by construction (one decision bar per day per hour); `c[i−m]` must be finite. H is the Amsterdam clock hour
  at which the decision bar closes (m15: the bar ending hh:00; h1: the bar ending hh:00). The grid is **every whole hour from 01 to
  22**, uniform, nothing chosen: 23:00 and 00:00 fall in the engine's 22:45 → 00:15 entry block. No half hours and no hour taken
  from any release time (A15 §1.3). Not on h4 (h4 closes sit on an unknown anchor, §3.3.4). A TOD rule never draws the session
  filter (it would empty or duplicate it).
- **3.4 MAX** and **3.6 BAND** use rolling means over a fixed number of bars, never reset at a session, day or week (§7).
- **3.5 OSC** mirror: RSI on mirrored prices = 100 − RSI, so "revert" buys `RSI ≤ T` and sells `RSI ≥ 100 − T`.
- **3.7 CTX:** X is one symbol, declared in `context` (A14 §1.1: at most 3; here exactly 1, never a traded symbol of the rule).
  `cx`, `hx` are `ctx["context"][X]["c"]`, `["h"]` (aligned, A14 §1.2); `HHx(n)[i]` is the max of the aligned `h` over the n
  aligned elements before i (where X was shut on schedule the aligned value repeats; the event additionally needs `age_ms[i] = 0`,
  so it fires only on a freshly closed X bar). NaN anywhere in the window or at i − 1 (holes, before X's history, FX quarantine) →
  no event. relation `same`: long the traded symbol when X breaks up; `opposite`: long the traded symbol when X breaks down. Mirror:
  both the traded and the context prices are negated. **m15 and h1 only:** h4 bars come from cTrader's exports with an unknown
  anchor that may differ between symbols (§3.3.4), so `age_ms = 0` might never hold on h4.
- **3.8 COT** (Legacy report, futures only, non-commercial category, CFTC current vintage, A14 §2.3(d)):
  - `net` = `Noncommercial Positions-Long (All)` − `Noncommercial Positions-Short (All)` for the symbol's contract (§6.4), both
    declared in `series` with the exact names `cot:legacy:<code>:Noncommercial Positions-Long (All)` and
    `cot:legacy:<code>:Noncommercial Positions-Short (All)`; `sign` = +1 if a long future is long the traded symbol, −1 if short.
    Both columns exist and are finite on every 2014–2024 row of all 13 codes (engine owner, 2026-11-17).
  - `P52(x)[i]` = 100 × the share of the last 52 distinct releases visible at bar i (the current one included) whose value is
    ≤ the current value. "Distinct releases" = the distinct `release_ms` in the aligned array up to bar i; fewer than 52 → NaN → no
    entry. With bars from 2014-01 this starts about 2015-01 (oil about 2018-07). Releases that land between the same two bar closes
    (catch-up weeks) merge into the later one; this is causal. Percentile of a **level**, never a week-on-week change
    (A14 §2.3(b)). Under the mirror, P52(−x) counts values ≥ the current one, so the mirror is exact including ties.
  - **State:** `side` = +1 on every bar where the long state holds (−1 for the mirrored state; mode fade swaps them). The engine's
    one-position rule makes this "be positioned while in the zone": after an exit the rule re-enters at the next bar while the state
    holds. A state is used because an event at the release bar would fall in the Friday pre-weekend entry block (A14 §2.1).
  - Every COT rule carries the A14 ±1% G2 perturbation stress (A14 §2.7) if it reaches G2.

## 4. Filters (0, 1 or 2 per rule): A15 §1.1's list only

Number of filters: 0 / 1 / 2 with probability 0.4 / 0.4 / 0.2; types drawn without replacement from the types allowed for the family,
each value uniform. All three are applied by the engine (`job.filters`, `engine/context.py`), to entries only, at the decision bar's
close.

| filter | values | definition (engine/context.py) |
|---|---|---|
| **session** | asia, london, ny | Amsterdam hour of the decision bar's close: asia [00, 08), london [08, 14), ny [14, 22) |
| **vol** | low, mid, high | volatility third of the last closed h4 bar (ATR(14) percentile over the previous 1,500 h4 values) |
| **regime** (A15's "trend") | trend, range | last closed h4 bar: \|close − SMA 200\| > k_symbol · ATR(14) (A4.5) |

- TOD rules draw from {vol, regime} only (§3.3).
- **Bloc** (A15 §1.1) enters through the symbol set (§6.2), not as a filter.
- **Dropped in v2 (sceptic findings 1–2; the user's decision 2026-11-17, "yes", relayed by the gatekeeper):** the `vix` filter, the `expiry` filter and the composer's with / against
  SMA-200 trend filter. They are not in A15 §1.1's list, the expiry calendar as wired omitted the quarterly expiries and stops at
  2024, and `expiry` is the one input that matches a main idea's file name this session saw (`idea_1007_monthly_opex_…`; §11).
- **No side filter, no year, month, day-of-week or date filter, no "recent" slice, no regime start date** (A15 §1.3).
- All three filters are unchanged by the mirror.
- Information (sceptic, finding 10): `regime`'s k_symbol is a median over 2014-11 → 2016-10, which lies inside the judged window.
  It is direction-free; stated, not changed.

## 5. Stop and exit

- **Stop (every rule):** `sl_dist = s · ATR(14)[i]`, s ∈ {1.0, 1.5, 2.0, 2.5, 3.0}. 1 R = the stop distance.
- **Exit,** one of three types with probability 1/3 each:
  - `tp`: target `r · sl_dist`, r ∈ {1.0, 1.5, 2.0, 3.0};
  - `time`: `hold_ms = b ×` the timeframe, b ∈ {3, 6, 12, 24} bars;
  - `none`: no target and no time exit; `exit_long[i]` = the block's short event at i (no filters), `exit_short[i]` = its long
    event (for COT: the mirrored state). Positions also end at the stop and at the class's flat times.
- **Class** ∈ {A, B, C}, uniform. The engine applies it (A8).

## 6. Symbols, timeframes, context and series

### 6.1 Traded universe
The 39 firm symbols (§3.2), store names: 28 G8 FX pairs; `US500, USTEC, US30, DE40, JP225, UK100, STOXX50`; `XAUUSD, XAGUSD`;
`XTIUSD, XBRUSD`. Data-only symbols (AUS200, F40, HK50, US2000) are never traded and never context. Short histories (DE40 from
2021-09, oil from 2017-07) stay in, as in the A3 menu.

### 6.2 Symbol set (1–4 symbols), every symbol equally likely (finding 7)
- size k uniform in {1, 2, 3, 4};
- mode `bloc` or `any`, 1/2 each:
  - `any`: k symbols drawn uniformly from the family's universe U without replacement;
  - `bloc`: a bloc b among the blocs with at least one symbol in U (equities, usd, metals, oil, crosses, as `engine/context.py`
    `bloc`), then min(k, m_b) symbols drawn uniformly from it without replacement, where m_b = the bloc's size within U. Bloc b is
    drawn with probability **∝ m_b / E[min(k, m_b)]** (k uniform on {1, 2, 3, 4}). Then a symbol's chance of being in the set is
    the same for every symbol in U, in each mode: no exposure, bloc or symbol is weighted up or down.
  - For U = the 39: bloc probabilities equities 0.172, usd 0.172, metals 0.070, oil 0.070, crosses 0.516; each symbol's inclusion
    0.0614 in `bloc` mode and 0.0641 in `any` mode, the same for all 39. For U = the COT 13: usd 0.446, equities 0.212, metals 0.182,
    oil 0.159; inclusion 0.159 in `bloc` mode.
  - The sampler reports each symbol's realised inclusion count with the list (a check, not a choice).
- Family universe U: the 39, except COT (§6.4: 13 symbols).
- **Timeframe** uniform over the family's list in §3 (m15 / h1 / h4; TOD and CTX m15 / h1).

### 6.3 Context symbol (CTX only)
Uniform over the 39 firm-tradable symbols minus the rule's traded symbols (A14 §1.1, §1.5). An FX context symbol makes the rule run
fx2015 as an FX rule (A14 §1.4).

### 6.4 COT contracts (Legacy, futures only)
| traded symbol | CFTC market | code | sign |
|---|---|---|---|
| EURUSD | Euro FX (CME) | 099741 | +1 |
| GBPUSD | British pound (CME) | 096742 | +1 |
| AUDUSD | Australian dollar (CME) | 232741 | +1 |
| NZDUSD | New Zealand dollar (CME) | 112741 | +1 |
| USDJPY | Japanese yen (CME) | 097741 | −1 |
| USDCHF | Swiss franc (CME) | 092741 | −1 |
| USDCAD | Canadian dollar (CME) | 090741 | −1 |
| XAUUSD | Gold (COMEX) | 088691 | +1 |
| XAGUSD | Silver (COMEX) | 084691 | +1 |
| XTIUSD | Crude oil, light sweet (NYMEX) | 067651 | +1 |
| US500 | E-mini S&P 500 (CME) | 13874A | +1 |
| USTEC | E-mini Nasdaq-100 (CME) | 209742 | +1 |
| US30 | E-mini DJIA ($5) (CME) | 124603 | +1 |

- **Coverage (finding 9), done:** the engine owner's count (`data-checks/cot/coverage.json`, release counts per code and year, no
  position values): every one of the 13 codes has 52 releases in each year 2014–2024 and 53 in 2018 (53 Tuesday as-of dates). All 13
  stay.
- **One direct, US-listed contract per symbol, where that contract is the main futures market of the underlying.** Excluded, with
  2014–2024 reasons: FX crosses (two contracts, no single positioning series); **JP225**: the main Nikkei futures market is Osaka
  (JPX), not CFTC-reported; CME's Nikkei contracts (USD and yen versions) are a small side market, so their speculator positions do
  not stand for the market's; **DE40, STOXX50, UK100**: their futures trade on Eurex and ICE Europe, outside the CFTC reports;
  **XBRUSD**: Brent's main contract is ICE Europe's, and WTI is a different contract.

### 6.5 Outside series used
Only the COT columns of §6.4 (COT rules). No VIX, no calendars, **no FRED series** (not stored).

## 7. Exclusions (A15 §1.3), each stated

| A15 §1.3 exclusion | how the grammar meets it |
|---|---|
| unbalanced rules; `side` filter | every family is one long condition and its mirror (§2); no side parameter or filter exists; mirror unit test (§10) |
| `recent` slice, regime start date | no date, year, month or regime-date parameter anywhere; every rule runs the full period |
| any anchored average or band (session, day, week, intraday dual: the §3.7 VWAP family) | only rolling SMA / EMA / RSI / ATR / N-bar channels over a fixed bar count; nothing resets at a session, day or week; no VWAP, no opening range, no prior-day or prior-session levels |
| every use of tick volume (A13) | `bars["vol"]` is never read (reviewer check, unit test that the composer's output is unchanged when `vol` is replaced by NaN) |
| time-of-day values derived from release times | TOD uses the full uniform grid of whole Amsterdam hours 01–22; no half hours; no value is taken from a release schedule |
| context symbols not tradable at the firms | context only from the 39; AUS200, F40, HK50, US2000 never appear |
| CFTC blocks other than levels / ≥ 52-week percentiles; CFTC only after the revision bound | COT = 52-release percentile of the net level (§3.8); no week-on-week change; the revision bound is done (A14 §2.7, 2026-11-17) |
| (A14 §2.5) news calendar as an entry signal | never read by the composer; no calendar series is used at all |

## 8. The sampler (planned; written only after the sceptic's review is resolved)

### 8.1 Code, seed, environment
- **Code:** `mining/sampler.py`, deterministic, numpy `Generator(PCG64)`, seeded once.
- **Seed:** `SAMPLER_SEED = 7029058316196824278` = the first 8 bytes (big-endian) of SHA-256("Edge Research A15 mining sweep 1:
  sampler"). Fixed by a public string, so the seed itself was not chosen among alternatives.
- **Environment pinned:** `~/.venvs/fastbt/bin/python` (Python 3.9.6), **numpy 2.0.2**. The sampler refuses to run under any other
  numpy version (Generator streams are not guaranteed stable across versions).

### 8.2 Canonical form and hash (finding 9)
- Canonical JSON: `engine.mining.canonical(def)` = `json.dumps(def, sort_keys=True, separators=(",", ":"))` (ASCII escapes by
  default); `def_hash` = `engine.mining.def_hash(def)`. The sampler imports these two functions, so the list and the runner use one
  definition.
- Arrays `symbols`, `context`, `series` are **stored sorted** (ASCII) in the def itself; the hash is over the def as given, and the
  runner refuses a def whose lists are not sorted.
- Types are fixed by a schema in the sampler: `n, t, p, H, m, fast, slow, w, T, b` are JSON integers; `stop_atr` and `r` are JSON
  numbers written by Python's float repr from the lists in §5 (always with a decimal point: `1.0`, `1.5`, `2.0`, `2.5`, `3.0`);
  every other value is a string. The canonicaliser asserts the schema, so one rule has exactly one text and one hash.
- `def_hash` = SHA-256 of the canonical text (UTF-8).

### 8.3 Draw
- **Order of draws per rule:** family (from a seeded permutation of 8 × 6,250 quota slots) → block parameters → timeframe → symbol
  set (mode, k, bloc, symbols) → context symbol (CTX) → number and types of filters → filter values → stop → exit type and value →
  class. Each value is drawn uniformly from its list unless §3–§6 say otherwise.
- **Non-adaptive:** the sampler reads nothing but its own code, its seed and this spec's constants. It is run once, before any mining
  job exists.
- **Duplicates:** a drawn definition whose hash is already on the list is discarded and **drawn again within the same family slot**
  (the discarded draw still consumes the generator, so the list is reproducible); the list holds exactly 50,000 distinct
  definitions, 6,250 per family.
- **Rejected combinations** (structurally empty, excluded by construction before hashing): TOD + session; a CTX context symbol equal
  to a traded symbol. No other rejection exists.

### 8.4 Binding (A15 §1.2) and one draw only
- **Output:** `mining/rules-sweep1.jsonl`, one line per rule in draw order: `{"rule_id": "M00001", "def_hash": "<hex>", "def": {...}}`
  (canonical text), ids M00001 … M50000. If the file is over 10 MB it is committed gzip-compressed; the bound hash is of the
  uncompressed bytes.
- **Committed together, in one commit, before the first mining job:** `mining/BOUND.json` in the engine owner's format
  (`engine/mining.py` `bound`): `{"n_rules": 50000, "list_file", "list_sha256"` (of the uncompressed bytes), `"sampler_sha256",
  "composer_sha256", "seed", "null_seed", "strategy": "mining/composer.py:intents"}`, plus two fields of this spec:
  **`"spec_sha256"`** (SHA-256 of this `SPEC.md`) and **`"numpy": "2.0.2"`**, and (sceptic v2 re-check, conditions 3 and 5)
  **`"null_symbols"`**, the exact ordered symbol list whose rows the null's sign tables use (§9), and **`"engine_commit"`**, the
  pinned engine commit of the sweep (A15 §10.6). The runner's `bound()` recomputes every line's `def_hash` and the list's SHA-256,
  and checks `spec_sha256` against `mining/SPEC.md` and the running numpy version, before any mining job.
- **One draw only.** The sampler is run once. Any change to this spec, the sampler or the seed after the draw voids the list and
  needs a new sceptic review before any new draw (A15 §1: a second sweep needs a new addendum, with k counting every rule drawn).

## 9. The null's 60 replicates (A15 §5, §10.3)

- **Exactly 60 replicates**, numbered 0 … 59. **Seed:** `NULL_SEED = 2028128550524854714` = the first 8 bytes (big-endian) of
  SHA-256("Edge Research A15 mining sweep 1: null").
- **Signs, as built by the engine owner** (`engine/mining.py` `sign_tables`, `entry_day`, `flip`): per replicate r, a table of ±1
  = `numpy.random.default_rng([NULL_SEED, r]).choice([-1, 1], size=(n_symbols, n_days))` (numpy 2.0.2), rows = every store symbol
  in sorted order **as bound in `BOUND.json` `"null_symbols"`** (§8.4; a symbol added to the store later changes nothing), columns =
  **Amsterdam calendar days** from 2014-11-01 on; a trade takes the sign of (its symbol, the Amsterdam day
  of its `entry_t`). The same sign for that (symbol, day) in every news mode and every rule (A15 §5.1). (v1's draft rule, a SHA-256
  per (rep, symbol, UTC date), is replaced by this, which was built first; both are seeded, fixed before any draw and independent of
  any result.)
- r_mid is multiplied by the sign; r_net = signed r_mid − (r_mid − r_net) (costs are not flipped).
- The statistic, z\* and the rule "z = z_k if no null rule passes the non-luck bars" are A15 §5.2–5.3 and §10.3; built by the engine
  owner (re-scoring from the per-mode compact arrays). No ledger rows; nothing added to k.

## 10. Checks before any mining job (in addition to the engine owner's guards, A15 §2)

1. **Look-ahead review (A15 §1.4):** the `lookahead-reviewer` reads this spec, every family and filter in `mining/composer.py`, and a
   seeded sample of 50 compiled rules (sample seed = first 8 bytes of SHA-256("Edge Research A15 mining sweep 1: review sample") =
   `9375309906280918020`, 50 ids drawn without replacement from the 50,000), then every rule that reaches judging.
2. **Composer unit tests** (`mining/test_composer.py`, synthetic bars only, no store data):
   - mirror: for each family × exit type, mirrored inputs give exactly `−side` and swapped exits;
   - no future: for random cut points j, outputs at bars ≤ j are identical with bars > j removed (prefix invariance);
   - **finite inputs (finding 6):** with NaN blocks inserted (warm-up, a context hole, a missing COT stretch) into series whose
     condition is true throughout, no event fires on the first bar after the NaN block, for every event family;
   - no tick volume: outputs unchanged with `vol` set to NaN;
   - decision window: no non-zero `side` before `first_ms` or at/after `end_ms`;
   - every `side ≠ 0` has a finite `sl_dist > 0`.
3. **Every family fires on synthetic data** (no structurally dead block), shown before the draw is bound.
4. **Sampler checks** (reported with the list, not choices): exact family quotas, 50,000 distinct hashes, canonical round-trip
   (re-canonicalising every `def` gives the same text), symbol inclusion counts (§6.2).

## 11. Compliance

- **A1.5 (nothing from post-2024 behaviour).** Every family is a textbook price, context or positioning condition named in A15 §1.1.
  Every value is a conventional round number (channel 10 / 20 / 55 / 100, SMA 50 / 100 / 200, RSI 2 / 5 / 14 and 10 / 20 / 30, ATR
  multiples 1–3, percentiles 70 / 80 / 90) or a full uniform grid (hours 01–22). None is chosen from how any market behaved after
  2024, and none from any backtest result. Symbol weights are uniform by construction (§6.2), so no exposure (metals and oil
  included) is weighted up.
- **What this session read (reverse firewall, A15 §6.2):** `CLAUDE.md`; `DESIGN.md` §3–§9 and the addenda A1–A15; the two A15 sceptic
  reports and the sceptic's review of SPEC v1; `engine/STRATEGY-API.md`; `strategies/referee.py`; `strategies/null_random.py`;
  `engine/costs.json`; `engine/context.py`; parts of `engine/series.py`; `data-checks/cot/README.md`. It did **not** read `ledger/`,
  `runs/`, `results/`, `gatekeeper/IC-WATCH.md`, batch reports, `STATUS.md`, `LOG.md`, `DIGEST.md`, any idea card or any lane
  module. Disclosed: listing `strategies/` showed the main ideas' file names (titles only, no results), and `DESIGN.md` A12 names
  IDEA-2001 and IDEA-3000 as amber at FTMO's costs. v1's `expiry` filter matched one of those names (IDEA-1007, monthly options
  expiry); it is dropped in v2. The remaining families are exactly the ones A15 §1.1 lists; none was added, removed or
  parameterised because of those names. The A15 §6.4 backstop covers any overlap.
- **§3.7 (seen families).** The VWAP family (session, weekly, intraday-dual VWAP and any anchored average or band) is excluded in
  full (§7). No family repairs a RoboQuant template; the grammar has no opening-range or session-breakout block. Mined rules count
  at the mining k regardless (A15 §4).
- **A13, A14** as in §7; the COT rules state "current vintage".

## 12. The cost test for flat or unmeasured add-ons (A15 §3.4, §10.4)

### 12.1 Routes, fixed per symbol
The route is fixed by `engine/costs.json` `addon_detail` at the pinned engine commit, no choice:

| route | symbols |
|---|---|
| **none** (add-on measured by hour) | AUDCAD, AUDCHF, AUDNZD, CADCHF, CHFJPY, EURGBP, EURNZD, GBPAUD, GBPCAD, GBPCHF, GBPNZD, GBPUSD, JP225, NZDCHF, NZDUSD, USDCHF |
| **G3 firm-feed check** (flat add-on; research-period FTMO ticks exist) | AUDJPY, AUDUSD, CADJPY, EURAUD, EURCAD, EURCHF, EURJPY, EURUSD, GBPJPY, NZDCAD, NZDJPY, USDCAD, USDJPY |
| **spread × 2 outside the cash session** (flat or unmeasured; no research-period FTMO ticks) | DE40, STOXX50, UK100, US30, US500, USTEC, XAGUSD, XAUUSD, XBRUSD, XTIUSD |

A multi-symbol rule takes the route of each of its symbols, and must pass every route it has.

**Derived by the runner, never set by a job (sceptic v2 re-check, condition 1).** Each symbol's route, its × 2 window (§12.4) and
the G3 window (§12.3) come from **one fixed table in `engine/mining.py`**, copied from this section, at the pinned engine commit.
The runner derives the stress of every G2 stage from the def: `g2-cost` = × 1.5 at all hours (§6.7); `g2-cost2x` = × 2 per symbol,
each symbol with its own window (none for symbols on the none or G3 routes, all hours for a G3 symbol moved to × 2 by §12.3);
`g2-feed` = G3 per symbol on its window. **No mining job may carry its own `stress`;** the runner refuses any job whose `stress`
differs from the derived one (unit test with a mixed-route rule, e.g. US500 + XAUUSD + EURUSD).

### 12.2 Spread × 2 (finding 8)
- **What is doubled:** the **whole simulated FTMO spread** (IC's tick spread at that moment + the FTMO add-on), at every tick outside
  the symbol's cash session, for fills (stops and targets hit at the wider bid / ask) and for the cost lines, the same mechanics as
  the §6.7 × 1.5 stress. Inside the cash session the spread is as in the base run.
- **Pass:** the rule, re-run with this spread, still passes **every judging bar (A15 §3.3), the mining luck bar at the frozen k
  included, in each news mode in which it was eligible at judging.** A fail in any such mode fails the rule. No near miss.

### 12.3 G3 (finding 8)
- **Ticks:** every FTMO tick of that symbol in the research period, from FTMO's tick export (`~/cAlgo/Exports/fastbt-ftmo-tick/`,
  read by the engine loader only). The engine owner's coverage (2026-11-17): the same for all 13 symbols, **2020-04-01 → 2021-07-02**
  (16 months, July 2021 partial). The export has no FTMO ticks from 2021-07-03 to 2025-06-22, and 2025+ is locked. **The G3 window
  is therefore 2020-04-01 → 2021-07-02 for every G3 symbol, no choice.** A mined rule's G3 judges only its trades inside that window
  (about 1.25 years: a weak check, stated). The G3 check (stage `g2-feed`) is built by the engine owner before the first mined G3.
- **Minimum trades (sceptic v2 re-check, condition 2; the 30 set by the gatekeeper, 2026-11-17):** a G3 symbol needs **at least 30 of
  the rule's trades on that symbol inside 2020-04-01 → 2021-07-02**, counted in news mode M0 of the rule's screen row. Below 30, that
  symbol leaves the G3 route and takes **spread × 2 at all hours** instead (§12.2; FX has no cash session). No choice remains.
- **Pass:** the §6.8 G3 bars as written (≥ 80% of trades within ±1 bar; P&L per trade inside the noise-test range), in each news
  mode in which the rule was eligible at judging.

### 12.4 Cash sessions
Each in its own local clock with its own DST, weekdays:

| symbol | cash session | clock |
|---|---|---|
| US500, USTEC, US30 | 09:30 – 16:00 | New York |
| DE40, STOXX50 | 09:00 – 17:30 | Frankfurt |
| UK100 | 08:00 – 16:30 | London |
| JP225 | not needed (route none); for the record TSE 09:00 – 15:00, 15:30 from 2024-11-05, lunch 11:30 – 12:30 | Tokyo |
| XAUUSD, XAGUSD | 08:20 – 13:30 (former COMEX gold floor session; silver's 08:25 – 13:25 lies inside it) | New York |
| XTIUSD, XBRUSD | 09:00 – 14:30 (former NYMEX floor session) | New York |
| FX (all 28) | none: × 2 at all hours where that route applies (no FX symbol is on it) | — |

Each window goes to the engine as the stress field `"cash_session": [zone, "HH:MM", "HH:MM"]` (`engine/data.py` `in_session`:
local time, Monday–Friday, start inclusive, end exclusive): `["America/New_York", "09:30", "16:00"]`, `["Europe/Berlin", "09:00",
"17:30"]`, `["Europe/London", "08:00", "16:30"]`, `["America/New_York", "08:20", "13:30"]`, `["America/New_York", "09:00", "14:30"]`.

**Stated limit (holidays):** every exchange holiday and half-day (US, Xetra, LSE, Eurex) is treated as a normal weekday: inside the
cash hours the spread is not doubled. That is a few days a year per symbol, so the test is slightly less strict on those days.

## 13. Job format and runner duties (agreed with the engine owner before the first job)

One screen job per rule, all four news modes, built only by **`engine.mining.job_for(rule_id, def)`** (the engine owner's
function; the mining session's queueing script uses nothing else):
`{"idea_id": "M00001", "card": "mining/SPEC.md", "lane": "mining", "stage": "screen", "rule_id": "M00001", "def_hash": "…",
"strategy": "mining/composer.py:intents", "params": <def>, "symbols": […], "timeframe": "h1", "class": "B",
"filters": {<session / vol / regime>}, "context": [<X>] or [], "series": [<names>] or [], "period": ["2014-11", "2024-12"],
"modes": ["M0", "M1", "M2", "M3"]}`. Later stages (engine owner's names): `judge-full` (full trades for a rule that reaches
judging), and the G2 rows `g2-noise`, `g2-cost`, `g2-cost2x` (§12.2), `g2-swap0`, `g2-neighbour`, `g2-feed` (G3, §12.3), each
carrying `parent_rule_id`.

- **Bound to the definition (finding 3).** The runner recomputes `def_hash` from `params` by §8.2 and refuses the job unless
  (`rule_id`, recomputed hash) is on the bound list. Every other field is **derived from `def`** (`symbols`, `timeframe`, `class`,
  `filters`, `context`, `series`); a job whose field differs from the derivation is refused. `period` is fixed at
  ["2014-11", "2024-12"], `from_ms` = 2014-11-01 in every path (A15 §10.1). Unit test (engine owner): a job with a bound id and hash
  but a changed symbol, filter, class, context, series or period is refused.
- **Zero-trade rows (finding 4).** A mining job whose rule produces no entry intent on a symbol (or at all) is **not refused**: the
  runner writes its row with zero trades for that symbol (flagged in `zero_trade_symbols`), red at the screen, so all 50,000 rows
  exist (A15 §3.5). The `ZERO INTENTS` refusal stays for real jobs.
- Rows go to `ledger-mining/` with the per-mode compact arrays (A15 §3.1).
- **The locked open (finding 5).** A mined candidate's open runs the same composer and the same pinned engine with the COT series
  and the context symbols extended past 2024 by a loader that is **byte-identical to the research loader for t ≤ 2024**. Before the
  first mined open, the engine owner shows this on a sample of mined rows (the extended loader re-runs them over 2014-11 → 2024-12
  and the trade arrays match byte for byte). The research-store cut (A14 §2.2) is unchanged for every other session.
- **G2 neighbour rows** (A15 §3.4) change one ordered parameter by one step; ordered parameters: n, t, p, H, m, fast, slow, w, T,
  stop_atr, r, b. Categorical values (mode, relation, filter values, symbols, timeframe, class, context symbol, exit type) have no
  neighbours. At a list's end only the inner neighbour exists.

## 14. What the sweep is expected to find

Close to nothing (A15 §4): at bar about 1.51, a rule needs a true Sharpe near 1.5 for an even chance. The point is an honest search
at full multiplicity, not a find. k at the freeze = max(50,000, distinct drawn rules with a screen row) + the main real rows then
(62 on 2026-11-17); the bar stays about 1.507.
