/** Screen-space label declutter (pure, so it is unit-tested without a GPU). */
export interface LabelInput {
  id: string;
  /** Anchor in canvas pixels; `visible` is false when behind the camera or outside the view. */
  x: number;
  y: number;
  visible: boolean;
  /** Label box size in pixels. */
  w: number;
  h: number;
  /** Lower value = placed first (the selected element, then equipment, then depth marks). */
  priority: number;
}

export interface LabelPlacement {
  id: string;
  shown: boolean;
  /** Top-left of the label box. */
  x: number;
  y: number;
  /** True when the box was moved away from its anchor and needs a leader line. */
  leader: boolean;
}

const overlaps = (a: { x: number; y: number; w: number; h: number }, b: { x: number; y: number; w: number; h: number }): boolean =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

const GAP = 3;
const OFFSET_X = 14;

/**
 * Greedy placement by priority: each label tries beside its anchor (right, then left), shifting
 * vertically in alternating steps until it neither overlaps a placed label nor leaves the canvas.
 * A label that cannot be placed is hidden (its list entry and inspector remain).
 */
export function layoutLabels(inputs: readonly LabelInput[], canvas: { w: number; h: number }): LabelPlacement[] {
  const order = [...inputs].sort((a, b) => a.priority - b.priority);
  const placed: { x: number; y: number; w: number; h: number }[] = [];
  const out = new Map<string, LabelPlacement>();
  for (const l of order) {
    if (!l.visible || l.x < -l.w || l.y < -l.h || l.x > canvas.w + l.w || l.y > canvas.h + l.h) {
      out.set(l.id, { id: l.id, shown: false, x: 0, y: 0, leader: false });
      continue;
    }
    let result: LabelPlacement | null = null;
    search: for (const side of [1, -1]) {
      const bx = side === 1 ? l.x + OFFSET_X : l.x - OFFSET_X - l.w;
      for (let step = 0; step <= 14; step += 1) {
        const dir = step % 2 === 0 ? 1 : -1;
        const dy = dir * Math.ceil(step / 2) * (l.h + GAP);
        const box = { x: bx, y: l.y - l.h / 2 + dy, w: l.w, h: l.h };
        if (box.x < 0 || box.y < 0 || box.x + box.w > canvas.w || box.y + box.h > canvas.h) continue;
        if (placed.some((p) => overlaps(p, box))) continue;
        placed.push(box);
        result = { id: l.id, shown: true, x: box.x, y: box.y, leader: step > 0 };
        break search;
      }
    }
    out.set(l.id, result ?? { id: l.id, shown: false, x: 0, y: 0, leader: false });
  }
  return inputs.map((i) => out.get(i.id)!);
}
