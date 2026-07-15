import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Guided learning",
};

export default function GuidedLearningLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
