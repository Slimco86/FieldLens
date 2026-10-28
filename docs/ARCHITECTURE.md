# FieldLens application architecture

Design baseline: 2026-10-27. Backlog: FL-014. **Design complete for review;
implementation is not approved or verified by this document.**

This answers the architecture request using the actual source inspection in
[equipment feasibility](EQUIPMENT_DATA_FEASIBILITY.md) and
[data discovery](VOLVE_DATA_DISCOVERY.md). Source schemas remain adapter-specific:
the canonical domain model below does not pretend that an uninspected completion
report has particular columns. Missing pilot access blocks real-data acceptance,
not definition of the system that validates and displays those records.

## 1. Decisions and boundaries

| Decision | Selected approach | Reason / evidence |
|---|---|---|
| Deployment | Local modular monolith: one Python API, one worker, one PostgreSQL instance, one browser | Owner-approved single-user WSL demo; minimizes services and memory |
| Engineering authority | Immutable sources -> attributed claims -> deterministic projections | Inspected drilling/completion label mismatches show why file names and model summaries cannot establish installed state |
| API | FastAPI REST `/api/v1`, OpenAPI-generated TypeScript; polling for jobs | Typed interfaces without a second Node API, websocket service or message broker |
| Persistence | PostgreSQL 17 + pgvector 0.8 release families; SQLAlchemy 2/Alembic | Relational integrity, full text, vectors and typed graph edges in one store |
| Background work | Separate Python worker sharing the same package and database | CPU-heavy work must not block async requests; persistent queue survives restarts |
| UI | React 19, TypeScript strict, Vite 8, R3F 9, Three.js/WebGL2 | Required interactive scene and linked panels; no SSR or WebGPU dependency |
| Retrieval | Exact IDs + PostgreSQL full text + local dense embeddings + typed graph expansion | Identifier precision and evidence coverage matter more than adding a graph service |
| Agent | One bounded Meta Responses tool loop through Python `openai` SDK | Meta is the application model; development-agent profiles are separate |
| Equipment | Procedural source-dimensioned primitives first; optional reviewed Blender GLB | Tubular records contain dimensions; Blender cannot establish missing installation facts |
| Context | Source-backed seabed mesh and depth-domain formation surfaces/picks | Mandatory context, not a reservoir simulator; never interpret TWT as depth |
| Packaging | Frontend production build served by FastAPI; Compose for DB | One local URL for demo; full application containers optional |

These are technical design selections, not measured compatibility claims.
The [technical baseline](TECHNICAL_BASELINE.md) retains the environment evidence.
The [execution plan](../plan/architecture-fieldlens-1.md) defines dependency gates.
The [contracts](specs/SHARED_CONTRACTS.md) are normative for implementation once approved.

## 2. Runtime and data flow

```mermaid
flowchart LR
  U[Browser: upload, scene, charts, evidence, assistant] --> A[FastAPI]
  A --> DB[(PostgreSQL + pgvector)]
  A --> FS[Local immutable sources and derived artifacts]
  W[Bounded Python worker] --> DB
  W --> FS
  FS --> P[Native parsers / optional OCR]
  P --> C[Claims with attribute evidence]
  C --> V[Validation and identity/reference resolution]
  V --> D[Deterministic geometry and temporal state]
  V --> R[Text chunks, vectors, typed graph]
  D --> DB
  R --> DB
  A --> M[Meta API: allowlisted tools only]
  M --> A
```

1. Upload files into a staging area, enforce limits while streaming, hash them and
   persist a source manifest and queued job. Return HTTP 202 with identifiers.
2. The worker claims a leased job, inspects signatures, chooses a registered
   format/profile and extracts original values and locators. Files never execute.
3. Normalize into typed claims. Resolve identity, units, references, configuration
   and temporal meaning separately. Quarantine conflicting/unsupported records.
4. Compute valid projections. Write immutable artifacts using temporary files and
   atomic rename; transactionally publish their metadata and revision membership.
5. Publish `ready` or `ready_with_issues` only after required checks. A failed
   replacement never moves the dataset's active-revision pointer.
6. The UI fetches versioned summaries and bounded geometry/series chunks. Every
   panel uses the same selection context. LLM tools call the same domain services.
7. Build retrieval projections from accepted evidence with explicit validity and
   provenance. Index readiness is separate from dataset readiness.

## 3. Module and repository layout

These are **planned paths**, not existing application files.

```text
pyproject.toml / uv.lock / .python-version
backend/fieldlens/
  app.py                    API composition and static frontend serving
  contracts/                shared Pydantic models and error envelopes
  persistence/              models, repositories and transactions
  jobs/                     leases, worker entry point, cancellation
  ingestion/                format registry, safe readers, source profiles
  engineering/              units, references, surveys, proximity, temporal state
  equipment/                installed instances, catalog models, render parameters
  context/                  seabed and formation projections
  series/                   production and log queries, display decimation
  evidence/                 source access, locators, chunks
  retrieval/                exact/full-text/vector/graph search
  assistant/                provider adapter, budget ledger, tools, orchestration
backend/migrations/         one serialized Alembic head
backend/tests/              unit, PostgreSQL integration and source-profile tests
frontend/src/
  api/                      generated types + request/error handling
  app/                      layout and shared selection
  features/{upload,scene,equipment,history,context,production,logs,evidence,assistant}/
frontend/tests/             interaction and browser acceptance
tests/fixtures/             synthetic and redistribution-approved fixtures only
infra/compose.yaml          PostgreSQL/pgvector; loopback port only
scripts/                    reviewed contract-export and verification commands
```

API routes orchestrate domain services; they do not contain engineering formulas.
Domain modules cannot import React/Three.js, call Meta, or issue arbitrary SQL.
Repository functions own SQL. Native parser adapters cannot publish active
revisions directly. Rendering parameters are downstream of validated claims.

## 4. Domain and persistence boundaries

| Domain | Authoritative records | Rebuildable projections |
|---|---|---|
| Dataset | Dataset, immutable revision, manifest membership, job attempts | Active-revision pointer and readiness summary |
| Evidence | Source document/blob, source record, locator, extraction run, attributed claim | Text chunks and search indexes |
| Identity | Field, well, wellbore, explicit aliases and sidetrack parent | Asset tree and search labels |
| Spatial | Survey stations, CRS/reference metadata, source picks/points | Trajectory samples, nearest-approach result, context meshes |
| Equipment | Installed instance/configuration claims, catalog model claims | Procedural/GLB render manifest |
| History | Effective-time events, baselines, scoped observations and corrections | Perforation intervals and length/state at selected time |
| Series | Series definition, measurement points, units and acquisition/time scope | Display-decimated windows |
| Assistant | Conversation request, tool execution, budget reservation and usage | Validated answer/action envelope |

Use typed tables, foreign keys and revision membership rather than one universal
entity-attribute-value table. Common evidence/claim envelopes accompany typed
domain rows; they do not replace type-specific constraints. SQL queries must
scope by dataset and revision, including evidence links and graph expansion.

Original files live outside Git and database rows. Store byte count, SHA-256 and
server-owned relative storage keys; never accept a client filesystem path as a
source identifier. Changed sources produce new revisions. Identical content
within a dataset is idempotent; a filename alone does not identify a correction.

## 5. Geometry, references and historical truth

- A dataset declares one analysis horizontal CRS and a separate vertical datum.
  Volve's proposed analysis CRS is WGS84 / UTM zone 31N (EPSG:32631); source
  ED50/UTM31 coordinates retain EPSG:23031. This is not a default for uploads with
  missing metadata. Approved transforms and their stated accuracy are recorded.
- Use double-precision NumPy and pyproj; reject unknown references or unavailable
  required transforms, and disable silent ballpark transformation.
- Keep vertical conversion explicit. For a verified RKB height above MSL,
  `z_msl = rkb_height_msl - tvd_rkb`. A horizontal EPSG transformation does not
  convert MSL to ellipsoidal height or resolve an unknown rig datum.
- A tested welleng adapter implements minimum curvature. Its output is compared
  with independent analytic fixtures, not merely with another call to itself.
- Store physical `(E, N, z_up)` coordinates. Rendering uses
  `(E-E0, z-z0, -(N-N0))`; the origin and axis mapping travel in the scene manifest.
  Float32 is permitted only for local display buffers.
- Closest approach uses independently resolved physical curves with an explicit
  discretization/error bound, never visible mesh vertices or sparse stations.
- Equipment radius exaggeration is an explicit display option. Missing placement
  remains an unlocated inspector item. Drilling runs and installed production
  configurations must not share an inferred installation timeline.
- Temporal queries require revision and explicit as-of selection. Use the
  [perforation specification](specs/PERFORATION_HISTORY.md); physical coverage,
  interval access and observed flow are distinct axes.

## 6. Source support and extraction selection

First-release reader families: CSV/DAT with an approved schema profile, XLSX,
LAS 2.x, WITSML 1.4.1.1 XML, and native-text PDF. Register source-specific identity,
unit, reference and event mappings only after inspection. LAS 3, arbitrary CAD,
SEG-Y/RMS simulator import and unsupported XML dialects return explicit
unsupported-format/profile results, not successful empty datasets.

Use standard CSV/ZIP readers, openpyxl read-only XLSX, lasio, defusedxml,
pypdf and pdfplumber. Preserve PDF page/table/word coordinates when available;
table extraction is not automatically trustworthy. Scanned pages remain
`ocr_required` until a separately measured OCR adapter passes the approved sample.
Docling is the selected first OCR/layout candidate, not a mandatory always-loaded
dependency. Its model/license/RSS gate precedes installation or use. MarkItDown
may assist plain-text discovery, but is not the authority for engineering tables.

The ~201 MB EDM export is a priority discovery lead, **not** admitted under the
25 MiB default upload profile. A later inspected streaming profile and explicit
limit approval are required. Do not download the whole release to unblock design.

## 7. UI composition and interaction

Scene-first desktop workspace: asset tree at left, scene in the center,
inspector/evidence/assistant tabs at right, and resizable production/log charts
below. The header always exposes dataset revision, as-of selection and processing
state. This is a design selection informed by the
[visual references](design/README.md), not an existing screenshot.

At 1280x720, switch side panels to accessible drawers; keep both chart families
available as tabs rather than deleting one. At 1920x1080 show both chart panels.
The asset tree provides a keyboard alternative to every selectable 3D object.
Tree, scene, chart and assistant actions dispatch one selection operation.

Use TanStack Query for server data and a small React context/reducer for selection,
panel state and pending action acknowledgments. Do not store geometry/log arrays
in that reducer. Request cancellation and context-key checks prevent stale data
appearing under a newer wellbore/date. Preserve original acquisition dates on logs.

Lazy-load R3F, ECharts and PDF.js feature boundaries. Use demand rendering outside
active interaction, shared/disposed GPU resources, reduced-motion support and
text-plus-color evidence labels. No per-frame React state updates.

## 8. Retrieval and Meta boundaries

Exact canonical IDs/validated aliases precede lexical and vector retrieval.
Use PostgreSQL `simple` text configuration plus a GIN index; preserve punctuation
in identifiers. Use exact cosine vector search first, not unmeasured HNSW.
The embedding candidate is `BAAI/bge-small-en-v1.5` (384 dimensions) via FastEmbed,
CPU-only, with model revision, license, normalization and query-prefix policy
recorded at its evaluation gate. An unavailable vector index is an explicit
degraded retrieval mode, not a passing hybrid-retrieval test.

Retrieve at most 20 lexical and 20 vector candidates, fuse with reciprocal rank
`1/(60+rank)`, then add at most 20 eligible graph neighbors within two hops.
Keep at most 10 final chunks and 12,000 context tokens. Apply dataset/revision,
entity, validation and temporal eligibility before ranking; uncertain-time claims
remain explicitly uncertain. Exact identifier hits must not broaden to siblings.

Tool allowlist: asset/evidence search, equipment facts, selected-time perforation
state, series windows, closest approach, and proposed viewer/chart/evidence
actions. Server validation checks IDs, context, arguments, outputs and citations.
Viewer actions are proposals with acknowledgment, not arbitrary scene scripts.
External equipment research requires public manufacturer/model identifiers and
its own query budget; ordinary field questions never trigger broad web search.

Use `muse-spark-1.3` Standard as the selected entitlement-test candidate.
Responses support and actual model access are gated by FL-003, not assumed from
SDK compatibility. Do not silently substitute another provider or Contributor
mode. The [Meta spec](specs/META_INTEGRATION.md) defines finite spending/retry rules.

## 9. Resource and reliability budgets

Design limits, not measurements; approval/validation occurs before execution.

| Resource | Initial limit / response |
|---|---|
| Runtime processes | One API, one worker, one DB; no Celery/Redis broker |
| Heavy computation | One parser/geometry/embedding job at a time; two numeric-library threads |
| Upload | 25 MiB/file, 100 MiB/revision, 200 files; HTTP 413 when exceeded |
| Archives | ZIP only, no nesting/symlinks/traversal/encryption; enforce actual expanded bytes within the same revision limit |
| PDF | 500 pages/file; process batches of <=20; account for every page |
| Job | 10-minute lease with heartbeat every 10 seconds; stage deadlines and cancellation between batches; one retry only for classified transient failure |
| Memory planning | API 384 MiB + DB 768 MiB + worker 1536 MiB; target <=3 GiB measured aggregate process RSS |
| OCR | Never concurrent with embedding/indexing; stop adapter evaluation above 1536 MiB worker RSS |
| Browser | Benchmark separately from WSL server RSS; no GPU availability claim until measured |
| Interaction | Project AC-9: p95 frame <=33.3 ms/30-second orbit at 1080p; local reads p95 <=1 s/20 requests during one import |
| Meta | One active request; six tool calls, four model turns, 90-second total deadline; detailed shared ledger in FL-003 |

Memory figures are budgets rather than OS enforcement guarantees. Measure child
process RSS too; pause further scheduling when available WSL RAM falls below
1 GiB. Do not count twenty logical CPUs as capacity for twenty parsing workers.
Job retries use attempt fencing so an expired worker cannot publish after a
replacement owns the lease. Startup marks abandoned work interrupted and queues
only eligible retries. Never execute parsing in FastAPI `BackgroundTasks`.

## 10. Tests, gates and delivery

See [feature index](specs/README.md) for all acceptance contracts and
[execution plan](../plan/architecture-fieldlens-1.md) for the runnable sequence.
Foundation work establishes actual commands; none are claimed to exist today.

Testing layers: deterministic unit fixtures; PostgreSQL/pgvector integration;
adapter source-fixture tests; React interactions; Playwright fresh-upload
end-to-end; opt-in live Meta evaluation. Label synthetic, mirror, replay and
official-source evidence separately.

G1 remains the accepted real-data manifest. G2 remains actual Meta entitlement
and credit verification. G4 remains submission/rights review. G5 is package,
parser, embedding and resource qualification. These are **execution and final
acceptance gates**, not promises or missing architectural decisions.

No multi-user hosting, authentication product, simulation, arbitrary-code tools,
automatic catalog privilege changes or new paid services are included. A failed
gate blocks affected slices; it does not authorize omitting a required capability.
