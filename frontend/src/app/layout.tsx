import type { Metadata } from "next";
import { connection } from "next/server";
import { AppShell } from "@/components/layout/AppShell";
import { LearningPreferencesBridge } from "@/components/layout/LearningPreferencesBridge";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";
import "@/components/layout/learning-workspace.css";

export const metadata: Metadata = {
  title: {
    default: "TRACE · ECG learning for medical students",
    template: "%s · TRACE",
  },
  description: "Learn ECG interpretation through guided lessons, focused practice, rapid reads, and clinical cases built for medical students.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // The per-request CSP nonce is injected by src/proxy.ts. Force request-time
  // rendering so Next can attach that nonce to every framework/page script;
  // statically generated HTML cannot safely use a request-specific nonce.
  await connection();
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>
        <AuthProvider>
          <LearningPreferencesBridge />
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
