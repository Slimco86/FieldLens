import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Button, Table, Title } from "@mantine/core";
import { ChevronDown, ChevronUp, CircleCheck, CircleHelp, CircleX, Info, RefreshCw } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState } from "../../design";
import { routeHash } from "../../app/shell/route";
import { ApiError } from "../../api/client";
import type { components } from "../../api/generated";
import { keyString } from "../projects/keys";
import { toFailure, useScopedResource, type Failure } from "../projects/scope";
import { usePolled } from "../uploads/usePolled";
import {
  cancelReconstructionRun,
  confirmReconstructionEstimate,
  getExposure,
  getStartGate,
  listReconstructionRuns,
  requestReconstructionEstimate,
  retryReconstructionRun,
  type ReconstructionEstimate,
} from "./api";
import { EstimateDialog } from "./EstimateDialog";
import { locatorText } from "./locator";
import { RunCell, RunDetail } from "./RunViews";
import { isActive, latestByWellbore } from "./runs";
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

export { locatorText };

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
  /** Names merged into this wellbore by an accepted proposal (revertible in the match review). */
  mergedFrom: S["MergedAlias"][];
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
        mergedFrom: b.merged_from ?? [],
      };
    }),
  );
  return [...rows.filter((r) => r.ready === true), ...rows.filter((r) => r.ready !== true)];
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

/** One entry per file within a category: record counts of its groups are combined; the first human locator is shown. */
export function filesOf(c: Category): { document_id: string; filename: string; records: number; first: Record<string, unknown> | undefined }[] {
  const out = new Map<string, { document_id: string; filename: string; records: number; first: Record<string, unknown> | undefined }>();
  for (const g of c.groups) {
    const cur = out.get(g.document_id) ?? { document_id: g.document_id, filename: g.filename, records: 0, first: undefined };
    cur.records += g.record_count;
    cur.first ??= g.sample[0]?.locator;
    out.set(g.document_id, cur);
  }
  return [...out.values()];
}

function SourcesCell({ row, projectId, onOpenSource }: { row: WellboreRow; projectId: string; onOpenSource: (documentId: string) => void }) {
  const cats = row.categories.filter((c) => c.groups.length > 0 || c.record_count > 0);
  const merged =
    row.mergedFrom.length === 0 ? null : (
      <p className={styles.note} aria-label={`Merged into ${row.wellboreName}`}>
        Merged from: {row.mergedFrom.map((a) => a.name).join(", ")}. Their files are listed here with this wellbore.
      </p>
    );
  if (cats.length === 0)
    return (
      <>
        {merged}
        <span>No source file carries data for this wellbore.</span>
      </>
    );
  return (
    <div aria-label={`Source files of ${row.wellboreName}`} role="group">
      {merged}
      {cats.map((c) => (
        <div key={c.category}>
          <h6 className={styles.catHeading}>
            {CATEGORY_LABEL[c.category]} - {c.record_count.toLocaleString("en-US")} {c.record_count === 1 ? "record" : "records"}
          </h6>
          <ul className={styles.list} aria-label={`${CATEGORY_LABEL[c.category]} files of ${row.wellboreName}`}>
            {filesOf(c).map((f) => (
              <li key={f.document_id}>
                <a
                  href={routeHash({ kind: "project", projectId, section: "sources" })}
                  aria-label={`Open ${f.filename} in Sources`}
                  onClick={(e) => {
                    e.preventDefault();
                    onOpenSource(f.document_id);
                  }}
                >
                  {f.filename}
                </a>{" "}
                <span className={styles.note}>
                  ({f.records.toLocaleString("en-US")} {f.records === 1 ? "record" : "records"}
                  {f.first !== undefined && <>; first at {locatorText(f.first)}</>})
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

interface Props {
  projectId: string;
  refreshKey: number;
  /** Switch to the Sources tab and show this file. */
  onOpenSource: (documentId: string) => void;
}

/** Adds the server's per-wellbore refusal reasons (422 not_ready) to the message when the response carries them. */
function withReason(f: Failure, e: unknown): Failure {
  const details = e instanceof ApiError ? e.details : null;
  const refusals = details?.refusals;
  if (!Array.isArray(refusals)) return f;
  const parts = refusals.flatMap((r: unknown) => {
    if (typeof r !== "object" || r === null) return [];
    const o = r as { wellbore_name?: unknown; reason?: unknown; gate_reasons?: unknown };
    const why = Array.isArray(o.gate_reasons)
      ? o.gate_reasons.map((g: { message?: unknown }) => (typeof g?.message === "string" ? g.message : "")).filter(Boolean).join("; ")
      : typeof o.reason === "string"
        ? o.reason
        : "";
    const name = typeof o.wellbore_name === "string" ? `${o.wellbore_name}: ` : "";
    return why === "" ? [] : [`${name}${why}`];
  });
  return parts.length === 0 ? f : { ...f, message: `${f.message} (${parts.join(" | ")})` };
}

export function ReconstructionList({ projectId, refreshKey, onOpenSource }: Props) {
  const exposure = useScopedResource(keyString(["recon", "exposure", projectId, refreshKey]), (signal) => getExposure(projectId, signal));
  const gate = useScopedResource(keyString(["recon", "gate", projectId, refreshKey]), (signal) => getStartGate(projectId, signal));
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const [version, setVersion] = useState(0);
  const runs = usePolled(
    keyString(["recon", "runs", projectId, refreshKey]),
    (signal) => listReconstructionRuns(projectId, signal),
    (d) => d.items.some(isActive),
    String(version),
  );
  const [pending, setPending] = useState<ReconstructionEstimate | null>(null);
  const [pendingScope, setPendingScope] = useState("");
  const [pendingProject, setPendingProject] = useState<string | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmFailure, setConfirmFailure] = useState<Failure | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyRun, setBusyRun] = useState<string | null>(null);
  const lock = useRef(false);
  const lastStart = useRef(0);
  const trigger = useRef<HTMLElement | null>(null);
  const current = useRef(projectId);
  useEffect(() => {
    current.current = projectId;
    return () => {
      current.current = "";
    };
  }, [projectId]);

  const data = exposure.state.kind === "ready" && exposure.state.data.project_id === projectId ? exposure.state.data : null;
  const gateData = gate.state.kind === "ready" && gate.state.data.project_id === projectId ? gate.state.data : null;
  const rows = useMemo(() => (data === null ? [] : buildRows(data, gateData)), [data, gateData]);
  const readyRows = rows.filter((r) => r.ready === true);
  const runItems = runs.state.kind === "ready" ? runs.state.data.items.filter((r) => r.project_id === projectId) : null;
  const latest = useMemo(() => latestByWellbore(runItems ?? []), [runItems]);
  // The "started" notice is only true while something is running; clear it when the active runs finish.
  const anyActive = (runItems ?? []).some(isActive);
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !anyActive) setNotice((n) => (n !== null && n.startsWith("Reconstruction started") ? null : n));
    wasActive.current = anyActive;
  }, [anyActive]);

  /** Estimate only; opens the confirm dialog. A double click sends one request (one in flight, repeats within a second ignored). */
  const startEstimate = async (ids: string[] | null, scope: string) => {
    if (lock.current || Date.now() - lastStart.current < 1000) return;
    trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    lock.current = true;
    lastStart.current = Date.now();
    setStarting(scope);
    setFailure(null);
    setNotice(null);
    try {
      const est = await requestReconstructionEstimate(projectId, ids);
      if (current.current !== projectId) return;
      if (est.project_id !== projectId) throw new Error("The estimate belonged to another project and was dropped.");
      if (est.estimate_id === null) {
        // Duplicate start: the server returns the active run(s); show them, do not error.
        setNotice("Every selected wellbore already has an active run. It is shown in the list; nothing new was started.");
        setVersion((n) => n + 1);
        restoreFocus();
      } else {
        setConfirmFailure(null);
        setPendingScope(scope);
        setPendingProject(projectId);
        setPending(est);
      }
    } catch (e) {
      if (current.current === projectId) setFailure(withReason(toFailure(e), e));
      restoreFocus();
    } finally {
      lock.current = false;
      if (current.current === projectId) setStarting(null);
    }
  };

  /** The trigger is disabled while the request runs, which drops focus to the body; put it back. */
  const restoreFocus = () => {
    const el = trigger.current;
    if (el !== null) window.setTimeout(() => el.isConnected && !el.matches(":disabled") && el.focus(), 50);
  };

  /** Close the dialog and give focus back to the control that opened it. */
  const closeDialog = () => {
    setPending(null);
    const el = trigger.current;
    if (el !== null) window.setTimeout(() => el.isConnected && el.focus(), 0);
  };

  const confirm = async () => {
    if (pending === null || pending.estimate_id === null || confirming) return;
    setConfirming(true);
    setConfirmFailure(null);
    try {
      await confirmReconstructionEstimate(projectId, pending.estimate_id, pending.total_estimated_usd);
      if (current.current !== projectId) return;
      closeDialog();
      setNotice("Reconstruction started. Progress is shown per wellbore; runs end partial until agent steps exist.");
      setVersion((n) => n + 1);
    } catch (e) {
      if (current.current === projectId) setConfirmFailure(toFailure(e));
    } finally {
      setConfirming(false);
    }
  };

  const cancelRun = async (runId: string) => {
    setBusyRun(runId);
    setFailure(null);
    try {
      await cancelReconstructionRun(projectId, runId);
      setNotice(null);
      if (current.current === projectId) setVersion((n) => n + 1);
    } catch (e) {
      if (current.current === projectId) setFailure(toFailure(e));
    } finally {
      setBusyRun(null);
    }
  };

  const retryRun = async (runId: string, scope: string) => {
    trigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setBusyRun(runId);
    setFailure(null);
    try {
      const est = await retryReconstructionRun(projectId, runId);
      if (current.current !== projectId) return;
      if (est.project_id !== projectId) throw new Error("The estimate belonged to another project and was dropped.");
      setConfirmFailure(null);
      setPendingScope(scope);
      setPendingProject(projectId);
      setPending(est);
    } catch (e) {
      if (current.current === projectId) setFailure(toFailure(e));
    } finally {
      setBusyRun(null);
    }
  };

  const reloadAll = () => {
    exposure.reload();
    gate.reload();
    setVersion((n) => n + 1);
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
              disabled={readyRows.length === 0 || starting !== null}
              loading={starting === "all ready wellbores"}
              aria-describedby="rc-all-reason"
              onClick={() => void startEstimate(null, "all ready wellbores")}
            >
              Reconstruct all ready wellbores ({readyRows.length})
            </Button>
            <span className={styles.note} id="rc-all-reason">
              Shows what each step would do first; nothing starts until you confirm it. Wellbore matches are only
              proposed: you accept or reject them in Wellbore name matches above.
            </span>
          </div>
          {failure !== null && (
            <Callout tone="danger" role="alert">
              <p>
                The request failed: {failure.message}
                {failure.code !== null && <> (<code>{failure.code}</code>)</>}. Nothing was started or spent.
              </p>
              {failure.requestId !== null && <p>Request ID: {failure.requestId}</p>}
            </Callout>
          )}
          {notice !== null && (
            <Callout tone="info" role="status">
              <p>{notice}</p>
            </Callout>
          )}
          {runs.state.kind === "error" && (
            <ErrorState
              message={`Run state could not be loaded: ${runs.state.error.message}`}
              requestId={runs.state.error.requestId}
              onRetry={runs.reload}
              retryLabel="Retry loading run state"
            />
          )}
          {runs.state.kind === "ready" && runs.state.refreshError !== null && (
            <Callout tone="warning" role="alert">
              <p>Refreshing run state failed: {runs.state.refreshError.message}. The list below may be out of date.</p>
            </Callout>
          )}
          {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard-scrollable region */}
          <div className={styles.scroll} role="region" aria-label="Identified wellbores table" tabIndex={0}>
            <Table captionSide="top">
              <Table.Caption>Identified wells and wellbores, ready first</Table.Caption>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th scope="col">Wellbore</Table.Th>
                  <Table.Th scope="col">Readiness</Table.Th>
                  <Table.Th scope="col">Sources</Table.Th>
                  <Table.Th scope="col">Action</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((r) => {
                  const expanded = open.has(r.wellboreId);
                  const detailId = `rc-detail-${r.wellboreId}`;
                  const run = latest.get(r.wellboreId);
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
                          <SourcesCell row={r} projectId={projectId} onOpenSource={onOpenSource} />
                        </Table.Td>
                        <Table.Td>
                          {run !== undefined && (
                            <RunCell
                              run={run}
                              busy={busyRun === run.run_id}
                              detailsOpen={expanded}
                              onDetails={() => toggle(r.wellboreId)}
                              onCancel={() => void cancelRun(run.run_id)}
                              onRetry={() => void retryRun(run.run_id, r.wellboreName)}
                            />
                          )}
                          {r.ready === true ? (
                            <Button
                              size="xs"
                              disabled={starting !== null || (run !== undefined && isActive(run))}
                              loading={starting === r.wellboreName}
                              aria-label={`Reconstruct ${r.wellboreName}`}
                              onClick={() => void startEstimate([r.wellboreId], r.wellboreName)}
                            >
                              Reconstruct
                            </Button>
                          ) : (
                            <span className={styles.note}>Not available: not ready</span>
                          )}
                        </Table.Td>
                      </Table.Tr>
                      {expanded && (
                        <Table.Tr id={detailId}>
                          <Table.Td colSpan={4}>
                            {run !== undefined && <RunDetail run={run} onOpenSource={onOpenSource} />}
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
      {pending !== null && pendingProject === projectId && (
        <EstimateDialog
          estimate={pending}
          scope={pendingScope}
          confirming={confirming}
          failure={confirmFailure}
          onConfirm={() => void confirm()}
          onClose={closeDialog}
        />
      )}
    </section>
  );
}
