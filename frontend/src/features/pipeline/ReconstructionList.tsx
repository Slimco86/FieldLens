import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Button, Table, Title } from "@mantine/core";
import { ChevronDown, ChevronUp, CircleCheck, CircleHelp, CircleX, Info, RefreshCw } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState } from "../../design";
import { routeHash } from "../../app/shell/route";
import type { components } from "../../api/generated";
import { keyString } from "../projects/keys";
import { toFailure, useScopedResource, type Failure } from "../projects/scope";
import {
  getExposure,
  getProcessingDocuments,
  getRun,
  listRuns,
  getStartGate,
  requestEstimate,
  type DocumentProcessingState,
  type ProcessingDocumentSelection,
} from "./api";
import styles from "./Pipeline.module.css";

type S = components["schemas"];
type Category = S["CategoryExposure"];
type Finding = S["ExposureFinding"];
type Gate = S["WellboreGate"];
type Reason = S["GateReason"];

export const CATEGORY_LABEL: Record<Category["category"], string> = {
  trajectory: "Trajectory",
  surface_location: "Surface location",
  logs: "Logs",
  production: "Production",
  equipment_completion: "Equipment and completion",
  perforations: "Perforations",
  other: "Other",
};

const HUMAN_LOCATOR_KEYS = new Set(["page", "sheet", "table", "row", "cell", "column", "line", "line_start", "line_end", "curve"]);

/** Short source locator text from the human-readable keys the server wrote (ids and kinds are never shown); nothing is interpreted. */
export function locatorText(loc: Record<string, unknown> | undefined): string {
  if (loc === undefined) return "no locator";
  const parts = Object.entries(loc)
    .filter(([k, v]) => HUMAN_LOCATOR_KEYS.has(k) && v !== null && typeof v !== "object")
    .map(([k, v]) => `${k} ${String(v)}`);
  return parts.length === 0 ? "no locator" : parts.join(", ").slice(0, 160);
}

export function categoryNotices(c: Category): string[] {
  const out: string[] = [];
  if (c.findings_truncated) {
    const shown = c.conflicts.length + c.gaps.length + c.findings.length;
    out.push(`Findings truncated: showing ${shown} of ${c.findings_total}.`);
  }
  if (c.proposals_truncated) out.push(`Proposals truncated: showing ${c.proposals.length} of ${c.proposal_total}.`);
  if (c.groups.some((g) => g.sample_truncated)) out.push("Some record samples are truncated; counts remain exact.");
  return out;
}

const REPEAT_GUARD_MS = 1000;
const READY = { tone: "success", icon: CircleCheck } as const;
const NOT_READY = { tone: "neutral", icon: CircleX } as const;
const UNKNOWN = { tone: "unknown", icon: CircleHelp } as const;
const BLOCK = { tone: "neutral", icon: Info } as const;

export interface WellboreRow {
  well: string;
  wellboreId: string;
  wellboreName: string;
  /** `null` when the start gate could not be read: never guessed. */
  ready: boolean | null;
  gate: Gate;
  blockNotStated: boolean;
  categories: Category[];
}

/** Ready wellbores first (server verdict), then the rest; stable within each group. Nothing is computed from data. */
export function buildRows(exposure: S["ProjectExposure"], gate: S["StartGate"] | null): WellboreRow[] {
  const qualifying = gate === null ? null : new Set(gate.qualifying_wellbore_ids);
  const gateById = new Map((gate?.wellbores ?? []).map((w) => [w.wellbore_id, w]));
  const rows = exposure.wells.flatMap((w) =>
    w.wellbores.map((b): WellboreRow => {
      const g = gateById.get(b.wellbore_id) ?? b.gate;
      return {
        well: w.name,
        wellboreId: b.wellbore_id,
        wellboreName: b.wellbore_name,
        ready: qualifying === null ? null : qualifying.has(b.wellbore_id),
        gate: g,
        blockNotStated: [...g.warnings, ...b.gate.warnings].some((x) => x.code === "BLOCK_NOT_STATED"),
        categories: b.categories,
      };
    }),
  );
  return [...rows.filter((r) => r.ready === true), ...rows.filter((r) => r.ready !== true)];
}

/** Documents carrying a wellbore's data (from exposure groups, by document id), de-duplicated in first-seen order. */
export function documentIdsOf(row: WellboreRow): string[] {
  return [...new Set(row.categories.flatMap((c) => c.groups.map((g) => g.document_id)))];
}

export interface Selection {
  selection: ProcessingDocumentSelection[];
  /** Why some carried documents are not part of the estimate (already processed, running, not processable, over the page cap). */
  skipped: string[];
  /** Set when nothing is selected: why (native parsers already read it, or another reason). */
  reason: string | null;
}

export const NATIVE_ONLY_REASON = "Nothing to process: data comes from native parsers";
const NO_DOCS_REASON = "Nothing to process: no document needs processing";

const BUSY = new Set<DocumentProcessingState["processing_status"]>(["queued", "running"]);

/** Chooses documents that carry the wellbores' data and still need processing. Over-cap documents need a page range, so they are skipped here. */
export function chooseDocuments(ids: string[], states: DocumentProcessingState[]): Selection {
  const byId = new Map(states.map((d) => [d.document_id, d]));
  const selection: ProcessingDocumentSelection[] = [];
  const skipped: string[] = [];
  for (const id of ids) {
    const d = byId.get(id);
    if (d === undefined) skipped.push(`${id}: not in the latest source revision`);
    else if (d.processing_status === "processed") skipped.push(`${d.original_filename}: already processed`);
    else if (BUSY.has(d.processing_status)) skipped.push(`${d.original_filename}: already queued or running`);
    else if (!d.processable) skipped.push(`${d.original_filename}: not processable${d.not_processable_reason === null ? "" : ` (${d.not_processable_reason})`}`);
    else if (d.over_page_cap) skipped.push(`${d.original_filename}: over the page cap; choose a page range under Document processing below`);
    else selection.push({ document_id: id, pages: null });
  }
  // `processable` is the server's verdict (a readable PDF that can be estimated now); a native parser does not exclude a file.
  const nativeOnly = ids.length > 0 && ids.every((id) => byId.get(id)?.processable === false);
  return { selection, skipped, reason: selection.length > 0 ? null : nativeOnly ? NATIVE_ONLY_REASON : NO_DOCS_REASON };
}

/** Every unmet code the server reported (gate reasons and unmet conditions). */
export function unmetSummary(gate: S["StartGate"]): string {
  const codes = [...new Set([...gate.unmet.map((u) => u.code), ...gate.conditions.filter((c) => !c.met).map((c) => c.code)])];
  return codes.length === 0 ? "The server reports unmet conditions." : `${codes.length} condition(s) unmet: ${codes.join(", ")}.`;
}

function FindingList({ label, items }: { label: string; items: Finding[] }) {
  if (items.length === 0) return null;
  return (
    <ul className={styles.list} aria-label={label}>
      {items.map((f) => (
        <li key={f.issue_id}>
          <strong>{f.kind === "conflict" ? "Conflict" : f.kind === "gap" ? "Gap" : "Finding"}</strong> <code>{f.code}</code>{" "}
          {f.message} <span className={styles.note}>({f.severity}; {locatorText(f.locators[0])})</span>
        </li>
      ))}
    </ul>
  );
}

/** One entry per code (the server repeats it per wellbore) with the wellbores it names; per-wellbore text stays in the detail rows. */
export function groupWarnings(items: Reason[], names: Map<string, string>): { code: string; message: string; wellbores: string[] }[] {
  const out = new Map<string, { code: string; message: string; wellbores: string[] }>();
  for (const w of items) {
    const g = out.get(w.code) ?? { code: w.code, message: w.message, wellbores: [] };
    const n = w.wellbore_id === null || w.wellbore_id === undefined ? undefined : names.get(w.wellbore_id);
    if (n !== undefined && !g.wellbores.includes(n)) g.wellbores.push(n);
    out.set(w.code, g);
  }
  return [...out.values()];
}

function Reasons({ label, items, kind }: { label: string; items: Reason[]; kind: string }) {
  if (items.length === 0) return null;
  return (
    <ul className={styles.list} aria-label={label}>
      {items.map((r, i) => (
        <li key={`${r.code}-${i}`}>
          <strong>{kind}</strong> <code>{r.code}</code> {r.message}
        </li>
      ))}
    </ul>
  );
}

function CategoryDetail({ c }: { c: Category }) {
  const name = CATEGORY_LABEL[c.category];
  const validation = new Map<string, number>();
  for (const g of c.groups) for (const [k, n] of Object.entries(g.validation_counts)) validation.set(k, (validation.get(k) ?? 0) + n);
  const nothing =
    c.gap_reasons.length === 0 &&
    c.conflicts.length === 0 &&
    c.gaps.length === 0 &&
    c.findings.length === 0 &&
    c.proposal_total === 0 &&
    validation.size === 0 &&
    c.conflicting_record_count === 0;
  if (nothing && categoryNotices(c).length === 0) return null;
  return (
    <li>
      <strong>{name}</strong>
      {c.gap_reasons.length > 0 && (
        <div>
          Gaps: {c.gap_reasons.map((g) => <code key={g}>{g} </code>)}
        </div>
      )}
      {(validation.size > 0 || c.conflicting_record_count > 0) && (
        <div>
          Record states: {validation.size === 0 ? "none" : [...validation.entries()].map(([k, n]) => `${k} ${n}`).join(", ")}
          {c.conflicting_record_count > 0 && <> ({c.conflicting_record_count} conflicting)</>}
        </div>
      )}
      <FindingList label={`${name} conflicts`} items={c.conflicts} />
      <FindingList label={`${name} gaps`} items={c.gaps} />
      <FindingList label={`${name} findings`} items={c.findings} />
      {c.proposal_total > 0 && (
        <div>
          Model proposals (not facts): {c.proposal_total}, accepted {c.accepted_proposal_count}.
        </div>
      )}
      {categoryNotices(c).map((n) => (
        <Callout key={n} tone="warning" role="status">
          <p>{n}</p>
        </Callout>
      ))}
    </li>
  );
}

function SourcesCell({ row, projectId, onOpenSource }: { row: WellboreRow; projectId: string; onOpenSource: (documentId: string) => void }) {
  const cats = row.categories.filter((c) => c.groups.length > 0);
  if (cats.length === 0) return <span>No source file carries data for this wellbore.</span>;
  return (
    <ul className={styles.list} aria-label={`Source files of ${row.wellboreName}`}>
      {cats.map((c) => (
        <li key={c.category}>
          <strong>{CATEGORY_LABEL[c.category]}:</strong>{" "}
          {c.groups.map((g, i) => (
            <Fragment key={`${g.run_id}-${g.kind}`}>
              {i > 0 && "; "}
              <a
                href={routeHash({ kind: "project", projectId, section: "sources" })}
                aria-label={`Open ${g.filename} in Sources`}
                onClick={(e) => {
                  e.preventDefault();
                  onOpenSource(g.document_id);
                }}
              >
                {g.filename}
              </a>{" "}
              <span className={styles.note}>
                ({g.record_count.toLocaleString("en-US")} {g.kind}
                {g.sample[0] !== undefined && <>; first at {locatorText(g.sample[0].locator)}</>})
              </span>
            </Fragment>
          ))}
        </li>
      ))}
    </ul>
  );
}

function RecordCounts({ row }: { row: WellboreRow }) {
  const nonzero = row.categories.filter((c) => c.record_count > 0);
  if (nonzero.length === 0) return <span>No records</span>;
  return (
    <ul className={styles.list} aria-label={`Records of ${row.wellboreName}`}>
      {nonzero.map((c) => (
        <li key={c.category}>
          {CATEGORY_LABEL[c.category]}: {c.record_count.toLocaleString("en-US")}
        </li>
      ))}
    </ul>
  );
}

interface Props {
  projectId: string;
  refreshKey: number;
  /** Switch to the Sources tab and show this file. */
  onOpenSource: (documentId: string) => void;
  /** A new estimate exists (nothing spent); the run view shows it with its separate confirm. */
  onEstimated: (runId: string) => void;
}

export function ReconstructionList({ projectId, refreshKey, onOpenSource, onEstimated }: Props) {
  const exposure = useScopedResource(keyString(["recon", "exposure", projectId, refreshKey]), (signal) => getExposure(projectId, signal));
  const gate = useScopedResource(keyString(["recon", "gate", projectId, refreshKey]), (signal) => getStartGate(projectId, signal));
  const docStates = useScopedResource(keyString(["recon", "pdocs", projectId, refreshKey]), (signal) => getProcessingDocuments(projectId, signal));
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [pending, setPending] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string[] | null>(null);
  const lock = useRef(false);
  const lastStart = useRef(0);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const data = exposure.state.kind === "ready" && exposure.state.data.project_id === projectId ? exposure.state.data : null;
  const gateData = gate.state.kind === "ready" && gate.state.data.project_id === projectId ? gate.state.data : null;
  const rows = useMemo(() => (data === null ? [] : buildRows(data, gateData)), [data, gateData]);
  const readyRows = rows.filter((r) => r.ready === true);
  const docItems = docStates.state.kind === "ready" && docStates.state.data.project_id === projectId ? docStates.state.data.items : null;
  /** Why a wellbore has nothing to estimate, from the loaded document states; `null` when it has a candidate (or states are unknown). */
  const nothingFor = (targets: WellboreRow[]): string | null => {
    if (docItems === null) return null; // unknown: the click re-reads and checks again
    const ids = [...new Set(targets.flatMap(documentIdsOf))];
    if (ids.length === 0) return "Nothing to process: no source file carries data for it";
    return chooseDocuments(ids, docItems).reason;
  };
  const allNothing = readyRows.length > 0 ? nothingFor(readyRows) : null;

  /** Estimate only: fresh document states are read at click time; nothing is confirmed or spent here. */
  const process = async (targets: WellboreRow[], name: string) => {
    // A double click sends one request: one in flight at a time, and a click right after one is a repeat.
    if (lock.current || Date.now() - lastStart.current < REPEAT_GUARD_MS) return;
    lock.current = true;
    lastStart.current = Date.now();
    setPending(name);
    setFailure(null);
    setNotice(null);
    try {
      const ids = [...new Set(targets.flatMap(documentIdsOf))];
      const docs = await getProcessingDocuments(projectId, new AbortController().signal);
      if (!alive.current) return;
      if (docs.project_id !== projectId) throw new Error("The document answer belonged to another project and was dropped.");
      const { selection, skipped, reason } = chooseDocuments(ids, docs.items);
      if (selection.length === 0) {
        setNotice(
          ids.length === 0
            ? ["No source file carries data for the selected wellbore(s), so there is nothing to estimate."]
            : [reason ?? NO_DOCS_REASON, ...skipped],
        );
        return;
      }
      // Reuse an existing unconfirmed estimate for exactly this document set instead of creating another.
      const wanted = selection.map((d) => d.document_id).sort().join(",");
      const existing = await listRuns(projectId, new AbortController().signal);
      if (!alive.current) return;
      const candidates = existing.items.filter((r) => r.status === "estimated").sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5);
      for (const c of candidates) {
        const full = await getRun(projectId, c.run_id, new AbortController().signal);
        if (!alive.current) return;
        const same =
          full.project_id === projectId &&
          full.status === "estimated" &&
          full.documents.map((d) => d.document_id).sort().join(",") === wanted &&
          full.documents.every((d) => d.pages.page_start === 1 && d.pages.page_end === d.page_count);
        if (same) {
          setNotice(["An estimate for these documents already exists and is shown below; no new estimate was requested."]);
          onEstimated(full.run_id);
          return;
        }
      }
      const key = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
      const run = await requestEstimate(projectId, selection, key);
      if (!alive.current) return;
      if (skipped.length > 0) setNotice(["Some documents are not part of this estimate:", ...skipped]);
      onEstimated(run.run_id);
    } catch (err) {
      if (alive.current) setFailure(toFailure(err));
    } finally {
      lock.current = false;
      if (alive.current) setPending(null);
    }
  };

  const reloadAll = () => {
    exposure.reload();
    gate.reload();
  };
  const toggle = (id: string) => {
    const next = new Set(open);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setOpen(next);
  };

  return (
    <section aria-labelledby="rc-list" className={styles.section}>
      <Title order={6} id="rc-list">
        Identified wells and wellbores
      </Title>
      <p className={styles.note}>
        Wellbores the system identified, ready ones first. Readiness is the server&rsquo;s start gate; nothing is computed
        in the browser. Wellbores named without a block stay separate until a merge is accepted (merge review is not yet
        available).
      </p>
      {exposure.state.kind === "loading" && <LoadingState label="Loading identified wellbores…" status />}
      {exposure.state.kind === "error" && (
        <ErrorState
          message={`Identified wellbores could not be loaded: ${exposure.state.error.message}`}
          requestId={exposure.state.error.requestId}
          onRetry={exposure.reload}
          retryLabel="Retry loading identified wellbores"
        />
      )}
      {exposure.state.kind === "ready" && data === null && (
        <ErrorState message="The wellbore answer belonged to another project and was dropped." requestId={null} onRetry={exposure.reload} />
      )}
      {gate.state.kind === "error" && (
        <ErrorState
          message={`Readiness could not be loaded, so no wellbore can be processed from here: ${gate.state.error.message}`}
          requestId={gate.state.error.requestId}
          onRetry={gate.reload}
          retryLabel="Retry loading readiness"
        />
      )}
      {gate.state.kind === "ready" && gateData === null && (
        <ErrorState message="The readiness answer belonged to another project and was dropped." requestId={null} onRetry={gate.reload} />
      )}
      {data !== null && !data.resolved_current && (
        <Callout tone="warning" role="status">
          <p>Stored identities are out of date with the latest extraction; resolve identities again before trusting this grouping.</p>
        </Callout>
      )}
      {data !== null && data.unresolved_record_count > 0 && (
        <Callout tone="warning" role="status">
          <p>{data.unresolved_record_count} record(s) have no resolved wellbore and are not listed below.</p>
        </Callout>
      )}
      {gateData !== null && !gateData.can_start && (
        <Callout tone="warning" role="status">
          <p>
            <strong>No wellbore is ready to process.</strong> {unmetSummary(gateData)}
          </p>
        </Callout>
      )}
      {gateData !== null && gateData.warnings.length > 0 && (
        <Callout tone="warning" label="Gate warnings">
          <ul className={styles.list} aria-label="Gate warnings">
            {groupWarnings(gateData.warnings, new Map(rows.map((r) => [r.wellboreId, r.wellboreName]))).map((g) => (
              <li key={g.code}>
                <strong>Warning</strong> <code>{g.code}</code> {g.message}
                {g.wellbores.length > 0 && <> Wellbores: {g.wellbores.join(", ")}.</>}
              </li>
            ))}
          </ul>
        </Callout>
      )}
      {data !== null && rows.length === 0 && (
        <EmptyState title="No wellbore identified">
          <p>No data can be grouped under a wellbore yet. Upload and parse sources, then resolve identities.</p>
        </EmptyState>
      )}
      {data !== null && rows.length > 0 && (
        <>
          <div className={styles.actions}>
            <Button
              disabled={readyRows.length === 0 || allNothing !== null || pending !== null}
              aria-describedby={allNothing !== null ? "rc-all-reason" : undefined}
              loading={pending === "all"}
              onClick={() => void process(readyRows, "all")}
            >
              Process all ready wellbores ({readyRows.length})
            </Button>
            {allNothing !== null && (
              <span className={styles.note} id="rc-all-reason">
                {allNothing}
              </span>
            )}
            <span className={styles.note}>
              Requests a free estimate for the documents that carry these wellbores&rsquo; data and are not processed yet.
              Nothing starts or is spent until you confirm the estimate below. Today a run is a stub step: it is not
              reconstruction, there is no OCR, and merge review is not available.
            </span>
          </div>
          {failure !== null && (
            <Callout tone="danger" role="alert">
              <p>
                The estimate was not created: {failure.message}
                {failure.code !== null && <> (<code>{failure.code}</code>)</>}. Nothing was started or spent.
              </p>
              {failure.requestId !== null && <p>Request ID: {failure.requestId}</p>}
            </Callout>
          )}
          {notice !== null && (
            <Callout tone="info" role="status">
              <ul className={styles.list}>
                {notice.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </Callout>
          )}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard-scrollable region */}
          <div className={styles.scroll} role="region" aria-label="Identified wellbores table" tabIndex={0}>
            <Table captionSide="top">
              <Table.Caption>Identified wells and wellbores, ready to process first</Table.Caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Wellbore</Table.Th>
                  <Table.Th scope="col">Readiness</Table.Th>
                  <Table.Th scope="col">Records per category</Table.Th>
                  <Table.Th scope="col">Sources</Table.Th>
                  <Table.Th scope="col">Action</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((r) => {
                  const expanded = open.has(r.wellboreId);
                  const detailId = `rc-detail-${r.wellboreId}`;
                  return (
                    <Fragment key={r.wellboreId}>
                      <Table.Tr className={r.ready === true ? styles.readyRow : undefined}>
                        <Table.Th scope="row">
                          <div className={styles.note}>Well {r.well}</div>
                          <div>Wellbore {r.wellboreName}</div>
                          {r.blockNotStated && (
                            <Chip spec={BLOCK} label="Block not stated" />
                          )}
                          <div>
                            <Button
                              variant="subtle"
                              size="compact-xs"
                              aria-expanded={expanded}
                              aria-controls={detailId}
                              aria-label={`${expanded ? "Hide" : "Show"} details of ${r.wellboreName}`}
                              leftSection={expanded ? <ChevronUp size={12} aria-hidden="true" /> : <ChevronDown size={12} aria-hidden="true" />}
                              onClick={() => toggle(r.wellboreId)}
                            >
                              {expanded ? "Hide details" : "Details"}
                            </Button>
                          </div>
                        </Table.Th>
                        <Table.Td>
                          {r.ready === true && <Chip spec={READY} label="Ready" />}
                          {r.ready === false && <Chip spec={NOT_READY} label="Not ready" />}
                          {r.ready === null && <Chip spec={UNKNOWN} label="Readiness unknown" />}
                          {r.ready === false &&
                            (r.gate.unmet.length === 0 ? (
                              <p className={styles.note}>The server gave no reason.</p>
                            ) : (
                              <Reasons label={`Why ${r.wellboreName} is not ready`} items={r.gate.unmet} kind="Not met" />
                            ))}
                          {r.ready === null && <p className={styles.note}>The start gate could not be read.</p>}
                        </Table.Td>
                        <Table.Td>
                          <RecordCounts row={r} />
                        </Table.Td>
                        <Table.Td>
                          <SourcesCell row={r} projectId={projectId} onOpenSource={onOpenSource} />
                        </Table.Td>
                        <Table.Td>
                          {r.ready === true && nothingFor([r]) !== null ? (
                            <span className={styles.note}>{nothingFor([r])}</span>
                          ) : r.ready === true ? (
                            <Button
                              size="xs"
                              aria-label={`Process ${r.wellboreName}`}
                              disabled={pending !== null}
                              loading={pending === r.wellboreId}
                              onClick={() => void process([r], r.wellboreId)}
                            >
                              Process
                            </Button>
                          ) : (
                            <span className={styles.note}>Not available: not ready</span>
                          )}
                        </Table.Td>
                      </Table.Tr>
                      {expanded && (
                        <Table.Tr id={detailId}>
                          <Table.Td colSpan={5}>
                            <Reasons label={`Warnings of ${r.wellboreName}`} items={r.gate.warnings} kind="Warning" />
                            <ul className={styles.list} aria-label={`Gaps, conflicts and findings of ${r.wellboreName}`}>
                              {r.categories.map((c) => (
                                <CategoryDetail key={c.category} c={c} />
                              ))}
                            </ul>
                          </Table.Td>
                        </Table.Tr>
                      )}
                    </Fragment>
                  );
                })}
              </Table.Tbody>
            </Table>
          </div>
        </>
      )}
      <div className={styles.actions}>
        <Button size="xs" variant="default" leftSection={<RefreshCw size={14} aria-hidden="true" />} onClick={reloadAll}>
          Refresh wellbores
        </Button>
      </div>
    </section>
  );
}
