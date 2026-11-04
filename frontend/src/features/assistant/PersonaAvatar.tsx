import { useEffect, useState } from "react";
import type { AvatarState } from "./turnState";
import styles from "./Assistant.module.css";

const QUERY = "(prefers-reduced-motion: reduce)";

export function usePrefersReducedMotion(): boolean {
  const read = () => typeof window.matchMedia === "function" && window.matchMedia(QUERY).matches;
  const [reduced, setReduced] = useState(read);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(QUERY);
    const on = () => setReduced(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

const LABEL: Record<AvatarState, string> = {
  idle: "Assistant idle",
  thinking: "Assistant thinking",
  answering: "Assistant answering",
  "refusal-error": "Assistant could not answer",
};

/** SVG persona (D3): a face with state-specific eyes/mouth. No voice, no 3D. Static when reduced motion. */
export function PersonaAvatar({ state, size = 40, reducedMotion }: { state: AvatarState; size?: number; reducedMotion?: boolean }) {
  const prefers = usePrefersReducedMotion();
  const reduced = reducedMotion ?? prefers;
  const motion = reduced ? "static" : "animated";
  return (
    <svg
      role="img"
      aria-label={LABEL[state]}
      width={size}
      height={size}
      viewBox="0 0 40 40"
      className={styles.avatar}
      data-state={state}
      data-motion={motion}
    >
      <circle cx="20" cy="20" r="18" className={styles.avatarFace} />
      <line x1="20" y1="2" x2="20" y2="7" className={styles.avatarStroke} />
      <circle cx="20" cy="2" r="2" className={styles.avatarAntenna} />
      {state === "refusal-error" ? (
        <g className={styles.avatarStroke}>
          <path d="M11 15l6 6M17 15l-6 6M23 15l6 6M29 15l-6 6" />
        </g>
      ) : (
        <g className={styles.avatarEyes}>
          <circle cx="14" cy={state === "thinking" ? 17 : 19} r="2.4" />
          <circle cx="26" cy={state === "thinking" ? 17 : 19} r="2.4" />
        </g>
      )}
      {state === "idle" ? <path d="M13 27q7 4 14 0" className={styles.avatarStroke} /> : null}
      {state === "thinking" ? <circle cx="20" cy="28" r="2" className={styles.avatarMouthDot} /> : null}
      {state === "answering" ? <ellipse cx="20" cy="28" rx="4.5" ry="3" className={styles.avatarMouth} /> : null}
      {state === "refusal-error" ? <path d="M14 30q6-4 12 0" className={styles.avatarStroke} /> : null}
    </svg>
  );
}
