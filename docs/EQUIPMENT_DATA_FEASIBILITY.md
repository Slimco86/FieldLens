# Equipment data: real dimensions found; installed completion still unverified

Reviewed 2026-10-27 after the owner identified equipment data as a project-critical
concern. **Verdict: promising but not a completed feasibility gate.** We have
inspected real-format equipment records from a public Volve mirror. We have not
yet verified a coherent, date-specific installed completion for the chosen pilot.

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
| Daily drilling/workover reports | Operations, installation/removal context, configuration dates and narrative evidence | Candidate dates alone do not establish event history |
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
The three public mirror probes let us examine fields, but do not resolve pilot
completion/perforation coverage or this official-access problem.

### Documented, non-destructive diagnostic handoff

[Databricks recipient documentation](https://docs.databricks.com/aws/en/opensharing/read-data-databricks)
separates provider inspection (`USE PROVIDER` or provider ownership) from reading
a shared volume. Consequently, the provider-details 403 does not prove that
ordinary file access requires provider ownership, nor identify the cause of the
missing schema.

A privileged catalog owner/provider needs to verify:

1. The published share still contains the advertised `public.volve` volume and
   the catalog is mounted from that share.
2. The recipient's catalog/schema/volume read privileges cover those objects.
3. The intended files are visible before any compute, export or parser is run.

Do not prescribe an account upgrade, LinkedIn verification, catalog deletion or
reinstallation as a proven fix. The inspected Free Edition documentation does
not establish that one of these resolves this missing-schema failure.

## 7. Alternative-report search and final assessment

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

**Assessment complete; project equipment feasibility remains conditional.**
Available public source records demonstrate dimensional tubular/component data,
and the official inventory identifies richer engineering/completion sources.
The inspected samples do not demonstrate a complete installed pilot assembly,
and additional reports mislabeled by downstream tooling cannot supply that proof.
The next decisive input is actual pilot completion documentation, obtained through
restored share visibility or an authorized local copy. No further autonomous
permission change, paid service or invented geometry is justified by this search.

## Attribution

Underlying Volve data: Equinor, ExxonMobil Exploration & Production Norway AS,
and Bayerngas Norge AS, under the
[Volve-specific terms](https://equinoropendata.blob.core.windows.net/disclaimers/HRS%20and%20Terms%20and%20conditions%20for%20license%20to%20data%20-%20Volve.pdf).
Sample mirror: Alfonso Reyes / `f0nzie/volve-drilling`. This report selects,
summarizes and rounds source values; it does not alter the original files.
No endorsement is implied. Source terms are separate from any application code
license, and third-party rights still require review before broader publication.
