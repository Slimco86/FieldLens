import { Boxes, Compass, FileText, type LucideIcon } from "lucide-react";
import { SECTIONS, type Section } from "../../features/projects/keys";
import styles from "./ProjectTabs.module.css";

export const SECTION_LABEL: Record<Section, string> = {
  sources: "Sources",
  reconstruction: "Reconstruction",
  explore: "Explore",
};
const ICON: Record<Section, LucideIcon> = { sources: FileText, reconstruction: Boxes, explore: Compass };

interface Props {
  section: Section;
  onSection: (section: Section) => void;
}

/**
 * Project tabs. Selection is the URL (the parent navigates in `onSection`); every tab is a button
 * in tab order, so Tab/Shift+Tab reach each one and Enter or Space selects it.
 */
export function ProjectTabs({ section, onSection }: Props) {
  return (
    <nav aria-label="Project sections" className={styles.nav}>
      <ul className={styles.list}>
        {SECTIONS.map((s) => {
          const Icon = ICON[s];
          return (
            <li key={s}>
              <button
                type="button"
                className={styles.tab}
                aria-current={s === section ? "page" : undefined}
                onClick={() => onSection(s)}
              >
                <Icon size={16} aria-hidden="true" />
                {SECTION_LABEL[s]}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
