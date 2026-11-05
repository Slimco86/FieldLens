# FieldLens — submission summary

**Agentic reconstruction of oilfield assets from decades of historical records, powered by Meta Muse Spark.**
Meta AI Developer Hackathon (Oct 27 – Nov 4, 2026) · Indie track · Theme: Push the Frontier — Energy
Repository: https://github.com/Slimco86/FieldLens

## Problem

Global energy demand keeps rising, driven now by electrification and AI data centres, and oil and gas
still supply more than half of it. Producing that energy efficiently depends on understanding each
asset — but an oilfield is not one dataset; it is decades of them. Every well leaves survey reports,
completion logs, drilling data, well logs and daily production from many contractors in many formats.
The same well is named differently across sources, depths are measured along curving holes rather
than straight down, completions change over time (perforated, shut in, re-perforated), and records
conflict or leave things out. Engineers spend up to half their time finding and reconciling data, and
wells end up managed on partial information.

## Solution

FieldLens is a web application where an engineer creates a project, drops in the raw files of a field
— no labels, no schema, no prior knowledge of what is inside — and a Meta Muse Spark agent turns them
into an evidence-backed, explorable model of the field. Structured formats are parsed natively; the
agent reads what parsers cannot, resolves which records describe the same wellbore, and designs each
well's 3D asset. Deterministic code validates every proposal and computes all geometry, so every value
on screen traces back to the exact page, table cell or line of the source document. The result can be
explored in 3D, charted over time and questioned in plain language.

## Features introduced

1. **Upload without preparation** — incremental, hash-verified uploads; native parsers for WITSML,
   LAS, survey reports, perforation/pick tables and production spreadsheets, with page/line/cell locators.
2. **Automatic problem detection** — duplicate and block-less well names, missing surface locations,
   unstated survey status, unit/depth-reference gaps and conflicting values, each linked to evidence.
3. **Agentic reconstruction** — a persisted, five-stage run per wellbore (collect → read documents →
   match wellbores → assemble → design 3D asset) with cost estimate before confirmation, budget ledger,
   cancellation, retry and honest partial results.
4. **Identity resolution with a human in the loop** — model-proposed merges backed by survey
   fingerprints and deterministic guard checks; nothing merges until accepted, every merge is revertible.
5. **3D reconstruction & visualization** — wells placed at surveyed surface locations (stated CRS),
   minimum-curvature trajectories in double precision, casing, completion components and perforated
   intervals at measured depth, formation markers and labelled planes.
6. **End-to-end traceability** — every element shows its source; one click opens the PDF on the cited page.
7. **Charting** — production/injection, cumulative volumes, downhole and tubing/annulus pressure,
   on-stream hours and log curves per wellbore, with data tables and sources.
8. **Agentic assistant** — answers questions such as "When did the F-5 well switch from injector to
   producer?" with exact dates from stored series, citations and an inline chart.

## How Meta models are used — and why they are essential

All model calls use **Meta Muse Spark** through the Meta Model API (OpenAI-compatible SDK), server-side
only, inside a bounded harness (budget reservation, step/tool/time limits, cancellation, typed outputs,
server-side validation). The model proposes; deterministic code validates and decides.

- **Document reading (reconstruction stage S2).** Muse Spark reads PDFs that no native parser covers
  — completion reports, completion logs, biostratigraphy — classifies them, proposes labels and extracts
  wellbore identities with page and quote. *Essential* because these documents are free-form, vary by
  contractor and decade, and are often scanned; rules cannot cover them.
- **Identity matching (S3).** Given a deterministic candidate table (name similarity, slot, survey
  fingerprints), Muse Spark decides which differently written names denote the same wellbore and
  explains why. *Essential* because naming conventions are inconsistent across sources; the judgement
  needs language understanding, while guard checks and user acceptance keep it safe.
- **3D asset design (S5).** Muse Spark classifies and labels each equipment record (casing, tubing,
  packer, perforation, wellhead…) and sweeps the wellbore's documents for equipment; the server builds
  every component using only printed dimensions and depths. *Essential* to turn heterogeneous records
  into a coherent, readable asset without inventing numbers.
- **Agentic assistant.** Muse Spark plans calls to typed, allowlisted tools (series listing, exact
  series statistics with dates, evidence search, trajectories, formations, equipment) and returns
  typed answer blocks — cited text, verified values, links and chart requests — which the server
  validates and renders. *Essential* so engineers can ask in plain language and get exact, cited,
  plotted answers instead of searching through files.

This is agentic reconstruction, not chat over documents: the model's output becomes reviewable
proposals and validated records that drive the 3D model, charts and answers.

## Built during the hackathon

Everything was built during the event. The repository starts on kickoff day (first commit
Oct 26, 2026, planning documents only); all application code — project workspace and uploads, native
parsers, data-quality findings, reconstruction runs and agent harness, identity resolution, 3D viewer,
charts, traceability and the assistant — was written Oct 27 – Nov 4, 2026 (see the git history and
`CHANGELOG.md`, versions 0.1 → 0.56).

## Data

Demo data: wells F-12, F-14 and F-5 from the Equinor Volve open dataset (Equinor Open Data Licence).
The data is not redistributed in the repository.
