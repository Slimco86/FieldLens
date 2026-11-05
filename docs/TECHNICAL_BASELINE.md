# Technical baseline and engineering conventions

Date: 2026-10-26, America/New_York. Updated 2026-10-28 with the revised
[application architecture](ARCHITECTURE.md) and
implementation sequence (archived in git history).
Core stack families are retained. Project/reconstruction workflow defaults were
confirmed by the owner on October 28; package resolution, host qualification and performance remain
unverified execution gates.

## 1. Prefer a small system with explicit responsibilities

Use one Python application package for API, ingestion coordination, engineering
tools and agent integration; one React frontend; and PostgreSQL. Run one separate
bounded worker process for CPU-heavy parsing/geometry/indexing, backed by a
PostgreSQL job queue. No broker or independently deployed microservice is selected.
Production frontend files are served by FastAPI; Compose supplies the local DB.

Node is needed to build/develop the frontend, not to duplicate Python endpoints.
The renderer consumes derived geometry; it does not own engineering facts.
Application tools, not the model, control calculations and allowable scene actions.
The product boundary is a project, with separate immutable source and asset-model
revisions. The application agent reconstructs composite entities and relationships;
retrieval, charts and rendering serve that model rather than defining it.

## 2. Stack decisions

| Area | Selected design baseline | Rationale / qualification gate |
|---|---|---|
| Python | 3.12 via uv; project virtual environment | Already installed; conservative scientific-package compatibility |
| API and contracts | FastAPI + Pydantic | Typed boundaries, OpenAPI; generate frontend API types from the contract |
| Engineering | NumPy, pyproj, welleng behind tested adapters | Deterministic numeric/CRS handling; verify exact reader APIs and source format versions |
| Structured ingestion | Standard CSV, openpyxl, lasio and defusedxml; versioned source profiles | Preserve typed values, units and locators; no mandatory pandas for small streaming inputs |
| PDF/OCR | pypdf/pdfplumber for native text/tables; Docling first conditional OCR candidate | Account for every page; accuracy, memory and model licenses gate OCR activation |
| CAD/asset inputs | Format-specific import or deterministic procedural mesh generation | Do not promise arbitrary CAD-to-3D reconstruction; select needed formats at G1 |
| Offline equipment authoring | Optional Blender 4.5 LTS candidate plus bundled glTF exporter | Skill/workflow approved; exact build, installation and asset creation deferred. Not a runtime dependency |
| Frontend | React 19 + strict TypeScript + Vite 8; TanStack Query and a selection reducer | Server-state caching and one shared selection; no SSR requirement |
| 3D | Three.js + React Three Fiber 9; Drei helpers as needed; WebGL2 | Paired peer-compatible patches resolved at foundation; no alpha/WebGPU dependency |
| Charts and evidence | Apache ECharts; PDF.js | Production/log series and source-document inspection; load heavy viewers on demand |
| Persistence | PostgreSQL 17 + pgvector 0.8 families; SQLAlchemy 2, psycopg 3, Alembic | One relational and retrieval store; pin compatible patch/image digest at setup |
| Knowledge graph | Typed entity/relationship/claim records in PostgreSQL | Graph semantics with foreign keys and provenance; bounded SQL traversal initially |
| Embeddings | FastEmbed with BAAI/bge-small-en-v1.5, 384 dimensions, CPU candidate | Pin model revision/license/preprocessing and pass recall/RSS gate; no assumed Meta embeddings API |
| Agent | Meta-compatible Python SDK transport, custom persistent harness and Pydantic tools | Reconstruction and exploration modes share run state, budget/recovery and retrieval; SDK alone is not the agent. Pydantic AI/LangGraph only for demonstrated complexity |
| Frontend tooling | Supported Node 24 LTS patch, npm and a committed lockfile | Installed Node 20 is EOL and below current Vite's minimum |
| Tests | pytest, Ruff, mypy; TypeScript/ESLint, Vitest, Playwright | Foundation creates actual commands; live Meta tests are explicit opt-in |
| Local services | Docker Compose for PostgreSQL/pgvector | Current daemon/Compose readiness is unverified; recheck after owner startup. Full app containers remain optional |

Freeze compatible stable versions in manifests and lockfiles after resolution.
Do not use floating `latest` images or install whole research inventories.
No dependency manifests or runnable test commands exist yet.

Registry check on 2026-10-27: React 19.3.1, R3F 9.8.2 and Vite 8.3.5.
R3F advertises React `>=19 <19.4`; Vite requires Node
`^20.19.0 || >=22.12.0`. These support the selected Node 24/React 19 baseline,
but are not a substitute for a resolved lockfile, typecheck and build.

## 3. Why one database can support three needs

Relational storage, vector retrieval and knowledge graphs are capabilities, not
an automatic requirement for three database products.

- **Relational:** wells/wellbores, component instances, survey revisions, source
  documents, extraction jobs, series metadata, dated perforation/state events,
  claims and provenance, project memberships, reconstruction proposals/reviews and
  model publications. Effective event time is distinct from report/import time.
- **Vector/full-text:** passages and catalog excerpts with document/asset filters.
  Exact IDs/model numbers must remain searchable even if embeddings miss them.
- **Graph:** typed edges such as `well_has_wellbore`, `sidetrack_of`,
  `component_installed_in`, `instance_of_catalog_model`, `claim_supported_by`,
  `series_for_asset`, and `intersects_formation`. Store origin, validity/revision
  and validation state, rather than treating every LLM-proposed edge as true.

Use explicit tables/foreign keys for core domain facts; avoid a universal
entity-attribute-value schema. A typed relationship table can express additional
traversals without erasing the core schema. Distinguish catalog models from
installed component instances.
Scope all reads/writes/tools by project and the appropriate source/model revision.
Source search must work before entity resolution; uncertain extracted observations
remain distinguishable from accepted model facts. Filenames/categories are hints.

The [reconstruction spec](specs/ASSET_RECONSTRUCTION.md) defines persistent runs,
typed candidate writes, semantic-support validation and proposed user publication.
One orchestrator/tool registry is enough initially; do not install a runtime agent
framework merely to relabel an SDK call as agentic.

Implement filtered full-text + vector retrieval with bounded, evidence-returning
graph expansion. Start with exact vector search for a small corpus; add HNSW only
after measuring retrieval latency/recall. Approximate search can lose filtered
results, so test it on well-specific queries. Pin embedding model revision,
dimension, distance metric and preprocessing; changed models require reindexing.

FastEmbed is an embedding library, not a requirement to deploy Qdrant. A dedicated
graph engine becomes a new decision only when representative traversal complexity,
performance, or graph algorithms cannot be handled clearly in PostgreSQL.
PostGIS likewise needs a demonstrated query requirement; pyproj/NumPy can serve
the initial coordinate and 3D trajectory calculations.

## 4. Data and geometry invariants

Preserve an immutable original document plus content hash. Every normalized
engineering property has source locators, original and normalized units, asset ID,
configuration/date, method/version and validation state. Derived objects reference
their input revision. Search indexes and meshes are rebuildable projections.

Keep evidence class (`source-measured`, `catalog-derived`, `interpolated`,
`generic`) separate from validation state. A reviewed catalog fact is still not
an as-built measurement. Unknown is not zero. Null log values, shut-in production
and zero production are not interchangeable.

Trajectory requirements:

- Strictly validate MD order, finite angles, units, station identity and survey
  revision; resolve duplicate stations explicitly.
- Record north reference (true/grid/magnetic), CRS, vertical datum, rig/wellhead
  reference and offsets. An EPSG code alone does not resolve vertical depth.
- Use validated minimum-curvature reconstruction/interpolation. Reproduce
  documented coordinates within source-specific tolerances set before coding.
- Transform to a common physical frame before comparisons. Preserve double
  precision; subtract a documented local origin for browser coordinates and
  explicitly map axes/signs into the renderer.
- Compute nearest approach on properly resolved curves or segment geometry,
  including measured depths on both paths. A nearest pair of sparse stations is
  not necessarily the closest approach. Include branches/shared segments in tests.
- Never let display simplification, enlarged equipment radii or vertical
  exaggeration affect physical calculations.

Equipment can be generated from supported parametric shapes along validated
trajectories. Drawings inform parameters; the runtime agent does not emit executable
geometry code. A general photograph/drawing is not sufficient to recover unique
dimensions. Unknown-position equipment can appear in an unlocated inspection
panel instead of being assigned a fabricated location.

For complex reusable equipment, the development 3D worker can follow the
[Blender skill](../.github/skills/fieldlens-blender-assets/SKILL.md) in an approved
offline asset slice. Keep editable source/reviewed bpy recipes separate from GLB
exports and authoritative engineering claims. Use Blender's bundled interpreter,
not the backend environment. Record exact build/export settings and validate
units/axes/pivot/IDs, permitted resources and browser budgets before acceptance.
No Blender executable was found on WSL PATH during preparation; setup and real
export/consumer tests remain deferred, not satisfied by these instructions.

For offshore Volve, surface context may be seabed/bathymetry, not land terrain.
Formation picks do not establish a measured continuous surface or reservoir
volume. The selected representation is source-interpreted depth horizons plus
well formation picks, with explicit interpolation/coverage and no inferred closed
reservoir volume. G1 must validate that the real sources support this
[context-layer contract](specs/CONTEXT_LAYERS.md); notices alone do not pass.

Charts preserve date/timezone, depth reference, curve mnemonic and units. Distinguish
rates from daily volumes and cumulative production. Link well-level production to
the correct entity; do not arbitrarily assign it to one of several sidetracks.

### Historical perforations and completion footage

Follow the [perforation-history draft](specs/PERFORATION_HISTORY.md) and approve
its source mappings before implementation. Preserve perforation/reperforation
events rather than storing only the latest completion snapshot.

- Store event effective time/precision, source/report time, wellbore and affected
  interval identities, original event meaning, evidence and dataset revision.
  Date-only events do not imply an exact midnight operation or same-day ordering.
- Preserve recorded MD/TVD endpoints with units/depth references; derive missing
  coordinates only through a validated survey and record the derivation. TVD-to-MD
  inversion can be non-unique; never pick a crossing silently.
- Separate physical perforated coverage, interval access state and evidenced
  producing/injecting/shut-in status. Well-level flow does not establish interval
  flow, and whole-well shut-in does not erase or necessarily isolate perforations.
- Name the aggregate **total perforated length (MD)**, also **perforated footage**
  when expressed in feet. Normalize and union intervals before summing lengths;
  exclude gaps/overlaps. Track **open perforated length** separately. Reperforating
  existing coverage is a distinct event but not automatically additional length.
- Preserve ambiguous source "completion footage" as reported until its meaning
  is validated. Horizontal displacement, TVD span, lateral completion length,
  shot density and tunnel penetration are not interchangeable with perforated MD length.
- Return as-of state under an explicit dataset revision; key caches, retrieval
  and viewer actions by asset/time/precision/revision. Preserve acquisition dates
  for logs/series and show partial/unknown history instead of zero-filling.

## 5. Meta integration, external research, and cost

Public [Meta documentation](https://dev.meta.ai/docs/overview) confirms base URL
`https://api.meta.ai/v1` and Muse Spark models. Initial candidate:
`muse-spark-1.3` in **Standard** mode, subject to account entitlement.
On 2026-10-27 the owner confirmed a local API key and permission to process public
data using an appropriate model. Key contents were not read; no entitlement,
balance or live-protocol test has run. Source/provider terms still apply.

[Responses](https://dev.meta.ai/docs/protocols) is the documented default for new
agent workflows. Use typed tools, explicit call/result IDs and supported replay
semantics. Keep reasoning replay opaque; it is not user-facing engineering evidence.
Prefer explicit stateless handling where supported rather than accidental remote
history retention. Check extraction schema support on the selected protocol;
the public structured-output example uses Chat Completions, so do not copy its
fields blindly into Responses.

Meta documents image/PDF input, tool calling and structured output. Schema
conformance does not verify measurements. The
[PDF limits](https://dev.meta.ai/docs/file-handling) are especially important:
currently the first 100 pages contribute text and only the first 50 page images
are retained. Split/select pages deliberately and preserve original locators;
never mark a long document fully processed after a truncated request.

For model-only equipment references, search by public manufacturer/model/revision,
prefer manufacturer datasheets, and preserve URL, access date, matching evidence,
license and catalog provenance. Search snippets alone are not authoritative
specifications. On ambiguity or failure, retain a generic/missing-data state.
Do not send private document excerpts or identifiers to web search.

Budget snapshot from [Meta pricing](https://dev.meta.ai/docs/pricing-rate-limits):

| Muse Spark Standard usage | Published price on review date |
|---|---|
| Uncached input | USD 1.25 / million tokens |
| Cached input | USD 0.15 / million tokens |
| Output | USD 4.25 / million tokens |
| Web search | USD 2.50 / 1,000 queries, plus token costs |

For illustration, 10,000 uncached input + 2,000 billed output tokens cost
approximately USD 0.021 before search/retries; this is not a measured per-user-query
cost. Count every tool-loop turn, retry, and billed reasoning/output token.

**Proposed spending guardrail, requiring owner confirmation at G2:** warn at USD
100 consumed; pause unattended experimentation at USD 120 and retain USD 30 for
evaluation/demo. Enforce remaining-budget checks before new requests with a
bounded output/call allowance, reserve for concurrent in-flight requests, and
reconcile with the provider balance. Local estimates cannot guarantee the
team-wide balance when other tools/keys also spend credit.

Contributor mode permits Meta to use submitted content for training; it is not
an interchangeable discount toggle. No such permission is assumed. Keep ordinary
tests offline with deterministic stubs; make paid smoke/evaluation runs opt-in.

## 6. Reliability and operational conventions

Use async I/O for provider/database calls; keep CPU-heavy OCR/parsing/geometry
out of the event loop. Limit parser workers, document pages, upload bytes, job
concurrency, tool steps and total request duration in feature specs.

Persist job state and input/output revisions. Make transitions explicit
(`queued`, `running`, `succeeded`, `failed`, `cancelled`, and any required partial
state); detect interrupted jobs on restart. Commit accepted normalized data
transactionally. A failed refresh must not relabel old results as newly verified.

Use bounded retries with backoff and retry-after handling only for transient,
retryable operations. Show user-visible errors; log request/job IDs, stage,
duration and sanitized diagnostics. Avoid raw prompts/documents in ordinary logs.
Define deterministic tool contracts for selection, highlight, chart and source
navigation; UI acknowledgment must distinguish issued actions from completed ones.

Bind local services to loopback by default. Keep API keys backend-only. Validate
uploads and extracted archives, disable XML external entities, constrain paths,
sanitize rendered Markdown, and prevent arbitrary URL fetching by model tools.
Use database migrations, parameterized queries, least-privilege application access,
and fixtures against real PostgreSQL/pgvector behavior.

Reuse Three.js materials/geometries, dispose resources, use stable object IDs, and
avoid per-frame React updates. Paginate large record lists; stream/batch numeric
arrays; keep original chart values for tool calculations despite display decimation.

## 7. Observed WSL environment

Initial read-only checks on 2026-10-26, refreshed where noted on 2026-10-27.
These are observed tools, not installed project dependencies or performance
certification.

| Resource | Observation | Consequence |
|---|---|---|
| OS | Ubuntu 20.04.6 under WSL2 | Check native wheel/glibc compatibility; do not assume an OS upgrade |
| Default Python | Conda 3.9.23; system Python 3.8.10 | Neither is the project runtime |
| Managed Python | uv-installed 3.12.13 and 3.13.12 | Select 3.12 explicitly |
| uv | 0.11.20 | Available |
| Node / npm | 20.11.1 / 10.2.4; no alternate Node found in inspected common locations | Provision supported Node 24 at setup, not an obsolete Vite workaround |
| CPU / WSL memory | 20 logical CPUs; 7.6 GiB RAM, 2 GiB swap visible | Concurrency must be bounded; this is not total host RAM |
| GPU | NVIDIA RTX 3070 Ti Laptop, 8,192 MiB reported | Does not prove browser acceleration or model/parser compatibility |
| Docker | CLI 26.1.3; 2026-10-27 daemon unreachable and `docker compose` unavailable in the current shell | Earlier Desktop 29.8.2/Compose 5.6.0 success is historical; owner can start Docker, then recheck before setup |
| Database clients | `psql`, `sqlite3` on PATH | No FieldLens database/pgvector service has been provisioned |
| OCR utilities | `tesseract`, `pdftotext`, `pdfinfo` not on PATH | Do not assume a ready OCR pipeline |

Latest resource snapshot: approximately 4.2 GiB available WSL RAM and 163 GiB
free disk. Capacity is shared and transient; do not allocate workers from CPU
count alone.

Install or change tools only during approved setup work. No system/runtime
upgrades, project package installations, image pulls or paid calls were performed.
Data discovery used temporary `uv --no-project --python 3.12 --with pypdf`
analysis after a missing-package failure; resolved `pypdf` 6.21.3 was used only
to inspect public access/license PDFs. It is not a finalized ingestion dependency.

## References

- [Vite requirements](https://vite.dev/guide/) and [Node support status](https://nodejs.org/en/about/previous-releases).
- [welleng](https://github.com/jonnymaserati/welleng), [Docling](https://github.com/docling-project/docling).
- [pgvector](https://github.com/pgvector/pgvector), [FastEmbed](https://qdrant.github.io/fastembed/).
- [R3F performance guidance](https://r3f.docs.pmnd.rs/advanced/pitfalls).
- [Meta protocols](https://dev.meta.ai/docs/protocols), [structured output](https://dev.meta.ai/docs/structured-output).
- [Perforated interval](https://glossary.slb.com/en/terms/p/perforated_interval),
  [measured depth](https://glossary.slb.com/en/terms/m/measured_depth), and
  [perforation density](https://glossary.slb.com/en/terms/p/perforation_density).
- [Development workflow](DEVELOPMENT_WORKFLOW.md): worktree resource isolation,
  schema/contract ownership, integration tests and synchronized application version.
