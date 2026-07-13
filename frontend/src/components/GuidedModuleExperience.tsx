"use client";

import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDashed,
  Clock3,
  Eye,
  FlaskConical,
  Link2,
  MessageCircleQuestion,
  PauseCircle,
  RotateCcw,
  SkipForward,
  Sparkles,
  Target,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { LearningInteractionRenderer } from "@/components/learning/LearningInteractionRenderer";
import { TutorChat } from "@/components/TutorChat";
import { api } from "@/lib/api";
import { GUIDED_MODULE_BY_ID, GUIDED_MODULES, type GuidedScene, type LearningPhase } from "@/lib/guidedCurriculum";
import { interactionsForScene } from "@/lib/learning/guidedInteractionSpecs";
import type { InteractionEvidence, LearningInteraction } from "@/lib/learning/interactionTypes";
import type { CasePacket, CaseSummary, ViewerAction, ViewerTaskEvidence, ViewerTaskSpec } from "@/lib/types";
import type { ECGPoint } from "@/lib/coordinates";

type SceneStatus = "not-started" | "viewed" | "attempted" | "needs-review" | "complete" | "skipped";
type ProgressState = Record<string, Record<string, SceneStatus>>;

const STORAGE_KEY = "trace-guided-scene-progress-v3";
const MODULE_TOTAL = GUIDED_MODULES.length + 1;

const phaseLabels: Record<LearningPhase, string> = {
  retrieve: "Retrieve",
  build: "Build the mechanism",
  see: "See it on a trace",
  discriminate: "Target vs mimic",
  do: "Do it on the ECG",
  explain: "Explain the evidence",
  transfer: "Transfer",
  connect: "Connect and continue",
};

const phaseIcons: Record<LearningPhase, typeof Sparkles> = {
  retrieve: RotateCcw,
  build: BrainCircuit,
  see: Eye,
  discriminate: FlaskConical,
  do: Target,
  explain: MessageCircleQuestion,
  transfer: ArrowRight,
  connect: Link2,
};

function loadProgress(): ProgressState {
  if (typeof window === "undefined") return {};
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function persistProgress(value: ProgressState) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Progress remains usable in memory when storage is unavailable.
  }
}

function statusLabel(status: SceneStatus) {
  if (status === "complete") return "Complete";
  if (status === "needs-review") return "Needs review";
  if (status === "skipped") return "Skipped";
  if (status === "attempted") return "Attempted";
  if (status === "viewed") return "In progress";
  return "Not started";
}

function taskForInteraction(interaction: LearningInteraction): ViewerTaskSpec | undefined {
  if (interaction.kind === "point") {
    return { mode: "point", prompt: interaction.gradePrompt, concept: interaction.concept, allowedLeads: interaction.allowedLeads };
  }
  if (interaction.kind === "region") {
    return { mode: "region", prompt: interaction.prompt, concept: interaction.concept, allowedLeads: interaction.allowedLeads, minimumDurationMs: interaction.minimumDurationMs };
  }
  if (interaction.kind === "caliper") {
    return { mode: "caliper", prompt: interaction.prompt, measurement: interaction.measurement, allowedLeads: interaction.target.lead ? [interaction.target.lead] : undefined };
  }
  if (interaction.kind === "march") {
    return { mode: "march", prompt: interaction.prompt, target: interaction.target, minimumMarkers: interaction.minimumMarkers };
  }
  return undefined;
}

export function GuidedModuleExperience({ moduleId }: { moduleId: string }) {
  const module = GUIDED_MODULE_BY_ID.get(moduleId);
  const [sceneIndex, setSceneIndex] = useState(0);
  const [progress, setProgress] = useState<ProgressState>({});
  const [choiceIndex, setChoiceIndex] = useState<number | null>(null);
  const [attemptCount, setAttemptCount] = useState(0);
  const [revealedPrinciple, setRevealedPrinciple] = useState(0);
  const [caseSummary, setCaseSummary] = useState<CaseSummary | null>(null);
  const [packet, setPacket] = useState<CasePacket | null>(null);
  const [loadingCase, setLoadingCase] = useState(false);
  const [caseError, setCaseError] = useState<string | null>(null);
  const [caseSelectionNotice, setCaseSelectionNotice] = useState<string | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<ECGPoint | null>(null);
  const [viewerActions, setViewerActions] = useState<ViewerAction[]>([]);
  const [viewerTaskEvidence, setViewerTaskEvidence] = useState<ViewerTaskEvidence | null>(null);
  const [interactionEvidence, setInteractionEvidence] = useState<Record<string, InteractionEvidence>>({});

  useEffect(() => {
    setProgress(loadProgress());
    const requested = new URLSearchParams(window.location.search).get("scene");
    if (requested && module) {
      const index = module.scenes.findIndex((item) => item.id === requested);
      if (index >= 0) setSceneIndex(index);
    }
  }, [module]);

  const scene = module?.scenes[sceneIndex];

  const setSceneStatus = useCallback((sceneId: string, status: SceneStatus) => {
    if (!module) return;
    setProgress((current) => {
      const existing = current[module.id]?.[sceneId];
      if (existing === "complete" && status !== "complete") return current;
      const next = {
        ...current,
        [module.id]: { ...(current[module.id] ?? {}), [sceneId]: status },
      };
      persistProgress(next);
      return next;
    });
  }, [module]);

  useEffect(() => {
    if (!scene || !module) return;
    const existing = progress[module.id]?.[scene.id] ?? "not-started";
    if (existing === "not-started") setSceneStatus(scene.id, "viewed");
  }, [module, progress, scene, setSceneStatus]);

  useEffect(() => {
    if (!scene) return;
    setChoiceIndex(null);
    setAttemptCount(0);
    setRevealedPrinciple(0);
    setSelectedPoint(null);
    setViewerActions([]);
    setViewerTaskEvidence(null);
    setInteractionEvidence({});
    setCaseSummary(null);
    setPacket(null);
    setCaseError(null);
    setCaseSelectionNotice(null);
    setLoadingCase(true);
    let cancelled = false;
    api.tutorial(scene.lessonId, scene.focusConcept)
      .then(async (data) => {
        if (cancelled) return;
        if (data.selection?.requestedConceptUnavailable) {
          setCaseSelectionNotice(`No reliable ${scene.focusConcept.replaceAll("_", " ")} exemplar is available in the active corpus. This tracing is for mechanism or contrast only and cannot prove target recognition.`);
        } else if (data.selection?.exemplarRejections?.length) {
          setCaseSelectionNotice("A conflicted or borderline candidate was excluded by the teaching-exemplar gate; the tracing below is the next eligible case.");
        }
        setCaseSummary(data.recommendedCase);
        const nextPacket = await api.packet(data.recommendedCase.caseId);
        if (!cancelled) setPacket(nextPacket);
      })
      .catch((error: Error) => {
        if (!cancelled) setCaseError(error.message);
      })
      .finally(() => {
        if (!cancelled) setLoadingCase(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scene]);

  if (!module || !scene) {
    return (
      <div className="page">
        <section className="panel pad">
          <h1>Module not found</h1>
          <p className="muted">This guided module is not in the current curriculum map.</p>
          <Link className="button primary" href="/learn">Return to curriculum</Link>
        </section>
      </div>
    );
  }

  const sceneStatus = progress[module.id]?.[scene.id] ?? "viewed";
  const productionInteractions = interactionsForScene(module.id, scene.id);
  const selectedChoice = choiceIndex === null ? null : scene.choices[choiceIndex];
  const sceneComplete = sceneStatus === "complete";
  const completedCount = module.scenes.filter((item) => progress[module.id]?.[item.id] === "complete").length;
  const skippedCount = module.scenes.filter((item) => progress[module.id]?.[item.id] === "skipped").length;
  const progressPercent = Math.round((completedCount / module.scenes.length) * 100);
  const totalMinutes = module.scenes.reduce((sum, item) => sum + item.minutes, 0);
  const priorModule = GUIDED_MODULES.find((item) => item.order === module.order - 1);
  const nextModule = GUIDED_MODULES.find((item) => item.order === module.order + 1);
  const PhaseIcon = phaseIcons[scene.phase];
  const parts = Array.from(new Set(module.scenes.map((item) => item.part)));
  // Capture the narrowed values for callbacks. TypeScript cannot preserve the
  // guard above inside nested functions because those functions run later.
  const activeModule = module;
  const activeScene = scene;
  const viewerInteraction = productionInteractions.find((interaction) => ["point", "region", "caliper", "march"].includes(interaction.kind));
  const viewerTask = viewerInteraction ? taskForInteraction(viewerInteraction) : undefined;

  function answer(index: number) {
    const selected = activeScene.choices[index];
    setChoiceIndex(index);
    setAttemptCount((current) => current + 1);
    if (selected.correct) setSceneStatus(activeScene.id, "complete");
    else setSceneStatus(activeScene.id, "needs-review");
  }

  function recordInteractionEvidence(nextEvidence: InteractionEvidence) {
    const merged = { ...interactionEvidence, [nextEvidence.interactionId]: nextEvidence };
    setInteractionEvidence(merged);
    const required = productionInteractions.filter((interaction) => interaction.requiredForCompletion);
    const complete = required.length > 0 && required.every((interaction) => merged[interaction.id]?.correct);
    setSceneStatus(activeScene.id, complete ? "complete" : "needs-review");
  }

  function goTo(index: number) {
    if (index < 0 || index >= activeModule.scenes.length) return;
    setSceneIndex(index);
    const next = activeModule.scenes[index];
    window.history.replaceState(null, "", `/learn/${activeModule.id}?scene=${encodeURIComponent(next.id)}`);
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
    window.setTimeout(() => document.getElementById("guided-scene-title")?.focus({ preventScroll: true }), 0);
  }

  function skipScene() {
    setSceneStatus(activeScene.id, "skipped");
    if (sceneIndex < activeModule.scenes.length - 1) goTo(sceneIndex + 1);
  }

  const waypoint = `${module.shortTitle} · ${scene.id} ${scene.title}`;
  const lessonReturnPrompt = `Return to ${waypoint}. Resume the checkpoint: ${scene.task}`;
  const returnTo = encodeURIComponent(`/learn/${module.id}?scene=${scene.id}`);

  return (
    <div className="page guided-module" style={{ "--module-accent": module.accent } as React.CSSProperties}>
      <header className="guided-module-header">
        <div className="guided-module-heading">
          <Link className="button subtle small" href="/learn"><ArrowLeft size={15} /> Curriculum</Link>
          <p className="eyebrow">Module {module.order} of {MODULE_TOTAL} · Guided learning</p>
          <h1>{module.title}</h1>
          <p>{module.outcome}</p>
          <div className="guided-module-meta">
            <span><Clock3 size={15} /> {module.duration}</span>
            <span><Target size={15} /> {module.scenes.length} scenes · {totalMinutes} min core path</span>
            <span><Link2 size={15} /> Requires {module.prerequisiteLabel}</span>
          </div>
        </div>
        <div className="guided-progress-card" aria-label={`${completedCount} of ${module.scenes.length} scenes complete`}>
          <div><strong>{progressPercent}%</strong><span>scene completion</span></div>
          <div className="guided-progress-track"><i style={{ width: `${progressPercent}%` }} /></div>
          <p><CheckCircle2 size={14} /> {completedCount} complete <span>·</span> <PauseCircle size={14} /> {skippedCount} skipped</p>
          <small>Completion is not competency mastery; transfer is checked in Train and Rapid.</small>
        </div>
      </header>

      <section className="guided-context-strip" aria-label="Learning connections">
        <div><ChevronLeft size={16} /><span><small>Recall from</small><strong>{scene.recallFrom}</strong></span></div>
        <div className="current"><CircleDashed size={17} /><span><small>Now</small><strong>{scene.objective}</strong></span></div>
        <div><ChevronRight size={16} /><span><small>Reuse next</small><strong>{scene.nextConnection}</strong></span></div>
      </section>

      <div className="guided-workspace">
        <nav className="guided-scene-rail" aria-label="Module scenes">
          <div className="guided-rail-title">
            <span>Scene map</span>
            <small>Skip stays separate from completion.</small>
          </div>
          {parts.map((part) => (
            <div className="guided-part" key={part}>
              <p>{part}</p>
              {module.scenes.map((item, index) => {
                if (item.part !== part) return null;
                const status = progress[module.id]?.[item.id] ?? "not-started";
                return (
                  <button
                    className={`guided-scene-link${index === sceneIndex ? " active" : ""} ${status}`}
                    key={item.id}
                    type="button"
                    onClick={() => goTo(index)}
                    aria-current={index === sceneIndex ? "step" : undefined}
                  >
                    <span>{status === "complete" ? <Check size={13} /> : item.id}</span>
                    <span><strong>{item.title}</strong><small>{statusLabel(status)} · {item.minutes} min</small></span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <main className="guided-stage">
          <section className="guided-scene-card">
            <header className="guided-scene-head">
              <div>
                <p className="eyebrow"><PhaseIcon size={14} /> {phaseLabels[scene.phase]} · Scene {sceneIndex + 1}/{module.scenes.length}</p>
                <h2 id="guided-scene-title" tabIndex={-1}>{scene.title}</h2>
                <p>{scene.objective}</p>
              </div>
              <button className="button subtle small" type="button" onClick={skipScene}><SkipForward size={15} /> Skip & review later</button>
            </header>

            <div className="guided-why-chain" aria-label="First-principles model">
              <div className="guided-chain-heading">
                <span><BrainCircuit size={17} /> Build the why-chain</span>
                <small>Reveal one link at a time, then test it on the trace.</small>
              </div>
              <div className="guided-chain-steps">
                {scene.firstPrinciples.map((principle, index) => {
                  const revealed = index <= revealedPrinciple;
                  return (
                    <button
                      className={revealed ? "revealed" : ""}
                      key={principle}
                      type="button"
                      onClick={() => setRevealedPrinciple(index)}
                      aria-pressed={revealed}
                    >
                      <i>{index + 1}</i>
                      <span>{revealed ? principle : index === 0 ? "Start with the mechanism" : "Reveal the next consequence"}</span>
                    </button>
                  );
                })}
              </div>
              <div className="guided-clinical-bridge"><Sparkles size={16} /><span><strong>Why this changes practice</strong>{scene.clinicalBridge}</span></div>
            </div>
          </section>

          <section className="guided-viewer-wrap" aria-label="Real tracing workspace">
            <div className="guided-viewer-label">
              <div><p className="eyebrow">See it on a real tracing</p><strong>{caseSummary?.displayId ?? "Selecting a grounded case…"}</strong></div>
              {packet ? <span>Tier {packet.teaching_tier} · {packet.waveform.sampling_frequency} Hz · {packet.signal_quality.status}</span> : null}
            </div>
            {loadingCase ? <div className="panel pad guided-loading">Loading the real ECG and its evidence packet…</div> : null}
            {caseError ? <div className="warning">The real-case workspace could not load: {caseError}</div> : null}
            {caseSelectionNotice ? <div className="selection-note guided-case-notice">{caseSelectionNotice}</div> : null}
            {caseSummary && packet ? (
              <ECGViewer
                caseId={caseSummary.caseId}
                actions={viewerActions}
                groundedRois={sceneComplete ? packet.ptbxl_plus.fiducials.rois ?? [] : []}
                onCoordinate={setSelectedPoint}
                medianBeats={packet.ptbxl_plus.median_beats}
                task={viewerTask}
                onTaskEvidence={setViewerTaskEvidence}
              />
            ) : null}
          </section>

          {productionInteractions.length ? (
            <div id="guided-scene-checkpoint" className="guided-production-checkpoint" tabIndex={-1}>
              {productionInteractions.map((interaction) => (
                <LearningInteractionRenderer
                  key={interaction.id}
                  interaction={interaction}
                  packetMeasurements={packet?.ptbxl_plus.measurements}
                  viewerEvidence={viewerInteraction?.id === interaction.id ? viewerTaskEvidence : null}
                  onEvidence={recordInteractionEvidence}
                />
              ))}
            </div>
          ) : (
          <section id="guided-scene-checkpoint" className="guided-checkpoint panel pad" aria-labelledby="scene-checkpoint-title" tabIndex={-1}>
            <div className="guided-checkpoint-head">
              <div><p className="eyebrow">Commit before reveal</p><h2 id="scene-checkpoint-title">{scene.task}</h2></div>
              <span>{attemptCount ? `${attemptCount} attempt${attemptCount === 1 ? "" : "s"}` : "No score yet"}</span>
            </div>
            <div className="guided-choice-grid">
              {scene.choices.map((item, index) => {
                const selected = choiceIndex === index;
                const state = selected ? (item.correct ? "correct" : "incorrect") : "";
                return (
                  <button className={state} key={item.label} type="button" onClick={() => answer(index)}>
                    <span>{String.fromCharCode(65 + index)}</span><strong>{item.label}</strong>
                  </button>
                );
              })}
            </div>
            {selectedChoice ? (
              <div className={`guided-feedback ${selectedChoice.correct ? "correct" : "incorrect"}`} role="status" aria-live="polite">
                {selectedChoice.correct ? <CheckCircle2 size={18} /> : <RotateCcw size={18} />}
                <span><strong>{selectedChoice.correct ? "Evidence aligned" : "Rework the mechanism"}</strong>{selectedChoice.feedback}</span>
              </div>
            ) : null}
            {!selectedChoice?.correct && choiceIndex !== null ? <p className="muted guided-retry-note">Review the why-chain and the tracing, then choose again. An incorrect attempt never completes the scene.</p> : null}
          </section>
          )}

          {sceneComplete ? (
            <section className="guided-handoff panel pad" aria-label="Practice and transfer options">
              <div><p className="eyebrow">Scene complete · competency still needs transfer</p><h2>Now change the context.</h2></div>
              <div className="guided-handoff-grid">
                <Link href={`/train?concept=${encodeURIComponent(scene.focusConcept)}&returnTo=${returnTo}`}><Target size={18} /><span><strong>Practice this</strong><small>Target + close mimic + normal</small></span><ArrowRight size={16} /></Link>
                <Link href={`/rapid?focus=${encodeURIComponent(scene.focusConcept)}&returnTo=${returnTo}`}><Clock3 size={18} /><span><strong>Test it mixed</strong><small>Unannounced, tutor silent</small></span><ArrowRight size={16} /></Link>
                <Link href={`/practice?focus=${encodeURIComponent(scene.focusConcept)}&returnTo=${returnTo}`}><FlaskConical size={18} /><span><strong>Use it in a case</strong><small>Evidence → implication → decision</small></span><ArrowRight size={16} /></Link>
              </div>
            </section>
          ) : null}

          <div className="guided-scene-nav">
            <button className="button" type="button" onClick={() => goTo(sceneIndex - 1)} disabled={sceneIndex === 0}><ChevronLeft size={16} /> Previous</button>
            <span>{statusLabel(sceneStatus)} · {scene.minutes} min scene</span>
            {sceneIndex < module.scenes.length - 1 ? (
              <button className="button primary" type="button" onClick={() => goTo(sceneIndex + 1)} disabled={!sceneComplete}>Next scene <ChevronRight size={16} /></button>
            ) : nextModule ? (
              <Link className="button primary" href={`/learn/${nextModule.id}`}>Next module <ChevronRight size={16} /></Link>
            ) : (
              <Link className="button primary" href="/rapid">Begin mixed transfer <ArrowRight size={16} /></Link>
            )}
          </div>
        </main>

        <aside className="guided-tutor-dock">
          {caseSummary ? (
            <TutorChat
              mode="tutorial"
              caseId={caseSummary.caseId}
              lessonId={scene.lessonId}
              openingPrompt={`We are at ${waypoint}. ${caseSelectionNotice ? "The displayed ECG is a mechanism/contrast tracing, not a positive target; do not claim the requested finding is present. " : ""}${scene.tutorBrief} Ask a tangent at any time; I will connect it back to this checkpoint.`}
              lessonReturnPrompt={lessonReturnPrompt}
              lessonReturnLabel={`Return to ${scene.id} checkpoint`}
              waypointLabel={waypoint}
              onReturnToLesson={() => {
                const checkpoint = document.getElementById("guided-scene-checkpoint");
                checkpoint?.scrollIntoView({ behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
                checkpoint?.focus({ preventScroll: true });
              }}
              viewerState={{
                moduleId: module.id,
                moduleOrder: module.order,
                sceneId: scene.id,
                sceneTitle: scene.title,
                stepId: "checkpoint",
                objectiveId: scene.focusConcept,
                objective: scene.objective,
                learningPhase: scene.phase,
                attemptCount,
                selectedChoice: selectedChoice?.label ?? null,
                selectedChoiceCorrect: selectedChoice?.correct ?? null,
                interactionEvidence,
                selectedPoint,
                pausedWaypoint: lessonReturnPrompt,
                visibleLayout: "standard 3x4 sequential plus continuous lead-II rhythm strip",
              }}
              onViewerActions={setViewerActions}
              resetKey={`${module.id}-${scene.id}-${caseSummary.caseId}`}
            />
          ) : <div className="panel pad">Tutor will attach when the grounded tracing is ready.</div>}

          <section className="panel pad guided-tutor-note">
            <h3><MessageCircleQuestion size={16} /> Tangents keep your place</h3>
            <p>Ask the broader question. The tutor should answer the safe educational core, say how it connects, and return you to <strong>{scene.id}</strong> without clearing your answer or viewer state.</p>
          </section>
        </aside>
      </div>

      <footer className="guided-module-footer">
        {priorModule ? <Link href={`/learn/${priorModule.id}`}><ArrowLeft size={15} /> {priorModule.shortTitle}</Link> : <Link href="/learn/foundations"><ArrowLeft size={15} /> Foundations</Link>}
        <span>Module {module.order}/{MODULE_TOTAL} · {completedCount}/{module.scenes.length} complete · {skippedCount} review later</span>
        {nextModule ? <Link href={`/learn/${nextModule.id}`}>{nextModule.shortTitle} <ArrowRight size={15} /></Link> : <Link href="/rapid">Mixed transfer <ArrowRight size={15} /></Link>}
      </footer>
    </div>
  );
}
