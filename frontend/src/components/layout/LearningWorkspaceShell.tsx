"use client";

import { MessageSquare, X } from "lucide-react";
import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

type WorkspaceContextValue = {
  drawerId: string;
  drawerOpen: boolean;
  openDrawer: () => void;
  closeDrawer: () => void;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function useWorkspaceContext(): WorkspaceContextValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("Learning workspace primitives must be nested inside LearningWorkspaceShell.");
  return value;
}

type LearningWorkspaceShellProps = {
  children: ReactNode;
  className?: string;
  phase: string;
  tutorResetKey?: string | number | null;
};

export function LearningWorkspaceShell({
  children,
  className = "",
  phase,
  tutorResetKey = null,
}: LearningWorkspaceShellProps) {
  const drawerId = `learning-tutor-${useId().replaceAll(":", "")}`;
  const [drawerOpen, setDrawerOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  function openDrawer() {
    setDrawerOpen(true);
  }

  function closeDrawer() {
    setDrawerOpen(false);
    window.requestAnimationFrame(() => triggerRef.current?.focus());
  }

  useEffect(() => {
    setDrawerOpen(false);
  }, [tutorResetKey]);

  return (
    <WorkspaceContext.Provider value={{ drawerId, drawerOpen, openDrawer, closeDrawer, triggerRef }}>
      <section
        className={`learning-workspace-shell${className ? ` ${className}` : ""}`}
        data-learning-workspace="true"
        data-phase={phase}
      >
        {children}
      </section>
    </WorkspaceContext.Provider>
  );
}

type SessionBarProps = {
  children: ReactNode;
  className?: string;
  tutorAvailable?: boolean;
  tutorLabel?: string;
};

export function SessionBar({
  children,
  className = "",
  tutorAvailable = false,
  tutorLabel = "Open tutor",
}: SessionBarProps) {
  const { drawerId, drawerOpen, openDrawer, triggerRef } = useWorkspaceContext();
  return (
    <header className={`learning-session-bar${className ? ` ${className}` : ""}`}>
      {children}
      {tutorAvailable ? (
        <button
          className="button subtle small learning-tutor-trigger"
          type="button"
          ref={triggerRef}
          aria-controls={drawerId}
          aria-expanded={drawerOpen}
          aria-haspopup="dialog"
          onClick={openDrawer}
        >
          <MessageSquare size={15} aria-hidden="true" /> {tutorLabel}
        </button>
      ) : null}
    </header>
  );
}

export function WorkspaceNotices({ children }: { children?: ReactNode }) {
  if (!children) return null;
  return <div className="learning-workspace-notices">{children}</div>;
}

export function WorkspaceBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`learning-workspace-body${className ? ` ${className}` : ""}`}>{children}</div>;
}

export function WaveformPane({
  children,
  className = "",
  label = "ECG waveform",
}: {
  children: ReactNode;
  className?: string;
  label?: string;
}) {
  return (
    <section className={`learning-waveform-pane${className ? ` ${className}` : ""}`} aria-label={label}>
      {children}
    </section>
  );
}

export function ResponseRail({
  children,
  className = "",
  label,
  phase,
}: {
  children: ReactNode;
  className?: string;
  label: string;
  phase: string;
}) {
  return (
    <aside
      className={`learning-response-rail${className ? ` ${className}` : ""}`}
      aria-label={label}
      data-response-phase={phase}
    >
      {children}
    </aside>
  );
}

export function DisclosureArea({ children, className = "" }: { children?: ReactNode; className?: string }) {
  if (!children) return null;
  return (
    <footer className={`learning-disclosure-area${className ? ` ${className}` : ""}`}>
      {children}
    </footer>
  );
}

function dialogFocusableElements(container: HTMLElement) {
  return [...container.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => {
    const style = window.getComputedStyle(element);
    return !element.hidden
      && element.getAttribute("aria-hidden") !== "true"
      && style.display !== "none"
      && style.visibility !== "hidden";
  });
}

function trapDialogFocus(event: KeyboardEvent<HTMLElement>) {
  if (event.key !== "Tab") return;
  const focusable = dialogFocusableElements(event.currentTarget);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1)!;
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

export function TutorDrawer({
  children,
  title = "ECG tutor",
}: {
  children?: ReactNode;
  title?: string;
}) {
  const { drawerId, drawerOpen, closeDrawer } = useWorkspaceContext();
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const titleId = `${drawerId}-title`;

  useEffect(() => {
    if (!drawerOpen) return;
    const frame = window.requestAnimationFrame(() => closeRef.current?.focus());
    function keepModalKeyboardReachable(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") {
        if (event.defaultPrevented) return;
        event.preventDefault();
        closeDrawer();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current || dialogRef.current.contains(document.activeElement)) return;
      const focusable = dialogFocusableElements(dialogRef.current);
      const target = event.shiftKey ? focusable.at(-1) : focusable[0];
      if (!target) return;
      event.preventDefault();
      target.focus();
    }
    document.addEventListener("keydown", keepModalKeyboardReachable);
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("keydown", keepModalKeyboardReachable);
    };
  }, [closeDrawer, drawerOpen]);

  if (!children) return null;

  return (
    <div className="learning-tutor-layer" hidden={!drawerOpen} data-drawer-state={drawerOpen ? "open" : "closed"}>
      <button className="learning-tutor-backdrop" type="button" tabIndex={-1} aria-label="Close tutor" onClick={closeDrawer} />
      <aside
        ref={dialogRef}
        className="learning-tutor-drawer"
        id={drawerId}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            closeDrawer();
            return;
          }
          trapDialogFocus(event);
        }}
      >
        <header className="learning-tutor-drawer-header">
          <h2 id={titleId}>{title}</h2>
          <button className="button subtle small" type="button" ref={closeRef} onClick={closeDrawer}>
            <X size={16} aria-hidden="true" /> Close tutor
          </button>
        </header>
        <div className="learning-tutor-drawer-body">{children}</div>
      </aside>
    </div>
  );
}
