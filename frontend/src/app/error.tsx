"use client";

import { AlertTriangle, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

export default function RouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("TRACE route error", error);
  }, [error]);

  return (
    <section className="system-page" aria-labelledby="route-error-title">
      <span className="system-page-icon error" aria-hidden="true"><AlertTriangle /></span>
      <div>
        <p className="eyebrow">Workspace interrupted</p>
        <h1 id="route-error-title">This page did not finish loading.</h1>
        <p>Your saved learning record is unchanged. Retry the page, or return to your dashboard and choose another activity.</p>
        <div className="actions">
          <button className="button primary" type="button" onClick={reset}><RotateCcw size={17} aria-hidden="true" /> Retry</button>
          <Link className="button" href="/home">Return to dashboard</Link>
        </div>
      </div>
    </section>
  );
}
