"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const ROUTE_NAMES: Array<[string, string]> = [
  ["/home", "Learning dashboard"],
  ["/dashboard", "Learning dashboard"],
  ["/learn", "Guided learning"],
  ["/train", "Focused practice"],
  ["/rapid", "Rapid practice"],
  ["/practice", "Clinical cases"],
  ["/profile", "My learning"],
  ["/review", "Study plan"],
  ["/account", "Account"],
  ["/privacy", "Privacy and learning data"],
  ["/terms", "Terms of use"],
  ["/accessibility", "Accessibility"],
  ["/data-sources", "Data sources and attribution"],
  ["/verify-email", "Verify email"],
  ["/forgot-password", "Password recovery"],
  ["/reset-password", "Reset password"],
  ["/login", "Sign in"],
  ["/", "ECG learning home"],
];

function routeName(pathname: string) {
  return ROUTE_NAMES.find(([prefix]) => prefix === "/" ? pathname === "/" : pathname.startsWith(prefix))?.[1] ?? "Page";
}

export function RouteAccessibility({ pageNameOverride }: { pageNameOverride?: string } = {}) {
  const pathname = usePathname();
  const previousPathname = useRef<string | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const pageName = pageNameOverride ?? routeName(pathname);

  useEffect(() => {
    const routeChanged = previousPathname.current !== null && previousPathname.current !== pathname;
    previousPathname.current = pathname;

    const frame = window.requestAnimationFrame(() => {
      setAnnouncement(`${pageName} loaded`);
      if (routeChanged) {
        document.getElementById("main-content")?.focus({ preventScroll: true });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pageName, pathname]);

  return (
    <span
      className="sr-only"
      aria-live="polite"
      aria-atomic="true"
      data-route-accessibility-ready={announcement ? "true" : "false"}
    >
      {announcement}
    </span>
  );
}
