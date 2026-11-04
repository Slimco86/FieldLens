/**
 * Imperative camera rig (TASK-096, CM-1/CM-5/CM-6). THREE-free state machine driven from the
 * viewers' frame loops through refs: no React state, no allocation beyond small tuples per step.
 *
 *  - `fly` starts a smooth zoom-pan flight from the *current* pose (so a retarget mid-flight has no
 *    jump). Reduced motion applies the final pose at once (same pose, no animation).
 *  - `cancel` hands control back at the current pose (pointer/keyboard input).
 *  - `step(dt)` advances and returns the pose to apply, or null when idle.
 */
import { planFlight, poseFromPositions, positionOf, samplePose, type Flight, type OrbitPose, type V3 } from "./cameraPath";

export interface RigPose {
  position: V3;
  target: V3;
}

export interface FlyOptions {
  /** Apply the final pose immediately (prefers-reduced-motion, first framing). */
  instant?: boolean;
  /** Override the distance-scaled duration (seconds, still the caller's explicit choice). */
  durationS?: number;
}

export class CameraRig {
  private flight: Flight | null = null;
  private elapsed = 0;
  private pose: OrbitPose;

  constructor(initial: RigPose = { position: [0, 0, 1], target: [0, 0, 0] }) {
    this.pose = poseFromPositions(initial.position, initial.target);
  }

  get active(): boolean {
    return this.flight !== null;
  }

  /** Last pose the rig produced (or was synced to). */
  get current(): OrbitPose {
    return this.pose;
  }

  /** Align with the real camera (call before `fly` when the user may have moved it). */
  sync(real: RigPose): void {
    this.pose = poseFromPositions(real.position, real.target);
  }

  /** Start a flight to `to`; returns the pose to apply now when instant, else null. */
  fly(to: OrbitPose, opts: FlyOptions = {}): RigPose | null {
    if (opts.instant === true) {
      this.flight = null;
      this.pose = to;
      return { position: positionOf(to), target: to.target };
    }
    this.flight = planFlight(this.pose, to, opts.durationS);
    this.elapsed = 0;
    return null;
  }

  cancel(): void {
    this.flight = null;
  }

  /** Total duration of the running flight (tests/diagnostics), else 0. */
  get durationS(): number {
    return this.flight?.durationS ?? 0;
  }

  /** Advance by `dt` seconds; returns the pose to apply, or null when nothing is flying. */
  step(dt: number): RigPose | null {
    const f = this.flight;
    if (f === null) return null;
    this.elapsed += Math.max(0, dt);
    const t = Math.min(1, this.elapsed / f.durationS);
    this.pose = samplePose(f, t);
    if (t >= 1) this.flight = null;
    return { position: positionOf(this.pose), target: this.pose.target };
  }
}
