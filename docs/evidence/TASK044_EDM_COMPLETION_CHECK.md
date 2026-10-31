# TASK-044 evidence: offline check of the EDM export (PV-24) for production/completion equipment and perforation history

Status: investigation evidence, deterministic file observations only. Offline, read-only, no model or
provider call, no spend, no network, no database. Revision 1, 2026-10-31, branch
`feature/task-044-edm-completion-check` (base 1885ed1). Independent QA has not run.

Source: `Well_technical_data/EDM.XML/Volve F.edm.xml` (211,263,929 bytes, 320,922 lines; Landmark EDM
5000.14 export, header `DB_Version=EDM 5000.14.0`). It was streamed with the hardened expat set-up of
`backend/fieldlens/profiles/safexml.py` (DOCTYPE/entity declarations abort, no parameter entities, no network)
and a depth cap of 16. Nothing from the file is committed beyond short locators (`L<n>` = 1-based file line,
verified with `sed -n '<n>p'`); full extracts live only in gitignored `.local/`.

Reproduce (from the worktree root; both scripts are spikes, not a production profile):

```
python scripts/spikes/edm_census.py census SRC .local/edm_census.json
python scripts/spikes/edm_census.py dump SRC .local/edm_core.jsonl CD_WELL CD_WELLBORE CD_DATUM CD_ASSEMBLY \
    CD_ASSEMBLY_COMP CD_WEQP_PACKER CD_CASE CD_HOLE_SECT CD_SCENARIO CD_WELLBORE_TYPE
python scripts/spikes/edm_completion_scan.py .local/edm_core.jsonl F-12 F-14 F-5
```

## 1. Structure

Layout: `<export>` > `<TOPLEVEL>` (lookup tables: units-free catalogs such as CD_GRADE, CD_MATERIAL,
CD_GEO_*) and then one flat element per database row directly under `<export>`; every value is an XML
**attribute** (no element text). Maximum nesting depth is 4 (`export/BINARY_DATA/CD_ATTACHMENT_JOURNAL/
CD_ATTACHMENT`; `LINKTABLE` rows). 142 distinct element names. Row counts of the relevant ones:

| Group | Tables (rows) |
|---|---|
| Identity | CD_SITE 1, CD_WELL 21, CD_WELLBORE 54, CD_WELLBORE_TYPE 30, CD_DATUM 124 |
| Designs/cases | CD_SCENARIO 110, CD_CASE 2,620, CD_HOLE_SECT_GROUP 962, CD_HOLE_SECT 2,741 |
| Strings | CD_ASSEMBLY 3,902, CD_ASSEMBLY_COMP 10,650, CD_BHA_COMP_* (DP_HW 2,477; MWD 1,627; STAB 1,318; NOZZLE 1,558; JAR 817; MOTOR 749; BIT 632) |
| Completion equipment | CD_WEQP_PACKER 6 (only equipment-specific table) |
| Surveys | CD_SURVEY_HEADER 194, CD_SURVEY_STATION 4,953, CD_DEFINITIVE_SURVEY_HEADER 110, CD_DEFINITIVE_SURVEY_STATION 15,109 |
| Analysis (WellPlan/StressCheck) | TU_*, WP_* tables (torque/drag, hydraulics, cement, loads), tens of thousands of rows |
| Binary | CD_ATTACHMENT 719 (all `mime_type=dws-app-data/stresscheck` application data, not documents) |

There is **no** table for perforation or completion event history, well tests, daily reports, production or
injection, ESP/gas-lift pumps, nipples, bearings or installed/removed dates (the census contains no
element whose name contains PERF, COMPLET, TUBING, EVENT, REPORT, DAILY or PRODUC; `CD_WEQP_PACKER`, `WP_CASE_PUMP`
and `WP_CASE_BOOSTER_PUMP` are the only equipment-like names, the last two being rig mud-pump simulation parameters).
It is a drilling/well-planning (COMPASS, WELLPLAN, StressCheck, Wellcat) database, not a completion history.
Perforation, packer and SSSV *words* do occur in StressCheck design inputs (not history, not as-built):

| Where | Observation (design inputs) |
|---|---|
| `TU_CASE_PARAMETER` | `parameter_name` `ReservoirPerforationDepth` (13 rows) and `PackerDepth` (13 rows), 13 distinct scenario ids by my count (QA counted 19 scenarios), only F-10 A, F-13 and F-14 A. Cohort rows: F-14 A scenario `F-14 A NW target - SIGULU - rev0` (PROTOTYPE, L309937): L310295 `ReservoirPerforationDepth` 9498.3595800145, L310301 `PackerDepth` 8678.1496062645 (`parameter_value_num`, no unit). F-12 and F-5 have no such rows |
| `TU_CUSTOM_LOAD_PROFILE` | profiles named `Perforating Gun Firing Pressure` for F-1 wellbores (e.g. L101564, wellbore 3Ox3zu412Z = F-1 B); not cohort |
| `TU_LOAD_HEADER` | L101607 `L.10a.Tubing leak below closed SCSSSV` (F-13); not cohort |

None of these is a dated or installed record. Source conflict: the F-14 A `PackerDepth` 8678.15 (L310301) disagrees
with `CD_WEQP_PACKER.packer_depth` 8350.07 (L48650 and L48651) for the same sidetrack, a difference of 328.08 in the
file's unstated unit (equal to 100 m if feet). Both are design inputs; neither can be chosen without a rule.

Wells and wellbores: `CD_WELL.well_id` (opaque 10-char id), `well_common_name`, `well_legal_name` (`NO 15/9-F-12`
style, absent on some). `CD_WELLBORE` carries `wellbore_id`, `wellbore_name`, `parent_wellbore_id` (sidetrack
chain), `ko_md`, `bh_md`, `bh_tvd`, `wellbore_type_id` (lookup, e.g. OIL PRODUCER, WATER PRODUCER, Injection
Development). Unique identification of the cohort (all by `well_id`/`wellbore_id`, never by name):

| Well | well_id (L) | wellbore | wellbore_id (L) | Notes |
|---|---|---|---|---|
| F-12, legal `NO 15/9-F-12` | 6ekXXuRhFd (L24719) | `F-12` | FHcPbdxSIP (L24871) | single wellbore, type Production Development, bh_md 11368.44, bh_tvd 10017.91 |
| F-14, `NO 15/9-F-14` | z6foKJAbj2 (L24734) | `F-14` | EAnITCR5x1 (L24909) | bh_md 12123.03; type not set |
| F-14 | same | `F-14 A` | 1j6NvagBYE (L24908) | child of EAnITCR5x1, type WATER PRODUCER, no bh_md/ko_md; only 3 PROTOTYPE scenarios (L309937-39) |
| F-5, `NO 15/9-F-5` | w57BabYnwU (L24731) | `F-5` | 2suJ4qMKKw (L24901) | type Injection Development, bh_md 12260.83 |

Name traps: wellbores named `F-12` also exist under the wells `Relief well location 3` (w88Iwym18B, L24875) and
`Relief well location 5` (KN3GtZgOuN, L24890); a wellbore named `F-1 ...` sits under relief-well sites; F-11 is a
separate well (`15/9-F-11`, `15/9-F-11 A/B/T2`, ids 3W9ZjV2yj0 etc.) and has one packer row
(L48646 `Packer @ 3064`, wellbore uLkXB6Hbm2) and a 7" tubing design (L25337). The 6 `CD_WEQP_PACKER` rows split:
F-11 1 (L48646), F-13 3 (L48647 `Help packer`, L48648 `Production Packer`, L48649 fluid density only), F-14 A 2 (L48650, L48651). A name-based join would mix these; key
by `well_id` plus `wellbore_id`.

## 2. Units, datum and reference metadata the file states

The file states **no units** and no depth reference on assembly rows. There is no unit table
(`active_ui_unitsys_id=20` on every one of the 21 CD_WELL rows is an unresolved code) and CD_ASSEMBLY/CD_ASSEMBLY_COMP
carry no `datum_id`. A scenario/case-level reference does exist: `CD_SCENARIO.datum_id` (and `original_tubular_datum_id`
on some rows, and `CD_CASE.datum_id`) link to CD_DATUM. For the cohort, scenarios point at: F-12 `Rotary Table`;
F-14 and F-14 A `Inspirer Rotary Table`; F-5 `Rotary Table (As Installed)` (I verified the scenario links; QA verified
the case links). Because strings are not tied to a scenario, which datum a string depth uses is not stated. Facts only:
- CD_DATUM (124 rows) holds named datums with `datum_elevation` (e.g. F-12 `Rotary Table` 180.1181102355, default
  `Y`, L24766; `WELL` 72.17847769 L24765), still without unit.
- Magnitudes strongly suggest US oilfield internal units (OD `9.625`, `13.375`, `30.0` read as inches; depths
  such as water depth `298.556430445` = 91.0 m x 3.28084 and rotary table 180.118 = 54.9 m read as feet).
  This is an inference from magnitudes, not stated by the file. A cross-check that supports it: EDM `bh_md` for
  F-12/F-14/F-5 (11368/12123/12261, read as ft = 3465/3695/3737 m) lie just below the deepest PV-03 perforation
  base MD of each well (3281/3354/3712 m). A profile must not assume it; the unit system must be confirmed
  (e.g. from the EDM unit-system table that is not in this export) before any normalization.
- Casing/tubing `md_top = 298.556430445` equals `CD_WELL.wellhead_depth` and `water_depth`, so strings hang from
  the seabed wellhead; whether MD is relative to rotary table or the `WELL` datum is not stated.
- Dates are recorded as `{ts 'YYYY-MM-DD hh:mm:ss'}` (create/update times of the *record*, second precision).
  There are no installed/removed/effective dates for strings. `CD_DATUM.date_established` is a datum date, not an
  equipment date. `CD_CASE.job_date` is set on 6 rows (all F-10/F-15) and none for the cohort.

## 3. Production/completion equipment per wellbore

Design/case semantics observed: strings live in `CD_ASSEMBLY` (`string_type` Casing 2,663, Drillstring 834, Liner
70, Conductor 15, Tubing 4, Tieback 3, blank 313; `phase` PLAN/PROTOTYPE/ACTUAL/blank; `string_class`
Conductor/Surface/Intermediate/Production/blank, set on 411 rows) and components in `CD_ASSEMBLY_COMP`
(`comp_type_code`/`sect_type_code`, od_body, id_body, length, md_top/md_base on casing comps only, grade,
manufacturer on 1,724 rows, `model` on 13). `phase=ACTUAL` appears on 20 CD_CASE rows, all of them
torque/drag or hydraulics cases (running strings such as `7" liner scraper`), one ACTUAL scenario per
wellbore that is the COMPASS survey (`CD_SCENARIO` ACTUAL, e.g. F-12 L309867), and 10 CD_ASSEMBLY rows, all
drillstring `Assembly`/`Inner Assembly` rows (F-11 L25299/L25303, F-9 L25859/L25861, F-15 L28042/L28057/L28074/L28076
and two in the cohort: F-5 L27914 assembly gSjAB, F-14 L28157 assembly DSb2o), i.e. drilling-side running strings.
**No completion, tubing, liner or casing assembly row is flagged
as-built/installed**, there are no installation dates and the casing rows are StressCheck/WELLPLAN design
variants; hence none of what follows is installed history, only designs or what-if strings.

| Wellbore | Assemblies (type|phase, counts) | Tubing/Liner/Packer/Pump | Installed history? |
|---|---|---|---|
| F-12 FHcPbdxSIP | Casing 68 (all phase blank, 43 distinct size/base pairs), Conductor 1, Drillstring 1, untyped 42 | none. Only 4 CD_ASSEMBLY_COMP have `sect_type_code=CAS` (L31725, L31923, L31946, L31948; 3 with length/ID, none with md_top/md_base); 4 `HOO` hole openers (L31529, L31531, L31721, L31979) are drilling tools | none |
| F-14 EAnITCR5x1 | Casing 77 (49 distinct), Conductor 2, Drillstring 132 (PLAN 112), untyped 14 | no Tubing/Liner/Packer rows; one running-string tubing comp `7" 29 ppf` length 10236.22 in the case `Tubingvekt` (assembly 7nSnd L28123, comp L34989, phase PLAN) | none |
| F-14 A 1j6NvagBYE | 15 assemblies, all PROTOTYPE or blank | Tubing x2 (`7" Production Tubing`, L28083 phase blank, L28090 PROTOTYPE; md 298.556 to 8842.19, length 8543.64, TBG comps L34858/L34865 od 7.0 id 6.184 grade 13CR80); Liner x2 (`7" Production Liner` L28086, L28089; md 8842.19 to 12113.19, length 3270.997, comps L34859/L34863); PKR comps L34857/L34864 without dimensions; `CD_WEQP_PACKER` rows L48650/L48651 (`Packer #1`, `packer_depth` 8350.0656, `plug_depth` 8842.19, bore 7.0, `is_sheared N`); PBR 8.0 x 6.184, 20.997 long (comp L34847, Weatherford `Standard PBR`, in a drillstring-type running assembly 5nuQ8 L28078) | design only: scenarios are PROTOTYPE `F-14 A NW target` (planned sidetrack), records dated 2015-09/10 |
| F-5 2suJ4qMKKw | Casing 36 (24 distinct), Liner 2, Drillstring 18, untyped 10 | Liner x2 `7" Production Liner` (L27916 and L27948, `string_class` Production, md 9009.19 to 11896.33, record date 2005-11-22); no Tubing or Packer rows; one running-string tubing comp `7" 29 ppf S13CRS110` length 9022.31 in an unnamed assembly pKO8d (L27936, comp L34617) used by the case `Displace to overbalance` (L51789) | design only. The ACTUAL case `Pull tubing AJP 290816` (L51824, record date 2016-08-29) is a torque/drag model of a tubing pull job: weak circumstantial hint that tubing was present, not an equipment record |

Not found for any of the three wells as equipment records (searched by component codes, descriptions and table
names across the whole file): ESP, gas lift, SSSV, landing/nipple profiles, bearings, mandrels, screens, perforation
guns, quantity of installed items, installed/removed dates, status flags.

Weak circumstantial hints (names only, not equipment records, no dates of installation): F-12 has 5 `CD_HOLE_SECT_GROUP`
rows named `Run upper completion` (PROTOTYPE; L267186, L267194, L267206, L267218, L267220) and a case `Weight of tubing`
(L51016); F-14 main has cases `Pull tubing and displ. annulus SIGULU 170416` (L51977), `Pull tubing SIGULU 170416` (L52168)
and `Tubingvekt` (L52160); F-5 has `Pull tubing AJP 290816` (L51824). They suggest completion/workover design work
existed, nothing more. Drilling-side material (BHA, bits, drill pipe, MWD/LWD, hole openers, drilling casing runs) is by
far the dominant content (CD_BHA_COMP_*, 132 of F-14's 225 assemblies).

Hole sections (`CD_HOLE_SECT`: 99 F-12, 291 F-14, 66 F-5 rows; `od_casing`, `md_shoe`, `hole_size`, `length`) give
casing-shoe designs by hole-section group (PLAN/PROTOTYPE/blank; 4 ACTUAL groups exist but belong to F-11, F-9 A,
F-15 and F-15 D, none to the cohort). Example 2016 groups with phase blank: F-14 groups hAHGW/YM1Z0/yQ63d
(L269784-L269786, L269928-L269930, L269934), F-5 bvbev (L269540-L269542), F-12 puVYG (L268713). They hold casing
shoe/OD design data without dates or as-built flag.

## 4. Perforations and production-relevant events

The EDM export contains no perforation interval or event history (see section 1; only the design-input depths
`ReservoirPerforationDepth` for F-14 A, L310295, and no cohort well-test or status record). PV-03 (`Geophysical_Interpretations/Wells/Well_perforations_Volve.dat`,
48 data rows, header on line 1) holds for the cohort: F-12 5 intervals (file lines 31-35, top MD 3130.68 to base
3280.68), F-14 6 intervals (lines 36-41, 3005.00 to 3354.20), F-5 5 intervals (lines 45-49, 3605.00 to 3712.00),
perf type GUN, formation `Hugin Fm. VOLVE`; for these 16 rows the perf date, current status and status date are
blank (other wells such as 15/9-A-15 have `OPEN` and a date). Agreements/conflicts with EDM: no EDM counterpart
exists to agree or conflict with. The well identities agree (`NO 15/9-F-12`, `-F-14`, `-F-5` equal the EDM
`well_legal_name`). PV-03 therefore remains the only deterministic perforation source for the cohort and still
lacks effective time and open/isolated state. One caution for later reconciliation, if units are feet: the F-5
perforation bases (up to 3712 m) lie below the design 7" liner shoe 11896 ft = 3626 m (L27916), so the EDM F-5
liner designs cannot be treated as as-built geometry covering the perforations; other F-5 7" casing designs reach 12254 to 12490 ft.

Neighbouring already-present structured sources (not parsed here): RMS `wells/159f12|159f14|159f5/perforationsf*`
folders contain only `data_file` and `master.xml` (188 to 220 and 1.5 KB), no interval records. Wellcat/StressCheck
files in `Well_technical_data` are binary application files (`.wcd`/`.sck`), cohort relevant only by F-14 A NW
target name; `CasingSeat` and `WellPlan` folders are empty placeholders (`left_intentionally_empty.txt`).

## 5. Verdict per wellbore

| Wellbore | Sufficient deterministic completion-string data? | Evidence |
|---|---|---|
| F-12 | **None.** Only casing design variants with almost no components; no tubing, liner, packer, pump | section 3 counts; sample casing assemblies L25701, L25702, L25703, L25704, L25706, L25708, L25713, L25714, L25715, L25716, L25717, L25718; casing comps L31725, L31923, L31946, L31948 |
| F-14 | **None for the main wellbore.** Casing design variants only. **Partial, design-only** for sidetrack `F-14 A`: 7" tubing, 7" liner and one packer depth, planned (PROTOTYPE), not installed history and not linked to the PV-03 perforations | main: assemblies L28096, L28099, L28100, L28103, L28109, L28111, L28113, L28114, L28115, L28119; F-14 A: L28083, L28086, L28089, L28090, comps L34858, L34859, L34864, L34865, packers L48650, L48651 |
| F-5 | **None** for installed completion. Casing/liner design variants and a running-string tubing comp only | liners L27916, L27948; casing assemblies L27893, L27894, L27896, L27897, L27898, L27899, L27900, L27903, L27904, L27906, L27907, L27908; hole sections L269540-42 |

In no wellbore is an installed or as-built record, installation date, quantity or operating status present, so the
EDM cannot supply "equipment constituting the wellbore during production" at a date. Owner policy applies:
generic 3D equipment for the production tubing/packer/pump with unlocated or assembly-gap labels, with
EDM-derived casing/liner dimensions usable only as labeled design context (never as installed fact).
Sample counts per kind: casing assemblies (F-12 68, F-14 77, F-5 36, 10 locators each listed above and in the scan
output), hole sections (10 first locators per wellbore: F-12 L268669-L268678, F-14 L269650-L269659, F-5
L269519-L269528), cases (F-12 L50924-L50933, F-14 L51959-L51968, F-5 L51781-L51790). Kinds with fewer than 10
rows in the cohort are listed in full: Tubing 2, Liner 4 (F-14 A 2, F-5 2), packers 2, TBG comps 5.

## 6. Traps for a later profile

1. **No units, no depth datum** in the file; magnitude inference only; must be confirmed externally (block, not default).
2. **Design multiplicity**: 68/77/36 casing assemblies for three wellbores, only 43/49/24 distinct size/base; the same
   string repeats in PLAN, PROTOTYPE and blank phases (e.g. F-14 A tubing L28083 vs L28090). Duplicates differ by `assembly_id`
   only; there is no key that marks the as-built one. Selection must be rule-based and recorded as a warning, or blocked.
3. `phase` is on assemblies/cases/scenarios/hole-section groups inconsistently; blank is not "actual". ACTUAL means the
   survey or a torque-drag case, not an installed string.
4. **Running strings vs installed strings**: tubing/PBR/PKR components appear inside drillstring-type or unnamed
   assemblies (`5nuQ8`, `pKO8d`, `7nSnd`) belonging to T&D/hydraulics cases; they are not installed completions.
5. **Name collisions** between wells and relief-well wellbores (`F-12` under two relief-well sites); sidetrack naming
   (`F-14` and `F-14 A`, with F-14's bh_md 12123 close to F-14 A's liner base 12113.19, both unitless); F-11 neighbours.
6. Many attributes are blank strings or absent per row; casing comps for F-12 lack md_top/md_base; `length` and
   `md_*` can disagree (checked only by sampling).
7. Timestamps are record create/update times in `{ts ...}` syntax, not equipment effective times; do not feed to temporal state.
8. Large unrelated tables (LOAD_PROFILE 65,675, PORE_PRESSURE 39,084, FRAC_GRADIENT 37,257 rows) dominate size; a profile
   should whitelist tables. `CD_ATTACHMENT` blobs are application data and must be skipped.

## 7. Recommendation and measured streaming cost

Measured on this WSL host (single process, `uv run python -I`, expat, 1 MiB reads, `/usr/bin/time`): full census pass
5.0 s wall, peak RSS 38,572 kB (about 38 MiB); selective dump pass of 17 tables (22,023 rows) 3.2 s wall, 36 MiB RSS
(`ru_maxrss`). The 211 MB file therefore needs no special resource handling. Note `MAX_XML_BYTES` (64 MiB) and
`MAX_XML_NODES` (2,000,000) of the existing `stream_xml` helper are smaller than this file (the spike used the shared
hardened parser factory with its own depth cap and no byte cap); a production profile would need an explicit,
documented larger EDM limit or a table whitelist reader.

Recommendation: **a streaming EDM profile is not worthwhile for production/completion equipment or perforation
history** in the demo cohort, because the file has no installed/as-built records, no dates, no units and no perforation or
production tables. Low-cost optional value only: (a) identity/sidetrack and survey cross-checks (CD_WELL, CD_WELLBORE,
parent chain, `bh_md`), (b) labeled design context for casing/liner (shoe depth, OD, ID, weight/grade) if the owner
accepts design-variant data and units are confirmed. If ever built: scope 6 tables (CD_WELL, CD_WELLBORE, CD_DATUM,
CD_ASSEMBLY, CD_ASSEMBLY_COMP, CD_WEQP_PACKER), roughly 1 to 2 days with a gold fixture, fields: ids, names, parent,
`string_type`, `string_class`, `phase`, `assembly_name`, OD/ID/length/md_top/md_base/md_assembly_base as original strings
plus a unit status of `unconfirmed`, grade, manufacturer, `packer_depth`, record create/update timestamps, line locator;
validation: assembly-to-wellbore and well-to-wellbore consistency, per-component length against md span, duplicate
design collapse by (size, top, base), unit confirmation gate, no use for temporal state. Risks: wrongly presenting
design variants as installed equipment, unit/datum guess, F-14/F-14 A and relief-well name confusion.

Better use of effort for equipment: the completion documents (TASK-041/042 line); F-12 has none yet, so generic
placeholders apply per owner decision.

## 8. Limits of this check

Only the single XML export was parsed. Explicitly **not covered**: `Volve F.edm.zip` (77,698,104 bytes, not opened, assumed
to contain the same export), the `.sck` (StressCheck) and `.wcd` (Wellcat) application files, and the RMS
perforation folders (listed only; section 4), the Daily Drilling Report XML/HTML/PDF folders and the WITSML data. Coverage claims are limited to the tables and wellbores listed; unit and datum
statements are inferences from magnitudes where marked; field values were not compared across the large analysis tables.
