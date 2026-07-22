"use client";

import {
  ArrowLeft,
  ArrowRightLeft,
  BookOpenCheck,
  BrainCircuit,
  CheckCircle2,
  CircleAlert,
  Clock3,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  Stethoscope,
  TimerReset,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ECGViewer } from "@/components/ECGViewer";
import { ApiError, api, type LearningSessionReplay } from "@/lib/api";
import { conceptLabel } from "@/lib/coordinates";
import styles from "./replay.module.css";

const modePresentation = {
  training: { label: "Focused practice", Icon: BrainCircuit },
  rapid: { label: "Rapid practice", Icon: TimerReset },
  clinical: { label: "Clinical case", Icon: Stethoscope },
} as const;

const labelOverrides: Record<string, string> = {
  selectedAnswer: "Your classification",
  expectedAnswer: "Recommended classification",
  selectedOptionId: "Your selected option",
  recommendedOptionIds: "Recommended options",
  evidenceNote: "Why you chose it",
  freeTextAnswer: "Your summary",
  structuredAnswer: "Your structured interpretation",
  subskillTaskAnswer: "Your skill response",
  subskillTaskMatches: "Your matches",
  subskillTaskValue: "Your measured value",
  subskillTaskResult: "Skill task result",
  classificationCorrect: "Classification correct",
  skillCorrect: "Skill response correct",
  selectedSkillFeedback: "Selected skill",
  patternFeedback: "Pattern decision",
  firstLookFinding: "First-look finding",
  firstLookConfidence: "First-look confidence",
  fillInValue: "Your measured value",
  responseMs: "Response time",
  answerTimeMs: "Answer time",
  confidenceTimeMs: "Confidence time",
  correctObjectives: "Correctly identified",
  missedObjectives: "Missed findings",
  overcalledObjectives: "Overcalled findings",
  revealedDiagnosis: "Answer guide",
  teachingPoints: "Teaching points",
  correctStepAnswers: "Recommended step choices",
  correctMatches: "Recommended matches",
  expectedMeasurement: "Recommended measurement",
  incorrectMachineLineIds: "Incorrect machine statements",
  traceTarget: "Trace target",
  traceEvidence: "Your trace marker",
  trace: "Trace feedback",
  taskResponses: "Your task responses",
  taskFeedback: "Question-by-question feedback",
  axisScores: "Decision dimensions",
  clinicalApplicationEvidence: "Clinical reasoning",
  competencyOutcomes: "Skill outcomes",
  objectiveId: "Skill",
  subskill: "Skill focus",
  mappingSource: "Linked from",
  learningEvidence: "Practice type",
  recordStatus: "Status",
};

const tokenOverrides: Record<string, string> = {
  committed_event: "This question",
  session_focus: "This session",
  independent_assessment: "Scored practice",
  independent_transfer: "Scored practice",
  real_deidentified_ecg: "Deidentified ECG",
  verified: "Recorded",
};

const separatelyRenderedQuestionFields = new Set([
  "kind",
  "situation",
  "stem",
  "chips",
  "prompt",
  "options",
  "classificationOptions",
  "subskillTask",
  "testedObjectiveManifest",
  "taskPacket",
  "steps",
]);

function humanize(value: string) {
  if (labelOverrides[value]) return labelOverrides[value];
  return value
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replace(/^./, (letter) => letter.toUpperCase());
}

function formatToken(value: string) {
  if (tokenOverrides[value]) return tokenOverrides[value];
  if (/^[a-z0-9_:-]{1,120}$/i.test(value) && !value.includes(" ")) {
    const objective = value.includes(":") ? value.split(":")[0] : value;
    const label = conceptLabel(objective);
    if (label && label !== objective) return label;
    return humanize(value.replaceAll(":", " · "));
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isMeaningful(value: unknown): boolean {
  if (value === null || value === undefined || value === "") return false;
  if (Array.isArray(value)) return value.some(isMeaningful);
  if (isRecord(value)) return Object.values(value).some(isMeaningful);
  return true;
}

function formatPrimitive(key: string, value: string | number | boolean) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (key.toLocaleLowerCase().includes("score") && value >= 0 && value <= 1) return `${Math.round(value * 100)}%`;
    if (key.toLocaleLowerCase().endsWith("ms")) return `${(value / 1000).toFixed(value >= 10_000 ? 0 : 1)} sec`;
    return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
  }
  return formatToken(value);
}

function FriendlyValue({ fieldKey, value, depth = 0 }: { fieldKey: string; value: unknown; depth?: number }) {
  if (!isMeaningful(value)) return <span className={styles.mutedValue}>Not recorded</span>;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span>{formatPrimitive(fieldKey, value)}</span>;
  }
  if (Array.isArray(value)) {
    const meaningful = value.filter(isMeaningful);
    if (meaningful.every((item) => ["string", "number", "boolean"].includes(typeof item))) {
      return <span className={styles.tags}>{meaningful.map((item, index) => <span key={`${String(item)}:${index}`}>{formatPrimitive(fieldKey, item as string | number | boolean)}</span>)}</span>;
    }
    return <ol className={styles.nestedList}>{meaningful.map((item, index) => <li key={index}><FriendlyValue fieldKey={fieldKey} value={item} depth={depth + 1} /></li>)}</ol>;
  }
  if (isRecord(value) && depth < 3) {
    return <FriendlyRecord value={value} depth={depth + 1} />;
  }
  return <span className={styles.mutedValue}>Recorded detail unavailable</span>;
}

function FriendlyRecord({ value, depth = 0 }: { value: Record<string, unknown>; depth?: number }) {
  const rows = Object.entries(value).filter(([, item]) => isMeaningful(item));
  if (!rows.length) return <p className={styles.emptyRecord}>No additional detail was recorded.</p>;
  return (
    <dl className={depth ? styles.nestedFields : styles.fields}>
      {rows.map(([key, item]) => (
        <div key={key}>
          <dt>{humanize(key)}</dt>
          <dd><FriendlyValue fieldKey={key} value={item} depth={depth} /></dd>
        </div>
      ))}
    </dl>
  );
}

function optionRows(question: Record<string, unknown>) {
  const source = Array.isArray(question.options)
    ? question.options
    : Array.isArray(question.classificationOptions)
      ? question.classificationOptions
      : [];
  return source.filter(isRecord).map((option) => ({
    id: typeof option.id === "string" ? option.id : "",
    label: typeof option.text === "string" ? option.text : typeof option.label === "string" ? option.label : "Option",
  })).filter((option) => option.id);
}

function rapidTaskResponseLabel(
  task: NonNullable<LearningSessionReplay["question"]["taskPacket"]>["tasks"][number],
  response: unknown,
) {
  const optionLabel = (id: string) => task.options?.find((option) => option.id === id)?.label ?? id;
  if (typeof response === "string") return optionLabel(response);
  if (typeof response === "number") return `${response}${task.unit ? ` ${task.unit}` : ""}`;
  if (Array.isArray(response)) return response.map((item) => optionLabel(String(item))).join(", ");
  if (isRecord(response)) {
    const point = isRecord(response.point) ? response.point : null;
    if (point && typeof point.lead === "string" && typeof point.timeSec === "number") {
      return `${point.lead} at ${point.timeSec.toFixed(2)} sec`;
    }
    return Object.entries(response)
      .filter(([, value]) => isMeaningful(value))
      .map(([key, value]) => `${humanize(key)}: ${String(value)}`)
      .join(" · ");
  }
  return "No response recorded";
}

function RapidTaskReview({ replay }: { replay: LearningSessionReplay }) {
  const taskPacket = replay.question.taskPacket;
  if (!taskPacket?.tasks.length) return null;
  const responses = replay.submission.taskResponses ?? {};
  const feedbackRows = replay.feedback.taskFeedback ?? [];

  return (
    <div className={styles.rapidTaskReview} aria-label="Recorded Rapid questions">
      {taskPacket.tasks.map((task, index) => {
        const feedback = feedbackRows.find((row) => row.taskId === task.id);
        const response = responses[task.id];
        const selectedIds = new Set(
          Array.isArray(response)
            ? response.map(String)
            : typeof response === "string"
              ? [response]
              : [],
        );
        return (
          <article key={task.id} data-correct={feedback?.correct === true || undefined}>
            <header>
              <span>Question {index + 1}</span>
              {task.skillId ? <small>{humanize(task.skillId)}</small> : null}
              {typeof feedback?.correct === "boolean" ? (
                <strong>{feedback.correct ? "Correct" : "Review"}</strong>
              ) : null}
            </header>
            <h3>{task.prompt}</h3>
            {task.options?.length ? (
              <ol className={styles.taskOptions}>
                {task.options.map((option, optionIndex) => (
                  <li
                    key={option.id}
                    data-selected={selectedIds.has(option.id) || undefined}
                    data-recommended={feedback?.correctChoiceId === option.id || undefined}
                  >
                    <span>{String.fromCharCode(65 + optionIndex)}</span>
                    <div><strong>{option.label}</strong><small>{selectedIds.has(option.id) ? "Your response" : ""}{selectedIds.has(option.id) && feedback?.correctChoiceId === option.id ? " · " : ""}{feedback?.correctChoiceId === option.id ? "Recommended" : ""}</small></div>
                  </li>
                ))}
              </ol>
            ) : (
              <div className={styles.taskResponse}>
                <span>Your response</span>
                <strong>{rapidTaskResponseLabel(task, response)}</strong>
              </div>
            )}
            {feedback?.feedback ? <p className={styles.taskFeedback}>{feedback.feedback}</p> : null}
            {feedback?.referenceLabel ? <small className={styles.taskReference}>{feedback.referenceLabel}</small> : null}
          </article>
        );
      })}
    </div>
  );
}

type FocusedChoice = { id: string; label: string };
const focusedInterpretationKeys = [
  "rate",
  "rhythm",
  "axis",
  "intervals",
  "conduction",
  "st_t",
  "hypertrophy",
  "synthesis",
] as const;
type FocusedInterpretationKey = (typeof focusedInterpretationKeys)[number];
type FocusedFrameworkStep = {
  key: FocusedInterpretationKey;
  label: string;
  prompt: string;
  placeholder: string;
  choices: string[];
};

function isFocusedInterpretationKey(value: unknown): value is FocusedInterpretationKey {
  return typeof value === "string" && focusedInterpretationKeys.some((key) => key === value);
}

function focusedInterpretation(value: unknown): Partial<Record<FocusedInterpretationKey, string>> {
  if (!isRecord(value)) return {};
  return Object.fromEntries(focusedInterpretationKeys.flatMap((key) => (
    typeof value[key] === "string" ? [[key, value[key]]] : []
  ))) as Partial<Record<FocusedInterpretationKey, string>>;
}
type FocusedTask = {
  kind: "single_choice" | "matching" | "numeric_fill_in" | "confidence_commit";
  subskill: string;
  prompt: string;
  options: FocusedChoice[];
  choices: FocusedChoice[];
  rows: Array<{ id: string; clause: string }>;
  unit: string | null;
  frameworkVersion: string | null;
  frameworkSteps: FocusedFrameworkStep[];
};

function focusedChoices(value: unknown): FocusedChoice[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord).map((choice) => ({
    id: typeof choice.id === "string" ? choice.id : "",
    label: typeof choice.label === "string" ? choice.label : "",
  })).filter((choice) => choice.id && choice.label);
}

function focusedQuestionSnapshot(replay: LearningSessionReplay) {
  const snapshot = replay.question.questionSnapshot ?? replay.question.question_snapshot;
  return isRecord(snapshot) ? snapshot : null;
}

function focusedTaskFromReplay(replay: LearningSessionReplay): FocusedTask | null {
  const snapshot = focusedQuestionSnapshot(replay);
  const raw = isRecord(replay.question.subskillTask)
    ? replay.question.subskillTask
    : snapshot && isRecord(snapshot.task)
      ? snapshot.task
      : null;
  if (!isRecord(raw)) return null;
  const kind = raw.kind;
  if (kind !== "single_choice" && kind !== "matching" && kind !== "numeric_fill_in" && kind !== "confidence_commit") return null;
  const rows = Array.isArray(raw.rows)
    ? raw.rows.filter(isRecord).map((row) => ({
      id: typeof row.id === "string" ? row.id : "",
      clause: typeof row.clause === "string" ? row.clause : "",
    })).filter((row) => row.id && row.clause)
    : [];
  const frameworkSteps = Array.isArray(raw.frameworkSteps)
    ? raw.frameworkSteps.filter(isRecord).flatMap((step): FocusedFrameworkStep[] => {
      if (
        !isFocusedInterpretationKey(step.key)
        || typeof step.label !== "string"
        || typeof step.prompt !== "string"
        || !step.label
        || !step.prompt
      ) return [];
      return [{
        key: step.key,
        label: step.label,
        prompt: step.prompt,
        placeholder: typeof step.placeholder === "string" ? step.placeholder : "",
        choices: Array.isArray(step.choices)
          ? step.choices.filter((choice): choice is string => typeof choice === "string")
          : [],
      }];
    }).slice(0, 8)
    : [];
  return {
    kind,
    subskill: typeof raw.subskill === "string" ? raw.subskill : "",
    prompt: typeof raw.prompt === "string" ? raw.prompt : "Review the selected skill response.",
    options: focusedChoices(raw.options),
    choices: focusedChoices(raw.choices),
    rows,
    unit: typeof raw.unit === "string" ? raw.unit : null,
    frameworkVersion: typeof raw.frameworkVersion === "string" ? raw.frameworkVersion : null,
    frameworkSteps,
  };
}

function FocusedTargetIdentity({ replay }: { replay: LearningSessionReplay }) {
  const snapshot = focusedQuestionSnapshot(replay);
  const target = isRecord(replay.question.target)
    ? replay.question.target
    : snapshot && isRecord(snapshot.target)
      ? snapshot.target
      : null;
  const objectiveLabel = target && typeof target.objectiveLabel === "string"
    ? target.objectiveLabel.trim()
    : snapshot && typeof snapshot.objectiveLabel === "string"
      ? snapshot.objectiveLabel.trim()
      : "";
  const caseConceptLabel = target && typeof target.caseConceptLabel === "string"
    ? target.caseConceptLabel.trim()
    : snapshot && typeof snapshot.caseConceptLabel === "string"
      ? snapshot.caseConceptLabel.trim()
      : "";
  if (!objectiveLabel || !caseConceptLabel || objectiveLabel.localeCompare(caseConceptLabel, undefined, { sensitivity: "accent" }) === 0) return null;

  return (
    <dl className={styles.focusedTargetIdentity} aria-label="Focused practice context">
      <div><dt>Practice objective</dt><dd>{objectiveLabel}</dd></div>
      <div><dt>ECG example</dt><dd>{caseConceptLabel}</dd></div>
    </dl>
  );
}

function focusedTaskResult(replay: LearningSessionReplay) {
  return isRecord(replay.answerGuide.subskillTaskResult)
    ? replay.answerGuide.subskillTaskResult
    : null;
}

function taskResultText(result: Record<string, unknown> | null, key: string) {
  return result && typeof result[key] === "string" ? result[key] as string : null;
}

function taskResultNumber(result: Record<string, unknown> | null, key: string) {
  return result && typeof result[key] === "number" && Number.isFinite(result[key])
    ? result[key] as number
    : null;
}

function FocusedSystematicReview({ replay, task }: { replay: LearningSessionReplay; task: FocusedTask }) {
  const result = focusedTaskResult(replay);
  const submittedResponse = focusedInterpretation(replay.submission.structuredInterpretation);
  const submitted = Object.keys(submittedResponse).length
    ? submittedResponse
    : focusedInterpretation(result?.systematicInterpretation);
  const topLevelReviewed = Array.isArray(replay.answerGuide.reviewedFramework)
    ? replay.answerGuide.reviewedFramework.filter(isRecord)
    : [];
  const resultReviewed = result && Array.isArray(result.reviewedFramework)
    ? result.reviewedFramework.filter(isRecord)
    : [];
  const reviewed = topLevelReviewed.length ? topLevelReviewed : resultReviewed;
  const complete = typeof replay.answerGuide.systematicInterpretationComplete === "boolean"
    ? replay.answerGuide.systematicInterpretationComplete
    : result && typeof result.systematicInterpretationComplete === "boolean"
      ? result.systematicInterpretationComplete
      : null;
  if (!task.frameworkSteps.length) return null;

  return (
    <section className={styles.systematicReview} aria-label="Systematic ECG interpretation review">
      <header className={styles.systematicHeader}>
        <div><span>Full ECG interpretation</span><h4>Review your eight-step read</h4></div>
        {complete !== null ? <strong data-complete={complete || undefined}>{complete ? "All 8 steps recorded" : "Interpretation incomplete"}</strong> : null}
      </header>
      <ol className={styles.systematicSteps}>
        {task.frameworkSteps.map((step, index) => {
          const review = reviewed.find((row) => row.key === step.key);
          const submittedText = submitted[step.key];
          const learnerText = typeof submittedText === "string" && submittedText.trim()
            ? submittedText.trim()
            : "No response recorded";
          const reviewText = review && typeof review.review === "string" && review.review.trim()
            ? review.review.trim()
            : "Reviewed guidance unavailable";
          const grounded = review?.grounded === true;
          return (
            <li key={step.key}>
              <header><span>{index + 1}</span><div><strong>{step.label}</strong><small>{step.prompt}</small></div></header>
              <dl>
                <div><dt>Your interpretation</dt><dd>{learnerText}</dd></div>
                <div data-grounded={grounded || undefined}>
                  <dt>{grounded ? "Reviewed ECG evidence" : "Reviewed framework"}</dt>
                  <dd>{reviewText}</dd>
                </div>
              </dl>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function FocusedTaskReview({ replay }: { replay: LearningSessionReplay }) {
  const task = focusedTaskFromReplay(replay);
  if (!task) return null;
  const result = focusedTaskResult(replay);
  const resultCorrect = result && typeof result.correct === "boolean" ? result.correct : null;
  const choiceLabel = (choices: FocusedChoice[], id: string | null) => (
    id ? choices.find((choice) => choice.id === id)?.label ?? null : null
  );
  const selectedAnswer = taskResultText(result, "submittedAnswer")
    ?? (typeof replay.submission.subskillTaskAnswer === "string" ? replay.submission.subskillTaskAnswer : null);
  const reviewedAnswer = taskResultText(result, "correctAnswer");

  return (
    <article className={styles.focusedTaskReview} aria-label="Focused skill review">
      <header className={styles.focusedTaskHeader}>
        <div>
          <span>Selected skill</span>
          {task.subskill ? <strong>{humanize(task.subskill)}</strong> : null}
        </div>
        {resultCorrect !== null ? (
          <span className={styles.focusedTaskStatus} data-correct={resultCorrect || undefined}>
            {resultCorrect ? "Skill met" : "Review this skill"}
          </span>
        ) : null}
      </header>
      <h3>{task.prompt}</h3>

      {task.kind === "single_choice" ? (
        <ol className={styles.focusedChoiceReview}>
          {task.options.map((option, index) => {
            const selected = option.id === selectedAnswer;
            const reviewed = option.id === reviewedAnswer;
            return (
              <li key={option.id} data-selected={selected || undefined} data-reviewed={reviewed || undefined}>
                <span>{String.fromCharCode(65 + index)}</span>
                <div>
                  <strong>{option.label}</strong>
                  <small>{selected ? "Your selection" : ""}{selected && reviewed ? " · " : ""}{reviewed ? "Reviewed answer" : ""}</small>
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}

      {task.kind === "matching" ? (
        <ol className={styles.focusedMatchingReview}>
          {task.rows.map((row) => {
            const resultRows = result && Array.isArray(result.rows) ? result.rows.filter(isRecord) : [];
            const rowResult = resultRows.find((candidate) => candidate.rowId === row.id);
            const submittedMatches = isRecord(replay.submission.subskillTaskMatches)
              ? replay.submission.subskillTaskMatches
              : {};
            const submittedId = rowResult && typeof rowResult.submittedChoiceId === "string"
              ? rowResult.submittedChoiceId
              : typeof submittedMatches[row.id] === "string"
                ? submittedMatches[row.id] as string
                : null;
            const correctId = rowResult && typeof rowResult.correctChoiceId === "string"
              ? rowResult.correctChoiceId
              : null;
            const rowCorrect = rowResult && typeof rowResult.correct === "boolean" ? rowResult.correct : null;
            return (
              <li key={row.id} data-correct={rowCorrect === true || undefined}>
                <strong>{row.clause}</strong>
                <dl>
                  <div><dt>Your match</dt><dd>{choiceLabel(task.choices, submittedId) ?? "No match recorded"}</dd></div>
                  <div><dt>Reviewed match</dt><dd>{choiceLabel(task.choices, correctId) ?? "Reviewed match unavailable"}</dd></div>
                </dl>
              </li>
            );
          })}
        </ol>
      ) : null}

      {task.kind === "numeric_fill_in" ? (() => {
        const submitted = taskResultNumber(result, "submittedValue")
          ?? (typeof replay.submission.subskillTaskValue === "number" ? replay.submission.subskillTaskValue : null);
        const expected = taskResultNumber(result, "expectedValue");
        const tolerance = taskResultNumber(result, "tolerance");
        const unit = taskResultText(result, "unit") ?? task.unit ?? "";
        return (
          <dl className={styles.focusedNumericReview}>
            <div><dt>Your measurement</dt><dd>{submitted ?? "Not recorded"}{submitted !== null && unit ? ` ${unit}` : ""}</dd></div>
            <div><dt>Reviewed measurement</dt><dd>{expected ?? "Unavailable"}{expected !== null && unit ? ` ${unit}` : ""}</dd></div>
            <div><dt>Accepted tolerance</dt><dd>{tolerance !== null ? `±${tolerance}${unit ? ` ${unit}` : ""}` : "Unavailable"}</dd></div>
          </dl>
        );
      })() : null}

      {task.kind === "confidence_commit" && task.subskill === "calibrate_confidence" ? (
        <div className={styles.focusedConfidenceReview}>
          <span>Your confidence</span>
          <strong>{typeof replay.submission.confidence === "number" ? `${replay.submission.confidence} of 5` : "Not recorded"}</strong>
          <small>Calibration compares your certainty with the reviewed outcome over repeated ECGs.</small>
        </div>
      ) : null}
      {task.subskill === "synthesize" ? <FocusedSystematicReview replay={replay} task={task} /> : null}
    </article>
  );
}

function ClinicalStageTimeline({ replay }: { replay: LearningSessionReplay }) {
  const stages = Array.isArray(replay.question.steps)
    ? replay.question.steps.filter(isRecord)
    : [];
  if (!stages.length) return null;
  const selected = Array.isArray(replay.submission.stepAnswers)
    ? replay.submission.stepAnswers
    : [];
  const recommended = Array.isArray(replay.answerGuide.correctStepAnswers)
    ? replay.answerGuide.correctStepAnswers
    : [];
  const feedbackRows = Array.isArray(replay.feedback.stepFeedback)
    ? replay.feedback.stepFeedback.filter(isRecord)
    : [];

  return (
    <ol className={styles.stageTimeline} aria-label="Clinical episode stages">
      {stages.map((stage, index) => {
        const dataPoints = Array.isArray(stage.dataPoints)
          ? stage.dataPoints.filter(isRecord)
          : [];
        const sources = new Set(dataPoints.map((point) => point.source));
        const options = Array.isArray(stage.options) ? stage.options.filter(isRecord) : [];
        const selectedIndex = typeof selected[index] === "number" ? selected[index] as number : null;
        const recommendedIndexes = new Set(
          Array.isArray(recommended[index])
            ? (recommended[index] as unknown[]).filter((value): value is number => typeof value === "number")
            : [],
        );
        const stageFeedback = feedbackRows.find((row) => row.stageIndex === index);
        return (
          <li key={index}>
            <header>
              <span>{typeof stage.stageKind === "string" ? humanize(stage.stageKind) : `Stage ${index + 1}`}</span>
              {typeof stage.elapsedLabel === "string" ? <small><Clock3 size={13} aria-hidden="true" /> {stage.elapsedLabel}</small> : null}
            </header>
            <h3>{typeof stage.stageTitle === "string" ? stage.stageTitle : `Decision stage ${index + 1}`}</h3>
            {sources.has("authored_simulation") ? <p className={styles.sourceBadge}>Authored simulation update</p> : null}
            {sources.has("source_metadata") ? <p className={styles.sourceBadge}>Source-verified ECG metadata</p> : null}
            {typeof stage.clinicalUpdate === "string" ? <p className={styles.stageUpdate}>{stage.clinicalUpdate}</p> : null}
            {dataPoints.length ? (
              <dl className={styles.stageData}>
                {dataPoints.map((point, pointIndex) => (
                  <div key={`${String(point.label)}:${pointIndex}`}>
                    <dt>{String(point.label ?? "Clinical data")}</dt>
                    <dd><strong>{String(point.value ?? "")}</strong>{typeof point.detail === "string" ? <span>{point.detail}</span> : null}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {typeof stage.prompt === "string" ? <p className={styles.stagePrompt}>{stage.prompt}</p> : null}
            {options.length ? (
              <ol className={styles.stageOptions}>
                {options.map((option, optionIndex) => (
                  <li
                    key={optionIndex}
                    data-selected={selectedIndex === optionIndex || undefined}
                    data-recommended={recommendedIndexes.has(optionIndex) || undefined}
                  >
                    <span>{String.fromCharCode(65 + optionIndex)}</span>
                    <div><strong>{String(option.text ?? "Option")}</strong><small>{selectedIndex === optionIndex ? "Your response" : ""}{selectedIndex === optionIndex && recommendedIndexes.has(optionIndex) ? " · " : ""}{recommendedIndexes.has(optionIndex) ? "Recommended" : ""}</small></div>
                  </li>
                ))}
              </ol>
            ) : null}
            {stageFeedback ? (
              <div className={styles.stageFeedback} data-correct={stageFeedback.correct === true || undefined}>
                <strong>{stageFeedback.correct === true ? "Stage aligned" : "Review this stage"}</strong>
                {typeof stageFeedback.explanation === "string" ? <p>{stageFeedback.explanation}</p> : null}
                {typeof stageFeedback.supportedAnswer === "string" ? <small>Supported response: {stageFeedback.supportedAnswer}</small> : null}
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function QuestionCard({ replay }: { replay: LearningSessionReplay }) {
  const question = replay.question;
  const options = optionRows(question);
  const selected = typeof replay.submission.selectedOptionId === "string"
    ? replay.submission.selectedOptionId
    : typeof replay.submission.selectedAnswer === "string"
      ? replay.submission.selectedAnswer
      : null;
  const recommended = new Set([
    ...(Array.isArray(replay.answerGuide.recommendedOptionIds)
      ? replay.answerGuide.recommendedOptionIds.filter((item): item is string => typeof item === "string")
      : []),
    ...(typeof replay.answerGuide.expectedAnswer === "string" ? [replay.answerGuide.expectedAnswer] : []),
  ]);
  const chips = isRecord(question.chips)
    ? Object.entries(question.chips).filter(([, value]) => isMeaningful(value))
    : [];
  const supplementalQuestion = Object.fromEntries(
    Object.entries(question).filter(([key, value]) => (
      !separatelyRenderedQuestionFields.has(key)
      && !(replay.mode === "training" && ["target", "phase", "questionSnapshot", "question_snapshot"].includes(key))
      && isMeaningful(value)
    )),
  );

  return (
    <section className={styles.question} aria-labelledby="replay-question-heading">
      <p className="eyebrow">Question</p>
      <h2 id="replay-question-heading">What you were asked</h2>
      {chips.length ? <dl className={styles.chips}>{chips.map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{String(value)}</dd></div>)}</dl> : null}
      {typeof question.situation === "string" && question.situation ? <p className={styles.situation}>{humanize(question.situation)}</p> : null}
      {typeof question.stem === "string" && question.stem ? <p className={styles.stem}>{question.stem}</p> : null}
      {typeof question.prompt === "string" && question.prompt ? <p className={styles.prompt}>{question.prompt}</p> : null}
      {replay.mode === "training" ? <FocusedTargetIdentity replay={replay} /> : null}
      {options.length ? (
        <ol className={styles.options}>
          {options.map((option, index) => (
            <li key={option.id} data-selected={selected === option.id || undefined} data-recommended={recommended.has(option.id) || undefined}>
              <span>{String.fromCharCode(65 + index)}</span><div><strong>{option.label}</strong><small>{selected === option.id ? "Your response" : ""}{selected === option.id && recommended.has(option.id) ? " · " : ""}{recommended.has(option.id) ? "Recommended" : ""}</small></div>
            </li>
          ))}
        </ol>
      ) : null}
      {replay.mode === "training" ? <FocusedTaskReview replay={replay} /> : null}
      {replay.mode === "rapid" ? <RapidTaskReview replay={replay} /> : null}
      {replay.mode === "clinical" ? <ClinicalStageTimeline replay={replay} /> : null}
      {replay.mode !== "training" && isRecord(question.subskillTask) ? <details className={styles.questionDetails}><summary>Skill task</summary><FriendlyRecord value={question.subskillTask} /></details> : null}
      {isRecord(question.testedObjectiveManifest) ? <details className={styles.questionDetails}><summary>Skills checked in this item</summary><FriendlyRecord value={question.testedObjectiveManifest} /></details> : null}
      {replay.mode !== "clinical" && Array.isArray(question.steps) && question.steps.length ? <details className={styles.questionDetails}><summary>Decision steps</summary><FriendlyValue fieldKey="steps" value={question.steps} /></details> : null}
      {Object.keys(supplementalQuestion).length ? <details className={styles.questionDetails}><summary>Additional question details</summary><FriendlyRecord value={supplementalQuestion} /></details> : null}
    </section>
  );
}

function ReplayWaveformCard({
  replay,
  title,
  eyebrow,
  ecgRef,
  available,
  waveformPresentation,
  provenance,
}: {
  replay: LearningSessionReplay;
  title: string;
  eyebrow: string;
  ecgRef: LearningSessionReplay["ecgRef"];
  available: boolean;
  waveformPresentation: LearningSessionReplay["waveformPresentation"];
  provenance?: string;
}) {
  const isCurrentTracing = ecgRef === replay.ecgRef;
  const savedEvidence = isCurrentTracing
    ? replay.submission.viewerTaskEvidence ?? replay.submission.traceEvidence ?? null
    : null;
  const reviewedActions = isCurrentTracing ? replay.reviewActions ?? [] : [];
  return (
    <article className={styles.waveformCard}>
      <header>
        <div><p>{eyebrow}</p><h3>{title}</h3></div>
        {provenance ? <span><ShieldCheck size={13} aria-hidden="true" /> {provenance}</span> : null}
      </header>
      {savedEvidence || reviewedActions.length ? (
        <div className={styles.evidenceLegend} aria-label="ECG evidence legend">
          {savedEvidence ? <span data-kind="learner">Your saved mark / measurement</span> : null}
          {reviewedActions.length ? <span data-kind="reviewed">Reviewed reference</span> : null}
        </div>
      ) : null}
      {available ? (
        <div className={styles.viewer}>
          <ECGViewer
            ecgRef={ecgRef}
            waveformScope={{ kind: "review", sessionRef: replay.sessionRef, attemptIndex: replay.attemptIndex }}
            gradingMode="deferred"
            presentation={waveformPresentation.kind === "rhythm_strip"
              ? { kind: "rhythm_strip", leads: waveformPresentation.leads ?? [] }
              : { kind: "twelve_lead" }}
            actions={reviewedActions}
            reviewEvidence={savedEvidence}
            reviewMode
          />
        </div>
      ) : <div className={styles.noWaveform}><CircleAlert size={19} aria-hidden="true" /><span>This tracing can’t be shown right now.</span></div>}
    </article>
  );
}

function submittedLabel(value: string) {
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return "Submission time unavailable";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(instant);
}

export default function LearningSessionReplayPage() {
  const params = useParams<{ sessionRef: string | string[]; attemptIndex: string | string[] }>();
  const rawRef = params.sessionRef;
  const rawIndex = params.attemptIndex;
  const sessionRef = Array.isArray(rawRef) ? rawRef[0] : rawRef;
  const attemptIndexText = Array.isArray(rawIndex) ? rawIndex[0] : rawIndex;
  const attemptIndex = Number(attemptIndexText);
  const validAttempt = Number.isInteger(attemptIndex) && attemptIndex > 0;
  const [replay, setReplay] = useState<LearningSessionReplay | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState<"not_found" | "unavailable" | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!validAttempt) {
      setReplay(null);
      setFailed("not_found");
      setLoading(false);
      return () => { cancelled = true; };
    }
    setLoading(true);
    setFailed(null);
    api.learningSessionReplay(sessionRef, attemptIndex)
      .then((value) => { if (!cancelled) setReplay(value); })
      .catch((error: unknown) => {
        if (cancelled) return;
        setReplay(null);
        setFailed(error instanceof ApiError && error.status === 404 ? "not_found" : "unavailable");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [attemptIndex, retryKey, sessionRef, validAttempt]);

  const reviewHref = `/home/review/${encodeURIComponent(sessionRef)}`;
  const presentation = replay ? modePresentation[replay.mode] : null;
  const ModeIcon = presentation?.Icon;
  const feedbackTone = useMemo(() => {
    const score = replay?.feedback.score;
    return typeof score === "number" && score >= .7 ? "positive" : "neutral";
  }, [replay?.feedback.score]);

  if (loading) return <div className={`page ${styles.page}`}><div className={styles.loading} role="status">Opening your question review…</div></div>;

  if (!replay || failed || !presentation || !ModeIcon) {
    return (
      <div className={`page ${styles.page}`}>
        <Link className={styles.back} href={reviewHref}><ArrowLeft size={16} aria-hidden="true" /> Back to session</Link>
        <section className={styles.error} role="alert">
          <CircleAlert size={24} aria-hidden="true" />
          <div><h1>{failed === "not_found" ? "This question is not available" : "We couldn’t load this question"}</h1><p>{failed === "not_found" ? "It may be incomplete, no longer available, or connected to another account." : "Your completed work is still safe. Try opening the question again."}</p></div>
          {failed === "unavailable" ? <button type="button" onClick={() => setRetryKey((value) => value + 1)}><RefreshCw size={15} aria-hidden="true" /> Retry</button> : null}
        </section>
      </div>
    );
  }

  const trainingSubmissionFields = new Set([
    "selectedAnswer",
    "confidence",
    "subskillTaskAnswer",
    "subskillTaskMatches",
    "subskillTaskValue",
    "structuredInterpretation",
  ]);
  const submissionSummary = Object.fromEntries(
    Object.entries(replay.submission).filter(([key]) => (
      !["taskResponses", "stepAnswers", "viewerTaskEvidence", "traceEvidence"].includes(key)
      && !(replay.mode === "training" && trainingSubmissionFields.has(key))
    )),
  );
  const feedbackSummary = Object.fromEntries(
    Object.entries(replay.feedback).filter(([key]) => !["taskFeedback", "stepFeedback"].includes(key)),
  );
  const answerGuideSummary = Object.fromEntries(
    Object.entries(replay.answerGuide).filter(([key]) => (
      key !== "correctStepAnswers"
      && !(replay.mode === "training" && [
        "expectedAnswer",
        "subskillTaskResult",
        "systematicInterpretationComplete",
        "reviewedFramework",
      ].includes(key))
    )),
  );
  const isPartialPractice = replay.sessionStatus === "abandoned" && (replay.mode === "rapid" || replay.mode === "training");
  const partialSessionLabel = replay.mode === "training" ? "Partial Focused set" : "Partial Rapid round";

  return (
    <div className={`page ${styles.page}`}>
      <Link className={styles.back} href={reviewHref}><ArrowLeft size={16} aria-hidden="true" /> Back to session</Link>

      <header className={styles.header}>
        <span className={styles.modeIcon} data-mode={replay.mode} aria-hidden="true"><ModeIcon size={22} /></span>
        <div><p className="eyebrow">{isPartialPractice ? "Submitted ECG review" : "Question review"}</p><h1>{replay.displayId}</h1><p>{isPartialPractice ? partialSessionLabel : presentation.label} · Submitted {submittedLabel(replay.submittedAt)}</p></div>
        <span className={styles.reviewOnly}><ShieldCheck size={14} aria-hidden="true" /> Review only</span>
      </header>

      <aside className={styles.boundary} role="note">
        <ShieldCheck size={20} aria-hidden="true" />
        <p><strong>Your work is locked.</strong> You can explore this {isPartialPractice ? "submitted ECG" : "completed question"}, but nothing here is graded or saved. The layout may look a little different from your original session.</p>
      </aside>

      <section className={styles.viewerSection} aria-labelledby="replay-ecg-heading">
        <header><div><p className="eyebrow">Tracing{replay.comparison ? "s" : ""}</p><h2 id="replay-ecg-heading">{replay.comparison ? <ArrowRightLeft size={19} aria-hidden="true" /> : <ScanLine size={19} aria-hidden="true" />} {replay.comparison ? "Serial ECG replay" : "ECG replay"}</h2></div><p>Zoom, pan, or add temporary marks while you review.</p></header>
        <div className={replay.comparison ? styles.waveformComparison : styles.waveformSingle}>
          {replay.comparison ? (
            <ReplayWaveformCard
              replay={replay}
              title={replay.comparison.label}
              eyebrow="Earlier tracing"
              ecgRef={replay.comparison.ecgRef}
              available={replay.comparison.waveformAvailable}
              waveformPresentation={replay.comparison.waveformPresentation}
              provenance="Authenticated comparison"
            />
          ) : null}
          <ReplayWaveformCard
            replay={replay}
            title={replay.comparison ? "Current ECG" : "ECG tracing"}
            eyebrow={replay.comparison ? "Current tracing" : "Recorded tracing"}
            ecgRef={replay.ecgRef}
            available={replay.waveformAvailable}
            waveformPresentation={replay.waveformPresentation}
            provenance={replay.comparison ? "Same patient · later recording" : undefined}
          />
        </div>
      </section>

      <div className={styles.reviewWorkspace}>
        <QuestionCard replay={replay} />
        <aside className={styles.responsePanel} aria-label="Your answer and feedback">
          <section aria-labelledby="replay-submission-heading">
            <p className="eyebrow">Your work</p><h2 id="replay-submission-heading">Your response</h2>
            <FriendlyRecord value={submissionSummary} />
          </section>
          <section data-tone={feedbackTone} aria-labelledby="replay-feedback-heading">
            <p className="eyebrow">How you did</p><h2 id="replay-feedback-heading"><CheckCircle2 size={18} aria-hidden="true" /> Feedback</h2>
            <FriendlyRecord value={feedbackSummary} />
          </section>
          {replay.mode !== "training" || Object.keys(answerGuideSummary).length ? (
            <section aria-labelledby="replay-guide-heading">
              <p className="eyebrow">Learn from it</p><h2 id="replay-guide-heading"><BookOpenCheck size={18} aria-hidden="true" /> Answer guide</h2>
              <FriendlyRecord value={answerGuideSummary} />
            </section>
          ) : null}
        </aside>
      </div>

      {replay.provenance.contentLabel ? <p className={styles.provenance}>{replay.provenance.contentLabel}</p> : null}
    </div>
  );
}
