/**
 * Highlight bookkeeping for the fly-over (TASK-110). THREE-free: the viewer supplies `apply(id, on)`
 * (the existing `setHighlighted` material swap). The user's selection and the visited stop are two
 * independent sources; an element is lit while either holds it, so ending a fly-over restores the
 * user's selection and never un-lights it. `apply` fires only when an element's lit state changes,
 * i.e. on stop changes, never per frame.
 */
export class VisitHighlight {
  private selected: string | null = null;
  private visited: string | null = null;
  private lit = new Set<string>();

  constructor(private readonly apply: (id: string, on: boolean) => void) {}

  setSelected(id: string | null): void {
    this.selected = id;
    this.sync();
  }

  setVisited(id: string | null): void {
    if (id === this.visited) return;
    this.visited = id;
    this.sync();
  }

  /** Drop every highlight (the model/assets are being replaced or disposed). */
  clear(): void {
    for (const id of this.lit) this.apply(id, false);
    this.lit.clear();
  }

  private sync(): void {
    const want = new Set<string>();
    if (this.selected !== null) want.add(this.selected);
    if (this.visited !== null) want.add(this.visited);
    for (const id of this.lit) {
      if (!want.has(id)) {
        this.apply(id, false);
        this.lit.delete(id);
      }
    }
    for (const id of want) {
      if (!this.lit.has(id)) {
        this.apply(id, true);
        this.lit.add(id);
      }
    }
  }
}
