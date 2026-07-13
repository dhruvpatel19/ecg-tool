"use client";

import {
  Activity,
  BookOpen,
  BrainCircuit,
  ChartNoAxesCombined,
  Gauge,
  GraduationCap,
  LogIn,
  LogOut,
  Stethoscope,
  Settings,
  TimerReset,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useAuth } from "@/lib/auth";

const modeLinks = [
  { href: "/learn", index: "01", label: "Guided learning", short: "Learn", icon: GraduationCap },
  { href: "/train", index: "02", label: "Competency lab", short: "Train", icon: BrainCircuit },
  { href: "/rapid", index: "03", label: "Rapid reads", short: "Rapid", icon: TimerReset },
  { href: "/practice", index: "04", label: "Clinical cases", short: "Cases", icon: Stethoscope },
];

export function Navigation() {
  const pathname = usePathname();
  const { user, loading, logout } = useAuth();
  const [accountError, setAccountError] = useState<string | null>(null);

  async function signOut() {
    setAccountError(null);
    try {
      await logout();
    } catch {
      setAccountError("Sign-out could not be confirmed. You remain signed in; try again.");
    }
  }

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <aside className="side-nav">
      <Link className="brand" href="/" aria-label="Trace ECG home">
        <span className="brand-mark" aria-hidden="true">
          <Activity size={19} strokeWidth={2.2} />
        </span>
        <span className="brand-copy">
          <strong>TRACE</strong>
          <small>ECG intelligence</small>
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
            <Link className={`nav-link${active ? " active" : ""}`} href={link.href} key={link.href} aria-label={link.label} aria-current={active ? "page" : undefined}>
              <span className="nav-index">{link.index}</span>
              <Icon size={18} aria-hidden="true" />
              <span className="nav-long-label">{link.label}</span>
              <span className="nav-short-label">{link.short}</span>
            </Link>
          );
        })}

        <p className="nav-section-label nav-section-progress">Your learning</p>
        <Link className={`nav-link${isActive("/profile") ? " active" : ""}`} href="/profile" aria-label="Progress and insights" aria-current={isActive("/profile") ? "page" : undefined}>
          <span className="nav-index">··</span>
          <ChartNoAxesCombined size={18} aria-hidden="true" />
          <span className="nav-long-label">Progress & insights</span>
          <span className="nav-short-label">Progress</span>
        </Link>
        <Link className={`nav-link${isActive("/review") ? " active" : ""}`} href="/review" aria-label="Adaptive mastery coach" aria-current={isActive("/review") ? "page" : undefined}>
          <span className="nav-index">··</span>
          <BrainCircuit size={18} aria-hidden="true" />
          <span className="nav-long-label">Mastery coach</span>
          <span className="nav-short-label">Coach</span>
        </Link>
      </nav>

      <div className="nav-ai-status">
        <span className="status-orb" aria-hidden="true" />
        <div>
          <strong>AI coach ready</strong>
          <span>Grounded to each tracing</span>
        </div>
      </div>

      <div className="nav-account" aria-label="Account">
        {loading ? (
          <span className="nav-account-name muted">Loading profile…</span>
        ) : user ? (
          <>
            <span className="nav-avatar" aria-hidden="true">{(user.displayName || user.username).slice(0, 1).toUpperCase()}</span>
            <span className="nav-account-name" title={user.username}>
              <span>{user.displayName || user.username}</span>
              <small>Private server-synced progress</small>
            </span>
            <Link className="nav-account-action icon-only" href="/account" title="Account security" aria-label="Account security">
              <Settings size={15} aria-hidden="true" />
            </Link>
            <button className="nav-account-action icon-only" type="button" onClick={() => void signOut()} title="Sign out" aria-label="Sign out">
              <LogOut size={15} aria-hidden="true" />
            </button>
          </>
        ) : (
          <>
            <span className="nav-avatar guest" aria-hidden="true"><UserRound size={16} /></span>
            <span className="nav-account-name muted">
              <span>Guest learner</span>
              <small>This browser’s record · sign in to keep it across devices</small>
            </span>
            <Link className="nav-account-action icon-only" href="/login" title="Sign in" aria-label="Sign in">
              <LogIn size={15} aria-hidden="true" />
            </Link>
          </>
        )}
      </div>

      {accountError ? <div className="nav-account-error" role="alert">{accountError}</div> : null}

      <div className="nav-disclaimer">
        <BookOpen size={14} aria-hidden="true" />
        <span>For education, not clinical diagnosis.</span>
      </div>
    </aside>
  );
}
