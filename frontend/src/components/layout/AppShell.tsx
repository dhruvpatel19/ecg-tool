"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Navigation } from "@/components/Navigation";
import { isPublicEntryPath } from "@/lib/routeAccess";
import { RouteAccessibility } from "./RouteAccessibility";

/**
 * The marketing/auth entry experience and the signed-in learning workspace use
 * deliberately different shells. A public visitor should not land inside a
 * dashboard sidebar before they understand the product.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const publicEntry = isPublicEntryPath(pathname);

  return (
    <div className={`app-shell${publicEntry ? " public-shell" : ""}`}>
      <a
        className="skip-link"
        href="#main-content"
        onClick={() => window.requestAnimationFrame(() => {
          document.getElementById("main-content")?.focus({ preventScroll: true });
        })}
      >
        Skip to main content
      </a>
      <Navigation />
      <RouteAccessibility pageNameOverride={publicEntry && pathname === "/" ? "ECG learning home" : undefined} />
      <main className="main" id="main-content" tabIndex={-1}>{children}</main>
    </div>
  );
}
