"use client";

import {
  Activity,
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  FlaskConical,
  HeartPulse,
  Layers3,
  LockKeyhole,
  MessageCircleQuestion,
  MousePointer2,
  Route,
  Sparkles,
  Waves,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type CurriculumModule, type PathwayProgressItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { MODULES } from "@/lib/modules";
import { FOUNDATIONS_PATHWAY_ID, PRODUCTION_PATHWAY_ID } from "@/lib/pathways";
import {
  readFoundationsProgress,
  readProductionModuleProgress,
  subscribeProgress,
  type ModuleProgress,
} from "@/lib/progress";

const moduleIcons = [BookOpenCheck, Waves, Activity, Layers3, CircleDot, HeartPulse, CircleDot, BrainCircuit, FlaskConical, Route];

export default function LearnPage() {
  const { user, identityKey, loading: authLoading } = useAuth();
  const [modules, setModules] = useState<CurriculumModule[]>([]);
  const [expanded, setExpanded] = useState<string>("foundations");
  const [foundations, setFoundations] = useState<ModuleProgress | null>(null);
  const [productionProgress, setProductionProgress] = useState<Record<string, ModuleProgress>>({});
  const [resumeScenes, setResumeScenes] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (authLoading) return;
    let cancelled = false;
    api.curriculum().then((data) => {
      if (!cancelled) setModules(data.modules);
    }).catch((err: Error) => {
      if (!cancelled) setError(err.message);
    });
    const refresh = () => {
      setFoundations(readFoundationsProgress(13, identityKey));
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
      Promise.all([
        api.pathwayProgress(user.userId, PRODUCTION_PATHWAY_ID),
        api.pathwayProgress(user.userId, FOUNDATIONS_PATHWAY_ID),
      ])
        .then(([response, foundationsResponse]) => {
          if (cancelled) return;
          const foundationItem = foundationsResponse.items.find((item) => item.moduleId === "foundations");
          if (foundationItem) {
            const completedScenes = Number(foundationItem.state.completedScenes ?? foundationItem.completedActionIds.length);
            const totalScenes = Number(foundationItem.state.totalScenes ?? 13);
            setFoundations({
              completedScenes,
              totalScenes,
              done: foundationItem.status === "complete" || completedScenes >= totalScenes,
              started: foundationItem.status !== "not-started",
              bestAccuracy: Number(foundationItem.state.bestAccuracy ?? 0),
            });
          }
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
              .filter((item) => item.status !== "not-started" && item.status !== "complete")
              .at(-1);
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
  }, [authLoading, identityKey, user]);

  const summary = useMemo(() => {
    const selectorCount = modules.reduce((sum, module) => sum + module.lessons.length, 0);
    const sceneCount = MODULES.reduce((sum, module) => sum + (module.sceneCount ?? 0), 0);
    const caseCount = modules.reduce((sum, module) => sum + module.reliableCaseCount, 0);
    return { selectorCount: selectorCount || 18, sceneCount, caseCount };
  }, [modules]);

  return (
    <div className="page learn-home">
      <header className="learn-hero">
        <div>
          <p className="eyebrow">Mode 01 · Guided learning</p>
          <h1>Understand the trace,<br />not just the label.</h1>
          <p>
            A dependency-ordered curriculum with an AI tutor inside the learning loop. Ask a tangent, manipulate the ECG,
            test the idea, and return exactly where you paused.
          </p>
          <div className="hero-actions">
            <Link className="button primary" href="/learn/foundations">
              <Sparkles size={17} aria-hidden="true" /> {foundations?.started ? "Resume foundations" : "Start foundations"} <ArrowRight size={16} />
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

      <section className="learn-principles" aria-label="Learning design">
        <div><MousePointer2 size={18} /><span><strong>Learn by doing</strong><small>Directly on the waveform</small></span></div>
        <div><MessageCircleQuestion size={18} /><span><strong>Ask anything</strong><small>Tangents preserve your place</small></span></div>
        <div><FlaskConical size={18} /><span><strong>Use real variation</strong><small>Not one perfect cartoon</small></span></div>
        <div><Route size={18} /><span><strong>Release support</strong><small>Modeled → independent</small></span></div>
      </section>

      <section className="curriculum-section" id="curriculum">
        <div className="section-heading-row">
          <div>
            <p className="eyebrow">Curriculum map</p>
            <h2>From first wave to clinical synthesis.</h2>
          </div>
          <p>{modules.length || 10} modules · {summary.sceneCount} interactive scenes · {summary.selectorCount} adaptive selectors · grounded in {summary.caseCount ? `${summary.caseCount.toLocaleString()} case matches` : "the full ECG corpus"}</p>
        </div>

        <div className="curriculum-list">
          {(modules.length ? modules : fallbackModules).map((module, index) => {
            const Icon = moduleIcons[index] ?? BookOpenCheck;
            const open = expanded === module.id;
            const isFoundations = module.id === "foundations";
            const registryModule = MODULES.find((entry) => entry.id === module.id);
            const progress = isFoundations ? foundations : productionProgress[module.id];
            const pathway = progress?.totalScenes ? progress.completedScenes / progress.totalScenes : 0;
            const pathwayDone = Boolean(progress?.done);
            const competency = Math.round((module.mastery || 0) * 100);
            const sceneCount = registryModule?.sceneCount ?? progress?.totalScenes ?? 0;
            const startHref = isFoundations
              ? "/learn/foundations"
              : `/learn/${module.id}${resumeScenes[module.id] ? `?scene=${encodeURIComponent(resumeScenes[module.id])}` : ""}`;

            return (
              <article className={`curriculum-module${open ? " open" : ""}`} key={module.id}>
                <button className="curriculum-module-summary" type="button" onClick={() => setExpanded(open ? "" : module.id)} aria-expanded={open}>
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
                      <em>{sceneCount} scenes</em>
                    )}
                    <span className="curriculum-meter"><i style={{ width: `${Math.round(pathway * 100)}%` }} /></span>
                    <small>{Math.round(pathway * 100)}% pathway · {competency}% competency evidence</small>
                  </span>
                  <ChevronDown className="curriculum-chevron" size={18} aria-hidden="true" />
                </button>

                {open ? (
                  <div className="curriculum-module-detail">
                    <div className="lesson-chip-list">
                      {module.lessons.map((lesson, lessonIndex) => (
                        <Link
                          className={`lesson-chip${lesson.available || isFoundations ? "" : " disabled"}`}
                          href={isFoundations ? "/learn/foundations" : `/learn/${module.id}`}
                          key={lesson.id}
                          aria-disabled={!lesson.available && !isFoundations}
                        >
                          <span>{lessonIndex + 1}</span>
                          <div><strong>{lesson.title}</strong><small>{lesson.objectives.slice(0, 3).map((item) => item.label).join(" · ") || "Interactive foundation"}</small></div>
                          {lesson.available || isFoundations ? <ArrowRight size={15} /> : <LockKeyhole size={14} />}
                        </Link>
                      ))}
                    </div>
                    <div className="module-start-panel">
                      <p><Sparkles size={15} /> AI-guided pathway</p>
                      <strong>{sceneCount} interactive scenes · real-trace workspace</strong>
                      <span>{isFoundations ? "Animations, box counting, calipers, axis experiments, and three complete reads." : "Mechanism → trace → discrimination → checkpoint → matched practice, with an exact AI tangent waypoint."}</span>
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
  lessons: [
    {
      id: `${module.id}-pathway`,
      title: module.title,
      objectives: [],
      reliableCaseCount: 0,
      available: module.status === "ready",
      mastery: 0,
    },
  ],
}));
