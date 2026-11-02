import { CircleHelp, Link2, TriangleAlert, ShieldQuestion } from "lucide-react";
import { Callout, Chip } from "../../design";
import { categoryLabel } from "../uploads/format";
import type { DocumentCategory } from "../uploads/api";
import type { DocumentIdentityProposal, DocumentModelRead } from "./api";
import styles from "./Processing.module.css";

const UNVERIFIED = { tone: "warning", icon: ShieldQuestion } as const;
const LINKED = { tone: "info", icon: Link2 } as const;
const UNRESOLVED = { tone: "unknown", icon: CircleHelp } as const;

/** Model suggestion wording; the fallback bucket is named as such, never as a confident class. */
export function suggestedCategoryText(read: Pick<DocumentModelRead, "category" | "unclassified">): string {
  return read.unclassified ? "Others (unclassified)" : categoryLabel(read.category);
}

function Identity({ p }: { p: DocumentIdentityProposal }) {
  return (
    <li>
      <div>
        <strong>{p.name_as_written}</strong> ({p.subject_kind}){" "}
        <Chip spec={UNVERIFIED} label={p.label} />{" "}
        {p.resolution === "linked" ? (
          <Chip spec={LINKED} label={`Linked to wellbore ${p.wellbore_key ?? p.normalized_key ?? ""}`.trim()} />
        ) : (
          <Chip spec={UNRESOLVED} label="Unresolved (no existing wellbore matches exactly)" />
        )}
      </div>
      <div className={styles.muted}>Evidence on page {p.page}:</div>
      <blockquote className={styles.quote}>{p.quote}</blockquote>
    </li>
  );
}

/** The model's read of one document. Everything here is a proposal: nothing is verified or used in calculations. */
export function ModelRead({ read, userLabels, cacheHit }: { read: DocumentModelRead; userLabels: DocumentCategory[]; cacheHit: boolean }) {
  const noIdentity = read.warnings.find((w) => w.code === "no_wellbore_identity");
  const others = read.warnings.filter((w) => w.code !== "no_wellbore_identity");
  const suggestion = suggestedCategoryText(read);
  return (
    <div className={styles.list} aria-label="Model-read result">
      <div className={styles.row}>
        <Chip spec={UNVERIFIED} label={read.label} />
        {cacheHit && <span>Reused stored result, no model call.</span>}
      </div>
      <dl className={styles.facts}>
        {userLabels.length > 0 && (
          <>
            <dt>Your category (effective)</dt>
            <dd>{userLabels.map(categoryLabel).join(", ")}</dd>
          </>
        )}
        <dt>{userLabels.length > 0 ? "Model suggestion (unverified, not applied)" : "Model-suggested category (unverified)"}</dt>
        <dd>{suggestion}</dd>
        <dt>Tags (model-read)</dt>
        <dd>
          {read.tags.length === 0 ? (
            "none"
          ) : (
            <ul className={styles.tags} aria-label="Model-read tags">
              {read.tags.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          )}
        </dd>
        <dt>Pages read</dt>
        <dd>
          {read.pages_read} (window {read.pages.page_start}-{read.pages.page_end})
        </dd>
        <dt>Read by</dt>
        <dd>
          {read.provider} {read.model_revision}; prompt {read.prompt_version}, schema {read.schema_version}
        </dd>
      </dl>
      {noIdentity !== undefined && (
        <Callout tone="warning" role="status">
          <p>
            <strong>No wellbore identity found.</strong> {noIdentity.message} This does not block anything: the document stays visible with
            its category and tags.
          </p>
        </Callout>
      )}
      {read.identities.length > 0 && (
        <>
          <strong id={`ids-${read.document_id}`}>Wellbore identities proposed by the model</strong>
          <ul className={styles.list} aria-labelledby={`ids-${read.document_id}`}>
            {read.identities.map((p) => (
              <Identity key={p.proposal_id} p={p} />
            ))}
          </ul>
        </>
      )}
      {others.length > 0 && (
        <ul className={styles.list} aria-label="Model-read warnings">
          {others.map((w) => (
            <li key={w.code}>
              <TriangleAlert size={14} aria-hidden="true" /> <strong>Warning</strong> <code>{w.code}</code>
              {w.count > 1 ? ` (${w.count}x)` : ""}: {w.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
