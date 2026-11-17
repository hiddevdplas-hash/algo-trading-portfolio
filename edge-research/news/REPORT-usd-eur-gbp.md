# News calendar USD / EUR / GBP: report (built 2026-11-12 by the collection subagent; saved by the engine owner)

Scope: the USD, EUR and GBP event types that are high-impact in today's lists (the union of the sources), and their dates **2014-11-01 →
2024-12-31**, per DESIGN §3.6. No market data was read. Nothing is dated after 2024-12-31.

## Files
| file | what |
|---|---|
| `types-usd-eur-gbp.csv` | 50 types (USD 22, EUR 17, GBP 11): tier, sources (`firms`), official source, `collected` status |
| `dates/USD.csv`, `dates/EUR.csv`, `dates/GBP.csv` | one row per occurrence; local time + IANA zone; unscheduled events as `#` lines |
| `raw/build_usd_eur_gbp.py`, `raw/tier2.py` | rebuild the date files from the raw lists + the VWAP files (stdlib, VWAP read-only) |
| `raw/*.txt` | the official date lists read; the ForexFactory / FXStreet / Myfxbook page snapshots stay local (git-ignored) |

## Counts per type (tier 1 in bold)
| type | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 | 24 | total | end |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **FOMC_RATE** | 1 | 8 | 8 | 8 | 8 | 8 | 7 | 8 | 8 | 8 | 8 | 80 | n/a |
| **FOMC_PRESSER** | 1 | 4 | 4 | 4 | 4 | 8 | 7 | 8 | 8 | 8 | 8 | 64 | assumed |
| **US_CPI** | 2 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 122 | n/a |
| **US_NFP** | 2 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 122 | n/a |
| **ECB_RATE** | 2 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 82 | n/a |
| **ECB_PRESSER** | 2 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 82 | assumed |
| **BOE_RATE** | 2 | 12 | 11 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 89 | n/a |
| FOMC_MINUTES | 1 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 8 | 81 | n/a |
| US_PPI, US_RETAIL_SALES | 2 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 122 each | n/a |
| US_GDP_ADVANCE | 0 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 40 | n/a |
| US_GDP_SECOND_THIRD | 2 | 8 | 8 | 8 | 8 | 7 | 8 | 8 | 8 | 8 | 8 | 81 | n/a |
| US_PCE | 2 | 12 | 12 | 12 | 12 | 11 | 12 | 12 | 12 | 12 | 12 | 121 | n/a |
| US_JOBLESS_CLAIMS | 9 | 52 | 52 | 52 | 52 | 52 | 53 | 52 | 52 | 52 | 52 | 530 | n/a |
| US_ISM_MFG, US_ISM_SERVICES (derived) | 2 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 122 each | n/a |
| FED_CHAIR_TESTIFIES | 0 | 6 | 6 | 5 | 4 | 6 | 11 | 11 | 5 | 4 | 4 | 62 | 1 official, 61 no start |
| BOE_MPC_MINUTES | 2 | 7 | 0 | … | | | | | | | | 9 | n/a |
| BOE_MPR_PRESSER | 1 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 4 | 41 | assumed |
| UK_CPI | 2 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 122 | n/a |
| UK_LABOUR | 2 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 12 | 13 | 12 | 123 | n/a |
| UK_GDP | 0 | 4 | 4 | 4 | 8 | 12 | 12 | 12 | 12 | 12 | 12 | 92 | n/a |

Real low counts, not gaps:
- FOMC 2020 = 7: March was replaced by the unscheduled 15 Mar cut.
- US GDP second / third 2019 = 7 and PCE 2019 = 11: BEA merged releases during the shutdown.
- BoE 2016 = 11, then 8 a year from 2017.
- UK_GDP was quarterly until monthly GDP began on 10 Jul 2018.
- UK_LABOUR 2023 = 13: a partial release on 17 Oct.
- Jobless claims 2020 = 53 Thursdays.

## Tier 1: complete
- **FOMC rate decision** 14:00 ET: Fed history pages for 2014–17; the VWAP calendar from 2018.
- **FOMC press conference** 14:30 ET: quarterly until 2018, at every meeting from 2019.
- **US CPI and NFP** 08:30 ET: BLS archives. NFP equals the VWAP calendar row for row for 2018–24 (84 / 84).
- **ECB rate decision** 13:45 CET, 14:15 from 21 Jul 2022. **ECB press conference** 14:30, then 14:45 from the same date.
- **BoE rate decision** 12:00 London.
- **Unscheduled events left out** (kept as `#` lines):
  - FOMC 3 and 15 Mar 2020;
  - BoE 11 and 19 Mar 2020, and the 24 Jun 2016 statement;
  - ECB: the PEPP announcement of 18 Mar 2020 and the ad-hoc meeting of 15 Jun 2022.

## Corrections to the VWAP calendar (VWAP project not edited)
- **UK_CPI 2018-01-16 → 2020-02-19 (26 rows): the VWAP calendar says 07:00; the correct time is 09:30 London.** ONS moved
  market-sensitive releases from 09:30 to 07:00 on 25 Mar 2020 (ONS statement of 23 Mar 2020). Fixed here and marked `TIME CORRECTED`;
  the same switch applies to UK labour market and GDP. The closed VWAP files and their cBot calendars still carry 07:00.

## Time changes and holiday shifts
- **ECB:** decision 13:45 → 14:15, press conference 14:30 → 14:45 from 21 Jul 2022.
- **ONS:** releases 09:30 → 07:00 from 25 Mar 2020.
- **BEA personal income and outlays (PCE):** 10:00 ET on GDP days, otherwise 08:30.
- **2019 US shutdown:** GDP, PCE and retail sales dates follow the delayed releases.
- **Weekly jobless claims:** released on Wednesday in 17 holiday weeks.
- **BoE:** the May 2015 decision came on Monday 11 May (election week).

## Open items (engine owner's notes added)
1. **ISM dates are derived** from ISM's rule (first and third business day, 10:00 ET). ISM's calendar requires a login. Marked
   `DERIVED (UNVERIFIED)`.
2. **Testimony:** 61 of 62 rows have no official start time. The one record read (26 Feb 2019) ran 09:49–12:15.
   - Engine owner: these use a usual range of **09:30–17:00 New York** (`engine/news.py`), per DESIGN §3.6 for events without a fixed
     time. That covers any common start plus the 3.5 h default; a longer block only removes trading time.
   - Reading the ~60 govinfo hearing records would narrow it.
3. **Press-conference end times are all `assumed`,** so the engine's 60-minute default applies. FOMC press conferences sometimes run
   60–65 minutes, so a 75-minute default would be the conservative choice. Decision for the user.
4. **BoE Monetary Policy Report meetings 2018–24** follow the BoE's publication pattern rather than being read date by date. The three
   old-format Inflation Reports (Nov 2014, Feb 2015, May 2015) still need checking on an official page.
5. **Types listed but without dates:**
   - the speeches FED_CHAIR_SPEAKS, ECB_PRESIDENT_SPEAKS and BOE_GOV_SPEAKS: the official lists give dates but no start times;
   - UK_BUDGET, US_ADP, US_BENCHMARK_REVISION;
   - many types that only FXStreet or Myfxbook list.
6. **Scope, decision for the user:** the Myfxbook and FXStreet high-impact lists are very wide (German trade balance, BRC retail monitor,
   existing home sales and similar). Under DESIGN §3.6's union rule each becomes a tier-2 block. The alternative: FTMO + FundingPips +
   ForexFactory decide the blocks, and the FXStreet / Myfxbook-only types are used in the firm simulation only.
7. **FundingPips:** its public page lists categories only; the "Restricted" tags sit on a dashboard that needs a login.
8. **Impact levels move month to month.** "Today's types" means red / high at least once in the months read (Jun–Nov 2026).

## Cross-check: ForexFactory vs official times (Jun–Nov 2026)
- **Every fixed-time type matched to the minute:** US CPI, NFP, PPI, retail sales, ISM, GDP, PCE, ADP, the Fed (statement, press
  conference, minutes), the ECB, the BoE, and UK CPI, GDP and labour market.
- **No official fixed time:** Fed Chair speeches and testimony, BoE Governor speeches, the UK Budget, US elections.

## Sources
- Official: federalreserve.gov, bls.gov, bea.gov, census.gov, ecb.europa.eu, bankofengland.co.uk, ons.gov.uk, gov.uk statistics
  announcements, govinfo.gov (one hearing record), ALFRED release 180 (weekly claims).
- Copied: the VWAP files (not edited).
- Type lists: `rulebook/FTMO.md`, the FundingPips news page, ForexFactory Jun–Nov 2026, FXStreet Oct–Nov 2026, Myfxbook weeks of 9 and
  16 Nov 2026, each read in the browser one page at a time.

## A5 additions (2026-11-12, collection subagent; engine owner's notes in brackets)
New types collected: FED_CHAIR_SPEAKS 121, ECB_PRESIDENT_SPEAKS 190, BOE_GOV_SPEAKS 98, UK_BUDGET 12, US_ADP 120,
US_BENCHMARK_REVISION 6 (2019–2024). Totals: USD 2,062 rows, EUR 354, GBP 586.

**Speeches:** 121 of 409 (30%) have an official start time, all of them Fed speeches.
- **Fed:** times from the Fed's speech feed (`federalreserve.gov/json/ne-speeches.json`, Eastern time). Discussions and panels come from
  the monthly calendars (2017-01 → 2024-12) and are kept only when they have a video link.
- **ECB and BoE:** no times are published, so the A5.2 range applies (08:00–20:00 local) with the 60-minute default.
- **Excluded** (dinners, luncheons, IMFC written statements, closed sessions, events with neither text nor video): kept as `#` lines.
  The Mansion House dinner speeches (2019, 2022, 2024) fall under this exclusion even though their texts are published. Re-adding them
  is a one-line change; the user's call.
- [Engine owner: ECB_PRESIDENT_SPEAKS is marked "no" in the types file because ForexFactory showed it orange in Jun–Nov 2026. A5.2
  names the ECB President explicitly, so the engine counts it for research (`engine/news.py` A5_2_SPEECHES): the stricter reading, which
  only removes trading time. Flagged to the gatekeeper.]

**Testimony:** start times from the Fed calendars from 2017 (the hearing's "Watch Live" time). Where the prepared text was released
earlier, an extra row sits at the release time. 49 of 63 rows now have a start.

**ISM check (A5.4):** 239 dates checked against ISM's PR Newswire releases and 5 against ForexFactory day pages. The derived rule is
right for 221 of 244.
- **16 date mismatches:**
  - every January 2018–2024: ISM released one business day after the rule;
  - Good Friday 2015;
  - the national day of mourning on 5 Dec 2018.
- **7 time mismatches:** 09:00 ET stamps in Feb, Mar and Dec 2017, and 09:45 ET on 2015-08-03.
- Every mismatch has both rows, so both dates are blocked.

**Other sources:**
- **US_ADP:** ALFRED release 194, 08:15 ET; no report in Jul or Aug 2022.
- **US_BENCHMARK_REVISION:** BLS CES notices, 10:00 ET.
- **UK_BUDGET:** gov.uk content API; start 12:30 after PMQs (2018: Monday 15:30).

**Prompting tools:** after the switch, only Bash curl, `WebFetch` (bls.gov refuses curl; the ALFRED download hung) and the browser's
get_page_text on 5 ForexFactory pages.

**Open:**
- The ECB's 2024 speech index ends on 30 Aug 2024; Sep–Dec 2024 has only the 4 Dec hearing.
- The Fed's calendar page for September 2019 is missing on its site.
- Fed Chair discussions without text are covered only from 2017.
- Benchmark revisions 2015–2018 were not found.
- Testimony start times for 2015–2016 and Feb 2017 are still blank; those rows keep the 09:30–17:00 range.
