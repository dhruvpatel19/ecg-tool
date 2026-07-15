"use client";

import {
  Activity,
  BookOpen,
  BrainCircuit,
  ChartNoAxesCombined,
  Gauge,
  GraduationCap,
  LogOut,
  Stethoscope,
  Settings,
  TimerReset,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "@/lib/auth";
import { isPublicEntryPath } from "@/lib/routeAccess";

const modeLinks = [
  { href: "/learn", index: "01", label: "Guided learning", short: "Learn", icon: GraduationCap },
  { href: "/train", index: "02", label: "Focused practice", short: "Train", icon: BrainCircuit },
  { href: "/rapid", index: "03", label: "Rapid practice", short: "Rapid", icon: TimerReset },
  { href: "/practice", index: "04", label: "Clinical cases", short: "Cases", icon: Stethoscope },
];

export function Navigation() {
  const pathname = usePathname();
  const { user, loading, logout } = useAuth();
  const [accountError, setAccountError] = useState<string | null>(null);
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const signOutTriggerRef = useRef<HTMLButtonElement>(null);
  const signOutDialogRef = useRef<HTMLDivElement>(null);
  const cancelSignOutRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setShowSignOutConfirm(false);
  }, [pathname]);

  useEffect(() => {
    if (!showSignOutConfirm) return;

    cancelSignOutRef.current?.focus();
    function handleEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setShowSignOutConfirm(false);
      signOutTriggerRef.current?.focus();
    }

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [showSignOutConfirm]);

  function closeSignOutConfirm() {
    setShowSignOutConfirm(false);
    requestAnimationFrame(() => signOutTriggerRef.current?.focus());
  }

  async function signOut() {
    setAccountError(null);
    try {
      await logout();
      setShowSignOutConfirm(false);
    } catch {
      closeSignOutConfirm();
      setAccountError("Sign-out could not be confirmed. You remain signed in; try again.");
    }
  }

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const activeLearningRoute = modeLinks.find((link) => isActive(link.href));
  const onProgress = isActive("/profile");
  const onLegacyStudyPlan = isActive("/review");

  if (isPublicEntryPath(pathname)) {
    return (
      <header className="public-nav">
        <Link className="public-brand" href="/" aria-label="TRACE ECG learning home">
          <span className="public-brand-mark" aria-hidden="true">
            <Activity size={19} strokeWidth={2.3} />
          </span>
          <span><strong>TRACE</strong><small>ECG learning</small></span>
        </Link>
        <nav className="public-nav-links" aria-label="Website navigation">
          <Link href="/#learning-modes">Learning modes</Link>
          <Link href="/#how-it-works">How it works</Link>
          <Link href="/privacy">Data &amp; safety</Link>
        </nav>
        <div className="public-nav-actions">
          {user ? (
            <Link className="public-create" href="/dashboard">Open dashboard</Link>
          ) : (
            <>
              <Link className="public-signin" href="/login">Sign in</Link>
              <Link className="public-create" href="/login?mode=register">Create account</Link>
            </>
          )}
        </div>
      </header>
    );
  }

  return (
    <aside
      className={`side-nav${activeLearningRoute ? " learning-route-nav" : ""}`}
      data-learning-route={activeLearningRoute?.short.toLowerCase() ?? undefined}
    >
      <Link className="brand" href="/dashboard" aria-label="TRACE learning dashboard">
        <span className="brand-mark" aria-hidden="true">
          <Activity size={19} strokeWidth={2.2} />
        </span>
        <span className="brand-copy">
          <strong>TRACE</strong>
          <small>ECG learning</small>
        </span>
      </Link>

      <nav className="nav-links" aria-label="Primary navigation">
        <Link className={`nav-link nav-overview${isActive("/") ? " active" : ""}`} href="/" aria-current={isActive("/") ? "page" : undefined}>
          <Gauge size={18} aria-hidden="true" />
          <span>Today</span>
        </Link>

        <p className="nav-section-label">Learning modes</p>
        {modeLinks.map((link) => {
          const Icon = link.icon;
          const active = isActive(link.href);
          return (
            <Link className={`nav-link${active ? " active" : ""}`} href={link.href} key={link.href} aria-label={link.label} title={link.label} aria-current={active ? "page" : undefined}>
              <span className="nav-index">{link.index}</span>
              <Icon size={18} aria-hidden="true" />
              <span className="nav-long-label">{link.label}</span>
              <span className="nav-short-label">{link.short}</span>
            </Link>
          );
        })}

        <p className="nav-section-label nav-section-progress">Your learning</p>
        <Link
          className={`nav-link${onProgress || onLegacyStudyPlan ? " active" : ""}`}
          href="/profile"
          aria-label="My learning"
          title="My learning"
          aria-current={onProgress || onLegacyStudyPlan ? "page" : undefined}
        >
          <span className="nav-index">··</span>
          <ChartNoAxesCombined size={18} aria-hidden="true" />
          <span className="nav-long-label">My learning</span>
          <span className="nav-short-label">Progress</span>
        </Link>
      </nav>

      <div className="nav-account" aria-label="Account">
        {loading ? (
          <span className="nav-account-name muted">Loading profile…</span>
        ) : user ? (
          <>
            <span className="nav-avatar" aria-hidden="true">{(user.displayName || user.username).slice(0, 1).toUpperCase()}</span>
            <span className="nav-account-name" title={user.username}>
              <span>{user.displayName || user.username}</span>
              <small>Student account</small>
            </span>
            <Link className="nav-account-action icon-only" href="/account" title="Account security" aria-label="Account security">
              <Settings size={15} aria-hidden="true" />
            </Link>
            <button
              ref={signOutTriggerRef}
              className="nav-account-action icon-only"
              type="button"
              onClick={() => {
                setAccountError(null);
                setShowSignOutConfirm(true);
              }}
              title="Sign out"
              aria-label="Sign out"
              aria-haspopup="dialog"
              aria-expanded={showSignOutConfirm}
              aria-controls="nav-signout-dialog"
            >
              <LogOut size={15} aria-hidden="true" />
            </button>
          </>
        ) : null}
      </div>

      {showSignOutConfirm ? (
        <div className="nav-signout-backdrop" onMouseDown={closeSignOutConfirm}>
          <div
            ref={signOutDialogRef}
            id="nav-signout-dialog"
            className="nav-signout-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="nav-signout-title"
            aria-describedby="nav-signout-description"
            onMouseDown={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key !== "Tab") return;
              const controls = [...(signOutDialogRef.current?.querySelectorAll<HTMLElement>(
                'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
              ) ?? [])];
              const first = controls[0];
              const last = controls.at(-1);
              if (!first || !last) return;
              if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
              } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
              }
            }}
          >
            <div>
              <h2 id="nav-signout-title">Sign out of TRACE?</h2>
              <p id="nav-signout-description">Your learning record stays with this account.</p>
            </div>
            <div className="nav-signout-actions">
              <button ref={cancelSignOutRef} className="button secondary small" type="button" onClick={closeSignOutConfirm}>
                Stay signed in
              </button>
              <button className="button primary small" type="button" onClick={() => void signOut()}>
                Sign out
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {accountError ? <div className="nav-account-error" role="alert">{accountError}</div> : null}

      <div className="nav-disclaimer">
        <BookOpen size={14} aria-hidden="true" />
        <span>For education, not clinical diagnosis.</span>
      </div>
    </aside>
  );
}
