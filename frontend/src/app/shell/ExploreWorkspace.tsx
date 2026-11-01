import { useState, type ReactNode } from "react";
import { ActionIcon } from "@mantine/core";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import styles from "./ExploreWorkspace.module.css";

/**
 * Explore layout contract (UI-11). Four named regions mount here without changing this file:
 *
 *  - `tree`      evidence/asset tree (left); collapsible
 *  - `stage`     the 3D scene and charts (center); never collapses and takes the freed space
 *  - `inspector` selection details and evidence (right); collapsible
 *  - `dock`      assistant and activity (bottom); collapsible
 *
 * An absent region (undefined) renders nothing, not even a heading, so no empty panel implies a
 * feature that does not exist. A collapsed region keeps its content mounted (state survives) but
 * releases its space to the stage and leaves only a labelled toggle.
 */
export interface ExploreRegions {
  tree?: ReactNode;
  stage: ReactNode;
  inspector?: ReactNode;
  dock?: ReactNode;
}

type Collapsible = "tree" | "inspector" | "dock";

const COLLAPSE_ICON = {
  tree: [ChevronLeft, ChevronRight],
  inspector: [ChevronRight, ChevronLeft],
  dock: [ChevronDown, ChevronUp],
} as const;

const TITLE: Record<Collapsible, string> = { tree: "Tree", inspector: "Inspector", dock: "Dock" };

function Region({
  name,
  title,
  collapsed,
  onToggle,
  children,
}: {
  name: Collapsible;
  title: string;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const [Collapse, Expand] = COLLAPSE_ICON[name];
  const Icon = collapsed ? Expand : Collapse;
  const verb = collapsed ? "Expand" : "Collapse";
  return (
    <section
      className={`${styles.region} ${styles[name]} ${collapsed ? styles.collapsed : ""}`}
      aria-label={title}
      data-region={name}
      data-collapsed={collapsed}
    >
      <div className={styles.bar}>
        <span>{title}</span>
        <ActionIcon
          variant="subtle"
          color="gray"
          size="sm"
          aria-label={`${verb} ${title.toLowerCase()}`}
          aria-expanded={!collapsed}
          onClick={onToggle}
        >
          <Icon size={16} aria-hidden="true" />
        </ActionIcon>
      </div>
      <div className={styles.body} hidden={collapsed}>
        {children}
      </div>
    </section>
  );
}

export function ExploreWorkspace({ tree, stage, inspector, dock }: ExploreRegions) {
  const [collapsed, setCollapsed] = useState<Record<Collapsible, boolean>>({
    tree: false,
    inspector: false,
    dock: false,
  });
  const toggle = (name: Collapsible) => setCollapsed((c) => ({ ...c, [name]: !c[name] }));
  const region = (name: Collapsible, node: ReactNode | undefined) =>
    node === undefined ? null : (
      <Region name={name} title={TITLE[name]} collapsed={collapsed[name]} onToggle={() => toggle(name)}>
        {node}
      </Region>
    );
  return (
    <div className={styles.workspace} data-testid="explore-workspace">
      <div className={styles.row}>
        {region("tree", tree)}
        <section className={`${styles.region} ${styles.stage}`} aria-label="Stage" data-region="stage">
          <div className={styles.body}>{stage}</div>
        </section>
        {region("inspector", inspector)}
      </div>
      {region("dock", dock)}
    </div>
  );
}
