# Technical baseline and engineering conventions

Date: 2026-10-26, America/New_York. This is an initial, owner-agreed direction,
not a completed architecture or a claim that packages have been tested together.
Updated 2026-10-27 with historical perforation and parallel-delivery requirements.

## 1. Prefer a small system with explicit responsibilities

Use one Python application for API, ingestion coordination, engineering tools and
agent integration; one React frontend; and PostgreSQL. A bounded worker process
may isolate CPU-heavy ingestion without becoming an independently deployed service.
Decide process/container boundaries in feature specs after representative tests.

Node is needed to build/develop the frontend, not to duplicate Python endpoints.
The renderer consumes derived geometry; it does not own engineering facts.
Application tools, not the model, control calculations and allowable scene actions.

## 2. Stack decisions

| Area | Initial choice | Rationale / condition |
|---|---|---|
| Python | 3.12 via uv; project virtual environment | Already installed; conservative scientific-package compatibility |
| API and contracts | FastAPI + Pydantic | Typed boundaries, OpenAPI; generate frontend API types from the contract |
| Engineering | NumPy, pyproj, welleng behind tested adapters | Deterministic numeric/CRS handling; verify exact reader APIs and source format versions |
| Structured ingestion | Native CSV/XML/XLSX parsers; pandas/openpyxl only where useful | Preserve typed values, units and locators instead of asking an LLM to recalculate tables |
| PDF/OCR | Evaluate Docling on the selected samples | Layout/OCR capabilities are documented; cost, memory, accuracy and model licenses need measurement |
| CAD/asset inputs | Format-specific import or deterministic procedural mesh generation | Do not promise arbitrary CAD-to-3D reconstruction; select needed formats at G1 |
| Frontend | React + strict TypeScript + Vite | Small client application; no SSR requirement |
| 3D | Three.js + React Three Fiber; Drei helpers as needed; WebGL2 | Stable interactive rendering; no alpha/WebGPU dependency |
| Charts and evidence | Apache ECharts; PDF.js | Production/log series and source-document inspection; load heavy viewers on demand |
| Persistence | PostgreSQL + pgvector; SQLAlchemy/Alembic for access/migrations | One relational and retrieval store; versioned schema and transactional integrity |
| Knowledge graph | Typed entity/relationship/claim records in PostgreSQL | Graph semantics with foreign keys and provenance; bounded SQL traversal initially |
| Embeddings | Small local CPU model through FastEmbed, subject to sample evaluation | No assumed Meta embeddings API; no additional paid embedding service |
| Agent | Official OpenAI-compatible Python SDK targeting Meta; Pydantic tool schemas | A bounded single-agent tool loop first; Pydantic AI/LangGraph only if justified by real requirements |
| Frontend tooling | Supported Node 24 LTS patch, npm and a committed lockfile | Installed Node 20 is EOL and below current Vite's minimum |
| Tests | pytest, Ruff, Python type checking; TypeScript/ESLint, Vitest, Playwright | Install/configure with the corresponding feature; test actual behavior, not only snapshots |
| Local services | Docker Compose for PostgreSQL/pgvector is the preferred option | Docker now works; full application containers/devcontainer remain optional |

Freeze compatible stable versions in manifests and lockfiles after resolution.
Do not use floating `latest` images or install whole research inventories.
No dependency manifests or runnable test commands exist yet.

## 3. Why one database can support three needs

Relational storage, vector retrieval and knowledge graphs are capabilities, not
an automatic requirement for three database products.

- **Relational:** wells/wellbores, component instances, survey revisions, source
  documents, extraction jobs, series metadata, dated perforation/state events,
  claims and provenance. Effective event time is distinct from report/import time.
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
trajectories. Drawings inform parameters; the agent does not emit executable
geometry code. A general photograph/drawing is not sufficient to recover unique
dimensions. Unknown-position equipment can appear in an unlocated inspection
panel instead of being assigned a fabricated location.

For offshore Volve, surface context may be seabed/bathymetry, not land terrain.
Formation picks do not establish a measured continuous surface or reservoir
volume. Interpolation must state its method and limits; simulator grids/metadata
must be labeled according to their source. Reservoir representation is required,
but its minimum truthful form awaits the data audit.

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

Read-only checks on 2026-10-26; these are observed tools, not installed project
dependencies or performance certification.

| Resource | Observation | Consequence |
|---|---|---|
| OS | Ubuntu 20.04.6 under WSL2 | Check native wheel/glibc compatibility; do not assume an OS upgrade |
| Default Python | Conda 3.9.23; system Python 3.8.10 | Neither is the project runtime |
| Managed Python | uv-installed 3.12.13 and 3.13.12 | Select 3.12 explicitly |
| uv | 0.11.20 | Available |
| Node / npm | 20.11.1 / 10.2.4; no alternate Node found in inspected common locations | Provision supported Node 24 at setup, not an obsolete Vite workaround |
| CPU / WSL memory | 20 logical CPUs; 7.6 GiB RAM, 2 GiB swap visible | Concurrency must be bounded; this is not total host RAM |
| GPU | NVIDIA RTX 3070 Ti Laptop, 8,192 MiB reported | Does not prove browser acceleration or model/parser compatibility |
| Docker | CLI 26.1.3; Desktop daemon 29.8.2; Compose v5.6.0 | Rechecked successfully after owner enabled Docker Desktop |
| Database clients | `psql`, `sqlite3` on PATH | No FieldLens database/pgvector service has been provisioned |
| OCR utilities | `tesseract`, `pdftotext`, `pdfinfo` not on PATH | Do not assume a ready OCR pipeline |

Install or change tools only during approved setup work. No system/runtime
upgrades, package installations, image pulls or paid calls were performed here.

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
