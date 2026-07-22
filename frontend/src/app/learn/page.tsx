"use client";

import {
  Activity,
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  FlaskConical,
  HeartPulse,
  Layers3,
  LockKeyhole,
  Route,
  Sparkles,
  Waves,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  api,
  type CurriculumModule,
  type LearningResumeSession,
  type PathwayProgressItem,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { learningResumePresentation } from "@/lib/learningResume";
import { MODULES } from "@/lib/modules";
import { PRODUCTION_PATHWAY_ID } from "@/lib/pathways";
import {
  readProductionModuleProgress,
  subscribeProgress,
  type ModuleProgress,
} from "@/lib/progress";
import styles from "./learn.module.css";

const moduleIcons = [BookOpenCheck, Waves, Activity, Layers3, CircleDot, HeartPulse, CircleDot, BrainCircuit, FlaskConical, Route];

const lessonStartScenes: Record<string, Record<string, string>> = {
  "leads-vectors": {
    "lead-territories": "M02.S0",
    axis: "M02.S10",
  },
  "rhythm-ectopy": {
    rate: "M03.S3",
    "rhythm-basics": "M03.S0",
    ectopy: "M03.S6",
  },
  "av-brady": { "pr-av-block": "m04-s0" },
  "ventricular-conduction": {
    "qrs-conduction": "m05-s0",
    "bundle-branch-blocks": "m05-s1",
    "fascicular-preexcitation": "m05-s5",
    paced: "m05-s8",
  },
  tachyarrhythmias: {
    "af-flutter": "m06-s4",
    svt: "m06-s0",
  },
  "chambers-voltage": { hypertrophy: "m07-s0" },
  "repolarization-safety": { "qt-qtc": "m08-s0" },
  "ischemia-infarction": {
    "ischemia-st-t": "m09-s0",
    "mi-localization": "m09-s2",
  },
  "integration-transfer": { "integrated-interpretation": "m10-s0" },
};

const moduleStartScenes: Record<string, string> = {
  "leads-vectors": "M02.S0",
  "rhythm-ectopy": "M03.S0",
  "av-brady": "m04-s0",
  "ventricular-conduction": "m05-s0",
  tachyarrhythmias: "m06-s0",
  "chambers-voltage": "m07-s0",
  "repolarization-safety": "m08-s0",
  "ischemia-infarction": "m09-s0",
  "integration-transfer": "m10-s0",
};

function lessonHref(moduleId: string, lessonId: string) {
  if (moduleId === "foundations") return "/learn/foundations";
  const sceneId = lessonStartScenes[moduleId]?.[lessonId] ?? moduleStartScenes[moduleId];
  return sceneId ? `/learn/${moduleId}?scene=${encodeURIComponent(sceneId)}` : `/learn/${moduleId}`;
}

export default function LearnPage() {
  const { user, loading: authLoading } = useAuth();
  const [modules, setModules] = useState<CurriculumModule[]>([]);
  const [expanded, setExpanded] = useState<string>("");
  const [productionProgress, setProductionProgress] = useState<Record<string, ModuleProgress>>({});
  const [resumeScenes, setResumeScenes] = useState<Record<string, string>>({});
  const [guidedResume, setGuidedResume] = useState<LearningResumeSession | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    let cancelled = false;
    setGuidedResume(null);
    const nativeFoundationsReady = user
      ? api.migrateFoundationsNativeProgress(user.userId)
        .then(() => undefined)
        .catch(() => {
          if (!cancelled) setError("Your earlier Foundations history could not be prepared yet. Current native work is unchanged.");
        })
      : Promise.resolve();
    api.curriculum().then((data) => {
      if (!cancelled) setModules(data.modules);
    }).catch((err: Error) => {
      if (!cancelled) setError(err.message);
    });
    nativeFoundationsReady.then(() => api.learningResume()).then((snapshot) => {
      if (cancelled) return;
      if (snapshot.version !== "learning-resume-v1") {
        setGuidedResume(null);
        return;
      }
      const sessions = [snapshot.primary, ...snapshot.additional];
      setGuidedResume(sessions.find((session) => session?.mode === "guided") ?? null);
    }).catch(() => {
      if (!cancelled) setGuidedResume(null);
    });
    const refresh = () => {
      if (!user) {
        setProductionProgress(Object.fromEntries(
          MODULES
            .filter((module) => module.progressKey === "production" && module.sceneCount)
            .map((module) => [module.id, readProductionModuleProgress(module.id, module.sceneCount ?? 0)]),
        ));
        setResumeScenes({});
      }
    };
    refresh();
    if (user) {
      nativeFoundationsReady
        .then(() => api.pathwayProgress(user.userId, PRODUCTION_PATHWAY_ID))
        .then((response) => {
          if (cancelled) return;
          const byModule = new Map<string, PathwayProgressItem[]>();
          response.items.forEach((item) => byModule.set(item.moduleId, [...(byModule.get(item.moduleId) ?? []), item]));
          setProductionProgress(Object.fromEntries(MODULES
            .filter((module) => module.progressKey === "production" && module.sceneCount)
            .map((module) => {
              const items = byModule.get(module.id) ?? [];
              const completedScenes = items.filter((item) => item.status === "complete").length;
              const started = items.some((item) => item.status !== "not-started");
              return [module.id, {
                completedScenes,
                totalScenes: module.sceneCount ?? 0,
                done: completedScenes >= (module.sceneCount ?? 0),
                started,
                bestAccuracy: 0,
              } satisfies ModuleProgress];
            })));
          setResumeScenes(Object.fromEntries(MODULES.flatMap((module) => {
            const items = byModule.get(module.id) ?? [];
            const resumable = items
              .filter((item) => !["not-started", "complete", "skipped"].includes(item.status))
              .sort((left, right) => (
                (right.updatedAt ?? "").localeCompare(left.updatedAt ?? "")
                || (right.createdAt ?? "").localeCompare(left.createdAt ?? "")
                || left.sceneId.localeCompare(right.sceneId)
              ))[0];
            return resumable ? [[module.id, resumable.sceneId]] : [];
          })));
        })
        .catch((err: Error) => {
          if (!cancelled) setError(`Private pathway progress could not load. ${err.message}`);
        });
      return () => { cancelled = true; };
    }
    const unsubscribe = subscribeProgress(refresh);
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [authLoading, user]);

  const summary = useMemo(() => {
    const sceneCount = MODULES.reduce((sum, module) => sum + (module.sceneCount ?? 0), 0);
    return { sceneCount };
  }, []);
  const guidedResumePresentation = guidedResume ? learningResumePresentation(guidedResume) : null;

  return (
    <div className={`page learn-home ${styles.hub}`}>
      <header className="learn-hero">
        <div>
          <p className="eyebrow">Guided learning</p>
          <h1>Understand the trace,<br />not just the label.</h1>
          <p>
            Work through one idea at a time on real ECGs. Manipulate the trace, test your reasoning, and ask the
            grounded tutor when you need it.
          </p>
          <div className="hero-actions">
            <Link className="button primary" href={guidedResumePresentation?.href ?? "/learn/foundations"}>
              <Sparkles size={17} aria-hidden="true" /> {guidedResumePresentation ? "Resume Guided learning" : productionProgress.foundations?.started ? "Resume foundations" : "Start foundations"} <ArrowRight size={16} />
            </Link>
            <a className="button" href="#curriculum">Explore curriculum</a>
          </div>
        </div>

        <div className="learn-loop-card">
          <p className="eyebrow">Every lesson follows the loop</p>
          <div className="learn-loop">
            <span><i>1</i><strong>See it</strong><small>model + animate</small></span>
            <b aria-hidden="true">→</b>
            <span><i>2</i><strong>Try it</strong><small>point + measure</small></span>
            <b aria-hidden="true">→</b>
            <span><i>3</i><strong>Explain it</strong><small>reason back</small></span>
            <b aria-hidden="true">→</b>
            <span><i>4</i><strong>Transfer it</strong><small>new tracing</small></span>
          </div>
          <div className="learn-tutor-note">
            <BrainCircuit size={17} />
            <span><strong>Your tutor sees the lesson state.</strong> It can highlight a lead, place calipers, answer a tangent, or fade a hint—without inventing the ECG finding.</span>
          </div>
        </div>
      </header>

      {error ? <div className="warning">The live curriculum could not load. {error}</div> : null}

      <section className="curriculum-section" id="curriculum">
        <div className="section-heading-row">
          <div>
            <p className="eyebrow">Curriculum map</p>
            <h2>From first wave to clinical synthesis.</h2>
          </div>
          <p>{modules.length || 10} modules · {summary.sceneCount} interactive scenes · real ECGs throughout</p>
        </div>

        <div className="curriculum-list">
          {(modules.length ? modules : fallbackModules).map((module, index) => {
            const Icon = moduleIcons[index] ?? BookOpenCheck;
            const open = expanded === module.id;
            const isFoundations = module.id === "foundations";
            const registryModule = MODULES.find((entry) => entry.id === module.id);
            const progress = productionProgress[module.id];
            const pathway = progress?.totalScenes ? progress.completedScenes / progress.totalScenes : 0;
            const pathwayDone = Boolean(progress?.done);
            const competency = Math.round((module.mastery || 0) * 100);
            const assessedObjectiveCount = module.assessedObjectiveCount ?? 0;
            const sceneCount = registryModule?.sceneCount ?? progress?.totalScenes ?? 0;
            const startHref = isFoundations
              ? `/learn/foundations${resumeScenes[module.id] ? `?scene=${encodeURIComponent(resumeScenes[module.id])}` : ""}`
              : `/learn/${module.id}${resumeScenes[module.id] ? `?scene=${encodeURIComponent(resumeScenes[module.id])}` : ""}`;
            const summaryId = `curriculum-${module.id}-summary`;
            const detailId = `curriculum-${module.id}-detail`;

            return (
              <article className={`curriculum-module${open ? " open" : ""}`} key={module.id}>
                <button
                  id={summaryId}
                  className="curriculum-module-summary"
                  type="button"
                  onClick={() => setExpanded(open ? "" : module.id)}
                  aria-expanded={open}
                  aria-controls={detailId}
                >
                  <span className="curriculum-order">{String(index + 1).padStart(2, "0")}</span>
                  <span className="curriculum-icon"><Icon size={20} aria-hidden="true" /></span>
                  <span className="curriculum-title">
                    <strong>{module.title}</strong>
                    <small>{module.overview}</small>
                  </span>
                  <span className="curriculum-meta">
                    {pathwayDone ? (
                      <em><CheckCircle2 size={13} /> Pathway complete</em>
                    ) : progress?.started ? (
                      <em>{progress.completedScenes}/{sceneCount} scenes complete</em>
                    ) : (
                      <em>Not started · {sceneCount} scenes</em>
                    )}
                    <span
                      className="curriculum-meter"
                      role="progressbar"
                      aria-label={`${module.title} pathway progress`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(pathway * 100)}
                    ><i style={{ width: `${Math.round(pathway * 100)}%` }} /></span>
                    <small>
                      {Math.round(pathway * 100)}% pathway · {assessedObjectiveCount > 0
                        ? `${competency}% mastery estimate`
                        : "not independently assessed"}
                    </small>
                  </span>
                  <ChevronDown className="curriculum-chevron" size={18} aria-hidden="true" />
                </button>

                {open ? (
                  <div id={detailId} className="curriculum-module-detail" role="region" aria-labelledby={summaryId}>
                    <div className="lesson-chip-list">
                      {module.lessons.map((lesson, lessonIndex) => {
                        const available = lesson.available || isFoundations;
                        const contents = (
                          <>
                            <span>{lessonIndex + 1}</span>
                            <div><strong>{lesson.title}</strong><small>{lesson.objectives.slice(0, 3).map((item) => item.label).join(" · ") || "Interactive foundation"}</small></div>
                            {available ? <ArrowRight size={15} /> : <LockKeyhole size={14} />}
                          </>
                        );
                        return available ? (
                          <Link className="lesson-chip" href={lessonHref(module.id, lesson.id)} key={lesson.id}>
                            {contents}
                          </Link>
                        ) : (
                          <div
                            className="lesson-chip disabled"
                            key={lesson.id}
                            aria-disabled="true"
                            aria-label={`${lesson.title} unavailable`}
                            data-lesson-unavailable="true"
                          >
                            {contents}
                          </div>
                        );
                      })}
                    </div>
                    <div className="module-start-panel">
                      <p><Sparkles size={15} /> Guided pathway</p>
                      <strong>{sceneCount} interactive scenes · real-trace workspace</strong>
                      <span>{isFoundations ? "Animations, box counting, calipers, axis experiments, and three complete reads." : "Build the mechanism, work on a real trace, compare close mimics, and test transfer—with the tutor available when you need it."}</span>
                      <Link className="button primary" href={startHref}>{pathwayDone ? "Review pathway" : progress?.started ? "Resume pathway" : "Open pathway"} <ArrowRight size={15} /></Link>
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}

const fallbackModules: CurriculumModule[] = MODULES.map((module) => ({
  id: module.id,
  title: module.title,
  overview: module.blurb,
  order: module.order,
  prerequisites: module.prerequisites,
  reliableCaseCount: 0,
  available: module.status === "ready",
  mastery: 0,
  assessedObjectiveCount: 0,
  objectiveCount: 0,
  lessons: [
    {
      id: `${module.id}-pathway`,
      title: module.title,
      objectives: [],
      reliableCaseCount: 0,
      available: module.status === "ready",
      mastery: 0,
      assessedObjectiveCount: 0,
      objectiveCount: 0,
    },
  ],
}));
