"use client";

import { ArrowLeft, ArrowRight, Check, ClipboardList, Save } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import styles from "./FocusedInterpretationStepper.module.css";

export type FocusedInterpretationKey =
  | "rate"
  | "rhythm"
  | "axis"
  | "intervals"
  | "conduction"
  | "st_t"
  | "hypertrophy"
  | "synthesis";

export type FocusedInterpretationValue = Record<FocusedInterpretationKey, string>;

export type FocusedInterpretationStep = {
  key: FocusedInterpretationKey;
  label: string;
  prompt: string;
  placeholder: string;
  choices?: string[];
};

export const EMPTY_FOCUSED_INTERPRETATION: FocusedInterpretationValue = {
  rate: "",
  rhythm: "",
  axis: "",
  intervals: "",
  conduction: "",
  st_t: "",
  hypertrophy: "",
  synthesis: "",
};

export const DEFAULT_FOCUSED_INTERPRETATION_STEPS: FocusedInterpretationStep[] = [
  {
    key: "rate",
    label: "Rate",
    prompt: "Estimate the ventricular rate and classify the rate band.",
    placeholder: "e.g. approximately 78 bpm, normal rate",
    choices: ["Bradycardic", "Normal rate", "Tachycardic", "Rate uncertain"],
  },
  {
    key: "rhythm",
    label: "Rhythm",
    prompt: "Name the rhythm, regularity, and atrial-to-ventricular relationship.",
    placeholder: "e.g. regular sinus rhythm with 1:1 AV conduction",
    choices: ["Regular sinus rhythm", "Irregularly irregular", "Regular non-sinus rhythm", "Rhythm uncertain"],
  },
  {
    key: "axis",
    label: "Axis",
    prompt: "Assess the frontal-plane QRS axis from the limb leads.",
    placeholder: "e.g. normal axis, approximately +45°",
    choices: ["Normal axis", "Left axis deviation", "Right axis deviation", "Extreme axis"],
  },
  {
    key: "intervals",
    label: "P waves & PR",
    prompt: "Describe P-wave morphology and the PR interval before moving to the QRS.",
    placeholder: "e.g. upright sinus P waves in II; PR approximately 160 ms",
    choices: ["Sinus P waves / PR normal", "P-wave abnormality", "PR prolonged", "Short PR", "P waves not clearly measurable"],
  },
  {
    key: "conduction",
    label: "QRS & conduction",
    prompt: "Describe QRS width, morphology, conduction, and R-wave progression.",
    placeholder: "e.g. narrow QRS with normal precordial progression",
    choices: ["Narrow QRS / no block", "RBBB pattern", "LBBB pattern", "Other wide QRS"],
  },
  {
    key: "st_t",
    label: "ST–T & QT",
    prompt: "Describe repolarization morphology and its lead distribution.",
    placeholder: "e.g. no significant ST deviation or pathologic T-wave change",
    choices: ["No significant ST–T or QT abnormality", "ST elevation", "ST depression", "T-wave inversion", "QT/QTc prolonged", "Nonspecific ST–T change"],
  },
  {
    key: "hypertrophy",
    label: "Chambers & progression",
    prompt: "Check chamber enlargement, hypertrophy, and precordial progression.",
    placeholder: "e.g. no chamber enlargement; normal R-wave progression",
    choices: ["No chamber enlargement", "LVH pattern", "RVH pattern", "Atrial enlargement", "Progression abnormality"],
  },
  {
    key: "synthesis",
    label: "Final impression",
    prompt: "Prioritize the important findings in one evidence-limited ECG impression.",
    placeholder: "Lead with the dominant finding, then relevant qualifiers and limitations",
  },
];

type Choice = { id: string; label: string };
type BinaryChoice = { id: "present" | "absent"; label: string };

type Props = {
  value: FocusedInterpretationValue;
  onChange: (value: FocusedInterpretationValue) => void;
  activeIndex: number;
  onActiveIndexChange: (index: number) => void;
  steps?: FocusedInterpretationStep[];
  classificationPrompt: string;
  classificationOptions: BinaryChoice[];
  selectedClassification: "present" | "absent" | "";
  onClassificationChange: (value: "present" | "absent") => void;
  synthesisPrompt: string;
  synthesisOptions: Choice[];
  selectedSynthesis: string;
  onSynthesisChange: (value: string) => void;
  disabled?: boolean;
};

function stepIsComplete(
  step: FocusedInterpretationStep,
  value: FocusedInterpretationValue,
  selectedClassification: string,
  selectedSynthesis: string,
) {
  if (!value[step.key].trim()) return false;
  if (step.key !== "synthesis") return true;
  return Boolean(selectedClassification && selectedSynthesis && value.synthesis.trim().length >= 12);
}

export function FocusedInterpretationStepper({
  value,
  onChange,
  activeIndex,
  onActiveIndexChange,
  steps = DEFAULT_FOCUSED_INTERPRETATION_STEPS,
  classificationPrompt,
  classificationOptions,
  selectedClassification,
  onClassificationChange,
  synthesisPrompt,
  synthesisOptions,
  selectedSynthesis,
  onSynthesisChange,
  disabled = false,
}: Props) {
  const [overviewOpen, setOverviewOpen] = useState(false);
  const [focusRequest, setFocusRequest] = useState(0);
  const activePanelRef = useRef<HTMLDivElement | null>(null);
  const safeIndex = Math.min(Math.max(activeIndex, 0), Math.max(steps.length - 1, 0));
  const activeStep = steps[safeIndex] ?? DEFAULT_FOCUSED_INTERPRETATION_STEPS[0];
  const completed = steps.filter((step) => stepIsComplete(step, value, selectedClassification, selectedSynthesis)).length;
  const activeComplete = stepIsComplete(activeStep, value, selectedClassification, selectedSynthesis);

  function setField(key: FocusedInterpretationKey, fieldValue: string) {
    onChange({ ...value, [key]: fieldValue.slice(0, key === "synthesis" ? 600 : 300) });
  }

  function activateStep(index: number) {
    onActiveIndexChange(index);
    setFocusRequest((current) => current + 1);
  }

  useEffect(() => {
    if (focusRequest > 0) activePanelRef.current?.focus();
  }, [focusRequest, safeIndex]);

  return (
    <section className={styles.shell} aria-labelledby="focused-interpretation-heading">
      <header className={styles.header}>
        <div>
          <p>Complete ECG interpretation</p>
          <h3 id="focused-interpretation-heading">Use the same sequence on every tracing</h3>
        </div>
        <button
          className={styles.overviewButton}
          type="button"
          aria-pressed={overviewOpen}
          onClick={() => setOverviewOpen((current) => !current)}
          disabled={disabled}
        >
          <ClipboardList size={15} aria-hidden="true" /> {overviewOpen ? "Continue editing" : "Overview"}
        </button>
      </header>

      {overviewOpen ? (
        <ol className={styles.overview} aria-label="Interpretation overview">
          {steps.map((step, index) => {
            const complete = stepIsComplete(step, value, selectedClassification, selectedSynthesis);
            return (
              <li key={step.key} data-complete={complete || undefined}>
                <button type="button" onClick={() => { activateStep(index); setOverviewOpen(false); }} disabled={disabled}>
                  <span>{complete ? <Check size={13} aria-hidden="true" /> : index + 1}</span>
                  <div><strong>{step.label}</strong><small>{value[step.key].trim() || "Not completed"}</small></div>
                  <ArrowRight size={14} aria-hidden="true" />
                </button>
              </li>
            );
          })}
        </ol>
      ) : (
        <>
          <ol className={styles.stepList} aria-label="Systematic ECG interpretation steps">
            {steps.map((step, index) => {
              const current = index === safeIndex;
              const complete = stepIsComplete(step, value, selectedClassification, selectedSynthesis);
              return (
                <li key={step.key} data-current={current || undefined} data-complete={complete || undefined}>
                  <button
                    type="button"
                    aria-current={current ? "step" : undefined}
                    onClick={() => activateStep(index)}
                    disabled={disabled}
                  >
                    <span>{complete ? <Check size={13} aria-hidden="true" /> : index + 1}</span>
                    <strong>{step.label}</strong>
                    {complete && !current ? <small>{value[step.key]}</small> : null}
                  </button>
                </li>
              );
            })}
          </ol>

          <div className={styles.activeStep} ref={activePanelRef} tabIndex={-1} aria-label={`${activeStep.label} interpretation step`}>
            <div className={styles.activeHeading}>
              <span>{safeIndex + 1}</span>
              <div><small>Current step</small><h4>{activeStep.label}</h4></div>
            </div>
            <p>{activeStep.prompt}</p>

            {activeStep.choices?.length ? (
              <div className={styles.quickChoices} role="group" aria-label={`${activeStep.label} quick choices`}>
                {activeStep.choices.map((choice) => (
                  <button
                    type="button"
                    key={choice}
                    aria-pressed={value[activeStep.key] === choice}
                    onClick={() => setField(activeStep.key, choice)}
                    disabled={disabled}
                  >
                    {value[activeStep.key] === choice ? <Check size={13} aria-hidden="true" /> : null}{choice}
                  </button>
                ))}
              </div>
            ) : null}

            {activeStep.key === "synthesis" ? (
              <div className={styles.finalChecks}>
                <fieldset>
                  <legend>{classificationPrompt}</legend>
                  <div className={styles.finalOptions}>
                    {classificationOptions.map((option) => (
                      <button
                        type="button"
                        key={option.id}
                        aria-pressed={selectedClassification === option.id}
                        onClick={() => onClassificationChange(option.id)}
                        disabled={disabled}
                      >
                        {selectedClassification === option.id ? <Check size={13} aria-hidden="true" /> : null}{option.label}
                      </button>
                    ))}
                  </div>
                </fieldset>
                <fieldset>
                  <legend>{synthesisPrompt}</legend>
                  <div className={styles.synthesisOptions} role="radiogroup" aria-label={synthesisPrompt}>
                    {synthesisOptions.map((option) => (
                      <button
                        type="button"
                        role="radio"
                        aria-checked={selectedSynthesis === option.id}
                        key={option.id}
                        onClick={() => onSynthesisChange(option.id)}
                        disabled={disabled}
                      >
                        <span>{selectedSynthesis === option.id ? <Check size={13} aria-hidden="true" /> : null}</span>
                        {option.label}
                      </button>
                    ))}
                  </div>
                </fieldset>
              </div>
            ) : null}

            <label className={styles.preciseEntry} htmlFor={`focused-interpretation-${activeStep.key}`}>
              <span>{activeStep.choices?.length ? "Add a more precise entry, or edit the quick choice" : "Your evidence-limited impression"}</span>
              {activeStep.key === "synthesis" ? (
                <textarea
                  id={`focused-interpretation-${activeStep.key}`}
                  value={value[activeStep.key]}
                  placeholder={activeStep.placeholder}
                  onChange={(event) => setField(activeStep.key, event.target.value)}
                  disabled={disabled}
                />
              ) : (
                <input
                  id={`focused-interpretation-${activeStep.key}`}
                  value={value[activeStep.key]}
                  placeholder={activeStep.placeholder}
                  onChange={(event) => setField(activeStep.key, event.target.value)}
                  autoComplete="off"
                  disabled={disabled}
                />
              )}
            </label>

            <div className={styles.stepActions}>
              <button type="button" onClick={() => activateStep(Math.max(0, safeIndex - 1))} disabled={disabled || safeIndex === 0}>
                <ArrowLeft size={14} aria-hidden="true" /> Previous
              </button>
              <button
                className={styles.continueButton}
                type="button"
                onClick={() => {
                  if (safeIndex < steps.length - 1) activateStep(safeIndex + 1);
                  else setOverviewOpen(true);
                }}
                disabled={disabled || !activeComplete}
              >
                {safeIndex === steps.length - 1 ? <ClipboardList size={14} aria-hidden="true" /> : <Save size={14} aria-hidden="true" />}
                {safeIndex === steps.length - 1 ? "Review steps" : "Save & continue"}
                {safeIndex < steps.length - 1 ? <ArrowRight size={14} aria-hidden="true" /> : null}
              </button>
            </div>
          </div>
        </>
      )}

      <footer className={styles.footer}>
        <strong>{completed} of {steps.length} steps</strong>
        <span><Save size={13} aria-hidden="true" /> Draft saved in this tab until you check your answer</span>
      </footer>
    </section>
  );
}

export type FocusedReviewedFrameworkRow = {
  key: string;
  label: string;
  review: string;
  grounded: boolean;
};

export function FocusedInterpretationReview({
  submitted,
  reviewed,
  steps = DEFAULT_FOCUSED_INTERPRETATION_STEPS,
}: {
  submitted: FocusedInterpretationValue;
  reviewed: FocusedReviewedFrameworkRow[];
  steps?: FocusedInterpretationStep[];
}) {
  const reviewedByKey = new Map(reviewed.map((row) => [row.key, row]));
  return (
    <section className={styles.review} aria-labelledby="focused-framework-review-heading">
      <div className={styles.reviewHeading}>
        <ClipboardList size={17} aria-hidden="true" />
        <div><p>Systematic read review</p><h3 id="focused-framework-review-heading">Compare each step with grounded ECG data</h3></div>
      </div>
      <ol>
        {steps.map((step, index) => {
          const guide = reviewedByKey.get(step.key);
          return (
            <li key={step.key}>
              <span>{index + 1}</span>
              <div>
                <strong>{guide?.label || step.label}</strong>
                <p><small>Your entry</small>{submitted[step.key] || "No entry recorded"}</p>
                <p data-grounded={guide?.grounded || undefined}>
                  <small>{guide?.grounded ? "Reviewed ECG evidence" : "Review boundary"}</small>
                  {guide?.review ?? "The available ECG data did not independently verify this domain."}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
      <p className={styles.reviewBoundary}>The framework is formative here: completion and the final reviewed synthesis are checked. Domain-level mastery is only updated where the platform has an independent grading contract.</p>
    </section>
  );
}
