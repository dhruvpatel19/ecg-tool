import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Focused practice",
};

export default function FocusedPracticeLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
