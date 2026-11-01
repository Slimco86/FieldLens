import { Button, Table, Title } from "@mantine/core";
import { RefreshCw } from "lucide-react";
import { Callout, EmptyState, ErrorState, LoadingState } from "../../design";
import type { components } from "../../api/generated";
import { keyString } from "../projects/keys";
import { useScopedResource } from "../projects/scope";
import { getExposure } from "./api";
import styles from "./Pipeline.module.css";

type S = components["schemas"];
type Category = S["CategoryExposure"];
type Finding = S["ExposureFinding"];

export const CATEGORY_LABEL: Record<Category["category"], string> = {
  trajectory: "Trajectory",
  surface_location: "Surface location",
  logs: "Logs",
  production: "Production",
  equipment_completion: "Equipment and completion",
  perforations: "Perforations",
  other: "Other",
};

/** Short source locator text built only from keys the server wrote; nothing is interpreted. */
export function locatorText(loc: Record<string, unknown> | undefined): string {
  if (loc === undefined) return "no locator";
  const parts = Object.entries(loc)
    .filter(([, v]) => v !== null && typeof v !== "object")
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

function CategoryRow({ c }: { c: Category }) {
  const notices = categoryNotices(c);
  const validation = c.groups.flatMap((g) => Object.entries(g.validation_counts));
  const merged = new Map<string, number>();
  for (const [k, n] of validation) merged.set(k, (merged.get(k) ?? 0) + n);
  const first = c.groups[0]?.sample[0];
  return (
    <Table.Tr>
      <Table.Th scope="row">{CATEGORY_LABEL[c.category]}</Table.Th>
      <Table.Td>{c.present ? "Present" : "Absent (explicit gap)"}</Table.Td>
      <Table.Td className={styles.num}>{c.record_count.toLocaleString("en-US")}</Table.Td>
      <Table.Td>
        {merged.size === 0 ? "None" : [...merged.entries()].map(([k, n]) => `${k} ${n}`).join(", ")}
        {c.conflicting_record_count > 0 && <> ({c.conflicting_record_count} conflicting)</>}
      </Table.Td>
      <Table.Td>
        {c.gap_reasons.length > 0 && (
          <div>
            Gaps: {c.gap_reasons.map((g) => <code key={g}>{g} </code>)}
          </div>
        )}
        <FindingList label={`${CATEGORY_LABEL[c.category]} conflicts`} items={c.conflicts} />
        <FindingList label={`${CATEGORY_LABEL[c.category]} gaps`} items={c.gaps} />
        <FindingList label={`${CATEGORY_LABEL[c.category]} findings`} items={c.findings} />
        {c.groups.length > 0 && (
          <ul className={styles.list} aria-label={`${CATEGORY_LABEL[c.category]} sources`}>
            {c.groups.map((g) => (
              <li key={`${g.run_id}-${g.kind}`}>
                {g.filename}: {g.record_count} {g.kind}
                {g.survey_status !== null && g.survey_status !== undefined && <> (survey status {g.survey_status})</>}
                {g.sample[0] !== undefined && <span className={styles.note}> first at {locatorText(g.sample[0].locator)}</span>}
              </li>
            ))}
          </ul>
        )}
        {c.proposal_total > 0 && (
          <div>
            Model proposals (not facts): {c.proposal_total}, accepted {c.accepted_proposal_count}.
          </div>
        )}
        {first === undefined && c.groups.length === 0 && c.gap_reasons.length === 0 && "—"}
        {notices.map((n) => (
          <Callout key={n} tone="warning" role="status">
            <p>{n}</p>
          </Callout>
        ))}
      </Table.Td>
    </Table.Tr>
  );
}

export function ExposureSection({ projectId, refreshKey }: { projectId: string; refreshKey: number }) {
  const { state, reload } = useScopedResource(keyString(["pipeline", "exposure", projectId, refreshKey]), (signal) =>
    getExposure(projectId, signal),
  );
  const data = state.kind === "ready" && state.data.project_id === projectId ? state.data : null;
  const wellbores = data?.wells.flatMap((w) => w.wellbores.map((b) => ({ well: w.name, b }))) ?? [];
  return (
    <section aria-labelledby="pl-exposure" className={styles.section}>
      <Title order={6} id="pl-exposure">
        Data exposure per wellbore
      </Title>
      <p className={styles.note}>
        What the system found for each identified wellbore, by category, with first source locators. Records parsed from
        files are source records; model proposals are listed apart and are not facts until accepted.
      </p>
      {state.kind === "loading" && <LoadingState label="Loading data exposure…" status />}
      {state.kind === "error" && (
        <ErrorState
          message={`Data exposure could not be loaded: ${state.error.message}`}
          requestId={state.error.requestId}
          onRetry={reload}
          retryLabel="Retry loading data exposure"
        />
      )}
      {state.kind === "ready" && data === null && (
        <ErrorState message="The exposure answer belonged to another project and was dropped." requestId={null} onRetry={reload} />
      )}
      {data !== null && !data.resolved_current && (
        <Callout tone="warning" role="status">
          <p>Stored identities are out of date with the latest extraction; resolve identities again before trusting this grouping.</p>
        </Callout>
      )}
      {data !== null && data.unresolved_record_count > 0 && (
        <Callout tone="warning" role="status">
          <p>{data.unresolved_record_count} record(s) have no resolved wellbore and are not shown below.</p>
        </Callout>
      )}
      {data !== null && wellbores.length === 0 && (
        <EmptyState title="No wellbore identified">
          <p>No data can be grouped under a wellbore yet. Upload and parse sources, then resolve identities.</p>
        </EmptyState>
      )}
      {wellbores.map(({ well, b }) => (
        <details key={b.wellbore_id} className={styles.details}>
          <summary>
            {well} / {b.wellbore_name}
          </summary>
          <div className={styles.nested}>
            {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard-scrollable region */}
            <div className={styles.scroll} role="region" aria-label={`Exposure of ${b.wellbore_name} table`} tabIndex={0}>
              <Table captionSide="top">
                <Table.Caption>Data exposure for {b.wellbore_name}</Table.Caption>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th scope="col">Category</Table.Th>
                    <Table.Th scope="col">Present</Table.Th>
                    <Table.Th scope="col" className={styles.num}>Records</Table.Th>
                    <Table.Th scope="col">Validation</Table.Th>
                    <Table.Th scope="col">Gaps, conflicts and sources</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {b.categories.map((c) => (
                    <CategoryRow key={c.category} c={c} />
                  ))}
                </Table.Tbody>
              </Table>
            </div>
          </div>
        </details>
      ))}
      <div className={styles.actions}>
        <Button size="xs" variant="default" leftSection={<RefreshCw size={14} aria-hidden="true" />} onClick={reload}>
          Refresh data exposure
        </Button>
      </div>
    </section>
  );
}
