import { useEffect, useRef, useState } from "react";
import { Button, Title } from "@mantine/core";
import { CircleCheck, CircleX } from "lucide-react";
import { Callout, Chip, EmptyState, ErrorState, LoadingState } from "../../design";
import { keyString } from "../projects/keys";
import { toFailure, useScopedResource, type Failure } from "../projects/scope";
import { decideMergeProposal, listMergeProposals, type MergeAction, type MergeProposal } from "./api";
import styles from "../pipeline/Pipeline.module.css";

const OK = { tone: "success", icon: CircleCheck } as const;
const NO = { tone: "danger", icon: CircleX } as const;

const SECTIONS: { status: MergeProposal["status"]; title: string; help: string }[] = [
  { status: "pending", title: "To review", help: "Proposed by the model with a quote or a matching survey. Nothing is merged until you accept." },
  { status: "accepted", title: "Merged", help: "Applied. Reverting restores the separate names and marks dependent drafts out of date." },
  { status: "blocked", title: "Cannot be accepted", help: "A safety check failed, so these can never be merged." },
  { status: "rejected", title: "Rejected", help: "You rejected these; they are not proposed again." },
  { status: "reverted", title: "Reverted", help: "Merged earlier and then undone." },
];

const ACTION_LABEL: Record<MergeAction, string> = { accept: "Accept", reject: "Reject", revert: "Revert" };

function ProposalCard({ p, busy, onAct }: { p: MergeProposal; busy: boolean; onAct: (action: MergeAction) => void }) {
  const aliases = p.members.map((m) => m.name);
  const title = `${aliases.join(", ")} → ${p.target.name}`;
  const quotes = p.members.flatMap((m) => (m.evidence ?? []).map((e) => ({ alias: m.name, ...e })));
  const act = (action: MergeAction, variant: "filled" | "default") => (
    <Button size="xs" variant={variant} disabled={busy} aria-label={`${ACTION_LABEL[action]} ${title}`} onClick={() => onAct(action)}>
      {ACTION_LABEL[action]}
    </Button>
  );
  return (
    <li data-proposal-id={p.proposal_id} tabIndex={-1}>
      <strong>{title}</strong>
      <p className={styles.note}>
        Names <q>{aliases.join(", ")}</q> would join the wellbore <q>{p.target.name}</q> and all their files would be listed under it.
        {p.rationale ? ` Model rationale: ${p.rationale}` : ""}
      </p>
      {quotes.length === 0 ? (
        <p className={styles.note}>No verified evidence is stored.</p>
      ) : (
        <ul className={styles.list} aria-label={`Quotes for ${title}`}>
          {quotes.map((q, i) => (
            <li key={`${q.document_id}-${i}`}>
              {q.evidence_kind === "survey_match" ? (
                <>
                  <strong>Matching survey:</strong> {q.quote}{" "}
                  <span className={styles.note}>(about {q.alias}; document {q.document_id.slice(0, 8)}, compared by the server, not quoted)</span>
                </>
              ) : (
                <>
                  <q>{q.quote}</q>{" "}
                  <span className={styles.note}>(about {q.alias}; document {q.document_id.slice(0, 8)}, verified in the file)</span>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <ul className={styles.list} aria-label={`Safety checks for ${title}`}>
        {p.guard_results.map((g) => (
          <li key={g.code}>
            <Chip spec={g.passed ? OK : NO} label={g.passed ? "Passed" : "Failed"} /> <code>{g.code}</code> {g.detail}
          </li>
        ))}
      </ul>
      {!p.dataset_current && p.status === "pending" && (
        <p className={styles.note}>The project data changed since this was proposed; accepting re-checks every safety check.</p>
      )}
      <div className={styles.actions}>
        {p.status === "pending" && p.acceptable && (
          <>
            {act("accept", "filled")}
            {act("reject", "default")}
          </>
        )}
        {p.status === "pending" && !p.acceptable && act("reject", "default")}
        {p.status === "accepted" && act("revert", "default")}
      </div>
    </li>
  );
}

/** Review of proposed and applied wellbore name matches (TASK-065): Accept/Reject proposals, Revert applied merges. */
export function MergeReview({ projectId, onChanged }: { projectId: string; onChanged: () => void }) {
  const list = useScopedResource(keyString(["merge", projectId]), (signal) => listMergeProposals(projectId, signal));
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  // The acted-on button unmounts or is disabled; focus is moved deliberately once the list has settled.
  const pendingFocus = useRef<{ id: string; staleData: unknown } | null>(null);

  async function act(p: MergeProposal, action: MergeAction) {
    pendingFocus.current = { id: p.proposal_id, staleData: list.state.kind === "ready" ? list.state.data : null };
    setBusy(p.proposal_id);
    setFailure(null);
    try {
      await decideMergeProposal(projectId, p.proposal_id, action);
      list.reload();
      if (action !== "reject") onChanged();
    } catch (err) {
      setFailure(toFailure(err));
      list.reload();
    } finally {
      setBusy(null);
    }
  }

  const data = list.state.kind === "ready" ? list.state.data : null;
  useEffect(() => {
    const pending = pendingFocus.current;
    // Wait for the reloaded list: the pre-action rows are still shown until it settles.
    if (pending === null || busy !== null || data === null || data === pending.staleData) return;
    const id = pending.id;
    const row = document.querySelector<HTMLElement>(`[data-proposal-id="${id}"]`);
    if (row === null) return;
    pendingFocus.current = null;
    // The new Revert button after Accept; otherwise the proposal row itself (now in its new section).
    (row.querySelector<HTMLElement>("button:not(:disabled)") ?? row).focus();
  }, [data, busy]);
  return (
    <section aria-labelledby="merge-title" className={styles.panel}>
      <Title order={5} id="merge-title">
        Wellbore name matches
      </Title>
      <p className={styles.note}>
        The same wellbore is sometimes written differently (for example 15/9-F-12 and F-12). Matches are only proposed; a
        match is applied when you accept it, and you can revert it later.
      </p>
      {list.state.kind === "loading" && <LoadingState label="Loading name matches…" status />}
      {list.state.kind === "error" && (
        <ErrorState message={`Name matches could not be loaded: ${list.state.error.message}`} requestId={list.state.error.requestId} onRetry={list.reload} />
      )}
      {failure !== null && (
        <Callout tone="danger" role="alert">
          <p>
            That change was not applied: {failure.message}
            {failure.code !== null && <> (<code>{failure.code}</code>)</>}.
          </p>
        </Callout>
      )}
      {data !== null && data.items.length === 0 && (
        <EmptyState title="No name matches yet">
          <p>Run a reconstruction: the Match wellbores step proposes matches here for you to review.</p>
        </EmptyState>
      )}
      {data !== null &&
        SECTIONS.map((sec) => {
          const items = data.items.filter((p) => p.status === sec.status);
          if (items.length === 0) return null;
          return (
            <div key={sec.status}>
              <h6 className={styles.catHeading}>
                {sec.title} ({items.length})
              </h6>
              <p className={styles.note}>{sec.help}</p>
              <ul className={styles.list} aria-label={`${sec.title} name matches`}>
                {items.map((p) => (
                  <ProposalCard key={p.proposal_id} p={p} busy={busy === p.proposal_id} onAct={(a) => void act(p, a)} />
                ))}
              </ul>
            </div>
          );
        })}
    </section>
  );
}
