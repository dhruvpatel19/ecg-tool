import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "My learning",
};

export default function MyLearningLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
