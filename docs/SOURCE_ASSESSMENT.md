# Conversation synthesis, validity assessment, and evidence gates

Reviewed 2026-10-26, America/New_York. No engineering dataset was downloaded or
validated and no paid API call was made. Public documentation was inspected;
account entitlements and authenticated event rules were not.

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
| [Equinor Volve](https://www.equinor.com/energy/volve-data-sharing) | Official collection description and current Databricks access link, using rendered page | Individual contents, full applicable license terms, account access |
| [Equinor Marketplace provider](https://marketplace.databricks.com/provider/006d1a44-e5d8-4d20-8bd7-e9a311106007/Equinor-ASA) | Destination linked by Equinor | Download/access workflow not exercised |
| [Community metadata index](https://github.com/985185/volve-metadata-index) | Listed in source conversation | Independent accuracy, completeness and currency not audited |
| [SODIR FactPages](https://factpages.sodir.no/) / [FactMaps](https://factmaps.sodir.no/map) | Official-source candidates identified in source conversation | Relevant records/layers not retrieved in this task |
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

Candidate identifiers from the source conversation: `15/9-F-1`, `15/9-F-1 B`,
`15/9-F-1 C`, `15/9-F-4`. These are leads, not a selected or validated demo set.
Favor compatible records over those exact names. Sidetracks and well-level
production must not be conflated.

| Required evidence | Candidate category | Audit questions |
|---|---|---|
| Well locations and trajectories | EDM export, directional-survey tables, relevant WITSML records | Same wellbore/revision? MD/INC/AZI or documented positions? CRS, north reference, vertical/depth datum? |
| Installed components | Completion reports, schematics, well-technical exports | Model/revision, dimensions, units, intervals, dates, installation context? |
| Catalog specifications | Manufacturer datasheets identified from actual model names | Exact product match? Authoritative source? Terms permit use? No invented installed state? |
| Terrain/bathymetry | Relevant geospatial surfaces/grids | Geographic coverage, horizontal/vertical references, resolution and source rights? |
| Reservoir/formations | Geological picks, interpreted surfaces, reservoir boundaries/grids | What is measured versus interpreted? Enough metadata to align with wells? Required importer? |
| Production series | Owner's existing production data; Volve production files | Rates/volumes, units, dates/timezone, missingness, well versus wellbore association? |
| Well-log curves | LAS/DLIS or another documented export | Depth basis, null sentinels, mnemonics/units, intervals, wellbore identity? |

A location point layer does not replace a downhole survey. Production data alone
does not reconstruct well paths. Norne simulation inputs, mentioned in the source
conversation, do not automatically replace missing Volve documentation and must
not be mixed into a supposedly measured Volve scene.

**Smallest useful next sample:** one directional survey with coordinate/depth
metadata, one completion/equipment document, one production file, one log file,
and source candidates for terrain and reservoir/formations. Inspect jointly, then
expand to the related wellbores needed for cross-well questions. Do not bulk-fetch
the whole collection.

The audit must record a manifest with file hash, origin/license, format/version,
canonical IDs, references/units, locator strategy, expected facts, conflicts,
chosen configuration dates and missing coverage. The owner provides file paths
or authorizes selective acquisition; none are assumed here.

## 6. What must be verified before architecture

1. **Data:** approve the exact subset and the minimum truthful representation of
   every mandatory contextual layer. Set coordinate tolerances from the actual
   source precision, not an arbitrary universal accuracy promise.
2. **Reconstruction:** independently check at least one real trajectory; establish
   golden fixtures for survey interpolation, closest approach and equipment placement.
3. **Extraction:** run a representative document through a candidate parser and
   Meta extraction; compare claimed values and source locators with human-checked facts.
4. **API/cost:** with authorization, perform a bounded Meta smoke test covering
   text, image/PDF if needed, structured extraction, tool round-trip and streaming.
   Confirm remaining credit and cost accounting, without exposing credentials.
5. **Retrieval:** construct answerable and unanswerable questions with expected
   sources/tool results; test exact identifiers as well as semantic matching.
6. **Rules/rights:** obtain authenticated submission requirements and verify
   dataset/catalog processing and redistribution rights before external transmission
   or publication. Public-source availability is not blanket training permission.

These gates are requirements for the next feature specs, not tests already run.
