import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Learning dashboard",
};

export default function MyLearningLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
