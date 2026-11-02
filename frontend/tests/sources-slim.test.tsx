// AC-1 (TASK-063): the Sources tab holds only the project header, the tabs, the upload section, the source
// revision and the revision files; the Overview and pipeline panel moved to the Reconstruction tab.
// Stubbed fetch: this proves what the UI renders and requests, not the live backend.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "./render";
import { ProjectView } from "../src/features/projects/ProjectView";
import type { Section } from "../src/features/projects/keys";

const P = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const R = "11111111-1111-4111-8111-111111111111";
const D1 = "d1d1d1d1-d1d1-4d1d-8d1d-d1d1d1d1d1d1";
const SHA = "a".repeat(64);

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const page = (...items: unknown[]) => ({ items, page: { limit: 50, next_cursor: null } });

const PROJECT = {
  project_id: P, name: "Volve subset", description: "d", created_at: "2026-10-28T12:00:00Z", updated_at: "2026-10-28T12:00:00Z",
  latest_source_revision_id: R, active_model_revision_id: null,
};
const REVISION = {
  source_revision_id: R, project_id: P, manifest_hash: "f".repeat(64), created_at: "2026-10-29T12:00:00Z", status: "ready",
  parent_source_revision_id: null, coverage: null, is_latest: true, member_count: 1, stored_count: 1, failed_count: 0,
  pending_extraction_count: 0, unsupported_count: 0, job_id: null, job_status: null,
};
const DOC = {
  document_id: D1, project_id: P, original_filename: "traj.csv", sha256: SHA, size_bytes: 10, created_at: "2026-10-29T12:00:00Z",
  detected_media_type: "text/csv", format_family: "csv", origin_metadata: {}, storage_state: "stored", extraction_state: "extracted",
  processing_detail: null,
  classification: { user_categories: [], suggested_categories: [], tags: [], categories_origin: "none", classification_method: "none", classification_version: "1", metadata_version: 1, updated_at: "2026-10-29T12:00:00Z" },
  replaces_document_id: null, source_revision_id: R,
};
const cat = (name: string, over: Record<string, unknown> = {}) => ({
  category: name, present: false, record_count: 0, conflicting_record_count: 0, accepted_proposal_count: 0, proposal_total: 0,
  proposals_truncated: false, proposals: [], findings_total: 0, findings_truncated: false, conflicts: [], gaps: [], findings: [],
  gap_reasons: [], groups: [], ...over,
});
const GW = { well_id: "w", wellbore_id: "b", wellbore_name: "15/9-F-12", trajectory_validated: true, trajectory_sets: [], location_state: "located", unlocated: false, unmet: [], warnings: [] };
const GATE = { project_id: P, can_start: true, gate_version: "1", conditions: [], qualifying_wellbore_ids: ["b"], unmet: [], warnings: [], wellbores: [GW] };
const EXPOSURE = {
  project_id: P, resolved_current: true, resolver_version: "1", unresolved_record_count: 0, gate: GATE,
  wells: [{ well_id: "w", name: "15/9-F-12", wellbores: [{ project_id: P, well_id: "w", wellbore_id: "b", wellbore_name: "15/9-F-12", gate: GW, categories: [
    cat("trajectory", { present: true, record_count: 3, groups: [{ document_id: D1, run_id: R, filename: "traj.csv", kind: "trajectory_station", record_count: 3, evidence_class: "source_record", sample_truncated: false, validation_counts: {}, survey_status: null, profile_name: null, sample: [] }] }),
  ] }] }],
};

let urls: string[] = [];
function install() {
  urls = [];
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    urls.push(url);
    if (url === "/api/v1/session") return Promise.resolve(json({ csrf_token: "t".repeat(43) }));
    if (url === `/api/v1/projects/${P}`) return Promise.resolve(json(PROJECT));
    if (url.includes("/documents?")) return Promise.resolve(json(page(DOC)));
    if (url.includes("/source-revisions")) return Promise.resolve(json(page(REVISION)));
    if (url.endsWith("/identity/exposure")) return Promise.resolve(json(EXPOSURE));
    if (url.endsWith("/identity/start-gate")) return Promise.resolve(json(GATE));
    if (url.endsWith("/processing/documents")) return Promise.resolve(json({ project_id: P, source_revision_id: R, items: [] }));
    if (url.endsWith("/processing/runs")) return Promise.resolve(json({ items: [] }));
    throw new Error(`unexpected request ${url}`);
  }));
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function Harness({ initial = "sources" as Section }: { initial?: Section }) {
  const [section, setSection] = useState<Section>(initial);
  return <ProjectView projectId={P} section={section} onSection={setSection} onBack={() => undefined} onMissing={() => undefined} />;
}

describe("Sources tab content (AC-1)", () => {
  it("shows only header, tabs, upload, source revision and files; no Overview or pipeline, and no data requests for them", async () => {
    install();
    render(<Harness />);
    await screen.findByRole("table", { name: "Files in this source revision" });
    expect(screen.getByRole("heading", { name: "Volve subset" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit project details" })).toBeInTheDocument();
    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Files of revision/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Overview/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Processing pipeline|Reconstruction$/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Identified wells and wellbores/)).not.toBeInTheDocument();
    expect(screen.queryByText("Document processing")).not.toBeInTheDocument();
    expect(urls.filter((u) => /identity|processing|series|extraction|issues/.test(u))).toEqual([]);
  });

  it("lists the revision files (re-run extraction stays covered by the evidence tests)", async () => {
    install();
    render(<Harness />);
    const table = await screen.findByRole("table", { name: "Files in this source revision" });
    expect(within(table).getByText("traj.csv")).toBeInTheDocument();
  });
});

describe("Reconstruction tab in the project (AC-2, AC-3)", () => {
  it("opens the list and a Sources link switches to Sources and focuses that file", async () => {
    install();
    render(<Harness initial="reconstruction" />);
    const link = await screen.findByRole("link", { name: "Open traj.csv in Sources" });
    expect(screen.getByText("Reconstruct all ready wellbores (1)")).toBeInTheDocument();
    await userEvent.click(link);
    await screen.findByRole("table", { name: "Files in this source revision" });
    await waitFor(() => expect(document.getElementById(`source-file-${D1}`)).toHaveFocus());
    expect(screen.queryByText(/Identified wells and wellbores/)).not.toBeInTheDocument();
  });

  it("explains the missing prerequisite when there is no source revision", async () => {
    install();
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(String(input) === "/api/v1/session" ? json({ csrf_token: "t".repeat(43) }) : json({ ...PROJECT, latest_source_revision_id: null })),
    ));
    render(<Harness initial="reconstruction" />);
    expect(await screen.findByText(/requires an imported source revision/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Reconstruct( all.*)?$|^Process/ })).not.toBeInTheDocument();
  });
});
