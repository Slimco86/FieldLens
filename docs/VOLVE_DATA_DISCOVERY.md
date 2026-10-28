# Volve pilot: discovery findings and access handoff

Reviewed 2026-10-27. **Pilot files remain metadata-only; three small mirrored
F-4/F-7 equipment XML probes were subsequently inspected.** This is a
data-selection proposal, not an approved demo manifest. The subsequently completed
[architecture](ARCHITECTURE.md) preserves these source-data limitations.
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

### Owner access steps

The owner is now signed in and the listing reports an existing installation.
However, the catalog contains only `information_schema`; opening `public/volve`
returns "schema does not exist." Provider metadata requires ownership not held
by this user. The cause is unconfirmed; no upgrade, reinstall or permission change
was attempted. The steps below describe the normal route, not a fix already proven.

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
hash before admitting them to a manifest. A public GitHub mirror exposes a
2,344,094-byte production workbook at
[this pinned tree](https://github.com/f0nzie/volve_eclipse_reservoir/tree/0d34eaf1be7003a6c251dea938de3e3738501d71/inst/rawdata);
its bytes and equality to the official workbook were **not** checked. No mirror
engineering files from that production mirror were downloaded. A later equipment
probe inspected three small WITSML files from a different public mirror; those
are not verified copies of the current official release or selected pilot records.

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
5. **Native parsing remains the sensible first choice**, but actual XLSX/LAS/XML
   schemas and PDF text/table quality are unknown. Do not lock an OCR stack or
   assume table reconstruction succeeds from readable text.

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
