import type { DocumentCategory } from "./api";

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KiB", "MiB", "GiB"] as const;
  let value = n;
  let unit = "B";
  for (const u of units) {
    if (value < 1024) break;
    value /= 1024;
    unit = u;
  }
  return `${value >= 100 || Number.isInteger(value) ? Math.round(value) : value.toFixed(1)} ${unit}`;
}

const CATEGORY_LABEL: Record<DocumentCategory, string> = {
  trajectory: "Trajectory",
  completion_equipment: "Completion equipment",
  perforation_history: "Perforation history",
  production_injection: "Production / injection",
  well_logs: "Well logs",
  geology_reservoir: "Geology / reservoir",
  terrain_bathymetry: "Terrain / bathymetry",
  general_report: "General report",
};
export const categoryLabel = (c: DocumentCategory): string => CATEGORY_LABEL[c];

export function formatTime(iso: string): string {
  return new Date(iso).toUTCString();
}
