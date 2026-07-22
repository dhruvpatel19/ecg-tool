import type { ModelExploreInteraction, ModelFrame } from "@/lib/learning/interactionTypes";
import styles from "./InteractionModelVisual.module.css";

type InteractionModelVisualProps = {
  model: ModelExploreInteraction["model"];
  frame: ModelFrame;
  frameIndex: number;
  frameCount: number;
  concealed?: boolean;
};

function activeClass(active: boolean) {
  return active ? `${styles.structure} ${styles.active}` : styles.structure;
}

function CardiacCycleVisual({ frame, frameIndex }: { frame: ModelFrame; frameIndex: number }) {
  const active = frame.activeRegion ?? "ventricles";
  return <>
    <g className={styles.heartOutline}>
      <path d="M172 46C125 16 74 48 76 105c2 59 53 103 96 143 43-40 94-84 96-143 2-57-49-89-96-59Z" />
      <path d="M172 68v156M172 111l-53 61M172 111l53 61" />
    </g>
    <g className={styles.conductionPath}>
      <path d="M130 74C132 101 151 105 169 118M169 118v36M169 154l-46 50M169 154l50 50" />
    </g>
    <circle className={activeClass(active === "sa_node")} cx="130" cy="74" r="12" />
    <ellipse className={activeClass(active === "atria")} cx="172" cy="99" rx="48" ry="28" />
    <circle className={activeClass(active === "av_node")} cx="169" cy="119" r="9" />
    <path className={activeClass(active === "his_purkinje")} d="M169 132v24l-43 47m43-47 48 47" />
    <path className={activeClass(active === "ventricles" || active === "recovery")} d="M100 164c20 53 47 70 72 87 25-17 52-34 72-87" />
    <g className={styles.trace}>
      <path d="M302 193h26q8-13 17 0h25l9-10 9 10h12l10 24 13-74 14 59 10-9h27q20-34 42 0h28" />
      <path className={styles.traceFocus} d={frameIndex <= 1 ? "M328 193q8-13 17 0" : frameIndex <= 3 ? "M370 193l9-10 9 10h12l10 24 13-74 14 59 10-9" : "M447 193h27q20-34 42 0"} />
      <text x="324" y="226">P</text><text x="412" y="226">QRS</text><text x="486" y="226">T</text>
    </g>
    <text className={styles.diagramTitle} x="302" y="67">Electrical event</text>
    <text className={styles.diagramCopy} x="302" y="91">anatomy → surface trace</text>
  </>;
}

function VectorProjectionVisual({ frame }: { frame: ModelFrame }) {
  const angle = frame.vectorAngleDeg ?? 0;
  const radians = angle * Math.PI / 180;
  const projection = Math.cos(radians);
  const polarity = Math.abs(projection) < 0.22 ? "Isoelectric" : projection > 0 ? "Positive" : "Negative";
  const waveTop = projection > 0.22 ? 190 : projection < -0.22 ? 246 : 218;
  return <>
    <g className={styles.axis}>
      <circle cx="176" cy="147" r="105" />
      <path d="M47 147h258M176 18v258M85 91l182 112M85 203 267 91" />
      <text x="286" y="138">0°</text><text x="180" y="31">−90°</text><text x="182" y="273">+90°</text>
    </g>
    <g className={styles.leadAxis}><path d="M72 147h208" /><path d="m280 147-16-9v18Z" /><text x="84" y="132">away</text><text x="239" y="132">toward +</text></g>
    <g className={styles.vectorArrow} style={{ transform: `rotate(${angle}deg)`, transformOrigin: "176px 147px" }}><path d="M176 147h86" /><path d="m262 147-18-10v20Z" /></g>
    <path className={styles.projectionGuide} d={`M${176 + Math.cos(radians) * 86} ${147 + Math.sin(radians) * 86}V147`} />
    <g className={styles.trace}>
      <path d={`M339 218h50l13 ${waveTop - 218} 14 ${218 - waveTop}h27l13 ${218 - waveTop} 14 ${waveTop - 218}h52`} />
      <text className={styles.diagramTitle} x="338" y="83">Lead projection</text>
      <text className={styles.resultText} x="338" y="113">{polarity}</text>
      <text x="338" y="252">net vector {angle}°</text>
    </g>
  </>;
}

function AvLadderVisual({ frame, frameIndex }: { frame: ModelFrame; frameIndex: number }) {
  const descriptor = `${frame.label} ${frame.narration}`.toLowerCase();
  const conducted = descriptor.includes("3:1") ? [0, 3] : descriptor.includes("2:1") ? [0, 2, 4] : descriptor.includes("dissoci") ? [1, 4] : descriptor.includes("wencke") || descriptor.includes("mobitz i") ? [0, 1, 2, 4] : frameIndex === 0 ? [0, 1, 2, 3, 4] : [0, 2, 4];
  const xs = [120, 205, 290, 375, 460];
  return <>
    <g className={styles.ladderLanes}>
      <text x="35" y="75">Atria</text><text x="35" y="158">AV node</text><text x="35" y="241">Ventricle</text>
      <path d="M100 69h390M100 151h390M100 234h390" />
    </g>
    {xs.map((x, index) => <g key={x}>
      <circle className={styles.impulse} cx={x} cy="69" r="9" />
      {conducted.includes(index) ? <><path className={styles.conductedPath} d={`M${x} 78v62c0 12 12 12 12 23v60`} /><circle className={styles.ventricularEvent} cx={x + 12} cy="234" r="10" /></> : <><path className={styles.blockedPath} d={`M${x} 78v55`} /><path className={styles.blockMark} d={`M${x - 10} 139h20`} /></>}
    </g>)}
    <text className={styles.diagramTitle} x="104" y="294">Follow every atrial impulse to the ventricular lane.</text>
  </>;
}

function BundleActivationVisual({ frame }: { frame: ModelFrame }) {
  const descriptor = `${frame.label} ${frame.narration}`.toLowerCase();
  const rightLate = descriptor.includes("right") && !descriptor.includes("left");
  const leftLate = descriptor.includes("left") && !descriptor.includes("right");
  return <>
    <g className={styles.bundleHeart}><path d="M280 286C193 233 127 178 143 90c9-49 76-57 137-5 61-52 128-44 137 5 16 88-50 143-137 196Z" /><path d="M280 88v176" /></g>
    <g className={styles.bundleTree}><circle cx="280" cy="57" r="11" /><path d="M280 68v68M280 136l-69 73M280 136l69 73" /><path d="M211 209l-28 42m28-42 21 49M349 209l28 42m-28-42-21 49" /></g>
    <g className={rightLate ? styles.lateTerritory : styles.activeTerritory}><path d="M302 159c23 13 53 37 76 86" /><text x="363" y="171">RV</text></g>
    <g className={leftLate ? styles.lateTerritory : styles.activeTerritory}><path d="M258 159c-23 13-53 37-76 86" /><text x="169" y="171">LV</text></g>
    {(rightLate || leftLate) ? <g className={styles.lateForce}><path d={rightLate ? "M229 229c51 5 85-3 129-41" : "M331 229c-51 5-85-3-129-41"} /><text x="228" y="309">late unopposed force</text></g> : <text className={styles.diagramTitle} x="192" y="309">near-synchronous activation</text>}
  </>;
}

function ReentryVisual({ frameIndex }: { frameIndex: number }) {
  const step = frameIndex % 4;
  return <>
    <g className={styles.reentryCircuit}><path d="M166 57C76 95 74 226 165 265M190 265c91-38 93-169 2-208" /><path d="m166 57-22 1 14 17M190 265l22-1-14-17" /></g>
    <path className={styles.reentryBridge} d="M164 77c-39 54-39 111 2 165M192 77c39 54 39 111-2 165" />
    <circle className={styles.reentryPulse} cx={step === 0 ? 166 : step === 1 ? 105 : step === 2 ? 190 : 249} cy={step === 0 ? 57 : step === 1 ? 158 : step === 2 ? 265 : 158} r="13" />
    <g className={styles.trace}>
      <text className={styles.diagramTitle} x="318" y="73">Loop logic</text>
      <text x="318" y="105">1 · pathway available</text><text x="318" y="135">2 · impulse conducts</text><text x="318" y="165">3 · tissue recovers</text><text x="318" y="195">4 · impulse returns</text>
      <path d="M318 240h30l8 16 12-77 14 62 10-1h24q13-23 27 0h61" />
      <path className={styles.returnArrow} d="M493 240c22 0 31-17 31-37v-32" /><path className={styles.returnArrow} d="m524 171-8 15h16Z" />
    </g>
  </>;
}

function RepolarizationVisual({ frame }: { frame: ModelFrame }) {
  const descriptor = `${frame.label} ${frame.waveformLabel ?? ""} ${frame.narration}`.toLowerCase();
  const qtEmphasis = descriptor.includes("qt") || descriptor.includes("rate") || descriptor.includes("bazett") || descriptor.includes("fridericia");
  const electrolyte = descriptor.includes("potassium") || descriptor.includes("calcium") || descriptor.includes("low k") || descriptor.includes("high k") || descriptor.includes("low ca") || descriptor.includes("high ca");
  return <>
    <g className={styles.repolarizationTrace}>
      <path d="M35 185h72q15-24 30 0h36l10 19 18-108 19 86 13 3h50c29 0 40-38 68-38 31 0 39 38 76 38h91" />
      <path className={styles.segmentQrs} d="M173 185l10 19 18-108 19 86 13 3" />
      <path className={styles.segmentSt} d="M233 185h50" />
      <path className={styles.segmentT} d="M283 185c29 0 40-38 68-38 31 0 39 38 76 38" />
      <text x="194" y="76">QRS</text><text x="246" y="213">ST</text><text x="349" y="132">T</text>
    </g>
    {qtEmphasis ? <g className={styles.qtMeasure}><path d="M177 251v-15m0 8h250m0 7v-15" /><text x="274" y="273">QT spans activation + recovery</text></g> : null}
    {electrolyte ? <g className={styles.stateCard}><text x="38" y="51">Component model</text><text x="38" y="75">change one teaching state</text><rect x="38" y="90" width="82" height="9" rx="4" /><rect x="38" y="107" width="126" height="9" rx="4" /><rect x="38" y="124" width="58" height="9" rx="4" /></g> : <g className={styles.stateCard}><text x="38" y="51">Measure boundaries</text><text x="38" y="75">then interpret in context</text></g>}
  </>;
}

export function InteractionModelVisual({ model, frame, frameIndex, frameCount, concealed = false }: InteractionModelVisualProps) {
  const modelLabel = model.replaceAll("_", " ");
  if (concealed) {
    return <div className={styles.concealed} role="img" aria-label={`${frame.label} mechanism is concealed until a prediction is committed.`}>
      <span>Pause before the reveal</span>
      <strong>What should change in this state?</strong>
      <small>Commit a prediction, then inspect the mechanism and surface consequence.</small>
    </div>;
  }
  return <div className={styles.visual} data-model={model}>
    <header><span>{modelLabel}</span><small>Authored mechanism · state {frameIndex + 1}/{frameCount}</small></header>
    <svg viewBox="0 0 560 330" role="img" aria-label={`${frame.label}. ${frame.narration}`}>
      {model === "cardiac_cycle" ? <CardiacCycleVisual frame={frame} frameIndex={frameIndex} /> : null}
      {model === "vector_projection" ? <VectorProjectionVisual frame={frame} /> : null}
      {model === "av_ladder" ? <AvLadderVisual frame={frame} frameIndex={frameIndex} /> : null}
      {model === "bundle_activation" ? <BundleActivationVisual frame={frame} /> : null}
      {model === "reentry" ? <ReentryVisual frameIndex={frameIndex} /> : null}
      {model === "repolarization" ? <RepolarizationVisual frame={frame} /> : null}
    </svg>
    <footer><strong>{frame.waveformLabel ?? frame.label}</strong><span>Teaching model—not a patient tracing</span></footer>
  </div>;
}
