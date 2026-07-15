"use client";

import { Brain, CornerDownLeft, MessageSquare, Quote, Send, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type AdaptiveTutorContextRef, type ClinicalShiftTutorContextRef, type ClinicalTutorContextRef, type TutorMessageBody } from "@/lib/api";
import type { EcgCapability, TutorMessageResponse, ViewerAction } from "@/lib/types";

type ChatTurn = {
  id: string;
  role: "user" | "tutor";
  content: string;
  socraticQuestion?: string;
  citedEvidence?: string[];
  uncertaintyWarnings?: string[];
  suggestedNextStep?: string;
  onLessonTopic?: boolean;
  guidanceMode?: "reserved" | "quota_fallback";
  deliveryNotice?: string;
};

function tutorDeliveryNotice(raw: unknown) {
  if (!raw || typeof raw !== "object") return undefined;
  const value = raw as Record<string, unknown>;
  const remote = value.remoteCall && typeof value.remoteCall === "object"
    ? value.remoteCall as { attempted?: unknown; status?: unknown }
    : null;
  if (value.schemaStatus === "fallback" || value.schemaError) {
    return "Built-in grounded guidance replaced a tutor response that did not pass validation.";
  }
  if (value.provider === "grounded-fallback" && remote?.attempted && remote.status !== "success") {
    return "Built-in grounded guidance was used because the live tutor was unavailable.";
  }
  return undefined;
}

type TutorChatProps = {
  mode: "tutorial" | "practice" | "freeform";
  /** Learner-facing role for this moment, such as Coach, Debrief, or Attending challenge. */
  roleLabel?: string;
  /** Opaque ECG capability used only for request scoping; never rendered. */
  ecgRef?: EcgCapability | null;
  /** @deprecated Compatibility alias for legacy Guided modules. */
  caseId?: EcgCapability | null;
  lessonId?: string | null;
  /** Durable thread partition within a lesson/case, such as one Guided scene. */
  threadScope?: string | null;
  /** Prompt to re-send when the learner drifts off-topic and clicks "Return to lesson". */
  lessonReturnPrompt?: string;
  /** Learner-facing label for the exact paused waypoint. */
  lessonReturnLabel?: string;
  /** Persistent scene/step breadcrumb shown above the conversation. */
  waypointLabel?: string;
  /** Restores focus to the preserved lesson interaction without another AI call. */
  onReturnToLesson?: () => void;
  /** Optional opening line shown before the first user turn. */
  openingPrompt?: string;
  /** Extra viewer context (e.g. selected point) merged into each request. */
  viewerState?: Record<string, unknown>;
  /** Server-issued reference to a durably graded Clinical answer. */
  clinicalContext?: ClinicalTutorContextRef | null;
  /** Owner-bound reference to a completed, server-graded Clinical shift. */
  clinicalShiftContext?: ClinicalShiftTutorContextRef | null;
  /** Server-issued, owner-bound reference to the current deterministic mastery plan. */
  adaptiveContext?: AdaptiveTutorContextRef | null;
  /** Called whenever a tutor reply carries viewer actions, so the page can drive the ECGViewer. */
  onViewerActions?: (actions: ViewerAction[]) => void;
  /** Records that learner-visible assistance was requested in the active assessment step. */
  onAssistance?: () => void;
  /** Resets the thread when this key changes (e.g. switching lessons/cases). */
  resetKey?: string;
  /** Keep the tutor genuinely out of the independent workspace until requested. */
  collapsedByDefault?: boolean;
};

let turnCounter = 0;
function nextTurnId() {
  turnCounter += 1;
  return `turn-${turnCounter}-${Date.now()}`;
}

export function TutorChat({
  mode,
  roleLabel,
  ecgRef,
  caseId,
  lessonId,
  threadScope,
  lessonReturnPrompt,
  lessonReturnLabel,
  waypointLabel,
  onReturnToLesson,
  openingPrompt,
  viewerState,
  clinicalContext,
  clinicalShiftContext,
  adaptiveContext,
  onViewerActions,
  onAssistance,
  resetKey,
  collapsedByDefault = false,
}: TutorChatProps) {
  const requestEcgRef = ecgRef ?? caseId ?? null;
  const [threadId, setThreadId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [restoring, setRestoring] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typed, setTyped] = useState("");
  const [returnedTutorTurnId, setReturnedTutorTurnId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(collapsedByDefault);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const onViewerActionsRef = useRef(onViewerActions);

  useEffect(() => {
    onViewerActionsRef.current = onViewerActions;
  }, [onViewerActions]);

  // Reset the conversation when the lesson/case context changes.
  useEffect(() => {
    setThreadId(null);
    setTurns([]);
    setInput("");
    setError(null);
    setTyped("");
    setReturnedTutorTurnId(null);
    setCollapsed(collapsedByDefault);
  }, [resetKey, collapsedByDefault]);

  useEffect(() => {
    let active = true;
    const hasStableContext = Boolean(requestEcgRef || lessonId || mode === "freeform");
    if (!hasStableContext) return () => { active = false; };
    // Context changes must never leave another ECG's conversation visible
    // while its own history is being loaded.
    setThreadId(null);
    setTurns([]);
    setError(null);
    setTyped("");
    setReturnedTutorTurnId(null);
    setRestoring(true);
    api.tutorThreads({ mode, lessonId, ecgRef: requestEcgRef, scopeKey: threadScope, limit: 1 })
      .then(async ({ threads }) => {
        if (!active || !threads[0]) return;
        const restored = await api.tutorThread(threads[0].threadId);
        if (!active) return;
        setThreadId(restored.threadId);
        setTurns(restored.messages.map((message, index) => ({
          id: `restored-${restored.threadId}-${index}-${message.createdAt}`,
          role: message.role,
          content: message.content,
          socraticQuestion: typeof message.meta.socraticQuestion === "string" ? message.meta.socraticQuestion : undefined,
          citedEvidence: Array.isArray(message.meta.citedEvidence) ? message.meta.citedEvidence.filter((item): item is string => typeof item === "string") : [],
          uncertaintyWarnings: Array.isArray(message.meta.uncertaintyWarnings) ? message.meta.uncertaintyWarnings.filter((item): item is string => typeof item === "string") : [],
          suggestedNextStep: typeof message.meta.suggestedNextStep === "string" ? message.meta.suggestedNextStep : undefined,
          onLessonTopic: typeof message.meta.onLessonTopic === "boolean" ? message.meta.onLessonTopic : undefined,
          guidanceMode: message.meta.remoteUsage && typeof message.meta.remoteUsage === "object"
            && "status" in message.meta.remoteUsage
            && (message.meta.remoteUsage.status === "reserved" || message.meta.remoteUsage.status === "quota_fallback")
            ? message.meta.remoteUsage.status
            : undefined,
          deliveryNotice: tutorDeliveryNotice(message.meta),
        })));
        // Reapply only the most recent grounded tutor annotation. This
        // restores the visual teaching state without replaying stale actions
        // from every prior turn.
        const latestActionMessage = [...restored.messages]
          .reverse()
          .find((message) => message.role === "tutor" && message.viewerActions.length > 0);
        if (latestActionMessage) onViewerActionsRef.current?.(latestActionMessage.viewerActions);
      })
      .catch(() => {
        // A missing history must not disable asking a new grounded question.
      })
      .finally(() => { if (active) setRestoring(false); });
    return () => { active = false; };
  }, [resetKey, mode, requestEcgRef, lessonId, threadScope]);

  const latestTutor = useMemo(() => {
    for (let i = turns.length - 1; i >= 0; i -= 1) {
      if (turns[i].role === "tutor") return turns[i];
    }
    return null;
  }, [turns]);

  // Present one stable answer. Character-by-character updates add latency,
  // repeatedly move the scroll container, and create a different experience
  // for visual and screen-reader users.
  useEffect(() => {
    setTyped(latestTutor?.content ?? "");
  }, [latestTutor?.id, latestTutor?.content]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [turns, typed]);

  const send = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || sending) return;
      setSending(true);
      setError(null);
      const userTurn: ChatTurn = { id: nextTurnId(), role: "user", content: trimmed };
      setTurns((current) => [...current, userTurn]);
      setInput("");
      try {
        const body: TutorMessageBody = {
          mode,
          threadId: threadId ?? undefined,
          caseId: requestEcgRef ?? undefined,
          lessonId: lessonId ?? undefined,
          scopeKey: threadScope ?? undefined,
          message: trimmed,
          viewerState,
          clinicalContext: clinicalContext ?? undefined,
          clinicalShiftContext: clinicalShiftContext ?? undefined,
          adaptiveContext: adaptiveContext ?? undefined,
        };
        const response: TutorMessageResponse = await api.tutorMessage(body);
        setThreadId(response.threadId);
        const tutorContent = response.tutorMessage || response.feedback || "(No tutor message returned.)";
        const tutorTurn: ChatTurn = {
          id: nextTurnId(),
          role: "tutor",
          content: tutorContent,
          socraticQuestion: response.socraticQuestion,
          citedEvidence: response.citedEvidence ?? [],
          uncertaintyWarnings: response.uncertaintyWarnings ?? [],
          suggestedNextStep: response.suggestedNextStep,
          onLessonTopic: response.onLessonTopic,
          guidanceMode: response.remoteUsage?.status,
          deliveryNotice: tutorDeliveryNotice(response),
        };
        setTurns((current) => [...current, tutorTurn]);
        // Assistance changes the evidence boundary only after the learner has
        // actually received a substantive tutor response. A failed request is
        // still an independent attempt.
        if ((response.tutorMessage || response.feedback || "").trim()) onAssistance?.();
        if (response.viewerActions?.length) {
          onViewerActions?.(response.viewerActions);
        }
      } catch {
        setInput(trimmed);
        setError("The tutor could not respond. Your question is still here—try again when you are ready.");
      } finally {
        setSending(false);
      }
    },
    [sending, mode, threadId, requestEcgRef, lessonId, threadScope, viewerState, clinicalContext, clinicalShiftContext, adaptiveContext, onViewerActions, onAssistance],
  );

  function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    void send(input);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(input);
    }
  }

  const showReturnToLesson = Boolean(lessonReturnPrompt || onReturnToLesson)
    && latestTutor?.onLessonTopic === false
    && returnedTutorTurnId !== latestTutor.id;

  function returnToLesson() {
    if (onReturnToLesson) {
      onReturnToLesson();
      setReturnedTutorTurnId(latestTutor?.id ?? null);
      return;
    }
    if (lessonReturnPrompt) void send(lessonReturnPrompt);
  }

  return (
    <section className="panel tutor-chat" aria-label="Conversational ECG tutor">
      <div className="tutor-chat-header">
        <strong><Brain size={18} aria-hidden="true" /> Conversational Tutor</strong>
        <span className="muted">{roleLabel || modeLabel(mode)}</span>
        <button className="button subtle small" type="button" aria-expanded={!collapsed} onClick={() => setCollapsed((value) => !value)}>{collapsed ? "Open tutor" : "Collapse"}</button>
      </div>

      {collapsed ? (
        <button className="tutor-collapsed-prompt" type="button" onClick={() => setCollapsed(false)}>
          <MessageSquare size={17} aria-hidden="true" /><span><strong>Tutor silent.</strong> Open only if you want help; the attempt will retain its assistance history.</span>
        </button>
      ) : <>

      {waypointLabel ? (
        <div className="tutor-waypoint" aria-label="Paused lesson waypoint">
          <span>Lesson waypoint</span>
          <strong>{waypointLabel}</strong>
        </div>
      ) : null}

      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {latestTutor?.content || ""}
      </div>

      <div className="tutor-chat-scroll" ref={scrollRef}>
        {!turns.length ? (
          <div className="tutor-chat-empty">
            <MessageSquare size={18} aria-hidden="true" />
            <p>{restoring ? "Restoring this case’s tutor conversation…" : openingPrompt || "Ask about this ECG, or describe what you see and I will guide you with grounded evidence."}</p>
          </div>
        ) : null}

        {turns.map((turn) => {
          const isLatestTutor = turn.role === "tutor" && turn.id === latestTutor?.id;
          const text = isLatestTutor ? typed : turn.content;
          return (
            <div className={`chat-bubble ${turn.role}`} key={turn.id}>
              {turn.role === "tutor" ? (
                <span className="chat-author"><Brain size={14} aria-hidden="true" /> Tutor</span>
              ) : (
                <span className="chat-author">You</span>
              )}
              <p className="chat-text">{text}</p>
              {turn.role === "tutor" && (!isLatestTutor || typed === turn.content) ? (
                <>
                  {turn.socraticQuestion ? (
                    <div className="socratic">
                      <Quote size={14} aria-hidden="true" />
                      <span>{turn.socraticQuestion}</span>
                    </div>
                  ) : null}
                  {turn.citedEvidence?.length ? (
                    <div className="cited-row">
                      {turn.citedEvidence.map((evidence, idx) => (
                        <span className="cited-chip" key={`${turn.id}-cite-${idx}`}>{evidence}</span>
                      ))}
                    </div>
                  ) : null}
                  {turn.uncertaintyWarnings?.length ? (
                    <p className="uncertainty chat-uncertainty">{turn.uncertaintyWarnings.join(" ")}</p>
                  ) : null}
                  {turn.suggestedNextStep ? <p className="chat-next muted">Next: {turn.suggestedNextStep}</p> : null}
                  {turn.guidanceMode === "quota_fallback" ? (
                    <p className="chat-next muted">Built-in grounded guidance is active; the live tutor budget has reached its current limit.</p>
                  ) : null}
                  {turn.deliveryNotice ? <p className="chat-next muted">{turn.deliveryNotice}</p> : null}
                </>
              ) : null}
            </div>
          );
        })}

        {sending ? (
          <div className="chat-bubble tutor">
            <span className="chat-author"><Brain size={14} aria-hidden="true" /> Tutor</span>
            <p className="chat-text typing-dots"><span /><span /><span /></p>
          </div>
        ) : null}
      </div>

      {showReturnToLesson ? (
        <div className="return-to-lesson">
          <button className="button warn" type="button" onClick={returnToLesson} disabled={sending}>
            <Undo2 size={16} aria-hidden="true" />
            {lessonReturnLabel || "Return to lesson"}
          </button>
          <span className="muted">Your scene, answer, and viewer state are still here.</span>
        </div>
      ) : null}

      {error ? <div className="warning tutor-chat-error">{error}</div> : null}

      <form className="tutor-chat-input" onSubmit={onSubmit}>
        <textarea
          aria-label="Message the tutor"
          aria-describedby="tutor-privacy-note"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Type a message (Enter to send, Shift+Enter for a new line)"
          rows={2}
          maxLength={4000}
        />
        <button className="button primary" type="submit" disabled={restoring || sending || !input.trim()}>
          <Send size={16} aria-hidden="true" />
          Send
        </button>
        <span className="enter-hint muted"><CornerDownLeft size={13} aria-hidden="true" /> Enter</span>
        <small id="tutor-privacy-note" className="tutor-privacy muted">
          Do not enter patient names, record numbers, dates of birth, or other identifiers.
        </small>
      </form>
      </>}
    </section>
  );
}

function modeLabel(mode: TutorChatProps["mode"]) {
  if (mode === "tutorial") return "Tutorial mode";
  if (mode === "practice") return "Practice mode";
  return "Freeform";
}
