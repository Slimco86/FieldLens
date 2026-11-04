import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ActionIcon, Button } from "@mantine/core";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import { useExploreCommandHandlers } from "../../features/scene/ExploreCommandsContext";
import type { ExploreCommandMap } from "../../features/scene/exploreCommands";
import {
  ExploreStageProvider,
  readStageMode,
  STAGE_MODES,
  STAGE_MODE_LABEL,
  writeStageMode,
  type ExploreStageContext,
  type ExploreStageState,
  type StageMode,
} from "./exploreStage";
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
  /**
   * Charts slot (XC-7). Supplying it enables the Stage mode switch (3D / Charts / Split); without
   * it the stage is exactly the single 3D body. Both panes stay mounted while hidden.
   */
  charts?: ReactNode;
  /** Assistant dock slot (AV-7); rendered below the stage like `dock`, collapsible. Absent = nothing. */
  assistant?: ReactNode;
  /** Wellbore-versus-field context exposed to slots through `useExploreStage()`. Defaults to field. */
  context?: ExploreStageContext;
  /**
   * Charts-tab hook for the `openChart` command (the workspace's only `openChart` handler). Return false when the
   * chart/wellbore is not in the loaded set (the command is then `unhandled`); otherwise apply the window and focus
   * the chart. The workspace itself then reveals the Charts pane (3D -> Charts; Split stays Split).
   */
  onOpenChart?: (payload: ExploreCommandMap["openChart"]) => boolean;
}

type Collapsible = "tree" | "inspector" | "dock";

const COLLAPSE_ICON = {
  tree: [ChevronLeft, ChevronRight],
  inspector: [ChevronRight, ChevronLeft],
  dock: [ChevronDown, ChevronUp],
} as const;
const STYLE_NAME = { tree: "tree", inspector: "inspector", dock: "dock" } as const;

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
      className={`${styles.region} ${styles[STYLE_NAME[name]]} ${collapsed ? styles.collapsed : ""}`}
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

const FIELD_CONTEXT: ExploreStageContext = { kind: "field" };

function StageSwitch({ mode, onChange }: { mode: StageMode; onChange: (m: StageMode) => void }) {
  return (
    <div className={styles.stageSwitch} role="group" aria-label="Stage mode" data-testid="stage-switch">
      {STAGE_MODES.map((m) => (
        <Button key={m} size="compact-sm" variant={m === mode ? "light" : "subtle"} color="gray" aria-pressed={m === mode} onClick={() => onChange(m)}>
          {STAGE_MODE_LABEL[m]}
        </Button>
      ))}
    </div>
  );
}

export function ExploreWorkspace({ tree, stage, inspector, dock, charts, assistant, context = FIELD_CONTEXT, onOpenChart }: ExploreRegions) {
  const [collapsed, setCollapsed] = useState<Record<Collapsible, boolean>>({
    tree: false,
    inspector: false,
    dock: false,
  });
  const [mode, setMode] = useState<StageMode>(() => readStageMode());
  useEffect(() => writeStageMode(mode), [mode]);
  const hasCharts = charts !== undefined;
  // `openChart` has exactly one handler: this one (registered only when a Charts pane exists). It reveals the pane.
  useExploreCommandHandlers({
    ...(hasCharts
      ? {
          openChart: (p: ExploreCommandMap["openChart"]) => {
            if (onOpenChart !== undefined && !onOpenChart(p)) return false;
            setMode((m) => (m === "3d" ? "charts" : m));
            return true;
          },
        }
      : {}),
  });
  // Without a charts slot there is nothing to switch to: the stage is always the 3D body.
  const effective: StageMode = hasCharts ? mode : "3d";
  const stageState = useMemo<ExploreStageState>(() => ({ mode: effective, context }), [effective, context]);
  const toggle = (name: Collapsible) => setCollapsed((c) => ({ ...c, [name]: !c[name] }));
  const region = (name: Collapsible, node: ReactNode | undefined) =>
    node === undefined ? null : (
      <Region name={name} title={TITLE[name]} collapsed={collapsed[name]} onToggle={() => toggle(name)}>
        {node}
      </Region>
    );
  return (
    <ExploreStageProvider value={stageState}>
      <div className={styles.workspace} data-testid="explore-workspace">
        <div className={styles.row}>
          {region("tree", tree)}
          <section
            className={`${styles.region} ${styles.stage}`}
            aria-label="Stage"
            data-region="stage"
            data-stage-mode={effective}
            data-context={context.kind}
            data-wellbore-id={context.kind === "wellbore" ? context.wellboreId : undefined}
          >
            {hasCharts ? (
              <>
                <StageSwitch mode={effective} onChange={setMode} />
                <div className={styles.panes}>
                  <div className={styles.pane} data-pane="3d" hidden={effective === "charts"}>
                    {stage}
                  </div>
                  <div className={styles.pane} data-pane="charts" role="region" aria-label="Charts" hidden={effective === "3d"}>
                    {charts}
                  </div>
                </div>
              </>
            ) : (
              <div className={styles.body}>{stage}</div>
            )}
          </section>
          {region("inspector", inspector)}
        </div>
        {region("dock", dock)}
        {assistant !== undefined && (
          <div className={styles.assistantSlot} data-region="assistant">
            {assistant}
          </div>
        )}
      </div>
    </ExploreStageProvider>
  );
}
