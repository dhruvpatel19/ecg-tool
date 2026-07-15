import { ArrowLeft, ShieldCheck } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";
import styles from "./PublicInfoPage.module.css";

export function PublicInfoPage({
  eyebrow,
  title,
  intro,
  children,
}: {
  eyebrow: string;
  title: string;
  intro: string;
  children: ReactNode;
}) {
  return (
    <article className={styles.page}>
      <header className={styles.header}>
        <Link href="/"><ArrowLeft size={16} aria-hidden="true" /> Back to TRACE</Link>
        <p>{eyebrow}</p>
        <h1>{title}</h1>
        <div className={styles.intro}><ShieldCheck size={18} aria-hidden="true" /><span>{intro}</span></div>
      </header>
      <div className={styles.content}>{children}</div>
      <footer className={styles.footer}>
        <Link href="/privacy">Privacy</Link>
        <Link href="/terms">Terms</Link>
        <Link href="/accessibility">Accessibility</Link>
        <Link href="/data-sources">Data sources</Link>
      </footer>
    </article>
  );
}
