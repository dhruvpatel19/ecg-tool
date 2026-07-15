import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Rapid practice",
};

export default function RapidPracticeLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
