import type { Metadata } from "next";
import { connection } from "next/server";
import { Navigation } from "@/components/Navigation";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "TRACE · Adaptive ECG Learning",
  description: "AI-guided ECG learning, deliberate practice, rapid interpretation, and clinical decision training on grounded real waveforms.",
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
          <div className="app-shell">
            <a className="skip-link" href="#main-content">Skip to learning content</a>
            <Navigation />
            <main className="main" id="main-content" tabIndex={-1}>{children}</main>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}
