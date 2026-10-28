# Volve pilot: discovery findings and access handoff

Reviewed 2026-10-27. **The owner has now supplied a local official-data download:
33,678 files, 48,121,671,122 bytes (44.82 GiB), with all 33 acquisition candidates
present.** The per-well log layout differs from the candidate catalog layout.
See [the local content audit](#8-owner-supplied-local-data-content-audit) for
verified contents and important attribution/domain problems. The candidate CSV
is retained as the original selection list, not an accepted engineering manifest.
The [architecture](ARCHITECTURE.md) remains
provisional while the owner's project/reconstruction-agent/UX requirements are
worked through; source limitations have not been waived.
See the [equipment feasibility follow-up](EQUIPMENT_DATA_FEASIBILITY.md) for
actual fields, hashes and the unresolved installed-completion gate.

The owner chose to inspect real samples together before finalizing architecture.
No dataset was prepared. The owner also confirmed the indie track, public source
repository, a three-minute recorded demo, and local WSL or containerized runtime.
The Meta key is available locally and public-data processing is authorized,
subject to applicable source/provider terms; no key was read or API call made.

## 1. Recommendation

Audit **15/9-F-12, 15/9-F-14 and 15/9-F-5** first. F-12/F-14 are producer
candidates; SODIR explicitly identifies
[F-5 as an injector](https://factpages.sodir.no/en/wellbore/pageview/development/all/5769).
This offers more useful initial contrast than selecting only producers. It is
not a claim that their dated completion, production and perforation records
have already been reconciled.

| Candidate | Evidence found in metadata | Decision |
|---|---|---|
| F-12 | ACTUAL survey, three completion-report PDFs, completion plot, 21 LAS files in its exact wellbore folders | First audit candidate |
| F-14 | ACTUAL survey, final completion report, completion log, 26 LAS files | Second producer candidate |
| F-5 | ACTUAL survey, completion PDF and DOC, 30 LAS files; official injection purpose | Injector candidate |
| F-1 C | Distinct ACTUAL and PLAN surveys, completion reports, 27 LAS files | Reserve for a fourth/fifth wellbore or sidetrack demonstration |
| F-11 family | Separate base/A/B/T2 surveys; only one LAS for the base wellbore | Reserve until exact identities and histories are reconciled |

[SODIR's base F-11 record](https://factpages.sodir.no/en/wellbore/pageview/development/all/7078)
classifies it as **observation**, not production. Do not assign F-11 A/B data or
well-level production to the base wellbore. Counts above describe catalog entries,
not unique validated logs; a LAS file can be time-indexed or interpreted.

Start by inspecting F-12 plus shared files, then F-14/F-5. Select a common
historical window only after examining actual records. Three to five wellbores
remain a demo target, not a product limit or a reason to force unsuitable data.

## 2. Official access and rights

Primary sources:

- [Equinor's Volve page](https://www.equinor.com/energy/volve-data-sharing).
- [Volve Data Village listing](https://marketplace.databricks.com/details/5c3558ef-315c-44dd-baef-7062ac301f22/Equinor-ASA_Volve-Data-Village).
- [Official access guide](https://equinoropendata.blob.core.windows.net/userguides/Equinor%20open%20data%20-%20User%20Guide.pdf), pages 2-5.
- [Volve-specific license](https://equinoropendata.blob.core.windows.net/disclaimers/HRS%20and%20Terms%20and%20conditions%20for%20license%20to%20data%20-%20Volve.pdf), operative clauses 3-5 and Exhibit 1.
- [Marketplace terms](https://equinoropendata.blob.core.windows.net/disclaimers/Equinor%20open%20data%20-%20Terms%20and%20conditions.pdf).

### Earlier workspace checks and normal access steps

**Current access status:** the owner shared a working volume in another workspace
and then downloaded the source data locally. The earlier missing-volume,
installation-expiry hypothesis and account-mismatch observations below are
historical; they are not blockers to inspecting the owner's local files and do
not justify reinstalling anything now.

The owner is now signed in and the listing reports an existing installation.
However, the catalog contains only `information_schema`; opening `public/volve`
returns "schema does not exist." Provider metadata requires ownership not held
by this user. The cause is unconfirmed; no upgrade, reinstall or permission change
was attempted. The steps below describe the normal route, not a fix already proven.

Further read-only inspection confirmed an `ACTIVE` `DELTASHARING_CATALOG`,
`browse_only=false`, and the signed-in user as catalog owner. The source is
provider `equinorasa`, share `equinoropendata_volve`. Installation details say
**May 27**; catalog creation confirms 2026. That is 153 days before this review.
The current official listing explicitly states a **90-day usage policy**, with
installations automatically removed and reinstallation permitted. Expired access
is now a concrete hypothesis to test, not a proven diagnosis. An active catalog
shell does not establish a still-valid upstream data entitlement.

Refreshing/reinstalling only this listing is a documented recovery candidate.
Explicit authorization was requested but not received; no removal/reinstallation,
new terms acceptance or permission modification was performed. The listing's
published support address is **datasharing@equinor.com**. A provider inquiry can
include the public catalog/share names and missing-schema error without exposing
credentials or account identifiers. Do not send it automatically.

A later retry on October 27 reached a different, earlier access barrier:
Databricks displayed **"Signed in to a different account"** and required login.
Both the listing route and its original workspace-scoped URL reached that state.
This is a browser authentication blocker, not proof of installation expiry or
another volume-permission diagnosis. The owner must restore the correct workspace
session before the installation controls or original files can be rechecked.
No sign-out, credential handling or catalog changes were performed; the renewed
authorization request did not receive explicit approval.

1. Open the official listing and choose **Get access**. The guide requires
   sign-in/sign-up when not authenticated. Account creation and accepting terms
   are owner actions, not authorized agent actions.
2. Inspect the offered access options and costs. The listing is marked **Free**;
   this does not establish that a workspace, compute, export or network transfer
   is free. Do not start a paid trial/cluster or provision cloud resources merely
   to retrieve samples. Exact account eligibility and export UI remain untested.
3. The guide says the shared catalog can take up to one hour to appear. It can
   be accessed from the listing or Catalog. The community inventory uses:
   `dbfs:/Volumes/equinor_asa_volve_data_village/public/volve/`.
   This is a catalog path, not an anonymous HTTP download URL.
4. Locate only the files in the [candidate list](data/VOLVE_PILOT_CANDIDATES.csv).
   Check their sizes before downloading. Preserve directory structure and
   original filenames in a local directory outside the public repository.
5. Supply the local directory path for the audit. Keep credentials, signed
   download links and account identifiers out of committed documentation.

If that access route is unavailable, the owner can provide an authorized local
copy. Public mirrors are leads, not automatically equivalent to official files:
record mirror URL/revision, attribution, modifications and any available upstream
hash before admitting them to a manifest. The production workbook and a
daily-report conversion have now been downloaded and checked against their
pinned mirrors; see section 6. Their equality/fidelity to the official release
remains unverified. Mirror hashes must not be entered into the official candidate
CSV as though they verified the corresponding official files.

### Rights implications, not legal advice

The Volve-specific license permits commercial/noncommercial use, adaptation and
sharing, subject to its conditions. It is **not unmodified CC BY 4.0**:

- Do not sell the licensed material or present it misleadingly.
- Attribute Equinor and the former Volve license partners; include a reference
  to the terms and any applicable copyright notice.
- An adaptation's license must not prevent recipients from complying with the
  source terms. A public code license must not silently relicense the dataset.
- Do not imply sponsorship/endorsement or use names/trademarks to market the
  application as endorsed. Data is supplied as-is; third-party-rights risks remain.

Keep source data outside Git by default. Public derived fixtures, excerpts,
screenshots, geometry and the demo video need an attribution/rights check too.
Owner permission to process public data does not enable Contributor mode, waive
provider terms, or establish permission for every third-party document or asset.
Dataset-specific use/sharing terms take precedence over conflicting general
dataset terms; website/account terms remain a separate review.

## 3. Exact acquisition candidates

[VOLVE_PILOT_CANDIDATES.csv](data/VOLVE_PILOT_CANDIDATES.csv) contains **33**
case-sensitive relative paths. Join them to the catalog root only for discovery.
All rows are `metadata_only`, with unknown bytes and hashes deliberately blank.
`first` means shared context plus F-12; `second` means F-14/F-5 after the first
inspection. These are proposed acquisition waves, not approved engineering inputs.
`deferred_large` identifies the EDM export, reported by a community inventory as
approximately 201 MB; it is outside the proposed first-pass byte budget.

The first pass intentionally excludes the full PI archive, seismic cubes,
OpenWorks backup, RMS projects and Eclipse simulation outputs. They are not
prerequisites merely because they exist in the inventory.

| Family | What the candidate can establish after inspection | What its name cannot establish |
|---|---|---|
| Production XLSX | Sheet/cell schema, daily/monthly series, identities, units and nulls | Which downhole intervals produced or injected |
| ACTUAL survey PDF | Survey stations and coordinate/depth/north references | That all metadata are present or numeric extraction is accurate |
| Completion PDFs | Installed components, dimensions, intervals and effective dates | Complete lifecycle history from one report |
| EDT/EDM and WITSML equipment | Documented hole/casing sections, component dimensions, assembly and run records | That a drilling assembly or casing design is a permanently installed completion |
| Perforation DAT + README | Documented perforation intervals and any actual time fields | Opening/isolation/reperforation history when dates/events are absent |
| LAS | Index type, curve units/mnemonics, depth coverage and null sentinels | That every LAS is a depth log or source-measured petrophysics |
| Depth seabed/Hugin DAT + format XML | Interpreted surface coordinates and export schema | A measured reservoir volume or complete datum alignment |
| Well picks | Formation crossings and observed picks | A single unique depth per formation in a deviated well |

Completion reports may point to dated operations requiring a **second, explicit
selection** of daily drilling/workover evidence. XML report filenames exist for:

| Wellbore | XML filename count | Earliest/latest date in filenames |
|---|---|---|
| F-12 | 165 | 2007-06-14 / 2016-10-21 |
| F-14 | 134 | 2007-11-06 / 2016-10-20 |
| F-5 | 103 | 2007-11-15 / 2016-10-17 |

These are sparse inventory observations, not daily coverage, event effective
dates or proof of perforation operations. Select relevant reports from their
contents/references; do not download every XML or invent history between dates.

## 4. Findings that constrain the design

1. **Identity cannot come from directories alone.** The metadata's normalized
   `well` column collapses sidetracks. There is also a file named
   `15-9-F-11 B_Completion log.pdf` inside the F-12 report folder. Read headers
   and reconcile identifiers; quarantine conflicting attribution.
2. **Depth and time domains are distinct.** Exhibit 1 describes depth horizons
   as interpreted/interpolated. It describes fault polygons and fault sticks in
   TWT (milliseconds). Neither TWT nor a simulator schedule is measured historical
   depth/completion evidence. Faults are excluded from the initial depth-only
   list until a validated conversion or depth-domain source is available.
3. **Vertical references need explicit transforms.**
   [F-12's official record](https://factpages.sodir.no/en/wellbore/pageview/development/all/5599)
   reports ED50, UTM zone 31, RKB 54.0 m above MSL, MD 3520.0 m RKB and
   TVD 3107.0 m RKB. Its water depth is 91.0 m, whereas the field summary says
   80 m. Preserve source scope; neither scalar substitutes for a seabed surface.
4. **Static intervals are not temporal events.** Exhibit 1 describes the
   perforation DAT only as intervals. Historical coverage remains unverified.
   Simulator `COMPDAT`/schedule entries cannot silently fill real-event gaps.
5. **Native parsing remains the sensible first choice.** The mirrored workbook,
   equipment XML and report-conversion structures have now been inspected;
   pilot LAS schemas and original PDF text/table quality remain unknown. Do not
   lock an OCR stack or assume table reconstruction succeeds from readable text.

These findings reinforce the agreed evidence/identity/time separation; they do
not close the source gates or justify a final schema from filenames.

## 5. Reproducibility and audit status

The [community metadata index](https://github.com/985185/volve-metadata-index)
by Tejaswy Appalla is MIT-licensed metadata, not the engineering release. The
[v1.0 CSV](https://github.com/985185/volve-metadata-index/releases/download/v1.0/volve_catalog_v1.csv)
was downloaded to session storage and checked against its published SHA-256:

```text
bytes: 94665763
sha256: c145323bb3e60888db3c2837d073e509a21644e073240938973db5e1d0648045
columns: path,name,type,ext_norm,well,top_folder,tags
file rows: 404409
directory rows: 10176
```

Counts are not equivalent to Equinor's approximately 40,000-file original-release
description: the inventory includes dense PI exports and duplicated organization.
There is no file-size column. Original file existence, freshness and identity
must still be checked against the accessed release.

Official license/access PDFs were inspected locally with temporary Python 3.12
and `pypdf` 6.21.3 after that package was found missing. This is a research utility,
not adoption of an application parser. No OCR, engineering extraction benchmark,
Meta call, account creation, Docker startup or application implementation occurred.
The subsequent equipment probe parsed three public mirrored WITSML files with
Python 3.12 standard-library tools; its structural checks and limits are recorded
in the [equipment report](EQUIPMENT_DATA_FEASIBILITY.md).

**Next gate:** approve/obtain a bounded sample, execute the
[draft data-feasibility audit](specs/DATA_FEASIBILITY.md), and agree coverage and
numerical fixtures. Then finalize architecture, feature specs, the dependency DAG
and worktree execution sequence. The backlog remains blocked where those inputs
are required; metadata discovery is not a passed ingestion test.

Initial static checks passed: all 22 original candidate paths matched file rows in the
checksum-verified catalog; byte/hash fields remain unknown. Also checked 86 local
documentation links, 15 unique backlog IDs with acyclic dependencies, candidate
version agreement and `git diff --check`. These do not validate original contents.
Follow-up checks passed for all 33 exact paths, 95 local documentation links,
15 acyclic backlog items, DF-1 through DF-9, version agreement, sample hashes and
`git diff --check`. They do not replace the pilot source-content audit.

## 6. Acquired mirrors and the remaining acquisition gap

Verified copies and acquisition metadata are now retained in the existing
Git-ignored directory `data/volve/source-audit/`. Earlier session copies are
preserved. The local directory includes source files, provenance JSON, the
metadata catalog and official license/access PDFs; it is not distributed by a
Git checkout. These are research inputs, not an accepted demo manifest. No paid
Meta calls or cloud compute were used for acquisition.

| Acquired source | Verified content / integrity | Not yet established |
|---|---|---|
| [Production workbook](https://raw.githubusercontent.com/f0nzie/volve_eclipse_reservoir/0d34eaf1be7003a6c251dea938de3e3738501d71/inst/rawdata/Volve%20production%20data.xlsx) | 2,344,094 bytes; Git blob and SHA-256 checked; daily/monthly sheets; 15,634 daily rows under seven source wellbore labels | Official equality, units/quantity semantics, identity reconciliation and interval-level flow |
| [Daily-report conversion](https://huggingface.co/datasets/bengsoon/volve_daily_drilling_report/resolve/f0cbe11bfebb23f007b57a52cb903d9075db777c/data/all-00000-of-00001.parquet) | 2,180,278 bytes; published LFS SHA-256 checked; 1,759 unique reports under 26 labels, including 402 under F-12/F-14/F-5; selected completion and actual perforation narratives | XML conversion fidelity, missing numeric unit/datum attributes, complete installed geometry and history |
| [Three WITSML probes](EQUIPMENT_DATA_FEASIBILITY.md#3-small-source-audit-actual-fields-not-metadata-promises) | 7,776 bytes; pinned blob/hash checks and dimensioned component/bore fields | These are F-4/F-7 drilling probes, not a validated pilot production assembly |
| [F-5 trajectory mirror](https://github.com/maribickpostanes/Interactive-Well-Trajectory-Plot/tree/6231dc346f6a6f38be21404005d930d7d3abbc89) | Four XMLs plus file mapping, 542,300 bytes; published blob/size and local SHA-256 checked; source declares actual trajectories with MD/TVD/angle units | Overlap reconciliation, depth datum, horizontal CRS/wellhead origin, positional validation and other pilot surveys |

Production workbook SHA-256:
`7e9f7056af9bb89e907ce1b05ec85090e611021e072b6ecd395b5641a0689da9`.
Daily-report SHA-256:
`e4aec121079ad17cd2d3913646dd7d240e3a75d189458ce66ab3bf2af6ed2f56`.
See the [equipment follow-up](EQUIPMENT_DATA_FEASIBILITY.md#8-daily-report-conversion-real-completion-and-perforation-evidence)
for exact record/field locators and the critical cross-well attribution example.

The workbook's daily row counts are F-1 C 746, F-11 1,165, F-12 3,056,
F-14 3,056, F-15 D 978, F-4 3,327 and F-5 3,306. These are stored source labels,
not independently reconciled identities. Monthly data contains literal `NULL`
values; do not count every stored row as a measurement or zero-fill missing data.

**Answer to the all-required-data question: not yet verified.** The acquired
reports now supply real completion/perforation evidence, but the coherent
equipment tally, device dimensions, referenced surveys, original logs and
aligned seabed/formation inputs still need acquisition and content validation.
Additional historical events may exist; no complete coverage or verified initial
state is inferred from the report counts.

The next equipment-first bundle remains **PV-02, PV-03, PV-10 through PV-14,
and PV-23**, using the exact paths in the
[candidate CSV](data/VOLVE_PILOT_CANDIDATES.csv). It combines references/static
perforation intervals, the F-12 ACTUAL survey, three completion PDFs, the MD plot
and the EDT readme. The large EDM export is a separately bounded next step,
not an automatic download. The three small original DDRs identified in the
equipment report would also let us check conversion fidelity.

Authenticated access was rechecked on 2026-10-27 and still returned missing
`public` schema/volume errors. The provider/catalog owner needs to confirm the
published object and recipient read privileges, or supply an authorized local
copy. There is no evidence that a paid upgrade resolves this failure. The
companion `offset-well-intelligence-crew` repository was also inspected: its
derived-log inputs/generated analyses are not original completion reports.

## 7. F-5 trajectory acquisition and essential-data coverage

The four files at revision
`6231dc346f6a6f38be21404005d930d7d3abbc89` are named `1.xml` through `4.xml`;
`MetaDataFileInfo.txt` maps them to trajectory UIDs. Local copies use the
`mirror-f5-trajectory-` prefix. The sidecar `f5-trajectory-acquisition.json`
records immutable URLs, bytes, Git blob SHA-1, SHA-256, UIDs and limitations.

| Mirror file | Source section designation | Stations | Reported maximum MD, m |
|---|---|---:|---:|
| `1.xml` | 17.5in. | 38 | 1386.4288248 |
| `2.xml` | 12.25in. | 74 | 2913.3116232 |
| `3.xml` | 8.5in. | 96 | 3761.7654 |
| `4.xml` | 36in. | 9 | 213.0164904 |

All name F-5's main wellbore and include `Actual Traj` in their source names.
They preserve `uom="m"` for MD/TVD/displacements, `uom="dega"` for angles and
`aziRef="grid north"`. Each file's station MDs increase strictly. However, the
217 station rows have 203 distinct exact-decimal MD values: 12 MD values occur
in multiple files, and 11 have differing reported angles/TVD/displacements.
These are exact comparisons, not failures against an approved tolerance.
Do not concatenate or silently select between overlapping section records.
Depth datum, grid/CRS, wellhead origin and independent positional checks remain
unresolved; this is not yet a qualified field-positioned trajectory.

| Essential family | Current access/content status | Gate still open |
|---|---|---|
| Production/injection | Workbook acquired | Units, identities and quantity semantics |
| Trajectories | F-5 section XMLs acquired | F-12/F-14 sources, reference metadata and overlap/position validation |
| Installed equipment/completions | Operational narratives and separate drilling probes acquired | Complete production tally/drawing, actual device dimensions and installed locations |
| Perforation/completion history | Some explicit dated operations acquired | Complete supported baseline/history, TVD mapping and interval-flow evidence where claimed |
| Well logs | No selected original LAS acquired | Required log curves, units and acquisition/depth references |
| Seabed/bathymetry | No spatial source acquired | A referenced surface; a scalar water depth is not a substitute |
| Formations/reservoir context | No accepted spatial source acquired | Source-backed picks/depth surfaces and alignment metadata |

**Status at that mirror-only checkpoint: NOT PASSED.** The owner's hold on further design and
application implementation remains in force. The bounded alternative-originals
search found these survey sections, not a complete replacement for official
Volve access.

## 8. Owner-supplied local data: content audit

On October 27 the owner supplied `Downloads/Hackathon_Data` on the Windows host
and asked whether excluding seismic and the geoscience archive leaves an
important gap. The exact machine-local root is recorded in the Git-ignored
`data/volve/source-audit/local-inventory.json`; original files were not modified
or copied into Git. The attached discovery-document snapshot was not edited.

### Availability and scope

| Local family | Files | Bytes |
|---|---:|---:|
| Geophysical interpretations | 43 | 405,708,541 |
| Production | 2 | 2,343,915 |
| Reports | 3 | 187,239,137 |
| Eclipse reservoir model | 65 | 1,703,985,968 |
| RMS reservoir model | 5,325 | 9,799,424,396 |
| WITSML drilling records | 20,087 | 19,337,743,378 |
| Per-well logs/reports | 2,673 | 16,275,037,416 |
| Well technical data | 5,480 | 410,188,371 |
| **Total** | **33,678** | **48,121,671,122** |

All **33/33** pilot candidates exist, including the 211,263,929-byte EDM export.
For logs/reports, map catalog `Well_logs/<category>/<well>/...` to local
`Well_logs_pr_WELL/<well>/<category>/...`; `14.DIV. REPORTS` becomes
`14.DIV.REPORTS`. Eight zero-byte files are debug/job markers or files explicitly
named `left_intentionally_empty.txt`, not any of the 33 candidates. This is a
complete filesystem inventory, not a checksum/content audit of all 44.82 GiB.

### Contents actually checked

| Required family | Verified local evidence | Remaining qualification |
|---|---|---|
| Referenced trajectories | Native ACTUAL survey text plus PDF headers for F-12/F-14/F-5: 211/93/97 stations, ending at MD 3520/3750/3792 m; strictly increasing MD; explicit grid north, European 1950 Mean, UTM 31N, MSL and 54.90 m rotary-table references | Source revisions, tie-on and independent positional checks; do not substitute older 54.0 m metadata |
| Formation/reservoir context | Hugin Top/Base depth blocks with 184,066/186,756 points; BCU, Shetland and Ty depth surfaces; per-well formation picks including MD/TVD/TVDSS and repeated crossings | Interpreted surfaces, not a certified reservoir volume; preserve pick qualifiers and resolve vertical units/references/revisions |
| Seabed | A distinct DEPTH block with 280,641 points and reported Z range 83.0-103.4000015 | The same file also contains a TIME block; separate it before any depth rendering |
| Production/injection | Workbook ZIP CRC check passed; 15,634 daily rows, seven wellbore labels, including all three pilots; monthly sheet explicitly labels volumes `Sm3` and on-stream time `hrs` | Daily-field unit mapping and well-versus-interval flow remain separate validation tasks; preserve blanks and literal `NULL` |
| Well logs | Native, depth-indexed LAS with real non-null gamma curves for the pilots; F-12 also has 2,647 non-null interpreted porosity samples within MD 3102.102-3505.3524 | Raw and interpreted curves differ; some source depth ranges/coordinates conflict with the selected survey |
| Perforations/history | 48 interval-table rows, including 5 F-12, 6 F-14 and 5 F-5 intervals; 402 original pilot-labelled daily reports; selected dated completion/perforation narratives confirmed | All 16 pilot interval rows have blank perforation/status dates; not a complete historical state ledger |
| Equipment/completions | Source completion documents/drawings, original technical export, nine parseable pilot WITSML probes and original operational reports are present | Header-based attribution, scanned drawings, legacy Word files and installed-versus-design state require the focused [equipment audit](EQUIPMENT_DATA_FEASIBILITY.md) |

The official workbook is 2,342,595 bytes with SHA-256
`514d4e38763e09be7fbad12313429909b9799b1a6ec999bf5f36e0df1b6c9cae`.
It is **not byte-identical** to the earlier mirror; matching row counts alone
do not establish cell-by-cell equivalence.

### Important content traps, not reasons to download seismic

1. **The seabed filename is not the domain contract.**
   `Seabed+VelBuild_04_08+PUB+DEPTH.dat` begins with the seabed DEPTH block, but
   lines 280700-280704 introduce another horizon with domain **TIME**, followed
   by 235,613 points. Treating all 516,254 file rows as bathymetric depth would
   introduce false values above 2400. Read embedded block headers.
2. **Some report names/folders identify the wrong asset or report type.**
   F-12's three `COMPLETION_REPORT` PDFs describe the F-11 family. F-5's
   `COMPLETION_REPORT_1.PDF` is a drilling report. Their existence does not prove
   correctly attributed completion coverage; inspect alternative Word files
   and diagrams before concluding that a document is missing.
3. **A perforation table is not a time series.** Date/status columns exist,
   but are blank in every proposed pilot row. Original operational reports
   supply dated events, including F-14's July 5, 2008 firing interval, and
   sometimes describe another well. Reconstruct history from claim subjects
   and effective times; do not assign all events to the report's folder label.
4. **LAS selection matters.** The first F-12 raw MWD candidate contains no
   gamma-ray curve. Other files do. Its petrophysical input LAS declares and
   contains samples beyond the ACTUAL survey's 3520 m MD endpoint, and its
   header northing differs from that survey. Keep that conflict explicit.
   A separate interpreted output covers the reservoir interval and must be
   labelled as interpreted, not a raw sensor measurement.

**Scope conclusion:** raw seismic and the OpenWorks geoscience archive are not
required to display the existing interpreted formation/reservoir depth surfaces
and seabed. Re-interpreting seismic or reproducing the full geological modeling
project would be a different scope. The PI historian and duplicate `Well_logs`
layout are also not prerequisites for the current historical demo.

Local file availability is no longer the blocker. Source selection, equipment
extraction/attribution, temporal reconciliation and reference validation must
still be distinguished from a passed G1/owner-approved engineering manifest.
No architecture or application implementation is authorized by this audit.

The focused equipment audit now confirms an **AS INSTALLED F-14 schematic**
with device dimensions and MD placement. It also identifies a specific remaining
F-12 source target: the **completion tally dated 29-01-2008, As Installed**,
referenced by the 2016 plug logs but not located in the inspected documents.
The October 28 follow-up verifies **F-5's embedded Existing completion table**,
including safety-valve/packer dimensions and MD. Its three August 2008 perforation
intervals plus two October additions match the five static rows; two April 2016
additions show why that table alone is not a full history.

The expanded F-12 tally search covered 87 PDF paths / 68 unique contents / 3,262
pages plus selected scan and engineering-export inspection, without finding the
referenced tally. It did find February 2008 firing and November 2014 plug/firing
evidence. F-14's six initial intervals now have matching July 5-9, 2008 firing
records. Thus events are **not absent for all candidates**: remaining gates are
history completeness, conflicting claims and reference/state qualification.
F-11 B is a conditional reserve, not an automatic replacement: its detailed
completion drawing is explicitly **Plan**. See the
[target/history findings](EQUIPMENT_DATA_FEASIBILITY.md#10-target-qualification-and-history-follow-up-october-28).

The owner subsequently selected F-12/F-14/F-5 and accepted evidence-safe generic
F-12 equipment plus visible discrepancies. Cohort selection is closed; the final
manifest, references, historical coverage and required real-data acceptance are
not. Missing F-12 dimensions no longer block source-independent implementation
planning, and warnings never permit invented measurements or placement.

### Reproducible checks

The Git-ignored audit records are `local-inventory.json`,
`local-structured-audit.json`, `local-production-audit.json`, `local-f12-porosity-audit.json`,
`local-witsml-audit.json`, `local-completion-audit.json` and the subsequent
`local-target-followup-audit.json` under
`data/volve/source-audit/`. They retain exact local
paths, hashes, source line samples, counts and limitations. The filesystem walk
took 364.831 seconds; the corrected structured-data pass took 14.5 seconds with
25,940 KiB peak process RSS. These are audit measurements, not application
performance results. Native XML/XLSX/LAS/text readers and bounded local PDF
inspection were used. No code or macros embedded in source documents were
executed, and no paid Meta calls or cloud compute were used.
