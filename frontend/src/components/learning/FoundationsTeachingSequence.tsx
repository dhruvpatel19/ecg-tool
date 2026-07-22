"use client";

import { Check, ChevronLeft, ChevronRight, Pause, Play, RotateCcw, Sparkles, Target } from "lucide-react";
import { useEffect, useState } from "react";
import styles from "./FoundationsTeachingSequence.module.css";

type TeachingVisual =
  | "beat"
  | "grid"
  | "quality"
  | "rate"
  | "source"
  | "intervals"
  | "recovery"
  | "views"
  | "axis"
  | "sweep";

type TeachingBeat = {
  label: string;
  title: string;
  explanation: string;
  notice: string;
};

type TeachingLesson = {
  intro: string;
  visual: TeachingVisual;
  beats: TeachingBeat[];
  practiceLabel: string;
};

export const FOUNDATIONS_TEACHING: Record<string, TeachingLesson> = {
  S0: {
    intro: "A consistent sequence protects the signal, the measurements, and the final synthesis.",
    visual: "sweep",
    beats: [
      { label: "Signal", title: "Check the signal", explanation: "Confirm calibration and decide what the tracing can support.", notice: "Do not interpret detail the recording cannot show." },
      { label: "Rate", title: "Measure ventricular rate", explanation: "Check regularity before choosing a rate method.", notice: "Method follows the rhythm evidence." },
      { label: "Source", title: "Find atrial source", explanation: "Look for atrial activity and its relationship to QRS complexes.", notice: "Rate alone does not name the source." },
      { label: "Axis", title: "Estimate QRS direction", explanation: "Use limb-lead polarity to establish the frontal quadrant.", notice: "Judge the full QRS, not one spike." },
      { label: "Timing", title: "Measure intervals", explanation: "Place boundaries before converting boxes to time.", notice: "Values need units and a valid ruler." },
      { label: "ST–T", title: "Describe recovery", explanation: "Use a stable baseline and lead-specific landmarks.", notice: "Describe the finding before assigning a cause." },
      { label: "Synthesis", title: "Build the finding statement", explanation: "Combine only supported observations into a concise read.", notice: "The ECG description informs clinical reasoning; it does not replace it." },
    ],
    practiceLabel: "Try the first check",
  },
  S1: {
    intro: "Follow one electrical cycle across the heart and the tracing. The ECG records electrical activity—not contraction, pressure, or perfusion.",
    visual: "beat",
    beats: [
      {
        label: "Atria",
        title: "Atrial activation writes the P wave",
        explanation: "The impulse spreads through the thinner atrial muscle first. That electrical activation usually creates a small, rounded P wave.",
        notice: "Find the small wave before the QRS; do not use its size to judge atrial contraction strength.",
      },
      {
        label: "Ventricles",
        title: "A brief hand-off precedes the QRS",
        explanation: "The AV node briefly delays the impulse, then the His–Purkinje system activates the larger ventricles rapidly. The result is a short flat hand-off followed by the taller QRS complex.",
        notice: "The QRS represents ventricular activation. It does not directly show the pulse or blood pressure.",
      },
      {
        label: "Recovery",
        title: "Ventricular recovery writes the T wave",
        explanation: "After activation, the ventricular cells reset electrically. In lead II, a normal T wave is often upright like the dominant QRS, but direction depends on the lead.",
        notice: "Read P → QRS → T as activation, activation, then recovery—not as three mechanical contractions.",
      },
    ],
    practiceLabel: "Label a new beat",
  },
  S2: {
    intro: "ECG paper is a calibrated ruler. Establish paper speed and gain before turning boxes into time, voltage, rate, or intervals.",
    visual: "grid",
    beats: [
      {
        label: "Time",
        title: "Horizontal distance measures time",
        explanation: "At the usual 25 mm/s, one small horizontal box is 40 ms and one large box is 200 ms. Five large boxes span one second.",
        notice: "Count from the true beginning to the true end of the event before doing the arithmetic.",
      },
      {
        label: "Voltage",
        title: "Vertical distance measures voltage",
        explanation: "At the usual gain of 10 mm/mV, one small vertical box is 0.1 mV and one large box is 0.5 mV. Ten millimeters represent 1 mV.",
        notice: "Time runs left to right; voltage runs up and down. Keep the two rulers separate.",
      },
      {
        label: "Calibration",
        title: "A changed setting changes the math",
        explanation: "The calibration mark confirms the displayed gain and paper speed. At 50 mm/s, the paper moves twice as fast, so every horizontal box represents half as much time.",
        notice: "Glance at speed and gain first. If the ruler changes, every downstream measurement changes with it.",
      },
    ],
    practiceLabel: "Use the ruler",
  },
  S3: {
    intro: "Signal quality is not one global yes-or-no judgment. First name the finding you need, then ask whether that part of the tracing is readable.",
    visual: "quality",
    beats: [
      {
        label: "Question",
        title: "Readability depends on the question",
        explanation: "Large QRS complexes may remain easy to count while low-amplitude P waves or subtle ST–T detail disappear in noise.",
        notice: "Ask ‘readable for rate, atrial activity, or ST–T?’ instead of simply calling the ECG good or bad.",
      },
      {
        label: "Limit",
        title: "Locate what limits the answer",
        explanation: "Motion, baseline wander, and electrical interference affect different regions and measurements. Mark the affected interval before deciding what it prevents.",
        notice: "A localized artifact should not erase reliable evidence elsewhere on the tracing.",
      },
      {
        label: "Report",
        title: "Keep valid findings and name the gap",
        explanation: "A useful interpretation can say that ventricular rate is assessable while atrial source or fine ST–T detail is not assessable.",
        notice: "‘Not assessable’ is a defensible conclusion—not a guess and not a negative finding.",
      },
    ],
    practiceLabel: "Judge a new tracing",
  },
  S4: {
    intro: "Rate starts with valid ventricular events and regularity. Those two observations determine which calculation the strip can support.",
    visual: "rate",
    beats: [
      {
        label: "Anchor",
        title: "Mark QRS complexes, then check spacing",
        explanation: "Use the same point on consecutive QRS complexes. Even R–R spacing suggests a regular rhythm; changing spacing means one interval cannot represent the whole strip.",
        notice: "Do not count tall T waves or duplicated median beats as additional ventricular events.",
      },
      {
        label: "Regular",
        title: "For regular rhythms, spacing becomes rate",
        explanation: "At 25 mm/s, divide 300 by the number of large boxes between R waves. Four large boxes gives about 75 beats/min.",
        notice: "The 300 rule is a fast estimate for regular rhythms, not a universal formula.",
      },
      {
        label: "Irregular",
        title: "For irregular rhythms, average a true window",
        explanation: "Count QRS complexes in a continuous six-second strip and multiply by 10. This estimates the average ventricular rate across variable cycles.",
        notice: "Never repeat or tile a short strip to manufacture six seconds of rhythm evidence.",
      },
    ],
    practiceLabel: "Estimate the rate",
  },
  S5: {
    intro: "Atrial source and atrial-to-ventricular conduction are related, but they are not the same conclusion. Read and report both.",
    visual: "source",
    beats: [
      {
        label: "Source",
        title: "Start by finding repeatable P waves",
        explanation: "A sinus pattern has P waves with a consistent shape and timing. In lead II they are usually upright because atrial activation travels generally toward that lead.",
        notice: "A fast, slow, or regular ventricular rate does not by itself prove a sinus source.",
      },
      {
        label: "Relationship",
        title: "Test every P–QRS relationship separately",
        explanation: "Look for a P before every QRS, a QRS after every P, and a stable PR interval. This describes how atrial activity relates to ventricular activation.",
        notice: "One-to-one conduction alone does not establish where the atrial impulse began.",
      },
      {
        label: "Direction",
        title: "Use aligned leads when they are available",
        explanation: "A sinus P wave is typically upright in II and inverted in aVR because the same atrial vector points toward II and away from aVR.",
        notice: "If P waves cannot be seen reliably, report atrial source as not assessable rather than inventing one.",
      },
    ],
    practiceLabel: "Assess source and conduction",
  },
  S6: {
    intro: "Intervals are only reproducible when their boundaries are explicit. Place the endpoints first, then count boxes and report units.",
    visual: "intervals",
    beats: [
      {
        label: "Boundaries",
        title: "Measure onset to onset—or onset to offset",
        explanation: "PR begins at the start of the P wave and ends at QRS onset. QRS duration begins at the first departure from baseline and ends at the final return.",
        notice: "The P peak, R peak, and an early return inside the terminal QRS are common—but incorrect—boundaries.",
      },
      {
        label: "PR",
        title: "PR normally spans 120–200 ms",
        explanation: "At 25 mm/s, that is about three to five small boxes. It represents atrial-to-ventricular conduction time, including the AV nodal delay.",
        notice: "Report the measured PR and whether it is short, normal, or long before considering a named diagnosis.",
      },
      {
        label: "QRS",
        title: "QRS is normally under 120 ms",
        explanation: "Rapid ventricular activation through the His–Purkinje system usually completes in fewer than three small boxes.",
        notice: "‘Wide QRS’ is an observation. Its cause requires morphology, sequence, and clinical context taught later.",
      },
    ],
    practiceLabel: "Measure a new beat",
  },
  S7: {
    intro: "Recovery findings need a stable baseline, a clear QRS ending, and a visible T-wave ending. Learn the landmarks before judging them.",
    visual: "recovery",
    beats: [
      {
        label: "Baseline + J",
        title: "The J point is where QRS ends and ST begins",
        explanation: "Compare the ST segment with a stable baseline in the same lead—usually the TP segment when it is visible.",
        notice: "A small offset can be normal. Foundations describes direction and location before assigning a cause.",
      },
      {
        label: "ST + T",
        title: "ST and T describe ventricular recovery",
        explanation: "The ST segment is normally near baseline. T-wave direction is interpreted in lead context; it is often upright with a dominant upright QRS in II, with normal exceptions such as aVR and V1.",
        notice: "Avoid the shortcut that every normal T wave must point in the same direction as every QRS.",
      },
      {
        label: "QT",
        title: "QT spans QRS onset to T-wave end",
        explanation: "QT contains both ventricular activation and recovery, and it changes with heart rate. Corrected QT is introduced later.",
        notice: "If the T-wave end is not readable, QT is not assessable—do not force an endpoint.",
      },
    ],
    practiceLabel: "Mark recovery landmarks",
  },
  S8: {
    intro: "A 12-lead ECG is twelve directed views of the same evolving electrical process. Lead labels and display format tell you what each panel can support.",
    visual: "views",
    beats: [
      {
        label: "Navigate",
        title: "Limb and chest leads view different planes",
        explanation: "I, II, III, aVR, aVL, and aVF view the frontal plane. V1 through V6 move across the horizontal chest plane.",
        notice: "Learn the printed labels before using a panel; screen position alone is not a lead identity.",
      },
      {
        label: "Representation",
        title: "Shape panels and rhythm strips answer different questions",
        explanation: "Median or representative beats are excellent for comparing shape, but they are constructed summaries and cannot establish beat-to-beat timing.",
        notice: "Use a continuous rhythm strip for regularity and event relationships across time.",
      },
      {
        label: "Progression",
        title: "Across V1–V6, R usually grows as S shrinks",
        explanation: "The point where R first becomes taller than S is the transition, commonly around V3–V4.",
        notice: "Compare individual chest-lead QRS complexes before naming the transition point.",
      },
    ],
    practiceLabel: "Navigate the 12 leads",
  },
  S9: {
    intro: "Frontal QRS axis is the average direction of ventricular activation. Lead polarity is a projection of that direction, not a separate event.",
    visual: "axis",
    beats: [
      {
        label: "Projection",
        title: "Toward a lead is positive; away is negative",
        explanation: "Judge the net area of the full QRS. A vector pointing toward a lead’s positive pole produces a mainly positive QRS; pointing away produces a mainly negative one.",
        notice: "Do not use only the tallest spike or the T wave to decide QRS polarity.",
      },
      {
        label: "Quadrant",
        title: "Lead I and aVF establish the coarse quadrant",
        explanation: "I positive and aVF positive places the mean vector in the down-left quadrant and is definitely normal by the simple rule.",
        notice: "Write the two signs first. It prevents reversing the quadrant when the ECG is unfamiliar.",
      },
      {
        label: "Refine",
        title: "Lead II resolves the leftward border",
        explanation: "When I is positive and aVF is negative, lead II helps separate a still-normal leftward axis from left-axis deviation near the −30° boundary.",
        notice: "Foundations names direction. Causes such as fascicular disease belong to later modules.",
      },
    ],
    practiceLabel: "Explore the vector",
  },
  S10: {
    intro: "A complete read is a chain of evidence, not a list of labels. Watch how each checkpoint constrains the next one before you attempt the full sequence.",
    visual: "sweep",
    beats: [
      {
        label: "Sequence",
        title: "Use the same route every time",
        explanation: "Confirm signal and calibration, then read rate, source/rhythm, axis, intervals, QRS morphology, ST–T, and finally synthesis.",
        notice: "The fixed order reduces omissions; it does not replace attention to the patient’s clinical question.",
      },
      {
        label: "Evidence",
        title: "Attach every conclusion to a finding",
        explanation: "‘Sinus’ needs P-wave direction and P–QRS relationships. ‘Normal axis’ needs limb-lead polarity. Interval claims need boundaries, values, and units.",
        notice: "If the supporting signal is unavailable, preserve that uncertainty in the read.",
      },
      {
        label: "Synthesis",
        title: "Describe first; diagnose later",
        explanation: "Combine only the supported observations into one concise finding statement. Clinical interpretation then adds the indication, prior ECGs, examination, and other tests.",
        notice: "A precise description is safer than an impressive diagnosis the tracing cannot support.",
      },
    ],
    practiceLabel: "Work through the model",
  },
};

const FOUNDATIONS_RETRIEVAL_PROMPTS: Record<string, string[]> = {
  S1: [
    "Before naming the wave, which electrical event should occur first in the cycle?",
    "What evidence separates the AV hand-off from the start of ventricular activation?",
    "If the T wave changes direction in one lead, what should you inspect before calling recovery abnormal?",
  ],
  S2: [
    "At 25 mm/s, how many milliseconds should five small horizontal boxes represent?",
    "Which direction on the page measures voltage rather than time?",
    "If paper speed doubles, what happens to the time represented by one box?",
  ],
  S3: [
    "Could this signal support QRS timing even if it cannot support a P-wave claim?",
    "Which exact interval would you mark as the source of the limitation?",
    "How would you preserve the usable finding while naming the unavailable one?",
  ],
  S4: [
    "Which repeated landmark must be valid before you judge regularity?",
    "When does the 300 rule describe the tracing well enough to use it?",
    "Why would repeating a short strip create false rhythm evidence?",
  ],
  S5: [
    "What P-wave feature supports an atrial-source claim rather than only a rate claim?",
    "Can one-to-one P–QRS conduction prove that the impulse began in the sinus node?",
    "What conclusion remains safe when P waves are not reliably visible?",
  ],
  S6: [
    "Where does PR begin and where does it end?",
    "What must accompany a PR value so another reader can reproduce it?",
    "Why is ‘wide QRS’ a finding rather than a complete mechanism diagnosis?",
  ],
  S7: [
    "Which baseline would you name before describing the ST segment?",
    "What lead-specific exception prevents a universal T-wave shortcut?",
    "What should you report when the T-wave end cannot be placed reproducibly?",
  ],
  S8: [
    "Which printed lead labels anchor the frontal and horizontal planes?",
    "Can a representative median beat establish beat-to-beat regularity?",
    "Which adjacent chest leads would you compare to locate the first R/S crossover?",
  ],
  S9: [
    "Does a net QRS point toward or away from a lead when that lead is mainly positive?",
    "Write the signs in lead I and aVF before naming the quadrant.",
    "When I is positive and aVF negative, which lead refines the −30° boundary?",
  ],
  S10: [
    "Which checkpoint must remain first even when the likely diagnosis seems obvious?",
    "What exact lead, waveform, value, or interval would support your conclusion?",
    "Which words keep a concise synthesis from claiming more than the ECG shows?",
  ],
};

export function foundationsSceneHasTeaching(sceneId: string) {
  return sceneId in FOUNDATIONS_TEACHING;
}

function EcgGrid({ id }: { id: string }) {
  return (
    <defs>
      <pattern id={`${id}-minor`} width="16" height="16" patternUnits="userSpaceOnUse">
        <path d="M16 0H0V16" fill="none" stroke="currentColor" strokeWidth="0.6" />
      </pattern>
      <pattern id={`${id}-major`} width="80" height="80" patternUnits="userSpaceOnUse">
        <rect width="80" height="80" fill={`url(#${id}-minor)`} />
        <path d="M80 0H0V80" fill="none" stroke="currentColor" strokeWidth="1" />
      </pattern>
    </defs>
  );
}

const beatPath = "M18 150 H88 Q100 150 110 139 Q121 129 134 150 H187 L199 174 L215 62 L231 198 L248 126 L270 150 H332 Q348 150 360 132 Q378 109 398 150 H452";

function BeatVisual({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <EcgGrid id="teach-beat" />
      <rect width="470" height="240" fill="url(#teach-beat-major)" className={styles.svgGrid} />
      <rect x={step === 0 ? 86 : step === 1 ? 183 : 329} y="42" width={step === 0 ? 62 : step === 1 ? 92 : 82} height="160" rx="18" className={styles.focusWindow} />
      <path d={beatPath} className={styles.svgTraceGhost} />
      <path d={beatPath} className={styles.svgTrace} />
      <g className={step === 0 ? styles.activeGroup : styles.quietGroup}><circle cx="118" cy="66" r="20" /><text x="118" y="71">P</text></g>
      <g className={step === 1 ? styles.activeGroup : styles.quietGroup}><circle cx="215" cy="36" r="20" /><text x="215" y="41">QRS</text></g>
      <g className={step === 2 ? styles.activeGroup : styles.quietGroup}><circle cx="370" cy="86" r="20" /><text x="370" y="91">T</text></g>
    </svg>
  );
}

function GridVisual({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <EcgGrid id="teach-grid" />
      <rect width="470" height="240" fill="url(#teach-grid-major)" className={styles.svgGridStrong} />
      <path d="M32 177 H94 V99 H126 V177 H188" className={styles.calibrationPulse} />
      <g className={step === 0 ? styles.activeGroup : styles.quietGroup}>
        <path d="M222 172 V188 M222 180 H302 M302 172 V188" className={styles.measureLine} />
        <text x="262" y="207">200 ms</text>
      </g>
      <g className={step === 1 ? styles.activeGroup : styles.quietGroup}>
        <path d="M350 182 H334 M342 182 V102 M350 102 H334" className={styles.measureLine} />
        <text x="369" y="146">1 mV</text>
      </g>
      <g className={step === 2 ? styles.activeGroup : styles.quietGroup}>
        <rect x="210" y="30" width="226" height="48" rx="15" />
        <text x="323" y="50">25 mm/s · 10 mm/mV</text>
        <text x="323" y="68">verify before measuring</text>
      </g>
    </svg>
  );
}

function QualityVisual({ step }: { step: number }) {
  const noisyPath = "M18 132 L42 131 54 125 62 140 70 115 82 152 92 126 108 132 138 132 150 127 161 132 184 132 194 148 205 70 218 166 231 112 247 132 275 132 286 127 296 132 318 132 327 147 339 70 351 166 365 112 382 132 452 132";
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <EcgGrid id="teach-quality" />
      <rect width="470" height="240" fill="url(#teach-quality-major)" className={styles.svgGrid} />
      <path d={noisyPath} className={styles.svgTrace} />
      {step === 0 ? <g className={styles.signalMarks}><line x1="205" y1="50" x2="205" y2="182" /><line x1="339" y1="50" x2="339" y2="182" /><text x="272" y="216">QRS timing remains visible</text></g> : null}
      {step === 1 ? <g className={styles.artifactBox}><rect x="46" y="92" width="82" height="82" rx="13" /><text x="87" y="82">artifact</text></g> : null}
      {step === 2 ? <g className={styles.assessmentStack}><rect x="36" y="28" width="122" height="38" rx="12" /><text x="97" y="52">Rate ✓</text><rect x="174" y="28" width="122" height="38" rx="12" /><text x="235" y="52">P waves ?</text><rect x="312" y="28" width="122" height="38" rx="12" /><text x="373" y="52">ST–T ?</text></g> : null}
    </svg>
  );
}

function RateVisual({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <EcgGrid id="teach-rate" />
      <rect width="470" height="240" fill="url(#teach-rate-major)" className={styles.svgGrid} />
      <g className={step < 2 ? styles.activeTraceGroup : styles.quietTraceGroup}>
        <path d="M20 82 H70 L82 96 92 34 103 112 116 70 132 82 H210 L222 96 232 34 243 112 256 70 272 82 H350 L362 96 372 34 383 112 396 70 450 82" />
      </g>
      <g className={step === 2 ? styles.activeTraceGroup : styles.quietTraceGroup}>
        <path d="M20 183 H52 L64 197 74 135 85 213 98 171 142 183 H216 L228 197 238 135 249 213 262 171 278 183 H310 L322 197 332 135 343 213 356 171 450 183" />
      </g>
      {step === 0 ? <g className={styles.signalMarks}><line x1="92" y1="22" x2="92" y2="121" /><line x1="232" y1="22" x2="232" y2="121" /><line x1="372" y1="22" x2="372" y2="121" /><text x="232" y="142">equal R–R spacing</text></g> : null}
      {step === 1 ? <g className={styles.rateEquation}><rect x="143" y="142" width="184" height="66" rx="16" /><text x="235" y="168">300 ÷ 4 boxes</text><text x="235" y="192">≈ 75 beats/min</text></g> : null}
      {step === 2 ? <g className={styles.rateEquation}><rect x="132" y="24" width="206" height="58" rx="16" /><text x="235" y="49">6-second QRS count × 10</text><text x="235" y="70">average irregular rate</text></g> : null}
    </svg>
  );
}

function SourceVisual({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <EcgGrid id="teach-source" />
      <rect width="470" height="240" fill="url(#teach-source-major)" className={styles.svgGrid} />
      <text x="28" y="34" className={styles.svgLeadLabel}>II</text>
      <path d="M24 92 H51 Q63 92 72 77 Q82 61 94 92 H127 L138 105 150 45 162 119 175 79 193 92 H223 Q235 92 244 77 Q254 61 266 92 H299 L310 105 322 45 334 119 347 79 365 92 H446" className={styles.svgTrace} />
      <text x="28" y="142" className={styles.svgLeadLabel}>aVR</text>
      <path d="M24 183 H51 Q63 183 72 198 Q82 214 94 183 H127 L138 170 150 222 162 157 175 196 193 183 H223 Q235 183 244 198 Q254 214 266 183 H299 L310 170 322 222 334 157 347 196 365 183 H446" className={styles.svgTraceMuted} />
      {step === 0 ? <g className={styles.sourceFocus}><circle cx="82" cy="78" r="28" /><circle cx="254" cy="78" r="28" /><text x="168" y="30">same upright P shape</text></g> : null}
      {step === 1 ? <g className={styles.relationshipLines}><line x1="82" y1="66" x2="150" y2="42" /><line x1="254" y1="66" x2="322" y2="42" /><text x="236" y="129">P → next QRS, every time</text></g> : null}
      {step === 2 ? <g className={styles.directionBadge}><path d="M207 118 L262 66" /><path d="M250 69 L263 65 260 78" /><text x="236" y="129">toward II · away from aVR</text></g> : null}
    </svg>
  );
}

function IntervalsVisual({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <EcgGrid id="teach-intervals" />
      <rect width="470" height="240" fill="url(#teach-intervals-major)" className={styles.svgGridStrong} />
      <path d={beatPath} className={styles.svgTrace} />
      <g className={step <= 1 ? styles.activeGroup : styles.quietGroup}>
        <path d="M92 184 V201 M92 193 H199 M199 184 V201" className={styles.measureLine} />
        <text x="145" y="221">PR: onset → onset</text>
      </g>
      <g className={step === 0 || step === 2 ? styles.activeGroup : styles.quietGroup}>
        <path d="M199 32 V16 M199 24 H248 M248 32 V16" className={styles.measureLine} />
        <text x="224" y="12">QRS</text>
      </g>
      {step === 1 ? <g className={styles.thresholdBadge}><rect x="288" y="28" width="146" height="48" rx="14" /><text x="361" y="49">PR 120–200 ms</text><text x="361" y="66">3–5 small boxes</text></g> : null}
      {step === 2 ? <g className={styles.thresholdBadge}><rect x="288" y="28" width="146" height="48" rx="14" /><text x="361" y="49">QRS &lt; 120 ms</text><text x="361" y="66">fewer than 3 boxes</text></g> : null}
    </svg>
  );
}

function RecoveryVisual({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <EcgGrid id="teach-recovery" />
      <rect width="470" height="240" fill="url(#teach-recovery-major)" className={styles.svgGrid} />
      <path d={beatPath} className={styles.svgTrace} />
      <line x1="24" y1="150" x2="446" y2="150" className={step < 2 ? styles.baselineActive : styles.baselineMuted} />
      {step === 0 ? <g className={styles.landmarkGroup}><line x1="248" y1="36" x2="248" y2="184" /><circle cx="248" cy="150" r="6" /><text x="266" y="48">J point</text><path d="M248 175 H329" /><text x="289" y="196">ST</text></g> : null}
      {step === 1 ? <g className={styles.landmarkGroup}><path d="M248 174 H329" /><path d="M337 119 Q369 84 405 150" fill="none" /><text x="290" y="194">ST</text><text x="375" y="82">T</text></g> : null}
      {step === 2 ? <g className={styles.activeGroup}><path d="M199 196 V212 M199 204 H405 M405 196 V212" className={styles.measureLine} /><text x="302" y="228">QT: QRS onset → T end</text></g> : null}
    </svg>
  );
}

function ViewsVisual({ step }: { step: number }) {
  const leads = ["I", "aVR", "V1", "V4", "II", "aVL", "V2", "V5", "III", "aVF", "V3", "V6"];
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      {leads.map((lead, index) => {
        const col = index % 4;
        const row = Math.floor(index / 4);
        const x = 14 + col * 113;
        const y = 16 + row * 70;
        const chestIndex = lead.startsWith("V") ? Number(lead.slice(1)) : 0;
        const active = step === 0
          ? true
          : step === 1
            ? lead === "II"
            : chestIndex > 0;
        const rHeight = chestIndex ? 8 + chestIndex * 4 : 22;
        const sDepth = chestIndex ? 33 - chestIndex * 4 : 18;
        return (
          <g key={lead} className={active ? styles.leadTileActive : styles.leadTileMuted}>
            <rect x={x} y={y} width="103" height="56" rx="11" />
            <text x={x + 10} y={y + 17}>{lead}</text>
            <path d={`M${x + 9} ${y + 37} H${x + 40} L${x + 47} ${y + 37 - rHeight} L${x + 53} ${y + 37 + sDepth} L${x + 60} ${y + 37} H${x + 94}`} />
          </g>
        );
      })}
      {step === 1 ? <g className={styles.representationBadge}><rect x="112" y="211" width="246" height="25" rx="10" /><text x="235" y="228">continuous strip = timing across beats</text></g> : null}
      {step === 2 ? <g className={styles.progressionArrow}><path d="M238 211 H432" /><path d="M421 204 L433 211 421 218" /><text x="138" y="216">R grows · S shrinks</text></g> : null}
    </svg>
  );
}

function AxisVisual({ step }: { step: number }) {
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <g transform="translate(148 120)">
        <circle r="91" className={styles.axisCircle} />
        <path d="M0 0 L78 45 A90 90 0 0 1 0 90 Z" className={styles.axisNormalSector} />
        <line x1="-104" y1="0" x2="104" y2="0" className={styles.axisLine} />
        <line x1="0" y1="-104" x2="0" y2="104" className={styles.axisLine} />
        <text x="108" y="5">I+</text><text x="6" y="112">aVF+</text>
        <g className={styles.axisVector}><line x1="0" y1="0" x2="64" y2="58" /><path d="M50 55 L65 59 61 44" /></g>
      </g>
      <g className={styles.axisReadout}>
        <rect x="278" y="46" width="158" height="148" rx="18" />
        {step === 0 ? <><text x="357" y="81">Projection</text><text x="357" y="111">toward = positive</text><text x="357" y="136">away = negative</text><text x="357" y="171">use the full QRS</text></> : null}
        {step === 1 ? <><text x="357" y="81">Coarse quadrant</text><text x="357" y="118" className={styles.readoutStrong}>I +</text><text x="357" y="148" className={styles.readoutStrong}>aVF +</text><text x="357" y="176">definitely normal</text></> : null}
        {step === 2 ? <><text x="357" y="81">Borderline leftward</text><text x="357" y="118" className={styles.readoutStrong}>I + · aVF −</text><text x="357" y="149">check lead II</text><text x="357" y="176">boundary ≈ −30°</text></> : null}
      </g>
    </svg>
  );
}

function SweepVisual({ step }: { step: number }) {
  const stages = ["Signal", "Rate", "Source", "Axis", "Timing", "ST–T", "Synthesis"];
  return (
    <svg viewBox="0 0 470 240" aria-hidden="true" className={styles.visualSvg}>
      <path d="M46 79 H424" className={styles.sweepLine} />
      {stages.map((stage, index) => {
        const x = 46 + index * 63;
        const emphasized = step === 0 || (step === 1 && [2, 3, 4].includes(index)) || (step === 2 && index === 6);
        return <g key={stage} className={emphasized ? styles.sweepStageActive : styles.sweepStageMuted}><circle cx={x} cy="79" r="17" /><text x={x} y="84">{index + 1}</text><text x={x} y="113">{stage}</text></g>;
      })}
      {step === 0 ? <g className={styles.sweepMessage}><text x="235" y="166">same route · every ECG</text><text x="235" y="191">order protects against omissions</text></g> : null}
      {step === 1 ? <g className={styles.sweepMessage}><text x="235" y="166">finding → evidence</text><text x="235" y="191">lead · waveform · value · units</text></g> : null}
      {step === 2 ? <g className={styles.sweepMessage}><text x="235" y="166">supported observations</text><text x="235" y="191">→ one concise finding statement</text></g> : null}
    </svg>
  );
}

function TeachingVisual({ visual, step, label, playing, motionKey, onToggleMotion, onReplay }: { visual: TeachingVisual; step: number; label: string; playing: boolean; motionKey: number; onToggleMotion: () => void; onReplay: () => void }) {
  return (
    <div className={styles.visual} data-playing={playing ? "true" : "false"}>
      <div key={`${step}-${motionKey}`} className={styles.visualCanvas} role="img" aria-label={label}>
        {visual === "beat" ? <BeatVisual step={step} /> : null}
        {visual === "grid" ? <GridVisual step={step} /> : null}
        {visual === "quality" ? <QualityVisual step={step} /> : null}
        {visual === "rate" ? <RateVisual step={step} /> : null}
        {visual === "source" ? <SourceVisual step={step} /> : null}
        {visual === "intervals" ? <IntervalsVisual step={step} /> : null}
        {visual === "recovery" ? <RecoveryVisual step={step} /> : null}
        {visual === "views" ? <ViewsVisual step={step} /> : null}
        {visual === "axis" ? <AxisVisual step={step} /> : null}
        {visual === "sweep" ? <SweepVisual step={step} /> : null}
      </div>
      <div className={styles.motionControls} aria-label="Teaching animation controls">
        <button type="button" aria-pressed={playing} onClick={onToggleMotion}>{playing ? <Pause size={14} /> : <Play size={14} />}{playing ? "Pause motion" : "Play motion"}</button>
        <button type="button" onClick={onReplay}><RotateCcw size={14} /> Replay</button>
      </div>
    </div>
  );
}

export function FoundationsTeachingSequence({
  sceneId,
  activeStep,
  visitedSteps,
  onSelectStep,
  onBeginPractice,
}: {
  sceneId: string;
  activeStep: number;
  visitedSteps: number[];
  onSelectStep: (step: number) => void;
  onBeginPractice: () => void;
}) {
  const lesson = FOUNDATIONS_TEACHING[sceneId];
  const [playing, setPlaying] = useState(true);
  const [motionKey, setMotionKey] = useState(0);
  const safeStep = lesson ? Math.min(Math.max(activeStep, 0), lesson.beats.length - 1) : 0;

  useEffect(() => {
    setPlaying(true);
    setMotionKey((current) => current + 1);
  }, [safeStep, sceneId]);

  if (!lesson) return null;
  const beat = lesson.beats[safeStep];
  const allVisited = lesson.beats.every((_, index) => visitedSteps.includes(index));

  return (
    <section className={styles.studio} aria-labelledby={`${sceneId}-teaching-title`}>
      <header className={styles.studioHeader}>
        <div>
          <p className={styles.phaseLabel}>Learn · {safeStep + 1} of {lesson.beats.length}</p>
          <h2 id={`${sceneId}-teaching-title`}>Build the idea before you use it</h2>
          <p>{lesson.intro}</p>
        </div>
        <div className={styles.progress} aria-label={`${visitedSteps.length} of ${lesson.beats.length} ideas explored`}>
          {lesson.beats.map((item, index) => <i key={item.label} className={visitedSteps.includes(index) ? styles.visited : index === safeStep ? styles.current : ""} />)}
        </div>
      </header>

      <div className={styles.ownership} role="note">
        <span><Target size={15} /><strong>The module owns</strong> the visual model, evidence rules, questions, and score.</span>
        <span><Sparkles size={15} /><strong>Luna adds</strong> clarification and hints only when you ask; your first read stays yours.</span>
      </div>

      <div className={styles.stage}>
        <TeachingVisual visual={lesson.visual} step={safeStep} label={`${beat.title}. ${beat.explanation}`} playing={playing} motionKey={motionKey} onToggleMotion={() => setPlaying((current) => !current)} onReplay={() => { setPlaying(true); setMotionKey((current) => current + 1); }} />
        <article className={styles.explanation} aria-live="polite">
          <span>{String(safeStep + 1).padStart(2, "0")} · {beat.label}</span>
          <h3>{beat.title}</h3>
          <p>{beat.explanation}</p>
          <aside><strong>What to notice</strong>{beat.notice}</aside>
          <details className={styles.predict}><summary>Pause and predict</summary><p>{FOUNDATIONS_RETRIEVAL_PROMPTS[sceneId]?.[safeStep] ?? "What evidence would you inspect before committing to this conclusion?"}</p><small>Commit to the evidence first. The scored ECG task comes next.</small></details>
        </article>
      </div>

      <nav className={styles.beatTabs} aria-label="Lesson ideas">
        {lesson.beats.map((item, index) => (
          <button key={item.label} type="button" aria-current={index === safeStep ? "step" : undefined} onClick={() => onSelectStep(index)}>
            <span>{visitedSteps.includes(index) ? <Check size={13} /> : index + 1}</span>
            <strong>{item.label}</strong>
          </button>
        ))}
      </nav>

      <footer className={styles.actions}>
        <button className="button subtle" type="button" disabled={safeStep === 0} onClick={() => onSelectStep(safeStep - 1)}><ChevronLeft size={15} /> Previous idea</button>
        <p>{allVisited ? "You have the model. Apply it with feedback next." : "Explore each idea before starting practice."}</p>
        {allVisited ? <button className="button primary" type="button" onClick={onBeginPractice}>{lesson.practiceLabel} <Play size={15} /></button> : <button className="button primary" type="button" onClick={() => onSelectStep(Math.min(safeStep + 1, lesson.beats.length - 1))}>Next idea <ChevronRight size={15} /></button>}
      </footer>
    </section>
  );
}

export function FoundationsTeachingRecap({ sceneId, onReview }: { sceneId: string; onReview: () => void }) {
  const lesson = FOUNDATIONS_TEACHING[sceneId];
  if (!lesson) return null;
  return (
    <div className={styles.recap} role="note">
      <span><Check size={14} /> Concept explored</span>
      <p>{lesson.beats.map((beat) => beat.label).join(" → ")}</p>
      <button className="button subtle small" type="button" onClick={onReview}><RotateCcw size={13} /> Review the model</button>
    </div>
  );
}
