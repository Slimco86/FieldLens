# Conversation synthesis, validity assessment, and evidence gates

Reviewed 2026-10-26, America/New_York. No engineering dataset was downloaded or
validated and no paid API call was made. Public documentation was inspected;
account entitlements and authenticated event rules were not.
Updated 2026-10-27: historical perforation terminology, official access/license
documents, public wellbore records and a metadata-only catalog were inspected.
Later follow-ups acquired three small mirrored F-4/F-7 WITSML files, a production
workbook and a converted corpus of 1,759 daily reports. Selected narratives now
establish source-reported production-completion and perforation operations, but
not a complete dimensioned pilot assembly or historical coverage. Official
candidate files remain unacquired. See the
[data-discovery findings and access handoff](VOLVE_DATA_DISCOVERY.md).
Four additional mirrored F-5 trajectory sections now preserve explicit units,
but overlap/reference/position validation remains open. Read-only access diagnosis
also found the listing's 90-day policy and the older May 27 installation; an
authorized refresh is a recovery candidate, not a completed fix.

**Latest checkpoint:** the owner has now supplied an official local download.
The earlier access failures above are historical. All 33 pilot candidate files
are present within a 33,678-file inventory. Actual source surveys, interpreted
depth horizons, seabed, production, logs and selected original event reports
were inspected. Important report-attribution, time/depth-domain and historical
coverage limitations are documented in the
[local content audit](VOLVE_DATA_DISCOVERY.md#8-owner-supplied-local-data-content-audit).
Seismic and the geoscience archive are not required for the existing interpreted
depth-layer scope; file availability is not a passed engineering manifest.

## 1. Source and precedence

Primary design source:
[Hackathon Idea Selection conversation](https://chatgpt.com/share/6ae00399-28c4-83e9-b646-84ead55a2dfd).
The supplied private conversation URL exposed only a login page. The shared
version contained an initial recommendation, the user's proposal request, the
proposal, the user's research request, and a data/tool inventory.

The conversation establishes a useful concept, not verified implementation facts.
Its claims about novelty, automatic reconstruction and technical feasibility are
proposals, not benchmarks, market research or evidence of complete source coverage.

**Precedence:** the owner's subsequent clarifications in this session supersede
earlier assistant suggestions:

- Uploading data must actually generate the model; well count is not the objective.
- Terrain/bathymetry, reservoir/formation context, production and well logs are
  required, not optional extensions.
- Equipment can use cited catalog research or an explicitly generic fallback.
- PostgreSQL + pgvector + typed relationship tables are the agreed knowledge layer,
  superseding an intermediate SQLite recommendation.
- Work must be iterative and spec-driven. A manual adjudication interface is deferred;
  reliable validation and truthful uncertainty handling are not.
- Historical perforations require MD/TVD placement, total perforated length,
  reperforation and separate production/injection/shut-in/access state. See the
  [draft feature contract](specs/PERFORATION_HISTORY.md) for proposed semantics.
- Development uses orchestrated parallel feature worktrees and versioned integration;
  this does not add a multi-agent framework to the runtime application.
- The owner initially had no prepared dataset and chose joint sample inspection
  before final architecture; an official local download is now available.
  Indie track, public repository, three-minute recorded
  demo, and local WSL/container runtime are owner-confirmed requirements.
- A Meta key is ready locally and processing public data is authorized, subject
  to source/provider terms; entitlement, balance and protocol behavior are untested.

## 2. Most important ideas worth retaining

1. **One connected engineering model:** field, wellbore, component, chart, source
   and agent action refer to the same stable identities.
2. **AI plus deterministic reconstruction:** probabilistic interpretation proposes
   structured claims; validated numeric tools construct trajectories and assets.
3. **Evidence is a product feature:** users can move from a spatial object or answer
   to the record supporting it.
4. **Cross-well investigation:** nearest approach and completion comparison are
   meaningful without claiming reservoir connectivity.
5. **Small real dataset, general workflow:** curate the demonstration without
   hard-coding the application to chosen well names or a fixed number of paths.
6. **Broader infrastructure vision:** other fields, plants and utilities may follow;
   no generic multi-industry framework is required before the Volve demonstration.

## 3. Technical and logical validity

| Conversation / requirement | Assessment | Required treatment |
|---|---|---|
| Volve is a credible primary source | Supported at collection level: Equinor describes about 40,000 files and 2008-2016 production history | Specific compatible files still require inspection |
| 3-5 wells make an achievable demo | Plausible presentation scale, not proof of effort or data completeness | Prioritize complete source coverage; do not impose a five-well product cap |
| Technical equipment data is essential to the value proposition | F-14 and F-5 drawings supply device dimensions/MD. Owner selected F-12/F-14/F-5 and accepted an explicit generic F-12 limitation | Apply DF-9 to a real installed assembly; validate references/history and expose source-linked warnings. Missing F-12 dimensions never become measurements |
| PDF/diagram understanding can reconstruct all equipment | Overstated without dimensions, view conventions and installed-state evidence | Supported parametric geometry plus catalog/generic fallback; no universal inverse-CAD claim |
| Meta Muse provides multimodal and agent tools | Supported by current public Meta docs, not a fabricated model family | Verify account entitlement and actual extraction/tool behavior |
| Structured output guarantees reliable data | It constrains shape, not engineering correctness | Domain validation, evidence locators, deterministic checks |
| welleng can accelerate trajectory/WITSML/EDM work | Maintainer documents minimum curvature, EDM and a WITSML 1.4.1.1 log/tubular reader tested on Volve exports | Reader coverage is not every WITSML object/version; test selected installed release against actual files |
| Docling solves engineering document ingestion | Good parser candidate; documented layout/OCR support | OCR errors, model weights, memory, table associations and diagrams still need evaluation |
| React/Python/Node are adequate | Credible for a small interactive scene; no inherent need for a Node API | Actual bottlenecks are parsing, provider latency, payloads, geometry size and database work; benchmark |
| WebGPU or CAD kernels are essential | Not established for this workload | Stable WebGL2 and procedural geometry first |
| Agentic RAG requires multiple databases | Logical graph and vector capabilities are useful; separate engines are not intrinsically necessary | Agreed PostgreSQL/pgvector/typed-edges baseline |
| Formation tops imply a reservoir volume | Not logically valid | Distinguish observed picks, interpreted surfaces and actual grid/boundary data |
| Well proximity indicates connection or collision risk | Unsupported without additional geology/uncertainty/engineering analysis | Label as geometric centerline proximity only |
| Generic equipment preserves a useful UX | Valid when transparently represented | Mark missing dimensions/identity/placement and exclude display defaults from calculations |
| Public data/skills are automatically reusable | False | Review actual data, code, model-weight and asset terms separately |
| Full scope fits the remaining hackathon time | Not yet established | Mandatory data/API gates; no promise before evidence |

The expanded scope is materially more demanding than the conversation's original
trajectory/completion-focused MVP. This is a real schedule risk even with AI
coding assistance. Richer requirements do not reduce the time needed to obtain
compatible measurements or validate engineering semantics.

## 4. Source inventory and verification limits

| Source | What was verified | What was not |
|---|---|---|
| [Equinor Volve](https://www.equinor.com/energy/volve-data-sharing) | Official access/license documents and the owner's local download inspected; all 33 candidates present; selected engineering contents and hashes checked | Full-cohort reference/history qualification, uninspected documents and publication rights remain open |
| [Volve Marketplace listing](https://marketplace.databricks.com/details/5c3558ef-315c-44dd-baef-7062ac301f22/Equinor-ASA_Volve-Data-Village) | Free listing, sign-in access guide, source/license links | Authenticated acquisition/export and any workspace/compute cost |
| [Community metadata index](https://github.com/985185/volve-metadata-index) | v1.0 CSV hash verified; exact candidate paths, counts and identity anomalies inspected | Independent accuracy, completeness, freshness and original-file bytes |
| [Original conversation's detailed inventory](https://github.com/gabrielserrao/spe-2026-challenge/blob/main/DATA_SOURCES.md) | Documents EDT/EDM assembly/casing tags and WITSML object families; official license also identifies EDT exports | Actual large EDM bytes/schema semantics and installed-versus-designed configuration; old direct-download URL now redirects |
| [Public WITSML sample mirror](https://github.com/f0nzie/volve-drilling/tree/3698c43d4adc0ee11ffa8fd5f876fa961c9c846d) | Three pinned files, 8 component and 4 geometry records, sizes/hashes/metric fields inspected | Current official-byte equivalence, pilot coverage, installation dates, depth datum and complete device geometry |
| [Production workbook mirror](https://github.com/f0nzie/volve_eclipse_reservoir/tree/0d34eaf1be7003a6c251dea938de3e3738501d71/inst/rawdata) | Pinned 2,344,094-byte XLSX acquired; blob/SHA-256 and daily/monthly structure checked; 15,634 daily rows | Official equality, units, identity/quantity semantics and interval-scoped flow |
| [Daily-report conversion](https://huggingface.co/datasets/bengsoon/volve_daily_drilling_report/tree/f0cbe11bfebb23f007b57a52cb903d9075db777c) | Pinned 2,180,278-byte Parquet acquired; LFS hash, 1,759 unique reports and selected completion/perforation narratives inspected | Original XML fidelity, numeric unit/datum attributes, complete installed geometry/history; header wellbore can differ from the activity subject |
| [PetroRAG](https://github.com/yohanesnuwara/PetroRAG/tree/ac4f27ef4e1683e9b79c661cf50451dff2b00fd9) | Secondary extract's "Completion Report" label conflicts with its F-15-family drilling-report header | Original PDFs absent; no installed-completion proof from the label or chunks |
| [SODIR FactPages](https://factpages.sodir.no/) / [FactMaps](https://factmaps.sodir.no/map) | Volve field and F-12 references; F-5 injection and base F-11 observation purpose | Full trajectories, dated interval state, spatial-layer downloads |
| [Public event page](https://cerebralvalley.ai/e/meta-ai-developer-hackathon) | Nov 4, 9 PM ET deadline; Meta model families; tracks/themes | Full contest rules and required final artifacts |
| [Event details/rules entry](https://cerebralvalley.ai/e/meta-ai-developer-hackathon/details) | Access redirects to login | Authenticated content not inspected |
| [Meta overview/models](https://dev.meta.ai/docs/models) | Muse Spark/Wonder multimodal inputs and documented API availability | This team's permitted models, credit balance, limits or successful calls |
| [Meta pricing](https://dev.meta.ai/docs/pricing-rate-limits) | Standard/Contributor distinction and published token/search pricing | Hackathon-specific billing exceptions or actual remaining credit |
| [welleng](https://github.com/jonnymaserati/welleng) | Maintainer feature descriptions, Apache-2.0 badge, Volve reader claim | Independent numerical certification or installed-release compatibility |
| [Docling](https://github.com/docling-project/docling) | Supported-format/OCR claims; MIT project badge; current Python >=3.10 guidance | Selected model-weight licenses, sample accuracy, runtime footprint |

The research inventory also lists many alternative skills and libraries. This
document does not certify that catalog or instruct agents to install it. Coding
skills are development instructions, not runtime engineering capabilities.
PyMuPDF and any other copyleft/commercially dual-licensed components require an
explicit license check before adoption; they are not baseline dependencies.

## 5. Joint data audit: choose files by evidence coverage

The owner selected **F-12/F-14/F-5** on October 28 after
[local source inspection](VOLVE_DATA_DISCOVERY.md). F-12's generic equipment
limitation and visible discrepancies are accepted; F-11 B is not an automatic
replacement. This settles cohort choice, not the final hashed manifest or
reference/history qualification. Do not conflate sidetracks or invent placement.

| Required evidence | Candidate category | Audit questions |
|---|---|---|
| Well locations and trajectories | EDM export, directional-survey tables, relevant WITSML records | Same wellbore/revision? MD/INC/AZI or documented positions? CRS, north reference, vertical/depth datum? |
| Installed components | Completion reports, schematics, EDT/EDM exports, WITSML tubular/run/geometry records | Model/revision, dimensions, units, intervals, dates, installation context? Explicitly distinguish drilling assemblies, planned designs and permanent completion |
| Historical perforations and state | Perforation/reperforation reports, completion/workover histories, dated well/interval status records | Event effective date versus report date? MD/TVD endpoints/references? Scope of shut-off? Production/injection evidence? Footage meaning, overlaps, initial coverage and corrections? |
| Catalog specifications | Manufacturer datasheets identified from actual model names | Exact product match? Authoritative source? Terms permit use? No invented installed state? |
| Terrain/bathymetry | Relevant geospatial surfaces/grids | Geographic coverage, horizontal/vertical references, resolution and source rights? |
| Reservoir/formations | Geological picks, interpreted surfaces, reservoir boundaries/grids | What is measured versus interpreted? Enough metadata to align with wells? Required importer? |
| Production series | Official Volve production workbook candidate; owner has no prepared data | Rates/volumes, units, dates/timezone, missingness, well versus wellbore association? |
| Well-log curves | LAS/DLIS or another documented export | Depth basis, null sentinels, mnemonics/units, intervals, wellbore identity? |

A location point layer does not replace a downhole survey. Production data alone
does not reconstruct well paths. Norne simulation inputs, mentioned in the source
conversation, do not automatically replace missing Volve documentation and must
not be mixed into a supposedly measured Volve scene.

**Smallest useful next sample:** one directional survey with coordinate/depth
metadata, one completion/equipment document, one production file, one log file,
perforation/state history for the same wellbore, and source candidates for terrain
and reservoir/formations. Inspect jointly, then
expand to the related wellbores needed for cross-well questions. Do not bulk-fetch
the whole collection.

The [draft feasibility spec](specs/DATA_FEASIBILITY.md) defines the audit.
It must record a manifest with file hash, origin/license, format/version,
canonical IDs, references/units, locator strategy, expected facts, conflicts,
chosen configuration dates and missing coverage. The owner provides file paths
or completes official access using the existing account confirmed by the owner.
The candidate list is metadata-only. The subsequent owner-supplied local download
resolves the earlier catalog/access problem; all 33 candidates are present.
The cohort and 128/512 MiB / 200-file upload bounds are now approved, but the
final source/profile/window manifest and publication rights remain G1 work.

The [equipment feasibility report](EQUIPMENT_DATA_FEASIBILITY.md) reassesses the
additional original sources and records actual sample attributes. SODIR helps
with identity/geospatial cross-checks; OPM/Norne is a separate simulation benchmark,
not a substitute source of Volve installed hardware.

## 6. What must be verified before affected implementation and acceptance

The [architecture](ARCHITECTURE.md) and [feature contracts](specs/README.md)
are now defined from the inspected evidence. The following remain execution/
acceptance gates; they no longer prevent source-independent design or foundation
work after approval.

1. **Data:** approve the exact subset and the minimum truthful representation of
   every mandatory contextual layer. Set coordinate tolerances from the actual
   source precision, not an arbitrary universal accuracy promise.
2. **Reconstruction:** independently check at least one real trajectory; establish
   golden fixtures for survey interpolation, closest approach, equipment placement
   and as-of perforation state/unique MD length, including overlap and reperforation.
3. **Extraction:** run representative documents through selected native readers;
   compare values/locators with human-checked facts. OCR or paid Meta extraction
   needs a demonstrated gap and its own approval, not automatic activation.
4. **API/cost:** with authorization, perform a bounded Meta smoke test covering
   text and the selected tool round-trip/replay behavior. Add image/PDF, structured
   extraction or streaming tests only when an approved feature uses them.
   Confirm remaining credit and cost accounting, without exposing credentials.
5. **Retrieval:** construct answerable and unanswerable questions with expected
   sources/tool results; test exact identifiers as well as semantic matching.
6. **Rules/rights:** obtain authenticated submission requirements and verify
   dataset/catalog processing and redistribution rights before external transmission
   or publication. Public-source availability is not blanket training permission.

These gates are represented in the completed feature specs, not tests already run.

## 7. Perforation terminology follow-up

Checked on 2026-10-27 against SLB's public glossary:
[perforated interval](https://glossary.slb.com/en/terms/p/perforated_interval),
[measured depth](https://glossary.slb.com/en/terms/m/measured_depth) and
[perforation density](https://glossary.slb.com/en/terms/p/perforation_density).
The first is an along-wellbore section; multiple sections can have unperforated
gaps. Density is shots per unit length, not completion length.

Recommended FieldLens label: **total perforated length (MD)** / **perforated
footage** in feet, explicitly defined as unique interval coverage. Track open
coverage separately. This exact aggregate is a proposed project definition, not a
universal definition of every source's "completion footage" field. Avoid "horizontal
depth": horizontal displacement and vertical thickness do not equal along-hole
length. A repeated perforation operation can alter coverage or other properties;
repeating the same interval does not inherently add unique perforated length.
