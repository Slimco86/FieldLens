import { useCallback, useEffect, useRef, useState, type MutableRefObject, type ReactNode, type Ref } from "react";
import { ActionIcon, AppShell, Burger } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Compass, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { layout } from "../../design/tokens";
import styles from "./Shell.module.css";

interface Props {
  /** Project management; rendered only when the local services are ready. */
  sidebar?: ReactNode;
  /** Top bar title; shown only while the local services are ready. */
  title?: string;
  /** Readiness indicator at the foot of the sidebar. */
  status?: ReactNode;
  mainRef?: Ref<HTMLElement>;
  busy?: boolean;
  children: ReactNode;
}

const SIDEBAR_KEY = "fieldlens.sidebar";

function readDesktopOpen(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_KEY) !== "collapsed";
  } catch {
    return true;
  }
}

/** Application frame: skip link, brand + project sidebar, top bar and the main landmark. */
export function Shell({ sidebar, title, status, mainRef, busy = false, children }: Props) {
  const [open, { toggle }] = useDisclosure(false);
  const [desktopOpen, setDesktopOpen] = useState(readDesktopOpen);
  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_KEY, desktopOpen ? "open" : "collapsed");
    } catch {
      /* storage unavailable: the choice lasts for this page only */
    }
  }, [desktopOpen]);
  const main = useRef<HTMLElement | null>(null);
  const setMain = useCallback(
    (el: HTMLElement | null) => {
      main.current = el;
      if (typeof mainRef === "function") mainRef(el);
      else if (mainRef) (mainRef as MutableRefObject<HTMLElement | null>).current = el;
    },
    [mainRef],
  );
  return (
    <>
      {/* The address hash is the route, so the skip link moves focus instead of changing the hash. */}
      <a
        className="fl-skip"
        href="#main"
        onClick={(event) => {
          event.preventDefault();
          main.current?.focus();
        }}
      >
        Skip to main content
      </a>
      <AppShell
        header={{ height: layout.header }}
        navbar={{ width: layout.sidebar, breakpoint: "md", collapsed: { mobile: !open, desktop: !desktopOpen } }}
        layout="alt"
        padding={0}
        transitionDuration={0}
      >
        <AppShell.Navbar component="aside" className={styles.navbar} data-open={open} aria-label="Project sidebar">
          <div className={styles.brand}>
            <span className={styles.mark} aria-hidden="true">
              <Compass size={16} />
            </span>
            <h1>FieldLens</h1>
          </div>
          <div className={styles.sidebarBody}>{sidebar}</div>
          {status !== undefined && <div className={styles.sidebarFoot}>{status}</div>}
        </AppShell.Navbar>
        <AppShell.Header>
          <div className={styles.header}>
            <Burger opened={open} onClick={toggle} hiddenFrom="md" size="sm" aria-label="Toggle project sidebar" />
            <ActionIcon
              visibleFrom="md"
              variant="subtle"
              color="gray"
              onClick={() => setDesktopOpen((v) => !v)}
              aria-label={desktopOpen ? "Collapse project sidebar" : "Expand project sidebar"}
              aria-expanded={desktopOpen}
              title={desktopOpen ? "Collapse project sidebar" : "Expand project sidebar"}
            >
              {desktopOpen ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
            </ActionIcon>
            {!desktopOpen && (
              <span className={styles.headerBrand}>
                <span className={styles.mark} aria-hidden="true">
                  <Compass size={16} />
                </span>
                FieldLens
              </span>
            )}
            {title !== undefined && <h2>{title}</h2>}
          </div>
        </AppShell.Header>
        <AppShell.Main id="main" tabIndex={-1} ref={setMain} aria-busy={busy} className={styles.main}>
          <div className={styles.content}>{children}</div>
        </AppShell.Main>
      </AppShell>
    </>
  );
}
