import { Button, Table, Title } from "@mantine/core";
import { RefreshCw } from "lucide-react";
import { CircleCheck, CircleHelp, CircleX, TriangleAlert } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState, type ChipSpec } from "../../design";
import { keyString } from "../projects/keys";
import { useScopedResource } from "../projects/scope";
import { getStartGate, type StartGate } from "./api";
import styles from "./Pipeline.module.css";

export type CheckState = "pass" | "warn" | "fail" | "unknown";

const CHIP: Record<CheckState, { spec: ChipSpec; label: string }> = {
  pass: { spec: { tone: "success", icon: CircleCheck }, label: "Pass" },
  warn: { spec: { tone: "warning", icon: TriangleAlert }, label: "Warning" },
  fail: { spec: { tone: "danger", icon: CircleX }, label: "Not met" },
  unknown: { spec: { tone: "unknown", icon: CircleHelp }, label: "Not assessed" },
};

export const CheckChip = ({ state }: { state: CheckState }) => <Chip spec={CHIP[state].spec} label={CHIP[state].label} />;

const CONDITION_TITLE: Record<string, string> = {
  WELLBORE_IDENTIFIED: "Wellbore identified",
  VALIDATED_TRAJECTORY: "Validated trajectory present",
};

export interface CheckRow {
  id: string;
  title: string;
  state: CheckState;
  /** Codes and messages exactly as the server wrote them. */
  details: { code: string | null; message: string }[];
}

/** Reads server verdicts only: pass/fail from `conditions[].met`, surface location from the server's per-wellbore flags. */
export function gateRows(gate: StartGate): CheckRow[] {
  const rows: CheckRow[] = gate.conditions.map((c) => ({
    id: c.code,
    title: CONDITION_TITLE[c.code] ?? c.code,
    state: c.met ? "pass" : "fail",
    details: [{ code: c.code, message: c.message }],
  }));
  const unmetByCondition = gate.unmet.map((u) => ({ code: u.code, message: u.message }));
  const target = rows.find((r) => r.state === "fail");
  if (target !== undefined) target.details.push(...unmetByCondition);
  const unlocated = gate.wellbores.filter((w) => w.unlocated);
  const locDetails = gate.wellbores.flatMap((w) =>
    w.warnings.filter((x) => x.code.startsWith("SURFACE_LOCATION")).map((x) => ({ code: x.code, message: `${w.wellbore_name}: ${x.message}` })),
  );
  rows.push({
    id: "SURFACE_LOCATION",
    title: "Surface location (warning only, never blocks)",
    state: gate.wellbores.length === 0 ? "unknown" : unlocated.length > 0 ? "warn" : "pass",
    details:
      gate.wellbores.length === 0
        ? [{ code: null, message: "No wellbore is identified, so no location was assessed." }]
        : unlocated.length > 0
          ? [
              { code: null, message: `Unlocated: ${unlocated.map((w) => w.wellbore_name).join(", ")}` },
              ...locDetails,
            ]
          : [{ code: null, message: "Every identified wellbore has a sourced surface location." }],
  });
  return rows;
}

/** Every unmet code the server reported (gate reasons and unmet conditions); the checklist below has the messages. */
export function unmetSummary(gate: StartGate): string {
  const codes = [...new Set([...gate.unmet.map((u) => u.code), ...gate.conditions.filter((c) => !c.met).map((c) => c.code)])];
  return codes.length === 0 ? "Conditions below are not met." : `${codes.length} condition(s) unmet: ${codes.join(", ")}. See the checklist below.`;
}

export function ReadinessChecklist({ projectId, refreshKey }: { projectId: string; refreshKey: number }) {
  const { state, reload } = useScopedResource(keyString(["pipeline", "gate", projectId, refreshKey]), (signal) =>
    getStartGate(projectId, signal),
  );
  const gate = state.kind === "ready" ? state.data : null;
  const valid = gate !== null && gate.project_id === projectId ? gate : null; // answers for another project are never shown
  return (
    <section aria-labelledby="pl-gate" className={styles.section}>
      <Title order={6} id="pl-gate">
        Readiness checklist
      </Title>
      <p className={styles.note}>
        Verdicts come from the server&rsquo;s start gate; nothing is computed in the browser. Reconstruction cannot be
        started from this build yet; this shows whether it could.
      </p>
      {state.kind === "loading" && <LoadingState label="Loading readiness checklist…" status />}
      {state.kind === "error" && (
        <ErrorState
          message={`Readiness checklist could not be loaded: ${state.error.message}`}
          requestId={state.error.requestId}
          onRetry={reload}
          retryLabel="Retry loading readiness checklist"
        />
      )}
      {gate !== null && valid === null && (
        <ErrorState message="The readiness answer belonged to another project and was dropped." requestId={null} onRetry={reload} />
      )}
      {valid !== null && (
        <>
          <Callout tone={valid.can_start ? "success" : "warning"} role="status">
            <p>
              <strong>{valid.can_start ? "Gate open" : "Gate closed"}:</strong>{" "}
              {valid.can_start
                ? `${valid.qualifying_wellbore_ids.length} wellbore(s) qualify.`
                : unmetSummary(valid)}
            </p>
          </Callout>
          <ul className={styles.list} aria-label="Readiness checks">
            {gateRows(valid).map((r) => (
              <li key={r.id}>
                <div className={styles.row}>
                  <CheckChip state={r.state} /> <strong>{r.title}</strong>
                </div>
                <ul className={styles.list}>
                  {r.details.map((d, i) => (
                    <li key={`${d.code ?? "x"}-${i}`}>
                      {d.code !== null && <code>{d.code}</code>} {d.message}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
          {valid.warnings.length > 0 && (
            <Callout tone="warning" label="Gate warnings">
              <ul className={styles.list}>
                {valid.warnings.map((w, i) => (
                  <li key={`${w.code}-${i}`}>
                    <strong>Warning</strong> <code>{w.code}</code> {w.message}
                  </li>
                ))}
              </ul>
            </Callout>
          )}
          {valid.wellbores.length === 0 ? (
            <EmptyState title="No wellbore identified">
              <p>No resolved wellbore exists yet, so there is nothing to check per wellbore.</p>
            </EmptyState>
          ) : (
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard-scrollable region
            <div className={styles.scroll} role="region" aria-label="Readiness per wellbore table" tabIndex={0}>
              <Table captionSide="top">
                <Table.Caption>Start gate per wellbore</Table.Caption>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th scope="col">Wellbore</Table.Th>
                    <Table.Th scope="col">Validated trajectory</Table.Th>
                    <Table.Th scope="col">Surface location</Table.Th>
                    <Table.Th scope="col">Server reasons</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {valid.wellbores.map((w) => (
                    <Table.Tr key={w.wellbore_id}>
                      <Table.Th scope="row">{w.wellbore_name}</Table.Th>
                      <Table.Td>
                        <CheckState_ ok={w.trajectory_validated} />
                      </Table.Td>
                      <Table.Td>
                        <CheckChip state={w.unlocated ? "warn" : "pass"} /> {w.unlocated ? "Unlocated" : "Located"}
                      </Table.Td>
                      <Table.Td>
                        {[...w.unmet, ...w.warnings].length === 0 ? (
                          "None"
                        ) : (
                          <ul className={styles.list}>
                            {w.unmet.map((u, i) => (
                              <li key={`u${i}`}>
                                <strong>Not met</strong> <code>{u.code}</code> {u.message}
                              </li>
                            ))}
                            {w.warnings.map((u, i) => (
                              <li key={`w${i}`}>
                                <strong>Warning</strong> <code>{u.code}</code> {u.message}
                              </li>
                            ))}
                          </ul>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </div>
          )}
        </>
      )}
      <div className={styles.actions}>
        <Button size="xs" variant="default" leftSection={<RefreshCw size={14} aria-hidden="true" />} onClick={reload}>
          Refresh readiness checklist
        </Button>
      </div>
    </section>
  );
}

function CheckState_({ ok }: { ok: boolean }) {
  return (
    <>
      <CheckChip state={ok ? "pass" : "fail"} /> {ok ? "Validated" : "Not validated"}
    </>
  );
}
