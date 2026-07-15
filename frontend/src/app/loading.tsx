"use client";

import { LoaderCircle } from "lucide-react";
import { usePathname } from "next/navigation";
import { isPublicEntryPath } from "@/lib/routeAccess";

type LoadingCopy = {
  eyebrow: string;
  title: string;
  body: string;
};

const PUBLIC_LOADING_COPY: Record<string, LoadingCopy> = {
  "/": {
    eyebrow: "TRACE",
    title: "Opening TRACE…",
    body: "Loading the ECG learning overview.",
  },
  "/login": {
    eyebrow: "Account access",
    title: "Opening account access…",
    body: "Sign in or create your account.",
  },
  "/verify-email": {
    eyebrow: "Account security",
    title: "Opening email verification…",
    body: "Loading this secure account step.",
  },
  "/forgot-password": {
    eyebrow: "Account recovery",
    title: "Opening password recovery…",
    body: "Loading this secure account step.",
  },
  "/reset-password": {
    eyebrow: "Account recovery",
    title: "Opening password reset…",
    body: "Loading this secure account step.",
  },
  "/account/email-change": {
    eyebrow: "Account security",
    title: "Opening email confirmation…",
    body: "Loading this secure account step.",
  },
};

const DEFAULT_PUBLIC_COPY: LoadingCopy = {
  eyebrow: "TRACE",
  title: "Opening this page…",
  body: "Loading TRACE information.",
};

const PRIVATE_LOADING_COPY: LoadingCopy = {
  eyebrow: "Your learning workspace",
  title: "Preparing your workspace…",
  body: "Loading your learning record and next activity.",
};

export default function Loading() {
  const pathname = usePathname();
  const copy = isPublicEntryPath(pathname)
    ? PUBLIC_LOADING_COPY[pathname] ?? DEFAULT_PUBLIC_COPY
    : PRIVATE_LOADING_COPY;

  return (
    <section className="system-page" aria-labelledby="route-loading-title" aria-busy="true">
      <LoaderCircle className="system-page-spinner" aria-hidden="true" />
      <div>
        <p className="eyebrow">{copy.eyebrow}</p>
        <h1 id="route-loading-title">{copy.title}</h1>
        <p>{copy.body}</p>
      </div>
    </section>
  );
}
