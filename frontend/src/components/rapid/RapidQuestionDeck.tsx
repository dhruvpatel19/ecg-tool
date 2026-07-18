"use client";

import { ArrowLeft, ArrowRight, Check, Crosshair, Send } from "lucide-react";
import { competencySkillLabel } from "@/lib/learning/skillLabels";
import type { RapidTaskPrompt } from "@/lib/types";

export type RapidTaskResponse = string | string[] | Record<string, string>;

type Props = {
  tasks: RapidTaskPrompt[];
  responses: Record<string, RapidTaskResponse>;
  activeIndex: number;
  onActiveIndexChange: (index: number) => void;
  onResponse: (taskId: string, response: RapidTaskResponse) => void;
  onSubmit: () => void;
  traceComplete?: boolean;
  disabled?: boolean;
  submitting?: boolean;
};

const FULL_READ_FIELDS = [
  ["rate", "Rate", "e.g. 78 bpm"],
  ["rhythm", "Rhythm", "Name rhythm and regularity"],
  ["conduction", "Conduction / intervals", "Only the relevant abnormality, or normal"],
  ["stT", "ST–T / ischemia", "Key repolarization finding and distribution"],
  ["impression", "Impression", "One concise, prioritized interpretation"],
] as const;

export function rapidTaskAnswered(
  task: RapidTaskPrompt,
  response: RapidTaskResponse | undefined,
  traceComplete = false,
) {
  if (["trace_point", "point_localization", "trace_region"].includes(task.type)) return traceComplete;
  if (Array.isArray(response)) return response.length > 0;
  if (typeof response === "string") return response.trim().length > 0;
  if (response && typeof response === "object") {
    if (task.type === "full_interpretation") {
      return String(response.impression ?? "").trim().length >= 3;
    }
    return Object.values(response).some((value) => value.trim().length > 0);
  }
  return false;
}

function ResponseControl({
  task,
  response,
  onResponse,
  traceComplete,
  disabled,
}: {
  task: RapidTaskPrompt;
  response: RapidTaskResponse | undefined;
  onResponse: (response: RapidTaskResponse) => void;
  traceComplete: boolean;
  disabled: boolean;
}) {
  if (task.type === "single_choice") {
    return (
      <div className="rapid-task-options" role="radiogroup" aria-label={task.prompt}>
        {(task.options ?? []).map((option, index) => {
          const selected = response === option.id;
          return (
            <button
              className={selected ? "selected" : ""}
              key={option.id}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={disabled}
              onClick={() => onResponse(option.id)}
            >
              <span>{String.fromCharCode(65 + index)}</span>
              <strong>{option.label}</strong>
              {selected ? <Check size={16} aria-hidden="true" /> : null}
            </button>
          );
        })}
      </div>
    );
  }

  if (task.type === "multiple_choice") {
    const selected = Array.isArray(response) ? response : [];
    return (
      <div className="rapid-task-options rapid-task-options-multiple" aria-label={task.prompt}>
        {(task.options ?? []).map((option) => {
          const checked = selected.includes(option.id);
          return (
            <label className={checked ? "selected" : ""} key={option.id}>
              <input
                type="checkbox"
                checked={checked}
                disabled={disabled}
                onChange={() => onResponse(checked
                  ? selected.filter((value) => value !== option.id)
                  : [...selected, option.id])}
              />
              <span>{option.label}</span>
            </label>
          );
        })}
      </div>
    );
  }

  if (["trace_point", "point_localization", "trace_region"].includes(task.type)) {
    return (
      <div className={`rapid-trace-task-status${traceComplete ? " complete" : ""}`} role="status">
        <Crosshair size={19} aria-hidden="true" />
        <div>
          <strong>{traceComplete ? "Trace selection captured" : "Use the active trace tool"}</strong>
          <span>{traceComplete ? "You can adjust it before submitting." : "Make the requested selection directly on the ECG."}</span>
        </div>
      </div>
    );
  }

  if (task.type === "full_interpretation") {
    const values = response && !Array.isArray(response) && typeof response === "object" ? response : {};
    return (
      <div className="rapid-full-read">
        {FULL_READ_FIELDS.map(([key, label, placeholder]) => (
          <label className={key === "impression" ? "rapid-full-read-impression" : ""} key={key}>
            <span>{label}</span>
            <input
              value={values[key] ?? ""}
              disabled={disabled}
              placeholder={placeholder}
              onChange={(event) => onResponse({ ...values, [key]: event.target.value })}
            />
          </label>
        ))}
        <p>Prioritize what matters. Supporting fields are available, but only the impression is required.</p>
      </div>
    );
  }

  const textValue = typeof response === "string" ? response : "";
  const numeric = task.type === "numeric" || task.type === "numeric_fill_in";
  return (
    <label className="rapid-task-entry">
      <span>{numeric ? task.responseLabel || "Your measurement" : "Your answer"}</span>
      <div>
        <input
          type={numeric ? "number" : "text"}
          inputMode={numeric ? "decimal" : undefined}
          min={numeric ? task.minValue ?? undefined : undefined}
          max={numeric ? task.maxValue ?? undefined : undefined}
          step={numeric ? task.step ?? "any" : undefined}
          autoComplete="off"
          value={textValue}
          disabled={disabled}
          placeholder={task.placeholder ?? (numeric ? "Enter a value" : "Use a concise clinical phrase")}
          onChange={(event) => onResponse(event.target.value)}
        />
        {task.unit ? <span>{task.unit}</span> : null}
      </div>
    </label>
  );
}

export function RapidQuestionDeck({
  tasks,
  responses,
  activeIndex,
  onActiveIndexChange,
  onResponse,
  onSubmit,
  traceComplete = false,
  disabled = false,
  submitting = false,
}: Props) {
  const safeIndex = Math.min(Math.max(activeIndex, 0), Math.max(tasks.length - 1, 0));
  const task = tasks[safeIndex];
  if (!task) return null;
  const answered = tasks.map((item) => rapidTaskAnswered(item, responses[item.id], traceComplete));
  const allRequiredAnswered = tasks.every((item, index) => item.required === false || answered[index]);
  const finalTask = safeIndex === tasks.length - 1;

  return (
    <section className="rapid-task-deck" aria-labelledby="rapid-task-title">
      <header className="rapid-task-deck-header">
        <div>
          <p>Question {safeIndex + 1} of {tasks.length}</p>
          <div className="rapid-task-progress" aria-label={`${answered.filter(Boolean).length} of ${tasks.length} answered`}>
            {tasks.map((item, index) => (
              <button
                key={item.id}
                type="button"
                className={`${index === safeIndex ? "active" : ""}${answered[index] ? " answered" : ""}`}
                aria-label={`Open question ${index + 1}${answered[index] ? ", answered" : ""}`}
                aria-current={index === safeIndex ? "step" : undefined}
                onClick={() => onActiveIndexChange(index)}
              />
            ))}
          </div>
        </div>
      </header>

      <div className="rapid-task-prompt">
        {task.skillId || task.subskill ? <p>{competencySkillLabel(task.skillId || task.subskill)}</p> : null}
        <h2 id="rapid-task-title">{task.prompt}</h2>
      </div>

      <ResponseControl
        task={task}
        response={responses[task.id]}
        onResponse={(response) => onResponse(task.id, response)}
        traceComplete={traceComplete}
        disabled={disabled}
      />

      <footer className="rapid-task-actions">
        <button
          className="button subtle"
          type="button"
          disabled={disabled || safeIndex === 0}
          onClick={() => onActiveIndexChange(safeIndex - 1)}
        >
          <ArrowLeft size={15} aria-hidden="true" /> Previous
        </button>
        {finalTask ? (
          <button
            className="button primary"
            type="button"
            disabled={disabled || submitting || !allRequiredAnswered}
            onClick={onSubmit}
          >
            <Send size={15} aria-hidden="true" /> {submitting ? "Checking…" : "Submit answers"}
          </button>
        ) : (
          <button
            className="button primary"
            type="button"
            disabled={disabled || (task.required !== false && !answered[safeIndex])}
            onClick={() => onActiveIndexChange(safeIndex + 1)}
          >
            Next <ArrowRight size={15} aria-hidden="true" />
          </button>
        )}
      </footer>
    </section>
  );
}
