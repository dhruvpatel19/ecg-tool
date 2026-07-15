import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Clinical cases",
};

export default function ClinicalCasesLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
