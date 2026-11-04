import { useEffect, useState, type MutableRefObject } from "react";
import type { ViewerCommands } from "./Viewer3D";
import { SPEEDS, type FlyOverStatus } from "./flyOverPlan";
import styles from "./Scene.module.css";

interface Props {
  commands: MutableRefObject<ViewerCommands | null>;
  status: FlyOverStatus;
  /** Disable when there is no 3D view or no located element (e.g. fallback table). */
  disabled?: boolean;
}

/**
 * Fly over (CM-3/CM-4): play/pause/stop, previous/next stop and speed for the single-wellbore view.
 * All buttons are native (keyboard operable); Esc and pointer input on the scene are handled by the
 * viewer and arrive here as a status change. The aria-live region announces each stop.
 */
export function FlyOverControls({ commands, status, disabled = false }: Props) {
  const [speed, setSpeed] = useState<number>(1);
  const active = status.state === "playing" || status.state === "paused";

  // Keep the viewer's speed in step with the select (also before the first start).
  useEffect(() => {
    commands.current?.setFlySpeed(speed);
  }, [commands, speed]);

  const start = () => {
    commands.current?.setFlySpeed(speed);
    commands.current?.flyOver();
  };

  return (
    <div className={styles.flyOver} role="group" aria-label="Fly over" data-testid="fly-over-controls" data-state={status.state}>
      {!active ? (
        <button type="button" onClick={start} disabled={disabled} data-testid="fly-over-start">
          Fly over
        </button>
      ) : (
        <>
          {status.state === "playing" ? (
            <button type="button" onClick={() => commands.current?.pauseFlyOver()} data-testid="fly-over-pause">
              Pause
            </button>
          ) : (
            <button type="button" onClick={() => commands.current?.resumeFlyOver()} data-testid="fly-over-play">
              Play
            </button>
          )}
          <button type="button" onClick={() => commands.current?.stopFlyOver()} data-testid="fly-over-stop">
            Stop
          </button>
          <button type="button" aria-label="Previous stop" onClick={() => commands.current?.stepFlyOver(-1)} disabled={status.stopIndex <= 0}>
            ‹
          </button>
          <button type="button" aria-label="Next stop" onClick={() => commands.current?.stepFlyOver(1)} disabled={status.stopIndex >= status.stopCount - 1}>
            ›
          </button>
        </>
      )}
      <label>
        Speed{" "}
        <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} aria-label="Fly-over speed" disabled={disabled}>
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </label>
      {active && status.stop !== null && (
        <span className={styles.flyCard} data-testid="fly-over-card">
          {status.stop.label} · {Math.round(status.stop.md).toLocaleString("en-US")} m MD · {status.stopIndex + 1}/{status.stopCount}
        </span>
      )}
      {active && status.unlocated.length > 0 && (
        <span className={styles.flyNote}>Not located, not visited: {status.unlocated.map((u) => u.label).join(", ")}</span>
      )}
      <p className="fl-sr-only" role="status" aria-live="polite" data-testid="fly-over-live">
        {status.announcement}
      </p>
    </div>
  );
}
