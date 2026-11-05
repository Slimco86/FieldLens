# FieldLens

**Agentic reconstruction of oilfield assets from decades of historical records — powered by Meta Muse Spark.**

Upload the raw files of a field (survey reports, completion logs, drilling XML, well logs,
production spreadsheets) with no labels and no data model. A Muse Spark agent sorts them,
resolves which records describe the same well, reconstructs every wellbore and its history,
and backs every value with the exact source page, table cell or line it came from. Engineers
then explore the field in 3D, read production/pressure charts and ask questions that are
answered with dates, citations and inline charts.

[![FieldLens demo video](https://img.youtube.com/vi/h8wsHxbxMug/maxresdefault.jpg)](https://www.youtube.com/watch?v=h8wsHxbxMug)

- **Demo video (3 min):** https://www.youtube.com/watch?v=h8wsHxbxMug
- **Built during** the Meta AI Developer Hackathon, Oct 27 – Nov 4, 2026 · theme **Push the Frontier · Energy** · indie track
- **Version:** see [VERSION](VERSION) and [CHANGELOG](CHANGELOG.md)

## The problem

Global energy demand keeps rising and oil and gas still supply more than half of it. Producing
it efficiently depends on understanding each asset — yet a mature field is not one dataset but
decades of them. The same well is written three different ways, depth is measured along curving
holes rather than straight down, completions change over time (perforated, shut in,
re-perforated), and records conflict or leave things out. Engineers can spend up to half their
time finding and reconciling data, and wells end up being managed on partial information.

## The solution

FieldLens turns that pile of files into an evidence-backed, explorable model of the field:

1. **Upload** raw files into a project — no categories or schema needed. Structured formats
   (WITSML XML, LAS, survey text, perforation/pick tables, production XLSX) are parsed natively
   and indexed immediately; everything is hash-verified and stored with provenance.
2. **Problems are flagged automatically**: duplicate or block-less well names, missing surface
   locations, unstated survey status, unit and depth-reference gaps, conflicting values.
3. **Agentic reconstruction** (per wellbore, estimate → confirm → five persisted stages):
   S1 collect sources · S2 *read documents* (Muse Spark) · S3 *match wellbores* (Muse Spark) ·
   S4 assemble a validated draft · S5 *design the 3D asset* (Muse Spark). The cost is shown before
   anything is spent; failures are recorded honestly as partial results.
4. **Identity resolution with a human in the loop**: the agent proposes that differently written
   names are one wellbore, backed by identical survey fingerprints and deterministic guard checks;
   nothing merges until the user accepts, and every merge can be reverted.
5. **Explore**: a 3D field placed at surveyed surface locations with real minimum-curvature
   trajectories, per-wellbore equipment and perforated intervals at their measured depths,
   formation tops, production/injection/pressure/on-stream charts — every element linked to its
   source (PDF opens on the cited page).
6. **Ask**: an agentic assistant that chooses tools, pulls exact values and dates from stored
   series, cites them, and plots the answer inline.

## Features

| Feature | What it does |
|---|---|
| Project workspace | Isolated projects, incremental hash-verified uploads (200 files / 128 MiB per file / 512 MiB per import), source revisions |
| Native parsing | WITSML trajectory/tubular/wbGeometry/BHA, LAS, survey reports (text + PDF), perforation and pick tables, production XLSX — with page/line/cell locators |
| Data-quality findings | Evidence-linked warnings and blocking errors; affected outputs are blocked, valid records are not hidden |
| Agentic reconstruction | Persisted per-wellbore runs (S1–S5) with estimates, budget ledger, cancellation, retry and honest partial states |
| Identity resolution | Model-proposed merges with survey-fingerprint evidence and deterministic guards; accept / reject / revert |
| 3D reconstruction & visualization | Field view at surveyed surface locations (stated CRS), minimum-curvature trajectories in double precision, casing/tubing/perforations at MD, formation markers and labelled level planes, fly-to, inspector |
| Traceability | Every element and value carries document, page/table/cell/line locator, extraction method and revision; the PDF viewer opens on the cited page |
| Charting | Wellbore and field charts: production/injection volumes, cumulative, downhole and tubing/annulus pressure, on-stream hours, perforation history, log curves; data tables and sources |
| Agentic assistant | Tool-calling agent over typed, allowlisted tools; answers are validated server-side (numbers, citations, links) and include inline charts built from stored series |

## How Meta models are used — and why they are essential

All model calls go to **Meta Muse Spark** (`muse-spark-1.3`) through the Meta Model API's
OpenAI-compatible endpoint, from the server only (key never reaches the browser). Every call runs
through a bounded harness: budget reservation and settlement, step/tool-call/time limits,
cancellation, typed outputs and server-side validation. **The model proposes; deterministic code
validates and decides** — Muse Spark never writes geometry, numbers or SQL directly.

| Component | What Muse Spark does | Why it is essential |
|---|---|---|
| S2 Read documents (`processing/model_step.py`, `candidates/harness.py`) | Reads PDFs that have no native parser: classifies the document, proposes labels, extracts wellbore identities with page + quote; scanned pages without a text layer can be sent as images (implemented; live image input not yet verified), and their reads are marked unverified | Completion reports and logs are free-form, often scanned; no rule-based parser covers them |
| S3 Match wellbores (`merge_proposals/proposer.py`) | Given a deterministic candidate table (name similarity, slot, survey fingerprints), proposes which differently written names are the same wellbore, with rationale and quotes | Naming conventions differ across contractors and decades; the judgement needs language understanding, while guards keep it safe |
| S5 Design 3D asset (`assetspec/live_designer.py`, `assetspec/sweep.py`) | Classifies and labels each equipment record (casing, tubing, packer, perforation…) and sweeps the wellbore's documents for equipment mentions | Turns heterogeneous equipment records into a coherent asset; the server sets every dimension and depth from printed values only |
| Agentic assistant (`chat/`) | Plans tool calls (list series, exact series statistics with dates, evidence search, trajectories, formations, equipment), then returns typed answer blocks: text with citations, verified values, links and chart requests | Lets engineers ask in plain language and get exact, cited, plotted answers instead of hunting through files |

Retrieval embeddings use a small local model (BAAI/bge-small-en-v1.5) because the Meta API has no
embeddings endpoint; full-text and exact-identifier search work without it.

## Architecture

```
React + TypeScript (Vite) ── Three.js / React Three Fiber 3D · ECharts charts · PDF viewer
        │  typed REST contracts (Pydantic → OpenAPI → generated TS client)
FastAPI (Python 3.12) ── jobs & reconstruction runs (bounded workers, leases, persisted state)
        │                 native parsers · validators · minimum-curvature wellpath (NumPy/pyproj)
        │                 agent harness → Meta Muse Spark (OpenAI-compatible SDK)
PostgreSQL 17 + pgvector ── projects, documents, records, claims, evidence, series, runs, budget ledger
Local storage ── original files by content hash (never inside database rows)
```

Engineering truth lives in source records and deterministic derivations; the renderer and the LLM
are never the source of truth. Planned/as-built, units, CRS/datum and MD vs TVD references are
preserved as stated and never assumed.

## Quick start

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 24.22.2, Docker (for
PostgreSQL + pgvector). A Meta Model API key is needed only for the agent steps.

```bash
uv sync --frozen
npm --prefix frontend ci
uv run python scripts/init_env.py      # creates .env (add MODEL_API_KEY=... for live agent runs)
./dev up                               # postgres, migrations, frontend build, API
# open http://127.0.0.1:8101/
./dev status | ./dev logs api -f | ./dev down
```

Tests: `./dev test all` (backend pytest against throwaway PostgreSQL databases, ruff, mypy strict,
frontend lint/typecheck/vitest/contracts/build). Default tests never call Meta. Full details:
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Data

The demo uses wells F-12, F-14 and F-5 from the **Equinor Volve open dataset**, used under the
Equinor Open Data Licence. Source files are **not** redistributed in this repository; download
them from Equinor and upload them into a project.

## Limitations

FieldLens is a historical, source-backed reconstruction — not a live operational twin, reservoir
simulator or certified engineering tool. Illustrative 3D widths are exaggerated and labelled;
generic placeholders never enter calculations; proximity is not proof of connectivity. Some
model reads can fail on very large documents (recorded as partial runs). Production data in
Volve is well-level and unit-less in the source spreadsheet, and is shown as such.

## License

Copyright 2026 Ievgen Voloshenko. Licensed under the [Apache License, Version 2.0](LICENSE); see
[NOTICE](NOTICE). Adapted third-party materials keep their own licenses ([docs/licenses](docs/licenses/)).

## Documentation

- [Development guide](docs/DEVELOPMENT.md) — setup, lanes, configuration, tests
- [Project specification](docs/PROJECT_SPEC.md) and [architecture](docs/ARCHITECTURE.md)
- [Feature specs](docs/specs/README.md) — one spec per feature with acceptance criteria
- [Backlog](docs/BACKLOG.md) — delivery ledger with evidence per task
- [Source assessment](docs/SOURCE_ASSESSMENT.md), [Volve data discovery](docs/VOLVE_DATA_DISCOVERY.md),
  [evaluation evidence](docs/evidence/)
- [Submission summary](docs/SUBMISSION.md)
- Development workflow and agent roster: [docs/DEVELOPMENT_WORKFLOW.md](docs/DEVELOPMENT_WORKFLOW.md),
  [.claude/agents](.claude/agents/README.md), [.github/agents](.github/agents/README.md)
