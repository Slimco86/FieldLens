import type { CSSProperties } from "react";
import {
  Ban,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  CircleX,
  Clock,
  Info,
  LoaderCircle,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import type { components } from "../api/generated";
import type { Tone } from "./tokens";
import styles from "./StatusChip.module.css";

type S = components["schemas"];

/** One chip for every status vocabulary: text label plus icon, never color alone (UI-7). */
export interface ChipSpec {
  tone: Tone;
  icon: LucideIcon;
  spin?: boolean;
}

const STORAGE: Record<S["SourceDocumentItem"]["storage_state"], ChipSpec> = {
  pending_verification: { tone: "info", icon: LoaderCircle, spin: true },
  stored: { tone: "success", icon: CircleCheck },
  quarantined: { tone: "danger", icon: Ban },
};
const EXTRACTION: Record<S["SourceDocumentItem"]["extraction_state"], ChipSpec> = {
  pending_extraction: { tone: "neutral", icon: Clock },
  unsupported: { tone: "unknown", icon: CircleHelp },
  extracted: { tone: "success", icon: CircleCheck },
  extracted_with_issues: { tone: "warning", icon: TriangleAlert },
  extraction_failed: { tone: "danger", icon: CircleX },
};
const JOB: Record<S["Job"]["status"], ChipSpec> = {
  queued: { tone: "info", icon: Clock },
  running: { tone: "info", icon: LoaderCircle, spin: true },
  succeeded: { tone: "success", icon: CircleCheck },
  partial: { tone: "warning", icon: TriangleAlert },
  failed: { tone: "danger", icon: CircleX },
  cancelled: { tone: "neutral", icon: Ban },
  interrupted: { tone: "warning", icon: TriangleAlert },
};
const EXTRACTION_RUN: Record<NonNullable<S["ExtractionReport"]["status"]>, ChipSpec> = {
  queued: { tone: "info", icon: Clock },
  running: { tone: "info", icon: LoaderCircle, spin: true },
  succeeded: { tone: "success", icon: CircleCheck },
  partial: { tone: "warning", icon: TriangleAlert },
  failed: { tone: "danger", icon: CircleX },
  interrupted: { tone: "warning", icon: TriangleAlert },
  unsupported: { tone: "unknown", icon: CircleHelp },
};
const REVISION: Record<S["SourceRevisionSummary"]["status"], ChipSpec> = {
  staging: { tone: "info", icon: LoaderCircle, spin: true },
  ready: { tone: "success", icon: CircleCheck },
  ready_with_issues: { tone: "warning", icon: TriangleAlert },
  failed: { tone: "danger", icon: CircleX },
};
const VALIDATION: Record<S["ValidationState"], ChipSpec> = {
  unreviewed: { tone: "neutral", icon: Clock },
  valid: { tone: "success", icon: CircleCheck },
  conflicting: { tone: "warning", icon: TriangleAlert },
  invalid: { tone: "danger", icon: CircleX },
  unsupported: { tone: "unknown", icon: CircleHelp },
  unverified: { tone: "warning", icon: CircleHelp },
};
const SEVERITY: Record<S["IssueSeverity"], ChipSpec> = {
  info: { tone: "info", icon: Info },
  warning: { tone: "warning", icon: TriangleAlert },
  error: { tone: "danger", icon: CircleAlert },
};

export const chipVocabulary = {
  storage: STORAGE,
  extraction: EXTRACTION,
  job: JOB,
  extractionRun: EXTRACTION_RUN,
  revision: REVISION,
  validation: VALIDATION,
  severity: SEVERITY,
} as const;

export const UNKNOWN_CHIP: ChipSpec = { tone: "unknown", icon: CircleHelp };

interface ChipProps {
  spec: ChipSpec;
  label: string;
}

export function Chip({ spec, label }: ChipProps) {
  const Icon = spec.icon;
  const vars = {
    "--chip-fg": `var(--fl-tone-${spec.tone}-fg)`,
    "--chip-bg": `var(--fl-tone-${spec.tone}-bg)`,
    "--chip-border": `var(--fl-tone-${spec.tone}-border)`,
  } as CSSProperties;
  return (
    <span className={styles.chip} data-tone={spec.tone} style={vars}>
      <Icon size={14} aria-hidden="true" className={spec.spin ? `${styles.icon} ${styles.spin}` : styles.icon} />
      <span className={styles.label}>{label}</span>
    </span>
  );
}

type Kind = keyof typeof chipVocabulary;

/** Typed status chip: `value` must be a member of the generated DTO enum for `kind`. */
export function StatusChip<K extends Kind>({
  kind,
  value,
  label,
}: {
  kind: K;
  value: keyof (typeof chipVocabulary)[K];
  label: string;
}) {
  const table = chipVocabulary[kind] as Record<PropertyKey, ChipSpec>;
  return <Chip spec={table[value] ?? UNKNOWN_CHIP} label={label} />;
}

const EVIDENCE_ICON: Record<S["EvidenceClass"], LucideIcon> = {
  source_record: CircleCheck,
  catalog_derived: Info,
  derived: Info,
  interpolated: TriangleAlert,
  generic: CircleHelp,
  model_proposal: CircleHelp,
};
const EVIDENCE_LABEL: Record<S["EvidenceClass"], string> = {
  source_record: "Source record",
  catalog_derived: "Catalog-derived",
  derived: "Derived",
  interpolated: "Interpolated",
  generic: "Generic placeholder",
  model_proposal: "Model-read, unverified",
};

/** Evidence class chip: colorblind-safe palette, always with icon and text. */
export function EvidenceClassChip({ value }: { value: S["EvidenceClass"] }) {
  const Icon = EVIDENCE_ICON[value];
  const key = value.replace(/_/g, "-");
  const vars = {
    "--chip-fg": `var(--fl-evidence-${key}-fg)`,
    "--chip-bg": `var(--fl-evidence-${key}-bg)`,
    "--chip-border": `var(--fl-evidence-${key}-border)`,
  } as CSSProperties;
  return (
    <span className={styles.chip} data-evidence={value} style={vars}>
      <Icon size={14} aria-hidden="true" className={styles.icon} />
      <span className={styles.label}>{EVIDENCE_LABEL[value]}</span>
    </span>
  );
}
