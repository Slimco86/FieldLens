# Equipment data: F-14 and F-5 dimensional evidence found

Updated 2026-10-28 after the owner identified equipment data as a project-critical
concern. **Latest verdict: source-backed dimensional reconstruction is feasible
for F-14 and F-5; the full cohort/history/reference gate is not passed.** Local
completion drawings supply device dimensions and MD intervals. F-12's specific
installed tally remains unlocated; F-11 B is a conditional reserve, not an
automatically better installed-data substitute. See the
[October 28 follow-up](#10-target-qualification-and-history-follow-up-october-28).
At earlier checkpoints we had
inspected dimensioned XML probes and a public conversion of daily reports containing
actual production-completion and perforation operations. We have not yet verified
a complete, dimensioned, date-specific installed assembly for the chosen pilot.

## 1. What 3D reconstruction actually requires

Complete manufacturer CAD is not a prerequisite for every component:

- **Casing/tubing:** validated diameters, interval/length, installation/configuration
  evidence and a referenced well trajectory support dimension-driven geometry.
- **Packers, valves, pumps and other discrete devices:** installed identity and
  MD location plus dimensions/drawings support source-backed geometry. A verified
  catalog match can fill product dimensions, but cannot establish installation.
- **Fine mechanical detail:** threads, internal mechanisms and complex surfaces
  need drawings/CAD or an explicitly illustrative shape. An outer envelope is not
  a mechanically exact replica.

The required distinction is **measured/validated geometry versus display detail**,
not "CAD file present versus impossible." However, an entire equipment scene made
from unlocated generic placeholders would not demonstrate the intended
source-backed reconstruction. Generic fallback remains useful for individual
missing attributes; it cannot prove dataset feasibility.

## 2. The original conversation's sources, reassessed

| Source | Useful contribution | Boundary / current evidence |
|---|---|---|
| Volve completion and well-engineering reports | Installed tubing/casing, discrete equipment, completion drawings and dated configurations where documented | Exact candidate PDFs located; their contents remain uninspected |
| Volve EDT/EDM export | Hole sections, casing designs, assemblies/components, well/wellbore identities and surveys | Official license Exhibit 1 identifies this export. [Community inventory](https://github.com/gabrielserrao/spe-2026-challenge/blob/main/DATA_SOURCES.md) documents its tags; not independently verified against the large XML |
| Volve WITSML `tubular`, `bhaRun`, `wbGeometry` | Component dimensions, assembly order, run context and bore/casing sections | Three small mirrored XML files inspected below; drilling equipment is not automatically permanent completion equipment |
| Daily drilling/workover reports | Operations, installation/removal context, configuration dates and narrative evidence | A pinned conversion now provides 1,759 reports, including 402 under the proposed pilot labels; selected completion/perforation narratives inspected in section 8, not a complete history audit |
| [Equinor Ask Volve](https://github.com/equinor/industrial-hackathon-2026/blob/main/ask-volve/README.md) | Official confirmation of the report/production corpus and access route | Another challenge description, not a separate equipment dataset or proof of complete geometry |
| [SODIR FactPages](https://factpages.sodir.no/) / [FactMaps](https://factmaps.sodir.no/map) | Official identities, wellhead coordinates, drilling/completion attributes and spatial context | Useful cross-checks, not a replacement for a downhole equipment tally; the open-data landing-page fetch returned 403 during this follow-up |
| [OPM/Norne](https://opm-project.org/?page_id=559) | Eclipse-format simulation benchmarks and reservoir-grid importer tests; ODbL terms apply | Different field and model inputs. Cannot supply Volve installed hardware or actual historical perforation events |
| [welleng exchange readers](https://github.com/jonnymaserati/welleng) | Candidate tooling for EDM and WITSML tubular/BHA parsing | A library is not a data source. Maintainer validation does not validate our particular records/version |
| [PetroRAG report extracts](https://github.com/yohanesnuwara/PetroRAG/tree/ac4f27ef4e1683e9b79c661cf50451dff2b00fd9) | Secondary text extracts can reveal report identities and additional leads | Original PDFs are absent; a document labeled "Completion Report" has a drilling-report header. Not accepted as installed-completion evidence |

The original conversation did **not** establish a verified, model-specific
manufacturer equipment library. Manufacturer research remains the next step only
after an exact model/variant is found in installation evidence. A vendor string
such as `BHI` is not enough to select an arbitrary Baker Hughes product.

The community inventory's old `data.equinor.com/dataset/Volve` "direct download"
link now redirects to Equinor's general data-sharing page. It is not a verified
alternative download route.

## 3. Small source audit: actual fields, not metadata promises

Source: Alfonso Reyes's public
[volve-drilling mirror](https://github.com/f0nzie/volve-drilling/tree/3698c43d4adc0ee11ffa8fd5f876fa961c9c846d).
Its README identifies the files as Volve drilling data. Three files were retrieved
at that fixed commit, totalling **7,776 bytes**, and retained outside the repository.
Their Git blob hashes match the mirror inventory; equality to the current official
release has not been established. F-4/F-7 are format/equipment probes, not an
automatic change to the proposed F-12/F-14/F-5 cohort.

| ID | Source | Bytes | Records inspected |
|---|---|---:|---|
| M1 | [F-4 tubular/1.xml](https://raw.githubusercontent.com/f0nzie/volve-drilling/3698c43d4adc0ee11ffa8fd5f876fa961c9c846d/witsml/Norway-Statoil-NO%2015_%2447%24_9-F-4/1/tubular/1.xml) | 1,737 | 2 components |
| M2 | [F-7 tubular/1.xml](https://raw.githubusercontent.com/f0nzie/volve-drilling/3698c43d4adc0ee11ffa8fd5f876fa961c9c846d/witsml/Norway-Statoil-NO%2015_%2447%24_9-F-7/1/tubular/1.xml) | 3,835 | 6 components |
| M3 | [F-4 wbGeometry/1.xml](https://raw.githubusercontent.com/f0nzie/volve-drilling/3698c43d4adc0ee11ffa8fd5f876fa961c9c846d/witsml/Norway-Statoil-NO%2015_%2447%24_9-F-4/1/wbGeometry/1.xml) | 2,204 | 4 bore sections |

SHA-256:

```text
M1 f3ae15bda8a12beaf0800323987dd8e79441beb1e07234cec625202f2c697d0b
M2 150e445d47f12428078d5d7bf0129323286206ef882e3b6e93f778f1a60ab9be
M3 331c713decb05b69087047cb5f164b96539a43e7352b3d0521f3871573ba5b78
```

### Representative engineering attributes

Values below are rounded for readability; original strings and `uom="m"` remain
in the immutable XML. Locators use namespace
`w = http://www.witsml.org/schemas/1series`, version `1.4.1.1`.
The table uses local-name/UID shorthand; brace lists name child fields, not a
literal XPath expression. An XPath consumer must bind and apply the `w` prefix.

| Attribute / source locator | Reported value | What it supports | Missing or conflicting context |
|---|---|---|---|
| M1 `tubular[@uid='16VIRG33']/tubularComponent[@uid='63VIRG33']/{od,id,len}` | Tubing OD 0.1778 m, ID 0.15748 m, length 2054 m | A source-reported tubular envelope | Assembly is `drilling`; no proof this is the installed production tubing or its MD placement |
| M1 component `62VIRG33` `{od,id,len}` | Drill pipe OD 0.1397 m, ID 0.1213612 m, length 562 m | Dimensioned tubular record | Total component length is not automatically one joint or a located interval |
| M2 `tubular[@uid='43VFNI35']/tubularComponent[@uid='183VFNI35']/{od,id,len}` | Crossover OD 0.18415 m, ID 0.06985 m, length 1.22 m | Dimensioned device envelope | Model, detailed profile/threads and installed depth absent |
| M2 component `185VFNI35` `{typeTubularComp,od,id,len}` | Spear; OD 0.14605 m, ID 0.0508 m, length 2.3 m | Source-reported fishing/drilling component | Not a pump/packer; do not substitute it for production equipment |
| M3 `wbGeometry[@uid='4VIRG33']/wbGeometrySection[@uid='18VIRG33']/{typeHoleCasing,mdTop,mdBottom,odSection,idSection}` | Casing, MD 593-2630 m; OD 0.244475 m, ID 0.216789 m | Diameter/depth fields needed for a casing interval | Depth datum and trajectory consistency still unverified |

**Match/evidence status:** extracted from mirrored source records, not catalog
matches, not validated installation claims. **Allowed use:** analysis under the
Volve data terms with attribution; no raw XML is added to the public repository.
Any redistributed derivative must retain the applicable source notices.

### Counter-evidence and traps

- Both tubular objects explicitly say `typeTubularAssy=drilling`. Their
  `itemState=actual` is a source label, not proof of permanent installed state.
- Creation/change timestamps are not installation dates. The geometry object's
  report timestamp is 2016-09-30, not evidence for the entire producing life.
- The four geometry sections report TVD equal to MD at every endpoint. Preserve
  these as source values and compare with an actual survey; do not assume this
  gives a validated vertical path or "correct" the values without evidence.
- Component XML order differs from the `sequence` fields. A consumer must inspect
  documented sequence/orientation semantics, not use document order as string order.
- `tensYield=0`, unknown connections and missing device models are not verified
  material/connection specifications. Zero must not become a certified strength.
- Exporter user/network metadata is present. Retain originals locally but exclude
  irrelevant account/network details from public excerpts and model context.

Validation performed with temporary Python 3.12 standard-library analysis:
per-file byte limits, expected Git blobs, SHA-256, no DTD/entity declarations,
XML parse/version, all 8 component and 4 section records, explicit metric units,
finite values, ID < OD and positive length/MD intervals. **These checks passed;
they are structural checks, not engineering certification or application tests.**

## 4. Prioritize the richer sources without confusing their meanings

The [expanded candidate list](data/VOLVE_PILOT_CANDIDATES.csv) adds:

- `Well_technical_data/EDT_EDM_read_me.txt`.
- `Well_technical_data/EDM.XML/Volve F.edm.xml` as **deferred_large**:
  the community inventory reports approximately 201 MB, not independently measured.
  Do not silently exceed the proposed sample budget; inspect size/access first,
  then approve a separate bounded streaming audit if needed.
- One `tubular`, `bhaRun` and `wbGeometry` XML candidate for each pilot folder.

Catalog XML counts by named folder (not reconciled wellbore/run identity):

| Folder | Tubular | BHA run | Wellbore geometry |
|---|---:|---:|---:|
| F-12 | 9 | 10 | 3 |
| F-14 | 6 | 7 | 2 |
| F-5 | 9 | 11 | 1 |

Community-documented EDM tag families include `CD_HOLE_SECT`, `CD_ASSEMBLY`,
`CD_ASSEMBLY_COMP`, `CD_CASE` and survey/wellbore records. Their semantics include
designs and drilling assemblies; they are not automatically production completion
records. Read the export documentation and join to dated installation evidence.

## 5. Equipment-specific go/no-go checkpoint

Proposed in [DF-9](specs/DATA_FEASIBILITY.md), pending owner approval at G1:

1. Select one pilot wellbore and one historical configuration/date.
2. Trace a coherent installed casing/tubing assembly to original source records,
   including physical sizes, MD placement, survey/reference compatibility and
   explicit missing attributes.
3. Include at least one located discrete completion device with evidenced type,
   axial length and outer diameter, from installation records or a verified
   catalog match. Separate source-backed envelope from illustrative fine detail.
4. Fail the checkpoint if the only evidence is drilling BHA data, a planned
   casing design, vendor-only catalog guessing or generic placeholders.

One pilot is an early feasibility check, not the final multi-well acceptance test.
If it fails, select better-supported data or obtain an explicit scope decision;
do not hide the gap behind Blender modeling.

## 6. Current access blocker

The owner successfully signed in. The Volve listing reports an existing
installation, but the catalog currently contains only `information_schema`.
Opening its advertised `public/volve` volume returned HTTP 404:
`Schema 'equinor_asa_volve_data_village.public' does not exist`.
Provider-details access returned HTTP 403 (not provider owner).

This is **not** a missing-account problem. The underlying cause is unconfirmed;
do not claim Free Edition is definitely unsupported, or that paying will fix it.
No catalog was removed/reinstalled, permissions changed, compute started or
subscription created. Next action is to have the owner/provider restore visibility
of the published share, or supply an authorized local copy of the selected files.
The public XML probes and subsequent report/production mirror acquisitions let us
examine real records, but do not resolve full pilot coverage or official access.

### Documented, non-destructive diagnostic handoff

[Databricks recipient documentation](https://docs.databricks.com/aws/en/opensharing/read-data-databricks)
separates provider inspection (`USE PROVIDER` or provider ownership) from reading
a shared volume. Consequently, the provider-details 403 does not prove that
ordinary file access requires provider ownership, nor identify the cause of the
missing schema.

A privileged catalog owner/provider needs to verify:

1. The published share still contains the advertised `public.volve` volume and
   the catalog is mounted from that share.
2. The recipient's catalog/schema/volume read privileges cover those objects,
   including the documented `READ VOLUME` privilege for the shared volume.
3. The intended files are visible before any compute, export or parser is run.

Do not prescribe an account upgrade, LinkedIn verification, catalog deletion or
reinstallation as a proven fix. The inspected Free Edition documentation does
not establish that one of these resolves this missing-schema failure.

## 7. Earlier alternative-report search

The follow-up checked additional public repository inventories, web discovery,
Zenodo metadata and report-source references. No independently verifiable
installed-completion PDF was acquired. This bounded search is not proof that no
such report exists in Volve.

One useful secondary source was PetroRAG's pinned `data/text-chunks.csv`
(493,884 bytes; SHA-256
`9cd2dcd7e5601df7f14eb1c702c472bd771aabd738dc9bf9f20f2fa035d49368`).
Its 360 chunks are labeled 199 geological, 91 completion and 70 drilling chunks.
The key `Article_ID=Completion Report_0` contains the header **FINAL WELL REPORT /
Drilling**, naming F-15 A/B/C, despite its surrounding "Completion Report" label.
The notebook references locally supplied PDFs, not a publicly downloadable
original. The original report type, full page coverage and installed equipment
must therefore be verified before admitting any extracted claims. Private
document-system links embedded in the export were not followed.

At that checkpoint, the inspected samples did not demonstrate an installed pilot
assembly. The subsequent acquisition below improves the evidence substantially,
but does not validate complete geometry or history. Reports mislabeled by
downstream tooling still cannot supply that proof. No permission change, paid
service or invented geometry is justified by an access failure.

## 8. Daily-report conversion: real completion and perforation evidence

Acquired 2026-10-27 from
[bengsoon/volve_daily_drilling_report](https://huggingface.co/datasets/bengsoon/volve_daily_drilling_report/tree/f0cbe11bfebb23f007b57a52cb903d9075db777c).
The publisher describes a WITSML-to-JSON conversion, distributed as
[one Parquet file](https://huggingface.co/datasets/bengsoon/volve_daily_drilling_report/resolve/f0cbe11bfebb23f007b57a52cb903d9075db777c/data/all-00000-of-00001.parquet).
Its **2,180,278 bytes** match the published LFS SHA-256:

```text
revision: f0cbe11bfebb23f007b57a52cb903d9075db777c
sha256: e4aec121079ad17cd2d3913646dd7d240e3a75d189458ce66ab3bf2af6ed2f56
```

The file has 1,759 rows with 1,759 unique `docName` values and 26 distinct
`nameWellbore` labels. F-12 has 165 reports, F-14 134, and F-5 103: **402
reports**, not 402 exclusively single-well records or a continuous daily history.
It retains activity narratives and offset-aware start/end strings. Python 3.12
with temporary PyArrow 26.0.0 read the Parquet after the reader was found missing;
this does not add PyArrow to the application stack.

The following are summaries of source-reported facts, not validated geometry.
Record and activity indices are **zero-based within the pinned file**. `docName`
plus the field locator provides a more readable record reference.

| Record / `docName` | Field locator | Source-reported evidence | Boundary |
|---|---|---|---|
| 740 / `15_9_F_12_2008_01_25` | `activity[5].comments` | Running a `7" x 9 5/8"` Granite production packer, tubing joints and a `7" 20 ft` PBR assembly; activity window 2008-01-24 21:00 to 2008-01-25 00:00, UTC+01:00 | A real model/family and assembly lead. Nominal size designations do not establish the packer's actual OD, length, exact variant or final MD |
| 746 / `15_9_F_12_2008_01_31` | `activity[3].comments` | Packer-setting/tubing-test operation; 2008-01-30 02:00-02:45, UTC+01:00 | Later configuration evidence, not an independently identified device or exact setting instant |
| 748 / `15_9_F_12_2008_02_02` | `activity[0].comments` | Testing the production packer from below and holding pressure on a TRSCSSV control line | Supports production-completion context; does not provide a complete tally or device dimensions |
| 866 / `15_9_F_14_2008_07_06` | `activity[8].comments` | Guns fired over interval 1, **3345-3354.2 m MDRT**; 2008-07-05 11:30-11:45, UTC+02:00 | An actual reported perforation event, not merely preparation. Preserve MDRT; do not call this TVD, total well perforated length or proof of interval flow |
| 832 / `15_9_F_14_2008_06_02` | `activity[6].comments` | Opening **F-12's** DHSV in a report whose `nameWellbore` is **F-14** | Claim subject cannot automatically inherit the report's wellbore. Cross-document entity and temporal reconciliation are essential |

Important limits:

- The conversion's structured survey/status numeric fields expose no corresponding
  unit/datum attributes. For example, `elevKelly="54.9"` is not permission to
  assume metres, silently replace the SODIR RKB value, or calculate coordinates.
  Units written explicitly in narratives remain evidence for those statements.
- Report filenames/end dates differ from activity dates. An operation's time
  window is not an exact event timestamp, and preparation/running-in is not firing.
- The full XML conversion was not audited for omissions or fidelity. Original
  XML UIDs, units and locators cannot be reconstructed by guessing.
- The dataset card declares CC BY 4.0. That label does not override underlying
  Volve-specific restrictions. Retain both provenance layers, attribute the
  original partners and mirror, and keep raw data outside Git.
- Complete casing/tubing continuity, installed discrete-device geometry, referenced
  surveys, all historical state changes and interval-scoped flow remain unverified.
  **DF-9 and the full pilot gate remain open.**

The checksum-verified metadata catalog contains exact XML, HTML and PDF basenames
for the three example reports ending `2008_01_25`, `2008_07_06` and `2008_06_02`
above. Their XML prefix is
`Well_technical_data/Daily Drilling Report - XML Version/`; append the complete
`docName` and `.xml`. This matches an inventory, not the original contents.
These small originals are useful fidelity checks once official access works.

**Verdict at the mirror-only checkpoint:** meaningful production-completion and dated perforation
evidence is now acquired, so the earlier evidence gap is narrower. A complete
source-backed 3D pilot is still not demonstrated. Prioritize the original
completion tally/drawing and referenced survey; use the Granite designation for
bounded product research only, without guessing a manufacturer or variant.

## 9. Local originals: as-installed F-14 proof and remaining gaps

The owner's local download resolves the source-access problem. All 33 candidate
files exist, but inspecting the originals changes several filename-based
assumptions. Source hashes, page/text counts, original report locators and scope
limits are retained in Git-ignored `data/volve/source-audit/local-completion-audit.json`.
This was a bounded source audit, not a reconstruction of every historical state.

### F-14: real installed geometry, not a drilling-assembly substitute

Source: `Well_logs_pr_WELL/15_9-F-14/14.DIV.REPORTS/FWR_Completion_F14.pdf`,
**PDF page 57, section 8.8, Completion Schematic, AS INSTALLED**.
The 60-page scanned PDF is 54,466,467 bytes; SHA-256:
`07206e97cba67eedd0ba2f6e67a20e7be654bfae2fd91159912f2f2595f7f334`.
The diagram labels MD as metres RKB, length as metres and Max OD/ID as inches.
These rows were read visually from rendered page crops; they are not OCR results.

| Source device | MD top-bottom, m RKB | Length, m | Max OD, inches | ID, inches |
|---|---:|---:|---:|---:|
| 7-inch Baker TSM 7.5 safety valve | 489.980-492.210 | 2.230 | 9.190 | 5.875 |
| Baker PBR size 190-60, 20 ft stroke | 2583.580-2592.020 | 8.440 | 8.240 | 6.043 |
| Granite packer 9 5/8-inch x 7-inch, size 831 x 600 | 2596.050-2597.590 | 1.540 | 8.300 | 6.000 |

The drawing also supplies tubing joints, other mandrels/carriers, casing intervals
and six perforation intervals. The PBR's **20 ft stroke is not its 8.440 m overall
row length**. These measurements support source-based dimensional envelopes;
they do not supply manufacturer CAD or every mechanical detail.

Reference and temporal qualification still prevent declaring the whole engineering
gate passed:

- The schematic gives `RKB-MSL: 53.870 m`; the ACTUAL survey and report page 56
  use 54.90/54.9 m. Keep these references separate pending reconciliation.
- The schematic's literal `Date Shot` is `7/9/2008`. The follow-up below locates
  all six original firing events over July 5-9: the drawing may summarize the
  campaign's last day, rather than contradict every earlier interval date.
  Its tubing-installation date still needs alignment with the operation sequence.
  Diagram update time, activity windows and installation time are different fields;
  do not apply one drawing date to every event.

**Conclusion:** equipment reconstruction is not dependent on downloading seismic
or finding a generic CAD library. At least one real pilot completion contains
the type, dimensions and MD placement needed. Compatible references and the
date-specific configuration still need qualification.

### F-12: a specific as-installed tally is still not located

The three `COMPLETION_REPORT_1/2/3.PDF` files in its report folder describe the
**F-11/F-11 A/F-11 B family**, not F-12. Its two legacy Word documents are a
drilling programme and recommendation, not an as-installed completion report.
`COMPLETION_LOG_MD_PLOT_2.PDF` is a geological summary, despite its filename.
The inspected drilling report supplies casing MD intervals; daily reports
provide actual packer-running/setting/testing events, but not a full device tally.

The 2016-08-15 and 2016-08-16 production plug logs explicitly refer to a
**"Completion tally dated 29-01-2008 As Installed"**. The first log, page 3,
also reports 7-inch tubing with ID 6.195 inches to 3024 m and a transition near
2918 m MD. This is a valuable source lead, not the referenced tally itself.
That tally was **not located in the inspected sources**; absence from the entire
release is not established. No separately named `tally` file appears in the
community catalog. If F-12 must have a fully dimensioned completion in the demo,
locating this specific document is the highest-value remaining source task.

### F-5: correct completion source exists in Word

Its `COMPLETION_REPORT_1.PDF` is a drilling report. The genuine completion report
is `15_9_F_5_FWR_Completion.doc`. Local legacy-Word extraction confirmed as-run
packer-setting/testing, liner-top/PBR operations and perforation intervals.
The October 28 follow-up below resolves the embedded-image inspection gap:
its dimensioned drawing is labelled **Existing**, with tubing-installation
metadata. This is not a missing-document problem.

### Historical and extraction limits

All 402 pilot-labelled original daily-report XMLs parsed without DTD/entity
content. The five earlier activity probes were confirmed against originals,
including the explicit F-14 firing interval and an F-14-labelled report
discussing F-12 equipment. Report counts and keyword matches are not a complete
history, an initial state, or interval-level flow attribution.

The audit profiled 20 PDFs, read six legacy Word documents, inspected six F-12
production-log PDFs and rendered selected pages. Several scans/embedded images
and later state transitions remain unread or unreconciled. Readers were temporary
local utilities: Python 3.12/pypdf 6.21.3, isolated pypdfium2/Pillow rendering,
and antiword 0.37-16 extracted into the session directory after it was missing.
No application dependency, system installation, OCR service or Meta call was
introduced, and source files were not changed.

## 10. Target qualification and history follow-up: October 28

The owner subsequently selected **15/9-F-12, 15/9-F-14 and 15/9-F-5**, accepting
generic/unlocated F-12 equipment and visible discrepancies. This is not a fully
qualified engineering manifest. The source-inspection follow-up searched the
specific missing F-12 tally, inspected F-5's embedded drawings and assessed
**15/9-F-11 B** as a possible replacement. F-11, F-11 A, F-11 T2 and F-11 B must
not be collapsed into one wellbore.

### F-12 tally: expanded search, still not located

The bounded native-text search covered **87 PDF paths, 68 distinct contents and
3,262 pages**: cross-well completion/FWR reports, all 31 F-12 PDFs and relevant
technical PDFs. Duplicate hashes confirm that copies of F-11 reports under F-12
are not independent F-12 evidence. The filename inventory has no separately
named tally/schematic/as-installed candidate. The full EDM tag scan and 112
F-12 assembly records did not identify this completion tally; drilling/casing
design assemblies are not a substitute.

The August 18, 2016 integrity log also references the **29-01-2008 As Installed**
tally (PDF pages 4 and 6), alongside the previously found August 15/16 plug-log
references. These are references, not the drawing itself. The 2009 PLT ZIP
contains four LAS files, not a tally attachment. All 20 pages of the two scanned
November 2014 plug/perforation PDFs were rendered for overview and selected
headers read at full resolution; they document interventions, not a full
completion tally.

**Result: not found in this search, not proven absent from the entire release.**
There was no general OCR pass over all scans or exhaustive inspection of every
embedded image in the 44.82 GiB download. F-12 still lacks a qualified complete
installed device/dimension/MD table, despite useful operational and log evidence.

### F-5: embedded dimensioned Existing completion verified

Original: `Well_logs_pr_WELL/15_9-F-5/14.DIV.REPORTS/15_9_F_5_FWR_Completion.doc`,
2,653,184 bytes; SHA-256
`ebe36ba321bb098398bc0f76d8d506d43a2c502781d8d1924dc37cba6f1dda3b`.
Nine PNGs were extracted inertly from its OLE Data stream, without running Word
macros. The decisive table is at **Data stream byte offset 2,062,779**:
1620 x 682 pixels, 104,397 bytes, SHA-256
`4e9dbae71416cae81184b2fae0f788372a158f7e385691a1c0bcd418f509d782`.
This is an embedded-image locator, not an asserted Word page number.

The drawing identifies **Existing / NO 15/9-F-5 (Main Wellbore)**, Water Injector,
`Tub.Inst.Date 8/18/2008`, `Opr.Fin.Date 8/27/2008`, and last update
`9/2/2009 1:46:42 PM`. Preserve those distinct dates. Columns explicitly give
MD in metres RKB, length in metres and Max OD/ID in inches.

| Visually verified device | MD top-bottom, m RKB | Length, m | Max OD, inches | ID, inches |
|---|---:|---:|---:|---:|
| 7-inch Baker TSM 7.5 safety valve | 508.470-511.000 | 2.530 | 9.190 | 5.875 |
| Granite packer 9 5/8-inch x 7-inch, size 831 x 600 | 2782.226-2783.766 | 1.540 | 8.310 | 6.000 |
| 7.50-inch sealstem, described as 15 ft | 2811.072-2814.492 | 3.420 | 7.500 | 6.039 |
| Baker Ratcheting Muleshoe | 2814.492-2815.982 | 1.490 | 7.450 | 5.994 |

The source also supplies tubing/casing intervals and part/serial identifiers.
The nominal 15-ft description is not the measured 3.420-m row length; maximum
OD is not a uniform body diameter. This is enough for source-backed dimensional
envelopes of these devices, not exact manufacturer mechanical detail or proof
that the same configuration remained installed at every later date.

### F-11 B: useful reserve, with a Plan-status caveat

The genuine final report is
`Well_logs_pr_WELL/15_9-F-11 B/14.DIV.REPORTS/COMPLETION_REPORT_3.PDF`,
64 pages; SHA-256
`359ddda1019e25e35eeb4bc16bc21f7f58ad6a12f30dc266d0ab975e9e978500`.
Pages 17-18, sections 4.7-4.8, record completion running on June 30-July 4, 2013
and packer setting/testing on July 4-6. Actual installation narrative therefore
exists. **However, the dimensioned table on PDF page 59 explicitly says
"Plan / Completion F-11 B IOR".** Its inclusion in a final report does not
silently convert every planned dimension and depth into an installed measurement.
The drawing is labelled page 1 of 2; the second tally sheet was not located here.

F-11 B also has an ACTUAL survey to 4770 m MD, dated 2013 interval-table rows and
later perforation operations. Those make it a credible reserve. Qualification
still needs exact installed-table corroboration, reference/history checks and
production identity mapping: the workbook uses `NO 15/9-F-11 H`, NPD code `7078`
and display label `15/9-F-11` in `Daily Production Data!B748:D748`.
Do not attribute that series to a sidetrack solely by its short display label.

**Owner decision after this inspection:** retain F-14/F-5 and select F-12 with
an explicit generic/unlocated equipment limitation. F-11 B remains a conditional
reserve, not a replacement. A complete installed F-12 tally is not a prerequisite
for this accepted presentation; supported component identity and placement are
still required for located geometry, and generic dimensions cannot enter
engineering calculations. Existing validated data remain usable while affected
claims/results are blocked.

### Perforation events exist for all three proposed targets

"History reconciliation" does **not** mean that no events are available.
The static table omits dates for all 16 pilot rows, but original daily reports
and service logs supply dated operations:

| Wellbore / effective date | Verified event evidence | Remaining distinction |
|---|---|---|
| F-12, February 11, 2008 | February 12 XML, activity 8, 13:30-15:00 +01:00, confirms TCP guns fired; report summary gives 3130-3281 m MDRT | Broad operation span is not one continuously perforated interval. Reconcile the five precise static intervals with the firing assembly |
| F-12, November 26, 2014 | November 27 XML, activity 7, sets an EVO plug at 3150 m; activities 17-18 position and activate guns; service-log page 1 reports 3126.2-3130.7 m | Report summary instead says 3126.2-3139.7 m. Preserve the conflict; two agreeing detailed sources support investigation, not silent overwrite |
| F-14, July 5-9, 2008 | Six explicit firing activities match all six static intervals exactly | Known initial physical union 73.2 m, not automatically flowing/open length at later dates |
| F-5, August 24-25, 2008 | Three firing activities match the three intervals in its Existing drawing | Physical union 45 m |
| F-5, October 16-17, 2008 | Two more perforation activities, 3619-3622 and 3605-3608 m | These explain why the static table has five intervals but the earlier drawing has three; combined physical union 51 m |
| F-5, April 19, 2016 | Two further activities, 3501-3510 and 3474-3492 m | Selected known physical union becomes 78 m; the five-row static table is not the complete later history |

Exact original XML locators below use **1-based activity ordinals**. Filenames are
under `Well_technical_data/Daily Drilling Report - XML Version/`; event dates
come from `dTimStart/dTimEnd`, not from the report filename.

| Wellbore | Report basename / activity | Observed MD interval, m |
|---|---|---:|
| F-14 | `15_9_F_14_2008_07_06.xml` / 9 | 3345-3354.2 |
| F-14 | `15_9_F_14_2008_07_07.xml` / 5 | 3312-3321.2 |
| F-14 | `15_9_F_14_2008_07_08.xml` / 15 | 3287-3296.2 |
| F-14 | `15_9_F_14_2008_07_09.xml` / 12 | 3044-3059.2 |
| F-14 | `15_9_F_14_2008_07_10.xml` / 5, 16 | 3021-3036.2; 3005-3020.2 |
| F-5 | `15_9_F_5_2008_08_25.xml` / 9 | 3704-3712 |
| F-5 | `15_9_F_5_2008_08_26.xml` / 2, 9 | 3682-3700.5; 3651.5-3670 |
| F-5 | `15_9_F_5_2008_10_17.xml` / 6 | 3619-3622 |
| F-5 | `15_9_F_5_2008_10_18.xml` / 3 | 3605-3608 |
| F-5 | `15_9_F_5_2016_04_20.xml` / 14, 30 | 3501-3510; 3474-3492 |

Remaining work is to establish a supported initial state and bounded historical
coverage, classify reservoir perforations versus tubing punches/abandonment
cuts, reconcile additions/overlap and plug/isolation/removal events, and align
MD/TVD/datum/revisions. Shut-in does not erase physical holes, and well-level
production/injection does not establish which interval flowed. For example,
F-14's 2016 shallow 144.5-147.5 m operation must not become reservoir-producing
footage. These checks are substantive, not just missing-date formatting.

The ignored `data/volve/source-audit/local-target-followup-audit.json` retains
source hashes, search coverage, 17 selected original activity observations,
static-table correspondence, exact-decimal union checks and the F-11 B survey
probe. The extracted F-5 image is retained alongside it. Earlier audit records
are preserved. No general OCR, application implementation, paid model call or
final G1/cohort acceptance is claimed.

## Attribution

Underlying Volve data: Equinor, ExxonMobil Exploration & Production Norway AS,
and Bayerngas Norge AS, under the
[Volve-specific terms](https://equinoropendata.blob.core.windows.net/disclaimers/HRS%20and%20Terms%20and%20conditions%20for%20license%20to%20data%20-%20Volve.pdf).
Sample mirrors: Alfonso Reyes / `f0nzie/volve-drilling`, and
`bengsoon/volve_daily_drilling_report` for the report conversion. This report selects,
summarizes and rounds source values; it does not alter the original files.
No endorsement is implied. Source terms are separate from any application code
license, and third-party rights still require review before broader publication.
