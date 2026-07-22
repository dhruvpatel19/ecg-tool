"use client";

import {
  ArrowRight,
  CheckCircle2,
  CircleAlert,
  ClipboardCheck,
  GraduationCap,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type PathwayProgressItem } from "@/lib/api";
import {
  FOUNDATIONS_SCENE_NAVIGATION,
  foundationsSceneHref,
  foundationsSceneNavigation,
} from "@/lib/learning/foundationsNavigation";
import { PRODUCTION_PATHWAY_ID } from "@/lib/pathways";
import styles from "./FoundationsStatusCard.module.css";

type FoundationsStatusCardProps = {
  learnerId: string | undefined;
};

function isReviewLater(item: PathwayProgressItem) {
  return item.status !== "complete" && item.state?.reviewLater === true;
}

function activeResumeItem(items: PathwayProgressItem[]) {
  return items
    .filter((item) => !isReviewLater(item) && ["viewed", "attempted", "needs-review"].includes(item.status))
    .sort((left, right) => {
      const leftTime = Date.parse(left.updatedAt ?? "");
      const rightTime = Date.parse(right.updatedAt ?? "");
      return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
    })[0] ?? null;
}

export function FoundationsStatusCard({ learnerId }: FoundationsStatusCardProps) {
  const [items, setItems] = useState<PathwayProgressItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (!learnerId) {
      setItems([]);
      setLoading(true);
      setError(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    api.pathwayProgress(learnerId, PRODUCTION_PATHWAY_ID)
      .then((response) => {
        if (cancelled) return;
        const knownScenes = new Set(FOUNDATIONS_SCENE_NAVIGATION.map((scene) => scene.id));
        setItems(response.items.filter((item) => (
          item.moduleId === "foundations" && knownScenes.has(item.sceneId as typeof FOUNDATIONS_SCENE_NAVIGATION[number]["id"])
        )));
      })
      .catch(() => {
        if (!cancelled) {
          setItems([]);
          setError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [learnerId, retryKey]);

  const summary = useMemo(() => {
    const byScene = new Map(items.map((item) => [item.sceneId, item]));
    const completed = items.filter((item) => item.status === "complete").length;
    const guidedChecks = new Set(
      items.flatMap((item) => item.completedActionIds.map((actionId) => `${item.sceneId}:${actionId}`)),
    ).size;
    const reviews = items.filter((item) => item.status === "needs-review" || isReviewLater(item)).length;
    const active = activeResumeItem(items);
    const next = active
      ?? FOUNDATIONS_SCENE_NAVIGATION
        .map((scene) => byScene.get(scene.id) ?? null)
        .find((item) => !item || (!isReviewLater(item) && !["complete", "skipped"].includes(item.status)))
      ?? FOUNDATIONS_SCENE_NAVIGATION
        .map((scene) => byScene.get(scene.id) ?? null)
        .find((item) => item && isReviewLater(item))
      ?? null;
    const allComplete = completed === FOUNDATIONS_SCENE_NAVIGATION.length;
    const sceneId = next?.sceneId ?? (allComplete ? "S0" : FOUNDATIONS_SCENE_NAVIGATION[0].id);
    const scene = foundationsSceneNavigation(sceneId) ?? FOUNDATIONS_SCENE_NAVIGATION[0];
    return {
      completed,
      guidedChecks,
      reviews,
      scene,
      href: foundationsSceneHref(scene.id) ?? "/learn/foundations",
      cta: allComplete ? "Review Foundations" : next && isReviewLater(next) ? "Review deferred scene" : items.length ? "Continue Foundations" : "Start Foundations",
      allComplete,
    };
  }, [items]);

  return (
    <section className={styles.card} aria-labelledby="foundations-status-heading" data-testid="foundations-status" aria-busy={loading}>
      <header>
        <span className={styles.identity} aria-hidden="true"><GraduationCap size={20} /></span>
        <div>
          <p className="eyebrow">Guided learning</p>
          <h2 id="foundations-status-heading">Your Foundations path</h2>
          <p>See what you have completed, what needs another look, and where to continue.</p>
        </div>
        {!loading && !error ? (
          <Link href={summary.href}>{summary.cta} <ArrowRight size={15} aria-hidden="true" /></Link>
        ) : null}
      </header>

      {loading ? (
        <div className={styles.status} role="status">Loading your Foundations path…</div>
      ) : error ? (
        <div className={styles.status} role="alert">
          <CircleAlert size={18} aria-hidden="true" />
          <span>Your Foundations path could not be loaded. Your saved work is unchanged.</span>
          <button type="button" onClick={() => setRetryKey((value) => value + 1)}><RefreshCw size={14} aria-hidden="true" /> Retry</button>
        </div>
      ) : (
        <>
          <div className={styles.metrics} aria-label="Foundations path status">
            <article>
              <span data-tone="path" aria-hidden="true"><CheckCircle2 size={18} /></span>
              <div><strong>{summary.completed}/{FOUNDATIONS_SCENE_NAVIGATION.length}</strong><h3>Lessons</h3><p>Foundations lessons completed.</p></div>
            </article>
            <article>
              <span data-tone="evidence" aria-hidden="true"><ClipboardCheck size={18} /></span>
              <div><strong>{summary.guidedChecks}</strong><h3>Evidence</h3><p>Practice questions completed across these lessons.</p></div>
            </article>
            <article>
              <span data-tone="review" aria-hidden="true"><RotateCcw size={18} /></span>
              <div><strong>{summary.reviews}</strong><h3>Reviews</h3><p>Lessons you marked for review or have not yet completed.</p></div>
            </article>
          </div>
          <footer>
            <div>
              <span>{summary.allComplete ? "Path complete · review from" : "Resume at"} {summary.scene.id}</span>
              <strong>{summary.scene.title}</strong>
            </div>
            <Link href={summary.href} aria-label={`${summary.cta}: ${summary.scene.title}`}><ArrowRight size={16} aria-hidden="true" /></Link>
          </footer>
        </>
      )}
    </section>
  );
}
