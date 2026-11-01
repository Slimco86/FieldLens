import { useMemo } from "react";
import { Button, Table, Title } from "@mantine/core";
import { Info, RefreshCw } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState, StatusChip, type ChipSpec } from "../../design";
import type { components } from "../../api/generated";
import { keyString } from "../projects/keys";
import { useScopedResource, type Resource } from "../projects/scope";
import { getIdentity, loadAllDocuments, loadReports, loadSeries, MAX_DOCUMENT_PAGES, MAX_REPORTS, MAX_SERIES_PAGES, SERIES_PAGE } from "./api";
import { countBy, groupSeries, unitWarnings } from "./model";
import styles from "./ProjectOverview.module.css";

type S = components["schemas"];

const EXTRACTION_LABEL: Record<S["ExtractionState"], string> = {
  pending_extraction: "Waiting for extraction",
  unsupported: "No extraction profile",
  extracted: "Extracted",
  extracted_with_issues: "Extracted with findings",
  extraction_failed: "Extraction failed",
};
const STORAGE_LABEL: Record<S["StorageState"], string> = {
  pending_verification: "Verifying",
  stored: "Stored",
  quarantined: "Quarantined",
};
const SEVERITY_LABEL: Record<S["IssueSeverity"], string> = { error: "Error", warning: "Warning", info: "Info" };
const SHOWN_ISSUES = 10;

const fmt = (n: number): string => n.toLocaleString("en-US");
const range = (a: number | null, b: number | null): string => (a === null || b === null ? "not available" : `${a} to ${b}`);

function Failure({ what, state, onRetry }: { what: string; state: Extract<Resource<unknown>, { kind: "error" }>; onRetry: () => void }) {
  return (
    <ErrorState
      message={`${what} could not be loaded: ${state.error.message}`}
      requestId={state.error.requestId}
      onRetry={onRetry}
      retryLabel={`Retry loading ${what.toLowerCase()}`}
    />
  );
}

function Section({ id, title, note, children }: { id: string; title: string; note?: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={id} className={styles.section}>
      <Title order={6} id={id}>
        {title}
      </Title>
      {note !== undefined && <p className={styles.note}>{note}</p>}
      {children}
    </section>
  );
}

function Counts({ label, rows }: { label: string; rows: [string, number][] }) {
  return (
    <ul className={styles.counts} aria-label={label}>
      {rows.map(([name, n]) => (
        <li key={name}>
          <span className={styles.count}>{fmt(n)}</span> {name}
        </li>
      ))}
    </ul>
  );
}

function Scroll({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard-scrollable region
    <div className={styles.scroll} role="region" aria-label={`${label} table`} tabIndex={0}>
      {children}
    </div>
  );
}

const NOT_YET: { name: string; why: string }[] = [
  { name: "Merge proposals for duplicate wells or wellbores", why: "needs the merge-proposal API (TASK-057)." },
  { name: "Equipment, reconstruction and scene", why: "need a reconstruction run and a published model revision; this build has none." },
];

const NOT_YET_CHIP: ChipSpec = { tone: "neutral", icon: Info };

export function ProjectOverview({ projectId, revisionId }: { projectId: string; revisionId: string | null }) {
  const docsKey = revisionId === null ? null : keyString(["overview", "documents", projectId, revisionId]);
  const docs = useScopedResource(docsKey, (signal) => loadAllDocuments(projectId, revisionId as string, signal));
  const docsData = docs.state.kind === "ready" ? docs.state.data : null;
  const reportsKey = docsData === null ? null : keyString(["overview", "reports", projectId, String(revisionId), String(docsData.docs.length)]);
  const reports = useScopedResource(reportsKey, (signal) => loadReports(projectId, (docsData?.docs ?? []), signal));
  const identity = useScopedResource(revisionId === null ? null : keyString(["overview", "identity", projectId, revisionId]), (signal) => getIdentity(projectId, signal));
  const series = useScopedResource(revisionId === null ? null : keyString(["overview", "series", projectId, revisionId]), (signal) => loadSeries(projectId, signal));

  const filenames = useMemo(() => new Map((docsData?.docs ?? []).map((d) => [d.id, d.filename])), [docsData]);
  const seriesData = series.state.kind === "ready" ? series.state.data : null;
  const groups = useMemo(() => (seriesData === null ? [] : groupSeries(seriesData.items, filenames)), [seriesData, filenames]);
  const warnings = useMemo(() => unitWarnings(groups), [groups]);

  const refresh = () => {
    docs.reload();
    reports.reload();
    identity.reload();
    series.reload();
  };

  return (
    <section aria-labelledby="overview-title" className={styles.overview}>
      <div className={styles.head}>
        <Title order={5} id="overview-title">
          Project data overview
        </Title>
        <Button
          size="xs"
          variant="default"
          leftSection={<RefreshCw size={14} aria-hidden="true" />}
          onClick={refresh}
          aria-label="Refresh project data overview"
        >
          Refresh
        </Button>
      </div>
      <p className={styles.note}>
        Counts and values below are read from the project APIs as stored, in the units written in the source files. They
        describe what was found in the files, not verified engineering results.
      </p>

      {revisionId === null && (
        <EmptyState title="No data yet">
          <p>This project has no imported source revision. Upload files below to see what they contain.</p>
        </EmptyState>
      )}
      {revisionId !== null && (<>
      <Section id="ov-documents" title="Documents" note="Latest source revision.">
        {docs.state.kind === "loading" && <LoadingState label="Loading documents…" />}
        {docs.state.kind === "error" && <Failure what="Documents" state={docs.state} onRetry={docs.reload} />}
        {docsData !== null && docsData.docs.length === 0 && (
          <EmptyState title="No documents in the latest revision">
            <p>The latest source revision has no files.</p>
          </EmptyState>
        )}
        {docsData !== null && docsData.docs.length > 0 && (
          <>
            <p className={styles.total}>
              <span className={styles.count}>{fmt(docsData.docs.length)}</span> documents
            </p>
            {docsData.truncated && (
              <Callout tone="warning">
                Only the first {fmt(MAX_DOCUMENT_PAGES * 50)} documents were counted; the project has more.
              </Callout>
            )}
            <Counts
              label="Documents by processing state"
              rows={countBy(docsData.docs, (d) => EXTRACTION_LABEL[d.extraction]).map(([k, n]) => [`${k}`, n])}
            />
            <Counts label="Documents by storage state" rows={countBy(docsData.docs, (d) => STORAGE_LABEL[d.storage])} />
            <Counts label="Documents by detected format" rows={countBy(docsData.docs, (d) => d.format)} />
          </>
        )}
      </Section>

      <Section
        id="ov-coverage"
        title="Extraction coverage per record kind"
        note="Record counts and each document's own stated coverage (complete, partial or unknown), per kind found by extraction."
      >
        {docsData === null && revisionId !== null && docs.state.kind !== "error" && <LoadingState label="Waiting for documents…" />}
        {docsData !== null && reports.state.kind === "loading" && <LoadingState label="Reading extraction reports…" />}
        {reports.state.kind === "error" && <Failure what="Extraction reports" state={reports.state} onRetry={reports.reload} />}
        {reports.state.kind === "ready" && (
          <>
            {reports.state.data.capped && (
              <Callout tone="warning">
                Reports were read for the first {MAX_REPORTS} of {reports.state.data.eligible} documents that have extraction output.
              </Callout>
            )}
            {reports.state.data.failed > 0 && (
              <Callout tone="warning" role="alert">
                {reports.state.data.failed} extraction report(s) could not be read; their records and issues are not counted.
              </Callout>
            )}
            {reports.state.data.kinds.length === 0 ? (
              <EmptyState title="No extracted records">
                <p>No document has produced extracted records yet ({reports.state.data.read} report(s) read).</p>
              </EmptyState>
            ) : (
              <Scroll label="Extraction coverage per record kind">
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Record kind</Table.Th>
                      <Table.Th className={styles.num}>Records</Table.Th>
                      <Table.Th className={styles.num}>Documents</Table.Th>
                      <Table.Th>Stated coverage of those documents</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {reports.state.data.kinds.map((k) => (
                      <Table.Tr key={k.kind}>
                        <Table.Td>{k.kind}</Table.Td>
                        <Table.Td className={styles.num}>{fmt(k.records)}</Table.Td>
                        <Table.Td className={styles.num}>{fmt(k.documents)}</Table.Td>
                        <Table.Td>
                          {k.complete} complete, {k.partial} partial, {k.unknown} unknown
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Scroll>
            )}
          </>
        )}
      </Section>

      <Section id="ov-issues" title="Issues by severity" note="Data-quality findings from extraction reports, with the first source location each cites.">
        {reports.state.kind === "loading" && <LoadingState label="Reading extraction reports…" />}
        {reports.state.kind === "error" && <p>Issues need the extraction reports, which could not be loaded (see above).</p>}
        {reports.state.kind === "ready" &&
          (reports.state.data.issues.length === 0 ? (
            <EmptyState title="No issues reported">
              <p>None of the {reports.state.data.read} extraction report(s) read lists a finding.</p>
            </EmptyState>
          ) : (
            <>
              <div className={styles.chips} role="group" aria-label="Issue counts by severity">
                {(["error", "warning", "info"] as const).map((sev) => (
                  <StatusChip key={sev} kind="severity" value={sev} label={`${SEVERITY_LABEL[sev]}: ${reports.state.kind === "ready" ? reports.state.data.severity[sev] : 0}`} />
                ))}
              </div>
              <ol className={styles.issues} aria-label={`First ${SHOWN_ISSUES} issues, most severe first`}>
                {reports.state.data.issues.slice(0, SHOWN_ISSUES).map((i) => (
                  <li key={i.issueId}>
                    <StatusChip kind="severity" value={i.severity} label={SEVERITY_LABEL[i.severity]} /> <code>{i.code}</code>{" "}
                    {i.message}
                    <span className={styles.muted}>
                      {" "}
                      — {i.filename}
                      {i.locator !== null ? `, ${i.locator}` : ", no source location cited"}
                    </span>
                  </li>
                ))}
              </ol>
              {reports.state.data.issues.length > SHOWN_ISSUES && (
                <p className={styles.muted}>
                  Showing {SHOWN_ISSUES} of {fmt(reports.state.data.issues.length)}. Open a document below for all of its findings.
                </p>
              )}
            </>
          ))}
      </Section>

      <Section
        id="ov-wells"
        title="Resolved wells and wellbores"
        note="Identity resolution over extracted records. Record counts are those the identity API links to each wellbore."
      >
        {identity.state.kind === "loading" && <LoadingState label="Loading identity…" />}
        {identity.state.kind === "error" && <Failure what="Well identity" state={identity.state} onRetry={identity.reload} />}
        {identity.state.kind === "ready" && (
          <>
            {!identity.state.data.resolved_current && (
              <Callout tone="warning">
                Stored identity rows do not match the current extraction output; the resolution is out of date.
              </Callout>
            )}
            {identity.state.data.wells.length === 0 ? (
              <EmptyState title="No wells resolved">
                <p>No well identity has been resolved from the extracted records.</p>
              </EmptyState>
            ) : (
              <Scroll label="Resolved wells and wellbores">
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Well / wellbore</Table.Th>
                      <Table.Th className={styles.num}>Documents</Table.Th>
                      <Table.Th className={styles.num}>Records</Table.Th>
                      <Table.Th>Records per kind</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {identity.state.data.wells.flatMap((w) => [
                      <Table.Tr key={w.well_id}>
                        <Table.Th scope="row">Well {w.name}</Table.Th>
                        <Table.Td className={styles.num}>{fmt(w.document_count)}</Table.Td>
                        <Table.Td className={styles.num}>{fmt(w.record_count)}</Table.Td>
                        <Table.Td>{w.wellbores.length} wellbore(s)</Table.Td>
                      </Table.Tr>,
                      ...w.wellbores.map((b) => (
                        <Table.Tr key={b.wellbore_id}>
                          <Table.Td className={styles.indent}>Wellbore {b.name}</Table.Td>
                          <Table.Td className={styles.num}>{fmt(b.document_count)}</Table.Td>
                          <Table.Td className={styles.num}>{fmt(b.record_count)}</Table.Td>
                          <Table.Td>
                            {(b.record_counts ?? []).length === 0
                              ? "none"
                              : (b.record_counts ?? []).map((c) => `${c.kind} ${fmt(c.records)}`).join(", ")}
                          </Table.Td>
                        </Table.Tr>
                      )),
                    ])}
                  </Table.Tbody>
                </Table>
              </Scroll>
            )}
            {identity.state.data.unresolved.length > 0 && (
              <Callout tone="warning">
                {fmt(identity.state.data.unresolved_record_count)} record(s) have no resolved well:{" "}
                {identity.state.data.unresolved
                  .map((u) => `${u.reason.replaceAll("_", " ")} (${u.record_count} records${u.labels.length > 0 ? `, e.g. ${u.labels.slice(0, 3).join("; ")}` : ""})`)
                  .join("; ")}
                .
              </Callout>
            )}
          </>
        )}
      </Section>

      <Section
        id="ov-series"
        title="Log and production series per wellbore"
        note="Wellbore labels are shown as written in the source files and are not mapped to the resolved wellbores above. Units are as stated; a missing unit is never filled in."
      >
        {series.state.kind === "loading" && <LoadingState label="Loading series…" />}
        {series.state.kind === "error" && <Failure what="Series" state={series.state} onRetry={series.reload} />}
        {seriesData !== null && seriesData.total === 0 && (
          <EmptyState title="No series">
            <p>No log or production series has been extracted from the files.</p>
          </EmptyState>
        )}
        {seriesData !== null && seriesData.total > seriesData.items.length && (
          <Callout tone="warning">
            Showing {fmt(seriesData.items.length)} of {fmt(seriesData.total)} series (first {MAX_SERIES_PAGES * SERIES_PAGE}).
          </Callout>
        )}
        {groups.map((g) => (
          <div key={`${g.label}|${g.wellName}`} className={styles.group}>
            <p className={styles.groupTitle}>
              {g.label === null ? "No wellbore label in the source" : `Wellbore ${g.label}`}
              {g.wellName !== null && <span className={styles.muted}> (well {g.wellName})</span>}
            </p>
            <Scroll label={`Series for ${g.label ?? "unlabelled data"}`}>
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Kind</Table.Th>
                    <Table.Th>Measure</Table.Th>
                    <Table.Th>Unit</Table.Th>
                    <Table.Th>Index</Table.Th>
                    <Table.Th>Index range</Table.Th>
                    <Table.Th>Value range</Table.Th>
                    <Table.Th className={styles.num}>Valid / samples</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {g.rows.map((r) => (
                    <Table.Tr key={r.id}>
                      <Table.Td>{r.kind}</Table.Td>
                      <Table.Td>{r.measure}</Table.Td>
                      <Table.Td>{r.unit ?? (r.unitStatus === "missing" ? "not stated" : r.unitStatus)}</Table.Td>
                      <Table.Td>
                        {r.indexName} ({r.indexUnit ?? (r.indexUnitStatus === "missing" ? "unit not stated" : r.indexUnitStatus)})
                      </Table.Td>
                      <Table.Td>
                        {r.indexFirst} to {r.indexLast}
                      </Table.Td>
                      <Table.Td>{range(r.min, r.max)}</Table.Td>
                      <Table.Td className={styles.num}>
                        {fmt(r.valid)} / {fmt(r.samples)}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Scroll>
          </div>
        ))}
      </Section>

      <Section id="ov-units" title="Unit and depth-default warnings">
        {(series.state.kind === "loading" || reports.state.kind === "loading") && <LoadingState label="Checking units…" />}
        {series.state.kind === "ready" && reports.state.kind !== "loading" && (
          <>
            {warnings.length === 0 && (reports.state.kind !== "ready" || reports.state.data.missingUnitIssues === 0) ? (
              <p>No series or issue reports a missing or mixed unit.</p>
            ) : (
              <ul className={styles.issues} aria-label="Unit warnings">
                {warnings.map((w, i) => (
                  <li key={`${w.row.id}-${i}`}>
                    {w.group.label ?? "Unlabelled"} · {w.row.measure}: {w.what}
                    {w.row.filename !== null ? ` — ${w.row.filename}` : ""}
                  </li>
                ))}
                {reports.state.kind === "ready" && reports.state.data.missingUnitIssues > 0 && (
                  <li>
                    {reports.state.data.missingUnitIssues} extraction issue(s) with code MISSING_UNIT (see Issues above).
                  </li>
                )}
              </ul>
            )}
            <p className={styles.muted}>
              Record-level depth values that defaulted to meters are listed per document in its extraction evidence, not here.
            </p>
          </>
        )}
        {series.state.kind === "error" && <p>Unit checks need the series list, which could not be loaded (see above).</p>}
      </Section>

      </>)}

      <Section id="ov-not-yet" title="Not available yet" note="These are not built or not connected in this version; nothing is shown for them rather than a guess.">
        <ul className={styles.issues} aria-label="Not available yet">
          {NOT_YET.map((n) => (
            <li key={n.name}>
              <Chip spec={NOT_YET_CHIP} label="Not available yet" /> <strong>{n.name}</strong>: {n.why}
            </li>
          ))}
        </ul>
      </Section>
    </section>
  );
}
