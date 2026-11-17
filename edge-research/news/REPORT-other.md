# News calendar CAD / AUD / NZD / CHF / JPY / oil: report (2026-11-12, collection subagent; saved and annotated by the engine owner)

Files:
- `types-other.csv`: 29 types, with columns `research` (yes / firm-sim-only, per A5) and `collected`.
- `dates/CAD.csv` 491 rows, `AUD.csv` 338, `NZD.csv` 235, `CHF.csv` 67, `JPY.csv` 178, `OIL.csv` 528: 1,837 rows in total, all within
  2014-11-01 → 2024-12-31.
- Generator `raw/build_other.py` and its helpers (`pdfrc4.py`, `boj_times2.py`, `dl.py`). Official downloads stay local in `raw/other-dl/`
  (git-ignored).

## Rows per type (2014 = Nov–Dec only)
| type | rows | where the time comes from |
|---|---|---|
| BOC_RATE (tier 1) | 81 | official |
| BOC_PC | 44 | official start ("ET approx."); end assumed (75 min, A5.3) |
| CA_CPI, CA_LFS, CA_GDP | 122 each | official (CA_GDP is new: monthly GDP) |
| RBA_RATE (tier 1) | 110 | official |
| RBA_PC | 8 | 15:30 standing practice (2024 on); end assumed |
| AU_LFS 122, AU_CPI 57, AU_GDP 41 | | official (monthly CPI indicator from late 2022) |
| RBNZ_RATE (tier 1) | 72 | official |
| RBNZ_PC | 41 | 15:00 practice from 2019; 2014–18 blank (17 rows) |
| NZ_CPI 40, NZ_GDP 41, NZ_LFS 41 | | official |
| SNB_RATE (tier 1) | 41 | 09:30 standard; 2014–17 not checked meeting by meeting |
| SNB_PC | 26 | 10:00 official practice; end assumed |
| BOJ_RATE (tier 1) | 89 | official actual time (the end of the meeting, from the minutes) |
| BOJ_PC | 89 | 15:30 practice (2 blank); end assumed |
| EIA_CRUDE | 528 | official schedule |

Official start times: 1,699 of 1,837 rows (92%). All 1,629 release and decision rows have an official date and time.

## How the sources were read
- **Copied from the VWAP calendar (2018–2024, unchanged):** BoC, Canada CPI and LFS, RBA, Australia LFS / CPI / GDP, RBNZ, NZ releases,
  SNB, EIA.
- **BOJ_RATE:** the VWAP calendar's 11:00 was a window start, not the announcement. The time used here is the end of the final session
  from each meeting's minutes (89 PDFs from boj.or.jp), which say the statement is released immediately after. Range 11:23–12:59 JST;
  the two 2020 special meetings ended at 13:59 and 09:54. [Engine: BOJ_RATE uses the usual range 11:00–14:00 Tokyo plus the actual
  time, DESIGN §3.6.]
- **BoC:** decision dates from the key-rate archive. Press-conference starts from the BoC's own pages, in ET:

  | period | starts at | when |
  |---|---|---|
  | until Jan 2020 | 11:15 | MPR meetings |
  | Apr 2020 | 10:30 | |
  | Jul 2020 – Oct 2023 | 11:00 | MPR meetings |
  | from 2024 | 10:30 | every decision |

- **Statistics Canada:** the yearly release-date lists. The 2020–24 PDFs reproduce the VWAP calendar's CPI and LFS dates exactly.
- **RBA:** meeting dates from the minutes index. Press conferences from 6 Feb 2024 at 15:30, with transcripts.
- **ABS:** archived issue pages, read from the "Released at 11:30 AM" line or the "Forthcoming issues" table. 37 rows for 2014–17 come
  from the schedule table. One rescheduling found: the Sep 2015 LFS moved from 8 to 15 October.
- **RBNZ:** rbnz.govt.nz refuses automated access, so the decisions come from a web.archive.org copy of its OCR table.
- **Stats NZ, 2014–17:** archived "Hot off the press" pages (10:45 embargo).
- **SNB:** decisions list. Press conferences at 10:00 Zurich: June and December only until June 2022, then every assessment from
  22 Sep 2022.
- **EIA:** weekly report archive. Holiday-week releases on Thursday at 11:00 ET in 2014–17; one 2018–24 exception, Friday 27 Dec 2024
  at 13:00.

## Left out (unscheduled; kept as `#` lines)
- BoC 13 and 27 Mar 2020; RBNZ 16 Mar 2020; SNB 18 Dec 2014 and 15 Jan 2015.
- RBA 19 Mar 2020 and BoJ 16 Mar / 22 May 2020 are kept, because they were announced in advance.

## Cross-check: ForexFactory, Jul–Nov 2026
- **Match to the minute:**
  - BoC 09:45 ET;
  - Canada releases 08:30 ET;
  - RBA 14:30 / 15:30 Sydney, Australian releases 11:30;
  - RBNZ 14:00 / 15:00, NZ releases 10:45;
  - SNB 09:30 / 10:00 Zurich;
  - BoJ press conference 15:30 Tokyo;
  - EIA 10:30 ET.
- **Do not match:**
  - BoC press conference: ForexFactory shows 10:45 against the official 10:30.
  - EIA holiday Thursdays: 12:00 on ForexFactory (2026) against 11:00 in the 2014–24 schedule. Live cBots should block both.
  - BoJ: no fixed time; ForexFactory records the actual time.

## Lists today
- **FTMO's list:** BoC, RBA, RBNZ and SNB decisions; Canada, Australia and NZ CPI, employment and GDP; crude inventories. No JPY events,
  no speeches, no press conferences.
- **ForexFactory red adds:** the five banks' press conferences, Canada monthly GDP (red in 3 of 5 months), NZ inflation expectations (red
  once), the BoJ decision, and some RBA and BoJ Governor speeches.
- **Myfxbook-only, firm simulation only:** JP GDP, JP trade, RBA minutes.

## Open items
1. **Speeches not collected:** BOC_GOV_SPEAKS, RBA_GOV_SPEAKS, RBNZ_GOV_SPEAKS, SNB_CHAIR_SPEAKS, BOJ_GOV_SPEAKS. The BoC listing alone is
   about 70 pages, and the permission system refused that download as bulk scraping. A slow pass needs the user's go. Most index pages
   give no start time, so most speeches would get the 08:00–20:00 day range. [Engine owner: sent to the gatekeeper.]
2. **NZ_INFL_EXP** is a research type (ForexFactory red once), but its dates were not collected: RBNZ refuses automated access.
3. **RBA_MINUTES, JP_GDP, JP_TRADE** (firm simulation only): not collected.
4. **RBNZ_PC:**
   - No press conference after non-MPS reviews is assumed (unverified).
   - The 2014–18 start times are unknown. [Engine: blank starts get the 08:00–20:00 local day range, like speeches.]
5. **SNB:** the 19 Mar 2020 press conference is not included. The 2014–17 decision time of 09:30 was not checked per meeting.
6. **BoJ press conference:** 15:30 is standing practice, not checked per meeting; the two 2020 special meetings are blank (day range).
7. **Third-party lists:** FXStreet past weeks were not read, and Myfxbook was read for only two weeks.
8. **Tool notes:**
   - Before the switch, the agent used browser JavaScript and clicks (ForexFactory, Myfxbook, FXStreet, web.archive.org, Stats NZ).
     After the switch, only WebFetch, WebSearch and Bash downloads.
   - The permission system refused four things: a ForexFactory JSON fetch with a browser user agent, an FXStreet API fetch, a command
     containing `rm -f` (nothing was removed), and the 77-page BoC listing download.

## Slow pass, 2026-11-12 evening: speeches, committee appearances, NZ inflation expectations (user's go "collect slowly")
Method: Python downloads only, one request at a time, 31 s apart, official sites only (plus web.archive.org copies of RBNZ and the old
snb.ch list); no browser. Scripts: `raw/make_speeches*.py`, `raw/parse_speeches.py`, `raw/slowdl.py`; tables
`raw/speeches-heads-2014-2024.csv`, `raw/speeches-boj-index.csv`, `raw/nz-inflation-expectations-2014-2024.csv`; pages in
`raw/speeches-dl/` (git-ignored, local).

| type | rows | official start | source of the start |
|---|---|---|---|
| BOC_GOV_SPEAKS | 100 | 24 | the speech's BoC webcast page, "(HH:MM (ET) approx.)" |
| BOC_GOV_TESTIFIES (new) | 38 | 0 | Commons / Senate committee appearances; no time on BoC pages |
| BOJ_GOV_SPEAKS | 130 | 0 | yearly index, date only; 9 abroad carry the venue's zone |
| SNB_CHAIR_SPEAKS | 54 | 43 | embargo time on the official PDF (Swiss time, also abroad) |
| RBNZ_GOV_SPEAKS | 28 | 0 | archived speech pages, 2014-11 → 2021-11 only |
| RBNZ_GOV_TESTIFIES (new) | 5 | 0 | the 2021 Finance and Expenditure Committee hearings |
| RBA_GOV_SPEAKS | 0 | – | rba.gov.au refused (HTTP 403) on the first page: stopped |
| NZ_INFL_EXP | 37 of 41 | 37 at 15:00 NZ | 23 from "Released"/"Last updated", 14 from the previous page's "Next release" |

Rows now: CAD 629, AUD 338, NZD 305, CHF 121, JPY 308, OIL 528 (2,229). Excluded as `#` lines: opening statements at BoC / SNB press
conferences (duplicate BOC_PC / SNB_PC), unscheduled March 2020 BoC conferences and SNB 2014-12-18 / 2015-01-15 / 2020-03-25, 6 RBNZ
speeches whose speaker could not be verified (archive HTTP 503 twice), 4 NZ_INFL_EXP releases not found (Nov 2014, Feb 2015, May 2019,
May 2024). Closed or off-the-record events cannot be listed one by one (RBNZ says most of its events are off the record).

[Engine owner] Rows without an official start (288 of the 355 new talk rows) get the 08:00–20:00 local day range; this now covers
committee appearances (kind testimony) too, except Fed testimony, which keeps its 09:30–17:00 New York usual range. Loader check: 4,728
research events (5,258 all types), no errors.

Open, from this pass:
- **RBA Governor speeches not collected** (rba.gov.au refuses automated access): needs another official route or the user's decision.
- **RBNZ speeches 2022–2024 and the May 2024 survey release missing** (web.archive.org refused newer RBNZ pages with HTTP 403).
- SNB: possible gap Nov 2021 – Mar 2022 (no archived list for that window). BoC listing misses items without a BoC author tag.
- 14 NZ_INFL_EXP dates are schedules, not confirmed release dates.

## Decisions (user, 2026-11-12 20:40, "Yes, all three", relayed by the gatekeeper)
- Committee appearances without an official start (43 BoC / RBNZ) keep the 08:00–20:00 local day range; Fed testimony stays 09:30–17:00
  New York.
- **Gaps accepted for now:** RBA Governor speeches (none collected) and RBNZ Governor speeches 2022–2024. Any candidate trading AUD or NZD
  pairs is checked against hand-collected RBA / RBNZ speech dates before its locked-period open. No gap is closed now.
