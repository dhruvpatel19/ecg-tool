"use client";

import { FileQuestion } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";

export default function NotFound() {
  const { user } = useAuth();
  const primaryHref = user ? "/home" : "/";
  return (
    <section className="system-page" aria-labelledby="not-found-title">
      <span className="system-page-icon" aria-hidden="true"><FileQuestion /></span>
      <div>
        <p className="eyebrow">Page not found</p>
        <h1 id="not-found-title">That learning route is not available.</h1>
        <p>The link may be out of date. Your progress has not been changed.</p>
        <div className="actions">
          <Link className="button primary" href={primaryHref}>{user ? "Return to dashboard" : "Return to home"}</Link>
          <Link className="button" href="/learn">Browse Guided learning</Link>
        </div>
      </div>
    </section>
  );
}
