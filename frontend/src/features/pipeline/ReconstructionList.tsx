import { Fragment, useMemo, useState } from "react";
import { Button, Table, Title } from "@mantine/core";
import { ChevronDown, ChevronUp, CircleCheck, CircleHelp, CircleX, Info, RefreshCw } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState } from "../../design";
import { routeHash } from "../../app/shell/route";
import type { components } from "../../api/generated";
import { keyString } from "../projects/keys";
import { useScopedResource } from "../projects/scope";
import { getExposure, getStartGate } from "./api";
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
  const cats = row.categories.filter((c) => c.groups.length > 0 || c.record_count > 0);
  if (cats.length === 0) return <span>No source file carries data for this wellbore.</span>;
  return (
    <ul className={styles.list} aria-label={`Source files of ${row.wellboreName}`}>
      {cats.map((c) => (
        <li key={c.category}>
          <strong>
            {CATEGORY_LABEL[c.category]} - {c.record_count.toLocaleString("en-US")} {c.record_count === 1 ? "record" : "records"}
          </strong>
          <ul className={styles.list} aria-label={`${CATEGORY_LABEL[c.category]} files of ${row.wellboreName}`}>
            {c.groups.map((g) => (
              <li key={`${g.run_id}-${g.kind}`}>
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
              </li>
            ))}
          </ul>
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
}

export function ReconstructionList({ projectId, refreshKey, onOpenSource }: Props) {
  const exposure = useScopedResource(keyString(["recon", "exposure", projectId, refreshKey]), (signal) => getExposure(projectId, signal));
  const gate = useScopedResource(keyString(["recon", "gate", projectId, refreshKey]), (signal) => getStartGate(projectId, signal));
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const data = exposure.state.kind === "ready" && exposure.state.data.project_id === projectId ? exposure.state.data : null;
  const gateData = gate.state.kind === "ready" && gate.state.data.project_id === projectId ? gate.state.data : null;
  const rows = useMemo(() => (data === null ? [] : buildRows(data, gateData)), [data, gateData]);
  const readyRows = rows.filter((r) => r.ready === true);
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
            <Button disabled aria-describedby="rc-all-reason">
              Reconstruct all ready wellbores ({readyRows.length})
            </Button>
            <span className={styles.note} id="rc-all-reason">
              Reconstruction start arrives in the next update. Nothing starts or is spent from this page yet. There is no
              OCR and merge review is not available.
            </span>
          </div>
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
                          {r.ready === true ? (
                            <>
                              <Button size="xs" disabled aria-describedby={`rc-start-${r.wellboreId}`}>
                                Reconstruct
                              </Button>
                              <span className="fl-sr-only" id={`rc-start-${r.wellboreId}`}>
                                Reconstruction start arrives in the next update
                              </span>
                            </>
                          ) : (
                            <span className={styles.note}>Not available: not ready</span>
                          )}
                        </Table.Td>
                      </Table.Tr>
                      {expanded && (
                        <Table.Tr id={detailId}>
                          <Table.Td colSpan={4}>
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
