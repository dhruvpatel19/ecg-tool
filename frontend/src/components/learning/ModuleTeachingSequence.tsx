"use client";

import { Check, ChevronLeft, ChevronRight, Pause, Play, RotateCcw, Sparkles, Target } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ProductionModule, ProductionScene } from "@/lib/learning/interactionTypes";
import { buildModuleTeachingLesson } from "@/lib/learning/modulePedagogy";
import styles from "./ModuleTeachingSequence.module.css";

function DiagramGrid({ id }: { id: string }) {
  return (
    <defs>
      <pattern id={`${id}-small`} width="15" height="15" patternUnits="userSpaceOnUse">
        <path d="M15 0H0V15" fill="none" stroke="currentColor" strokeWidth="0.55" />
      </pattern>
      <pattern id={`${id}-large`} width="75" height="75" patternUnits="userSpaceOnUse">
        <rect width="75" height="75" fill={`url(#${id}-small)`} />
        <path d="M75 0H0V75" fill="none" stroke="currentColor" strokeWidth="1" />
      </pattern>
      <marker id={`${id}-arrow`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0 0L10 5L0 10Z" />
      </marker>
    </defs>
  );
}

function SpatialDiagram({ step, id }: { step: number; id: string }) {
  const angles = [-34, 42, 112, -122];
  const angle = angles[step % angles.length]! * Math.PI / 180;
  const x = 235 + Math.cos(angle) * 112;
  const y = 130 + Math.sin(angle) * 88;
  return <>
    <circle cx="235" cy="130" r="86" className={styles.plane} />
    <line x1="78" y1="130" x2="392" y2="130" className={styles.axisLine} />
    <line x1="235" y1="34" x2="235" y2="226" className={styles.axisLine} />
    <g className={step === 0 ? styles.activeNode : styles.mutedNode}><circle cx="84" cy="130" r="25" /><text x="84" y="135">I</text></g>
    <g className={step === 1 ? styles.activeNode : styles.mutedNode}><circle cx="235" cy="216" r="25" /><text x="235" y="221">aVF</text></g>
    <g className={step === 2 ? styles.activeNode : styles.mutedNode}><circle cx="366" cy="82" r="25" /><text x="366" y="87">V1</text></g>
    <g className={step === 3 ? styles.activeNode : styles.mutedNode}><circle cx="366" cy="178" r="25" /><text x="366" y="183">V6</text></g>
    <g className={styles.vector}><circle cx="235" cy="130" r="18" /><path className={styles.motionPath} d={`M235 130 L${x} ${y}`} markerEnd={`url(#${id}-arrow)`} /></g>
    <text x="235" y="24" className={styles.diagramTitle}>one event · directed views</text>
  </>;
}

function RhythmDiagram({ step }: { step: number }) {
  const centers = [72, 168, 278, 394];
  return <>
    <path className={`${styles.trace} ${styles.motionPath}`} d="M24 82H48Q59 82 66 69Q75 54 84 82H105L113 96L124 35L135 108L147 70L160 82H201Q212 82 219 69Q228 54 237 82H258L266 96L277 35L288 108L300 70L313 82H352Q363 82 370 69Q379 54 388 82H409L417 96L428 35L439 108L450 82" />
    <path className={styles.timeline} d="M30 182H440" />
    {centers.map((cx, index) => <g key={cx} className={index === step % centers.length ? styles.activeNode : styles.mutedNode}><circle cx={cx} cy="182" r="21" /><text x={cx} y="187">{index === 0 ? "R–R" : index === 1 ? "P" : index === 2 ? "P→QRS" : "Name"}</text></g>)}
    <path className={styles.focusBracket} d={`M${Math.max(28, centers[step % centers.length]! - 38)} 124V145H${Math.min(442, centers[step % centers.length]! + 38)}V124`} />
    <text x="235" y="224" className={styles.diagramTitle}>timing → atrial evidence → relationship → category</text>
  </>;
}

function AvDiagram({ step }: { step: number }) {
  const rows = [{ y: 62, label: "Atria" }, { y: 130, label: "AV" }, { y: 198, label: "Ventricle" }];
  return <>
    {rows.map((row, index) => <g key={row.label} className={index === Math.min(step, 2) ? styles.activeLane : styles.mutedLane}><text x="42" y={row.y + 5}>{row.label}</text><line x1="105" y1={row.y} x2="438" y2={row.y} /></g>)}
    {[150, 242, 334, 426].map((x, beat) => <g key={x} className={beat === step % 4 ? styles.activePulse : styles.mutedPulse}><circle cx={x} cy="62" r="10" /><path className={styles.motionPath} d={`M${x} 72V${step === 1 && beat === 2 ? 126 : 188}`} /><circle cx={x} cy="198" r="12" /></g>)}
    {step === 1 ? <g className={styles.stopBadge}><rect x="307" y="105" width="55" height="42" rx="12" /><text x="334" y="131">pause</text></g> : null}
    <text x="267" y="235" className={styles.diagramTitle}>follow atrial events before naming the block</text>
  </>;
}

function ActivationDiagram({ step }: { step: number }) {
  return <>
    <path className={styles.heartOutline} d="M188 49C132 17 76 64 92 126C108 184 183 218 235 232C287 218 362 184 378 126C394 64 338 17 282 49C260 62 247 81 235 101C223 81 210 62 188 49Z" />
    <path className={`${styles.activationPath} ${styles.motionPath}`} d="M235 70V117L185 160M235 117L292 160M185 160L144 190M292 160L334 190" />
    <g className={step <= 1 ? styles.activeNode : styles.mutedNode}><circle cx="144" cy="190" r="25" /><text x="144" y="195">V1</text></g>
    <g className={step >= 2 ? styles.activeNode : styles.mutedNode}><circle cx="334" cy="190" r="25" /><text x="334" y="195">V6</text></g>
    <g className={styles.qrsPair}><path d="M34 72H58L67 91L80 28L94 103L109 58L128 72" /><path d="M342 72H360L370 91L384 38L396 105L411 61L442 72" /></g>
    <text x="235" y="22" className={styles.diagramTitle}>duration and pathway are separate evidence</text>
  </>;
}

function TachyDiagram({ step }: { step: number }) {
  const nodes = [
    { x: 235, y: 42, text: "Stability" },
    { x: 235, y: 103, text: "Width" },
    { x: 150, y: 171, text: "Regularity" },
    { x: 320, y: 171, text: "Atrial clues" },
  ];
  return <>
    <path className={`${styles.decisionLine} ${styles.motionPath}`} d="M235 64V81M235 125V142M235 142L150 151M235 142L320 151" />
    {nodes.map((node, index) => <g key={node.text} className={index === step % nodes.length ? styles.activeDecision : styles.mutedDecision}><rect x={node.x - 58} y={node.y - 20} width="116" height="40" rx="14" /><text x={node.x} y={node.y + 5}>{node.text}</text></g>)}
    <g className={styles.tachyTrace}><path className={styles.motionPath} d="M34 224H66L75 235L87 194L99 240L111 210L130 224H163L172 235L184 194L196 240L208 210L227 224H260L269 235L281 194L293 240L305 210L324 224H357L366 235L378 194L390 240L402 210L438 224" /></g>
  </>;
}

function VoltageDiagram({ step }: { step: number }) {
  const heights = [72, 126, 96, 152];
  return <>
    <g className={styles.chamberModel}><circle cx="135" cy="120" r="54" /><circle cx="190" cy="143" r="72" /><text x="135" y="124">RV</text><text x="202" y="150">LV</text></g>
    <g className={styles.voltageBars}>{heights.map((height, index) => <g key={height} className={index === step % 4 ? styles.activeBar : styles.mutedBar}><rect x={278 + index * 42} y={208 - height} width="25" height={height} rx="7" /><text x={290 + index * 42} y="228">{["V1", "V5", "aVL", "+ clue"][index]}</text></g>)}</g>
    <path className={`${styles.motionPath} ${styles.measureArrow}`} d="M264 210V70" />
    <text x="235" y="28" className={styles.diagramTitle}>threshold + supporting pattern + context</text>
  </>;
}

function RecoveryDiagram({ step }: { step: number }) {
  return <>
    <path className={styles.baseline} d="M24 160H448" />
    <path className={`${styles.trace} ${styles.motionPath}`} d="M24 160H86Q98 160 108 148Q120 132 132 160H176L188 178L203 70L218 194L234 132L253 160H302Q316 160 330 138Q349 110 369 160H448" />
    <g className={step === 0 ? styles.activeMarker : styles.mutedMarker}><line x1="50" y1="134" x2="50" y2="183" /><text x="50" y="122">baseline</text></g>
    <g className={step === 1 ? styles.activeMarker : styles.mutedMarker}><line x1="253" y1="122" x2="253" y2="189" /><text x="253" y="110">J</text></g>
    <g className={step === 2 ? styles.activeMarker : styles.mutedMarker}><path d="M188 213V229M188 221H382M382 213V229" /><text x="285" y="242">QT span</text></g>
    <g className={step === 3 ? styles.activeDecision : styles.mutedDecision}><rect x="310" y="32" width="130" height="45" rx="14" /><text x="375" y="51">rate · QRS · context</text><text x="375" y="67">before the claim</text></g>
  </>;
}

function TerritoryDiagram({ step }: { step: number }) {
  const leads = ["I", "aVR", "V1", "V4", "II", "aVL", "V2", "V5", "III", "aVF", "V3", "V6"];
  const groups = [[4, 8, 9], [2, 6, 10], [3, 7, 11], [0, 5]];
  return <>
    {leads.map((lead, index) => {
      const col = index % 4;
      const row = Math.floor(index / 4);
      const active = groups[step % groups.length]!.includes(index);
      return <g key={lead} className={active ? styles.activeLeadTile : styles.mutedLeadTile}><rect x={42 + col * 98} y={38 + row * 62} width="82" height="46" rx="12" /><text x={83 + col * 98} y={66 + row * 62}>{lead}</text></g>;
    })}
    <path className={`${styles.motionPath} ${styles.reciprocalArrow}`} d="M88 229H382" />
    <text x="235" y="248" className={styles.diagramTitle}>finding → contiguous group → opposing evidence → time boundary</text>
  </>;
}

function IntegrationDiagram({ step }: { step: number }) {
  const labels = ["Preflight", "Describe", "Prove", "Prioritize", "Communicate"];
  return <>
    {labels.map((label, index) => <g key={label} className={index === Math.min(step, labels.length - 1) ? styles.activeStack : index < step ? styles.doneStack : styles.mutedStack}><rect x={72 + index * 14} y={32 + index * 39} width={326 - index * 28} height="48" rx="14" /><text x="235" y={61 + index * 39}>{index + 1}. {label}</text></g>)}
    <path className={`${styles.motionPath} ${styles.stackArrow}`} d="M235 25V225" />
  </>;
}

function ConceptDiagram({ visual, step, id }: { visual: ReturnType<typeof buildModuleTeachingLesson>["visual"]; step: number; id: string }) {
  return (
    <svg viewBox="0 0 470 260" aria-hidden="true" className={styles.visualSvg}>
      <DiagramGrid id={id} />
      <rect width="470" height="260" fill={`url(#${id}-large)`} className={styles.grid} />
      {visual === "spatial" ? <SpatialDiagram step={step} id={id} /> : null}
      {visual === "rhythm" ? <RhythmDiagram step={step} /> : null}
      {visual === "av" ? <AvDiagram step={step} /> : null}
      {visual === "activation" ? <ActivationDiagram step={step} /> : null}
      {visual === "tachy" ? <TachyDiagram step={step} /> : null}
      {visual === "voltage" ? <VoltageDiagram step={step} /> : null}
      {visual === "recovery" ? <RecoveryDiagram step={step} /> : null}
      {visual === "territory" ? <TerritoryDiagram step={step} /> : null}
      {visual === "integration" ? <IntegrationDiagram step={step} /> : null}
    </svg>
  );
}

export function ModuleTeachingSequence({
  module,
  scene,
  activeStep,
  visitedSteps,
  onSelectStep,
  onBeginPractice,
  layout = "canvas",
}: {
  module: ProductionModule;
  scene: ProductionScene;
  activeStep: number;
  visitedSteps: number[];
  onSelectStep: (step: number) => void;
  onBeginPractice: () => void;
  layout?: "canvas" | "rail";
}) {
  const lesson = useMemo(() => buildModuleTeachingLesson(module, scene), [module, scene]);
  const safeStep = Math.min(Math.max(activeStep, 0), lesson.beats.length - 1);
  const beat = lesson.beats[safeStep]!;
  const allVisited = lesson.beats.every((_, index) => visitedSteps.includes(index));
  const [playing, setPlaying] = useState(true);
  const [motionKey, setMotionKey] = useState(0);

  useEffect(() => {
    setPlaying(true);
    setMotionKey((current) => current + 1);
  }, [safeStep, scene.id]);

  const diagramId = `teach-${module.id}-${scene.id}`.replace(/[^a-zA-Z0-9_-]/g, "-");

  return (
    <section className={`${styles.studio}${layout === "rail" ? ` ${styles.rail}` : ""}`} data-visual={lesson.visual} aria-labelledby={`${scene.id}-teaching-title`}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Learn the model · {safeStep + 1} of {lesson.beats.length}</p>
          <h2 id={`${scene.id}-teaching-title`}>{lesson.studioTitle}</h2>
          <p>{lesson.intro}</p>
        </div>
        <div className={styles.progress} aria-label={`${visitedSteps.length} of ${lesson.beats.length} ideas explored`}>
          {lesson.beats.map((item, index) => <i key={item.label} className={visitedSteps.includes(index) ? styles.visited : index === safeStep ? styles.current : ""} />)}
        </div>
      </header>

      <div className={styles.ownership} role="note">
        <span><Target size={15} /><strong>The module owns</strong> the model, evidence rules, questions, and scoring.</span>
        <span><Sparkles size={15} /><strong>Luna adds</strong> clarification and hints only when you ask; your first read stays yours.</span>
      </div>

      <div className={styles.stage}>
        <div className={styles.visual} data-playing={playing ? "true" : "false"}>
          <div key={`${safeStep}-${motionKey}`} className={styles.diagram} role="img" aria-label={`${lesson.visualSummary} ${beat.title}. ${beat.explanation}`}><ConceptDiagram visual={lesson.visual} step={safeStep} id={diagramId} /></div>
          <div className={styles.motionControls} aria-label="Teaching animation controls">
            <button type="button" aria-pressed={playing} onClick={() => setPlaying((current) => !current)}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? "Pause motion" : "Play motion"}</button>
            <button type="button" onClick={() => { setPlaying(true); setMotionKey((current) => current + 1); }}><RotateCcw size={14} /> Replay</button>
          </div>
        </div>

        <article className={styles.explanation} aria-live="polite">
          <span>{String(safeStep + 1).padStart(2, "0")} · {beat.label}</span>
          <h3>{beat.title}</h3>
          <p>{beat.explanation}</p>
          <aside><strong>Evidence check</strong>{beat.notice}</aside>
          <details className={styles.predict}><summary>Pause and predict</summary><p>{beat.retrievalPrompt}</p><small>Commit to the evidence you would inspect. The scored question comes next.</small></details>
        </article>
      </div>

      <nav className={styles.tabs} aria-label="Lesson ideas">
        {lesson.beats.map((item, index) => <button key={`${item.label}-${index}`} type="button" aria-current={index === safeStep ? "step" : undefined} onClick={() => onSelectStep(index)}><span>{visitedSteps.includes(index) ? <Check size={13} /> : index + 1}</span><strong>{item.label}</strong></button>)}
      </nav>

      <label className={styles.scrubber}>
        <span>Scrub the model</span>
        <input aria-label="Scrub through the teaching model" type="range" min={0} max={lesson.beats.length - 1} step={1} value={safeStep} onChange={(event) => onSelectStep(Number(event.currentTarget.value))} />
        <output>{safeStep + 1}/{lesson.beats.length}</output>
      </label>

      <footer className={styles.actions}>
        <button className="button subtle" type="button" disabled={safeStep === 0} onClick={() => onSelectStep(safeStep - 1)}><ChevronLeft size={15} /> Previous idea</button>
        <p>{allVisited ? "The authored model is complete. Apply it to the tracing without Luna answering first." : "Explore each idea before the ECG task."}</p>
        {allVisited
          ? <button className="button primary" type="button" onClick={onBeginPractice}>Start the ECG task <Play size={15} /></button>
          : <button className="button primary" type="button" onClick={() => onSelectStep(Math.min(safeStep + 1, lesson.beats.length - 1))}>Next idea <ChevronRight size={15} /></button>}
      </footer>
    </section>
  );
}

export function ModuleTeachingRecap({ module, scene, onReview, layout = "canvas" }: { module: ProductionModule; scene: ProductionScene; onReview: () => void; layout?: "canvas" | "rail" }) {
  const lesson = buildModuleTeachingLesson(module, scene);
  return (
    <div className={`${styles.recap}${layout === "rail" ? ` ${styles.railRecap}` : ""}`} role="note">
      <span><Check size={14} /> Model explored</span>
      <p>{lesson.beats.map((beat) => beat.label).join(" → ")}</p>
      <button className="button subtle small" type="button" onClick={onReview}><RotateCcw size={13} /> Review the model</button>
    </div>
  );
}
