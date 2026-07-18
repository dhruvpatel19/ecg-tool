"use client";

import {
  Activity,
  ArrowRight,
  Bookmark,
  BrainCircuit,
  CalendarDays,
  CheckCircle2,
  CircleAlert,
  Clock3,
  GraduationCap,
  MessageSquareText,
  RefreshCw,
  Sparkles,
  Stethoscope,
  TimerReset,
  TrendingUp,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { TutorChat } from "@/components/TutorChat";
import { ActivityPanel } from "@/components/my-learning/ActivityPanel";
import { CalendarPanel } from "@/components/my-learning/CalendarPanel";
import { CompetencyPanel } from "@/components/my-learning/CompetencyPanel";
import { SessionHistory } from "@/components/my-learning/SessionHistory";
import { StudyPlanPanel } from "@/components/my-learning/StudyPlanPanel";
import {
  api,
  type AdaptivePlan,
  type CompetencyCalendarProjection,
  type CompetencyObjective,
  type LearningResumeSnapshot,
  type LearningSessionSummary,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { conceptLabel } from "@/lib/coordinates";
import { competencyPracticeHref } from "@/lib/competencyRoutes";
import { learningHomeRecommendation } from "@/lib/learningHome";
import styles from "./home.module.css";

type HomePanel = "overview" | "competencies" | "activity" | "calendar" | "plan";

const panels: Array<{ id: HomePanel; label: string }> = [
  { id: "overview", label: "Home" },
  { id: "activity", label: "History" },
  { id: "competencies", label: "Progress" },
  { id: "calendar", label: "Schedule" },
  { id: "plan", label: "My plan" },
];

const modes = [
  { href: "/learn", label: "Guided learning", detail: "Build the mental model", Icon: GraduationCap },
  { href: "/train", label: "Focused practice", detail: "Strengthen one visual skill", Icon: BrainCircuit },
  { href: "/rapid", label: "Rapid practice", detail: "Rehearse complete reads", Icon: TimerReset },
  { href: "/practice", label: "Clinical cases", detail: "Apply ECGs in context", Icon: Stethoscope },
];

const SESSION_PAGE_SIZE = 10;

function appendUniqueSessions(current: LearningSessionSummary[], incoming: LearningSessionSummary[]) {
  const known = new Set(current.map((session) => session.sessionRef));
  return [...current, ...incoming.filter((session) => !known.has(session.sessionRef))];
}

function isPanel(value: string | null): value is HomePanel {
  return panels.some((panel) => panel.id === value);
}

function localDateKey(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function utcDateKey(date = new Date()) {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
}

function addDateKey(value: string, amount: number) {
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day + amount, 12));
  return utcDateKey(date);
}

function detectedTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function isDateKey(value: string | null): value is string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day;
}

function evidenceStateLabel(state: CompetencyObjective["subskills"][number]["state"]) {
  if (state === "durable") return "Retained";
  if (state === "consolidating") return "Consistent";
  if (state === "developing") return "Building";
  if (state === "acquiring") return "Getting started";
  return "Not started";
}

/**
 * Keep Luna's history with one stable evidence snapshot. The signed context is
 * intentionally short lived, while this non-authoritative scope changes only
 * when the plan inputs or destinations change.
 */
function adaptivePlanThreadScope(plan: AdaptivePlan) {
  const material = JSON.stringify({
    basis: plan.basis,
    primary: plan.primary ? {
      objectiveId: plan.primary.objectiveId,
      subskill: plan.primary.subskill,
      state: plan.primary.state,
      attempts: plan.primary.independentAttempts,
      highConfidenceWrong: plan.primary.highConfidenceWrong,
      dueState: plan.primary.dueState,
    } : null,
    priorities: plan.priorities.map((priority) => [
      priority.objectiveId,
      priority.subskill,
      priority.state,
      priority.independentAttempts,
      priority.highConfidenceWrong,
      priority.dueState,
    ]),
    stages: plan.stages.map((stage) => [
      stage.mode,
      stage.receiptConcept,
      stage.receiptSubskill,
      stage.suggestedLength,
    ]),
    guided: plan.guidedRemediation?.href ?? null,
  });
  let first = 0x811c9dc5;
  let second = 0x9e3779b9;
  for (let index = 0; index < material.length; index += 1) {
    const code = material.charCodeAt(index);
    first = Math.imul(first ^ code, 0x01000193);
    second = Math.imul(second ^ code, 0x85ebca6b);
  }
  return `adaptive-plan-v1-${(first >>> 0).toString(36)}-${(second >>> 0).toString(36)}`;
}

function HomeLoading() {
  return <div className="page"><div className={styles.pageLoading} role="status">Opening your learning dashboard…</div></div>;
}

export default function HomePage() {
  return (
    <Suspense fallback={<HomeLoading />}>
      <LearningHome />
    </Suspense>
  );
}

function LearningHome() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedPanel = searchParams.get("panel");
  const requestedDate = searchParams.get("date");
  const [panel, setPanel] = useState<HomePanel>(isPanel(requestedPanel) ? requestedPanel : "overview");
  const [activityVisited, setActivityVisited] = useState(requestedPanel === "activity");
  const [calendarVisited, setCalendarVisited] = useState(requestedPanel === "calendar");
  const [calendarDate, setCalendarDate] = useState(() => (
    isDateKey(requestedDate) ? requestedDate : localDateKey()
  ));
  const [plan, setPlan] = useState<AdaptivePlan | null>(null);
  const [resume, setResume] = useState<LearningResumeSnapshot | null>(null);
  const [objectives, setObjectives] = useState<CompetencyObjective[]>([]);
  const [sessions, setSessions] = useState<LearningSessionSummary[]>([]);
  const [savedSessions, setSavedSessions] = useState<LearningSessionSummary[]>([]);
  const [calendarProjection, setCalendarProjection] = useState<CompetencyCalendarProjection | null>(null);
  const [planLoading, setPlanLoading] = useState(true);
  const [resumeLoading, setResumeLoading] = useState(true);
  const [competenciesLoading, setCompetenciesLoading] = useState(true);
  const [sessionsLoading, setSessionsLoading] = useState(true);
  const [savedSessionsLoading, setSavedSessionsLoading] = useState(false);
  const [planFailed, setPlanFailed] = useState(false);
  const [resumeFailed, setResumeFailed] = useState(false);
  const [competenciesFailed, setCompetenciesFailed] = useState(false);
  const [sessionsFailed, setSessionsFailed] = useState(false);
  const [savedSessionsFailed, setSavedSessionsFailed] = useState(false);
  const [sessionsHasMore, setSessionsHasMore] = useState(false);
  const [sessionsNextOffset, setSessionsNextOffset] = useState<number | null>(null);
  const [savedSessionsHasMore, setSavedSessionsHasMore] = useState(false);
  const [savedSessionsNextOffset, setSavedSessionsNextOffset] = useState<number | null>(null);
  const [totalSavedItems, setTotalSavedItems] = useState(0);
  const [sessionsPaging, setSessionsPaging] = useState(false);
  const [sessionsPageError, setSessionsPageError] = useState<string | null>(null);
  const [coachOpen, setCoachOpen] = useState(false);
  const [coachDraft, setCoachDraft] = useState("");
  const [savedSessionsOnly, setSavedSessionsOnly] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const [planScheduleRequest, setPlanScheduleRequest] = useState(0);
  const coachDrawer = useRef<HTMLElement | null>(null);
  const coachReturnFocus = useRef<HTMLElement | null>(null);
  const coachClose = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const next = isPanel(requestedPanel) ? requestedPanel : "overview";
    setPanel(next);
    if (next === "activity") setActivityVisited(true);
    if (next === "calendar") {
      setCalendarVisited(true);
      if (isDateKey(requestedDate)) setCalendarDate(requestedDate);
    }
    if (requestedPanel && requestedPanel !== next) router.replace("/home", { scroll: false });
  }, [requestedDate, requestedPanel, router]);

  useEffect(() => {
    let cancelled = false;
    setPlanLoading(true);
    setResumeLoading(true);
    setCompetenciesLoading(true);
    setSessionsLoading(true);
    setPlan(null);
    setPlanFailed(false);
    setResumeFailed(false);
    setCompetenciesFailed(false);
    setSessionsFailed(false);
    setCalendarProjection(null);
    setSavedSessionsFailed(false);
    setSessionsPageError(null);
    setSessionsHasMore(false);
    setSessionsNextOffset(null);
    setSavedSessionsHasMore(false);
    setSavedSessionsNextOffset(null);

    api.adaptivePlan()
      .then((value) => { if (!cancelled) setPlan(value); })
      .catch(() => { if (!cancelled) { setPlan(null); setPlanFailed(true); } })
      .finally(() => { if (!cancelled) setPlanLoading(false); });
    api.learningResume()
      .then((value) => { if (!cancelled) setResume(value); })
      .catch(() => { if (!cancelled) { setResume(null); setResumeFailed(true); } })
      .finally(() => { if (!cancelled) setResumeLoading(false); });
    api.competencies("demo", detectedTimeZone())
      .then((value) => { if (!cancelled) { setObjectives(value.objectives); setCalendarProjection(value.calendarProjection); } })
      .catch(() => { if (!cancelled) { setObjectives([]); setCompetenciesFailed(true); } })
      .finally(() => { if (!cancelled) setCompetenciesLoading(false); });
    api.learningSessions(SESSION_PAGE_SIZE)
      .then((value) => {
        if (cancelled) return;
        setSessions(value.items);
        setSessionsHasMore(Boolean(value.hasMore));
        setSessionsNextOffset(value.nextOffset ?? null);
        setTotalSavedItems(typeof value.totalSavedItems === "number"
          ? value.totalSavedItems
          : value.items.reduce((total, session) => total + session.flaggedCount, 0));
      })
      .catch(() => { if (!cancelled) { setSessions([]); setSessionsFailed(true); } })
      .finally(() => { if (!cancelled) setSessionsLoading(false); });
    return () => { cancelled = true; };
  }, [retryKey]);

  useEffect(() => {
    if (!savedSessionsOnly) return;
    let cancelled = false;
    setSavedSessionsLoading(true);
    setSavedSessionsFailed(false);
    setSavedSessionsNextOffset(null);
    setSavedSessionsHasMore(false);
    api.learningSessions(SESSION_PAGE_SIZE, 0, true)
      .then((value) => {
        if (cancelled) return;
        const flagged = value.items.filter((session) => session.flaggedCount > 0);
        setSavedSessions(flagged);
        setSavedSessionsHasMore(Boolean(value.hasMore));
        setSavedSessionsNextOffset(value.nextOffset ?? null);
        if (typeof value.totalSavedItems === "number") setTotalSavedItems(value.totalSavedItems);
      })
      .catch(() => { if (!cancelled) { setSavedSessions([]); setSavedSessionsFailed(true); } })
      .finally(() => { if (!cancelled) setSavedSessionsLoading(false); });
    return () => { cancelled = true; };
  }, [savedSessionsOnly, retryKey]);

  useEffect(() => {
    if (coachOpen && !plan?.coachContext) setCoachOpen(false);
  }, [coachOpen, plan?.coachContext]);

  useEffect(() => {
    if (!coachOpen) return;
    coachClose.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setCoachOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(coachDrawer.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? []).filter((element) => !element.hasAttribute("hidden"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = previousOverflow;
      coachReturnFocus.current?.focus();
    };
  }, [coachOpen]);

  function choosePanel(next: HomePanel) {
    setPanel(next);
    if (next === "activity") setActivityVisited(true);
    if (next === "calendar") setCalendarVisited(true);
    router.push(
      next === "overview"
        ? "/home"
        : next === "calendar"
          ? `/home?panel=calendar&date=${encodeURIComponent(calendarDate)}`
          : `/home?panel=${next}`,
      { scroll: false },
    );
  }

  function openCalendar(date: string) {
    setCalendarDate(date);
    setPanel("calendar");
    setCalendarVisited(true);
    router.push(`/home?panel=calendar&date=${encodeURIComponent(date)}`, { scroll: false });
  }

  function schedulePlanAction() {
    if (!plan?.calendarAction) return;
    setCoachOpen(false);
    openCalendar(calendarProjection?.today ?? localDateKey());
    setPlanScheduleRequest((value) => value + 1);
  }

  function selectCalendarDate(date: string) {
    setCalendarDate(date);
    router.replace(`/home?panel=calendar&date=${encodeURIComponent(date)}`, { scroll: false });
  }

  function openCoach(draft = "") {
    coachReturnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setCoachDraft(draft);
    setCoachOpen(true);
  }

  async function refreshCoachContext(draft: string) {
    setCoachDraft(draft);
    setPlanLoading(true);
    setPlanFailed(false);
    try {
      setPlan(await api.adaptivePlan());
    } catch {
      setPlan(null);
      setPlanFailed(true);
    } finally {
      setPlanLoading(false);
    }
  }

  async function loadMoreSessionHistory() {
    if (sessionsPaging) return;
    const saved = savedSessionsOnly;
    const offset = saved ? savedSessionsNextOffset : sessionsNextOffset;
    if (offset === null) return;
    setSessionsPaging(true);
    setSessionsPageError(null);
    try {
      const value = await api.learningSessions(SESSION_PAGE_SIZE, offset, saved);
      if (saved) {
        setSavedSessions((current) => appendUniqueSessions(
          current,
          value.items.filter((session) => session.flaggedCount > 0),
        ));
        setSavedSessionsHasMore(Boolean(value.hasMore));
        setSavedSessionsNextOffset(value.nextOffset ?? null);
      } else {
        setSessions((current) => appendUniqueSessions(current, value.items));
        setSessionsHasMore(Boolean(value.hasMore));
        setSessionsNextOffset(value.nextOffset ?? null);
      }
      if (typeof value.totalSavedItems === "number") setTotalSavedItems(value.totalSavedItems);
    } catch {
      setSessionsPageError(saved
        ? "More saved outcomes could not be loaded. Your saved list is unchanged."
        : "Earlier completed sessions could not be loaded. The sessions already shown remain available.");
    } finally {
      setSessionsPaging(false);
    }
  }

  const allCells = useMemo(
    () => objectives.flatMap((objective) => objective.subskills.map((cell) => ({ objective, cell }))),
    [objectives],
  );
  const checkedSkills = useMemo(
    () => allCells.filter(({ cell }) => cell.independentAttempts > 0),
    [allCells],
  );
  const holdingSkills = useMemo(
    () => checkedSkills.filter(({ cell }) => cell.state === "durable" && !cell.isDue),
    [checkedSkills],
  );
  const dueSkills = useMemo(
    () => checkedSkills.filter(({ cell }) => cell.isDue),
    [checkedSkills],
  );
  const fallbackStrengthen = useMemo(() => {
    const seenObjectives = new Set<string>();
    return allCells
      .map(({ objective, cell }) => ({ objective, cell, href: competencyPracticeHref(cell.independentReceipt) }))
      .filter(({ cell, href }) => Boolean(href) && (
        cell.isDue
        || (cell.state !== "durable" && (
          cell.highConfidenceWrong > 0
          || (cell.independentAttempts > 0 && cell.independentMastery < 0.7)
        ))
      ))
      .sort((left, right) => (
        Number(right.cell.isDue) - Number(left.cell.isDue)
        || right.cell.overdueDays - left.cell.overdueDays
        || right.cell.highConfidenceWrong - left.cell.highConfidenceWrong
        || left.cell.independentMastery - right.cell.independentMastery
      ))
      .filter(({ objective }) => {
        if (seenObjectives.has(objective.objectiveId)) return false;
        seenObjectives.add(objective.objectiveId);
        return true;
      })
      .slice(0, 3);
  }, [allCells]);
  const strengthen = useMemo(() => {
    if (!plan || planFailed) return fallbackStrengthen;
    const cells = new Map(allCells.map(({ objective, cell }) => [`${objective.objectiveId}:${cell.subskill}`, { objective, cell }]));
    const seenObjectives = new Set<string>();
    return plan.priorities
      .map((priority) => {
        const match = cells.get(`${priority.objectiveId}:${priority.subskill}`);
        if (!match) return null;
        const href = competencyPracticeHref(match.cell.independentReceipt);
        if (!href || seenObjectives.has(match.objective.objectiveId)) return null;
        seenObjectives.add(match.objective.objectiveId);
        return { ...match, href };
      })
      .filter((value): value is NonNullable<typeof value> => Boolean(value))
      .slice(0, 3);
  }, [allCells, fallbackStrengthen, plan, planFailed]);

  const recommendation = learningHomeRecommendation(plan, resume, { planLoading, resumeLoading, planFailed });
  const coachThreadScope = useMemo(() => plan ? adaptivePlanThreadScope(plan) : null, [plan]);
  const warning = [
    resumeFailed ? "We could not check for unfinished sessions." : null,
    planFailed ? "Your tailored next step is temporarily unavailable." : null,
    competenciesFailed ? "Your progress details are temporarily unavailable." : null,
    sessionsFailed ? "Your completed sessions are temporarily unavailable." : null,
    savedSessionsFailed ? "Your saved items are temporarily unavailable." : null,
  ].filter(Boolean).join(" ");

  const firstName = (user?.displayName || user?.username || "there").trim().split(/\s+/)[0];
  const overdueCount = allCells.filter(({ cell }) => cell.dueState === "overdue" && cell.independentAttempts > 0).length;
  const calendarReviewCounts = new Map((calendarProjection?.reviewDays ?? []).map((day) => [day.date, day.total]));
  const calendarToday = calendarProjection?.today ?? localDateKey();
  const dueByDay = Array.from({ length: 7 }, (_, offset) => {
    const key = addDateKey(calendarToday, offset);
    const date = new Date(`${key}T12:00:00Z`);
    return {
      key,
      label: offset === 0 ? "Today" : new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" }).format(date),
      date: new Intl.DateTimeFormat(undefined, { day: "numeric", timeZone: "UTC" }).format(date),
      count: calendarReviewCounts.get(key) ?? 0,
    };
  });
  const upcomingReviewDays = dueByDay.filter((day) => day.count > 0);
  const upcomingReviewCount = upcomingReviewDays.reduce((total, day) => total + day.count, 0);
  const coachLead = planLoading
    ? "I’m reviewing your recent practice so I can point you to the right next step."
    : recommendation.kind === "resume"
      ? `You have an unfinished session: ${recommendation.title}. Finish it first, then we can plan what comes next.`
      : plan?.basis.baselineNeeded
        ? "Start with a short 5-ECG check so I can tailor your plan."
        : plan?.primary
          ? `${plan.primary.label} is the clearest place to focus next. I can explain why or help fit it into your week.`
          : "Ask me what to study, how to plan your week, or how two ECG ideas connect.";
  const coachUnavailable = planLoading
    ? "Luna is reviewing your latest plan."
    : planFailed
      ? "Luna is reconnecting to your latest plan."
      : !plan?.coachContext
        ? "Luna is temporarily unavailable; your practice and saved progress remain available."
        : null;

  return (
    <div className={`page ${styles.page}`}>
      <header className={styles.header}>
        <div>
          <h1>Welcome back, {firstName}.</h1>
          <p>Here’s the best place to start today.</p>
        </div>
        {panel !== "overview" ? (
          <button
            className={styles.coachShortcut}
            type="button"
            disabled={!plan?.coachContext}
            aria-describedby={coachUnavailable ? "coach-availability" : undefined}
            onClick={() => openCoach()}
          >
            <Sparkles size={16} aria-hidden="true" /> Plan with Luna
          </button>
        ) : null}
      </header>
      {coachUnavailable ? <p className="sr-only" id="coach-availability">{coachUnavailable}</p> : null}

      <div className={styles.tabs} role="tablist" aria-label="Learning dashboard sections">
        {panels.map((item) => (
          <button
            type="button"
            id={`home-tab-${item.id}`}
            key={item.id}
            role="tab"
            aria-label={item.id === "calendar" && dueSkills.length > 0 ? `${item.label}, review ready` : item.label}
            aria-selected={panel === item.id}
            aria-controls={`home-panel-${item.id}`}
            tabIndex={panel === item.id ? 0 : -1}
            onClick={() => choosePanel(item.id)}
            onKeyDown={(event) => {
              const current = panels.findIndex((candidate) => candidate.id === item.id);
              let next = current;
              if (event.key === "ArrowRight") next = (current + 1) % panels.length;
              else if (event.key === "ArrowLeft") next = (current - 1 + panels.length) % panels.length;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = panels.length - 1;
              else return;
              event.preventDefault();
              choosePanel(panels[next].id);
              requestAnimationFrame(() => document.getElementById(`home-tab-${panels[next].id}`)?.focus());
            }}
          >
            {item.label}
            {item.id === "calendar" && dueSkills.length > 0 ? <span className={styles.tabDot} aria-hidden="true" /> : null}
          </button>
        ))}
      </div>

      {warning ? (
        <div className={styles.warning} role="status" aria-live="polite">
          <span><CircleAlert size={17} aria-hidden="true" /> {warning} Everything that did load remains available.</span>
          <button type="button" onClick={() => setRetryKey((value) => value + 1)}><RefreshCw size={15} aria-hidden="true" /> Retry</button>
        </div>
      ) : null}

      <div id="home-panel-overview" role="tabpanel" aria-labelledby="home-tab-overview" className={styles.overview} hidden={panel !== "overview"}>
          <section className={styles.lunaHero} aria-labelledby="next-best-step">
            <div className={styles.lunaRecommendation}>
              <div className={styles.lunaIdentity}>
                <span aria-hidden="true"><Sparkles size={22} /></span>
                <div><strong>Luna</strong><small>Your study coach</small></div>
              </div>
              <p className={styles.heroEyebrow}>{recommendation.eyebrow}</p>
              <h2 id="next-best-step">{recommendation.title}</h2>
              <p className={styles.heroDetail}>{recommendation.detail}</p>
              <div className={styles.heroAction}>
                {recommendation.href ? (
                  <Link className="button primary" href={recommendation.href}>{recommendation.cta} <ArrowRight size={16} aria-hidden="true" /></Link>
                ) : (
                  <button className="button primary" type="button" disabled>{recommendation.cta}</button>
                )}
                {plan?.calendarAction && recommendation.kind !== "resume" && recommendation.kind !== "general" ? (
                  <button className="button subtle" type="button" onClick={schedulePlanAction}>
                    <CalendarDays size={15} aria-hidden="true" /> {plan.calendarAction.relationship === "follow_up" ? "Add follow-up to my week" : "Add to my week"}
                  </button>
                ) : null}
              </div>
              {recommendation.reason ? (
                <details className={styles.why}>
                  <summary>Why this next?</summary>
                  <p>{recommendation.reason}</p>
                </details>
              ) : null}
              {recommendation.after ? (
                <Link className={styles.after} href={recommendation.after.href}>
                  <span>Up next</span><strong>{recommendation.after.title}</strong><ArrowRight size={14} aria-hidden="true" />
                </Link>
              ) : null}
            </div>

            <aside className={styles.lunaConversation} aria-labelledby="luna-conversation-heading">
              <p className={styles.coachKicker}>Plan with Luna</p>
              <h3 id="luna-conversation-heading">Talk through your next step</h3>
              <p>{coachLead}</p>
              <div className={styles.coachPrompts} aria-label="Questions to ask Luna">
                <button type="button" disabled={!plan?.coachContext} onClick={() => openCoach(recommendation.kind === "resume" ? "What should I do after I finish this session?" : "Why is this my next step?")}>{recommendation.kind === "resume" ? "What should I do after this?" : "Why this next?"}</button>
                <button type="button" disabled={!plan?.coachContext} onClick={() => openCoach("How should I practice this skill?")}>How should I practice this?</button>
              </div>
              <button className={styles.askCoach} type="button" disabled={!plan?.coachContext} onClick={() => openCoach()}>
                <MessageSquareText size={17} aria-hidden="true" /> <span>Ask Luna about your plan</span> <ArrowRight size={16} aria-hidden="true" />
              </button>
              {coachUnavailable ? <p className={styles.coachUnavailable} role="status">{coachUnavailable}</p> : null}
              <small>Chat helps you plan and reflect. Your progress updates after completed practice.</small>
            </aside>
          </section>

          <section className={styles.metrics} aria-label="Learning progress summary">
            <article>
              <span className={styles.metricIcon} data-tone="checked"><CheckCircle2 size={18} aria-hidden="true" /></span>
              <div><span>Skills tested</span><strong>{competenciesLoading ? "…" : competenciesFailed ? "—" : checkedSkills.length}</strong><small>with scored ECG checks</small></div>
            </article>
            <article>
              <span className={styles.metricIcon} data-tone="holding"><TrendingUp size={18} aria-hidden="true" /></span>
              <div><span>Staying strong</span><strong>{competenciesLoading ? "…" : competenciesFailed ? "—" : holdingSkills.length}</strong><small>still strong on later checks</small></div>
            </article>
            <article>
              <span className={styles.metricIcon} data-tone="due"><Clock3 size={18} aria-hidden="true" /></span>
              <div><span>Ready to review</span><strong>{competenciesLoading ? "…" : competenciesFailed ? "—" : dueSkills.length}</strong><small>{competenciesFailed ? "timing unavailable" : overdueCount ? `${overdueCount} need${overdueCount === 1 ? "s" : ""} attention` : "nothing overdue"}</small></div>
            </article>
          </section>

          <div className={styles.dashboardGrid}>
            <section className={`${styles.card} ${styles.recentCard}`} aria-labelledby="recent-practice-heading">
              <div className={styles.cardHeading}>
                <div><p className="eyebrow">Recent work</p><h2 id="recent-practice-heading">Your latest practice</h2></div>
                <button type="button" onClick={() => choosePanel("activity")}>Open history <ArrowRight size={14} aria-hidden="true" /></button>
              </div>
              <SessionHistory items={sessions.slice(0, 2)} loading={sessionsLoading} failed={sessionsFailed} compact />
            </section>

            <section className={`${styles.card} ${styles.skillsCard}`} aria-labelledby="skills-strengthen-heading">
              <div className={styles.cardHeading}>
                <div><p className="eyebrow">Practice next</p><h2 id="skills-strengthen-heading">Skills to revisit</h2></div>
                <button type="button" onClick={() => choosePanel("competencies")}>View progress <ArrowRight size={14} aria-hidden="true" /></button>
              </div>
              {competenciesLoading ? <div className={styles.cardLoading} role="status">Finding the most useful skills to practice…</div> : competenciesFailed ? (
                <div className={styles.cardEmpty} role="status"><CircleAlert size={20} aria-hidden="true" /><span><strong>Your practice suggestions could not load.</strong><small>Nothing has been changed. Try again to restore this list.</small></span></div>
              ) : plan?.basis.baselineNeeded ? (
                <div className={styles.cardEmpty}>
                  <Sparkles size={20} aria-hidden="true" />
                  <span>
                    <strong>Your starting check comes first.</strong>
                    <small>Finish the 5-ECG check and Luna will show which skills are most useful to revisit here.</small>
                  </span>
                </div>
              ) : strengthen.length ? (
                <div className={styles.skillList}>
                  {strengthen.map(({ objective, cell, href }) => (
                    <article key={`${objective.objectiveId}:${cell.subskill}`}>
                      <span className={styles.skillStatus} data-state={cell.isDue ? "due" : cell.highConfidenceWrong ? "attention" : "building"} aria-hidden="true" />
                      <div><strong>{conceptLabel(objective.objectiveId)}</strong><small>{cell.subskill.replaceAll("_", " ")} · {cell.isDue ? cell.dueState === "overdue" ? "review soon" : "ready now" : cell.highConfidenceWrong ? "double-check" : "building"}</small></div>
                      {cell.independentAttempts ? <span>{evidenceStateLabel(cell.state)}<small>{cell.independentAttempts} scored check{cell.independentAttempts === 1 ? "" : "s"}</small></span> : <span>Not started<small>no scored check</small></span>}
                      <Link href={href!} aria-label={`Practice ${conceptLabel(objective.objectiveId)}: ${cell.subskill.replaceAll("_", " ")}`}><ArrowRight size={15} aria-hidden="true" /></Link>
                    </article>
                  ))}
                </div>
              ) : (
                <div className={styles.cardEmpty}><CheckCircle2 size={20} aria-hidden="true" /><span><strong>No suggested skill check right now.</strong><small>Complete a mixed ECG set whenever you’re ready for a new recommendation.</small></span></div>
              )}
            </section>
          </div>

          <section className={styles.week} aria-labelledby="review-schedule-heading">
            <div className={styles.weekIntro}>
              <span><CalendarDays size={18} aria-hidden="true" /></span>
              <div><p className="eyebrow">Schedule</p><h2 id="review-schedule-heading">Coming up this week</h2><p>Suggested reviews are spaced from your practice. Miss a day? Just pick up when you can.</p></div>
            </div>
            {competenciesLoading ? (
              <div className={styles.weekStatus} role="status">Loading your week…</div>
            ) : competenciesFailed || !calendarProjection ? (
              <div className={styles.weekStatus} role="status"><CircleAlert size={17} aria-hidden="true" /> Your suggested reviews could not load. Nothing has been guessed.</div>
            ) : upcomingReviewDays.length ? (
              <div className={styles.weekAgenda} aria-label={`${upcomingReviewCount} suggested review${upcomingReviewCount === 1 ? "" : "s"} this week`}>
                {upcomingReviewDays.slice(0, 3).map((day) => (
                  <button type="button" key={day.key} onClick={() => openCalendar(day.key)}>
                    <span><strong>{day.label}</strong><small>{day.date}</small></span>
                    <span>{day.count} suggested review{day.count === 1 ? "" : "s"}<ArrowRight size={15} aria-hidden="true" /></span>
                  </button>
                ))}
                {upcomingReviewDays.length > 3 ? <small>Plus {upcomingReviewDays.length - 3} more review day{upcomingReviewDays.length - 3 === 1 ? "" : "s"} in your schedule.</small> : null}
              </div>
            ) : (
              <div className={styles.weekEmpty}>
                <CheckCircle2 size={20} aria-hidden="true" />
                <span><strong>No suggested reviews this week</strong><small>You can still add study time or start a mixed ECG set whenever you’re ready.</small></span>
              </div>
            )}
            <button type="button" onClick={() => openCalendar(calendarProjection?.today ?? localDateKey())}>Open schedule <ArrowRight size={15} aria-hidden="true" /></button>
          </section>

          <details className={styles.modeDisclosure}>
            <summary><span><Activity size={17} aria-hidden="true" /> Practice another way</span><small>Choose the kind of practice that fits your goal.</small></summary>
            <div className={styles.modeGrid}>
              {modes.map(({ href, label, detail, Icon }) => (
                <Link href={href} key={href}><span><Icon size={18} aria-hidden="true" /></span><div><strong>{label}</strong><small>{detail}</small></div><ArrowRight size={15} aria-hidden="true" /></Link>
              ))}
            </div>
          </details>
      </div>

      <div id="home-panel-activity" role="tabpanel" aria-labelledby="home-tab-activity" className={styles.panelSurface} hidden={panel !== "activity"}>
          <header className={styles.panelHeader}><div><p className="eyebrow">History</p><h2>Your learning history</h2><p>Review past sessions and reopen questions or ECGs you saved.</p></div></header>
          <section className={styles.sessionSection} aria-labelledby="completed-sessions-heading">
            <div className={styles.sessionHeading}>
              <div><p className="eyebrow">Sessions</p><h3 id="completed-sessions-heading">Your sessions</h3></div>
              <div className={styles.sessionActions}>
                <p>See your results and reopen saved ECGs.</p>
                <button type="button" aria-pressed={savedSessionsOnly} onClick={() => setSavedSessionsOnly((value) => !value)}>
                  <Bookmark size={14} aria-hidden="true" /> {savedSessionsOnly ? "Show all sessions" : `Saved items (${totalSavedItems})`}
                </button>
              </div>
            </div>
            <SessionHistory
              items={savedSessionsOnly ? savedSessions : sessions}
              loading={savedSessionsOnly ? savedSessionsLoading : sessionsLoading}
              failed={savedSessionsOnly ? savedSessionsFailed : sessionsFailed}
              emptyState={savedSessionsOnly ? "saved" : "sessions"}
              emptyAction={!savedSessionsOnly && recommendation.href ? { href: recommendation.href, label: recommendation.cta } : undefined}
            />
            {sessionsPageError ? <p className={styles.sessionPageError} role="alert">{sessionsPageError}</p> : null}
            {(savedSessionsOnly ? savedSessionsHasMore : sessionsHasMore) ? (
              <button className={styles.loadSessions} type="button" disabled={sessionsPaging} onClick={() => void loadMoreSessionHistory()}>
                {sessionsPaging ? "Loading…" : savedSessionsOnly ? "Load more saved sessions" : "Load earlier sessions"}
              </button>
            ) : null}
            <div className={styles.historyDivider} aria-hidden="true" />
            {activityVisited ? <ActivityPanel competencyObjectives={competenciesFailed ? undefined : objectives} /> : null}
          </section>
      </div>

      <div id="home-panel-competencies" role="tabpanel" aria-labelledby="home-tab-competencies" className={styles.panelSurface} hidden={panel !== "competencies"}>
          <CompetencyPanel objectives={objectives} loading={competenciesLoading} failed={competenciesFailed} onRetry={() => setRetryKey((value) => value + 1)} />
      </div>

      <div id="home-panel-calendar" role="tabpanel" aria-labelledby="home-tab-calendar" className={styles.panelSurface} hidden={panel !== "calendar"}>
          {calendarVisited ? <CalendarPanel selectedDate={calendarDate} onSelectedDateChange={selectCalendarDate} planAction={plan?.calendarAction ?? null} planScheduleRequest={planScheduleRequest} /> : null}
      </div>

      <div id="home-panel-plan" role="tabpanel" aria-labelledby="home-tab-plan" className={styles.panelSurface} hidden={panel !== "plan"}>
          <StudyPlanPanel plan={plan} loading={planLoading || resumeLoading} failed={planFailed} recommendation={recommendation} onRetry={() => setRetryKey((value) => value + 1)} onOpenCoach={openCoach} onSchedulePlan={schedulePlanAction} />
      </div>

      {coachOpen && plan?.coachContext ? (
        <div className={styles.coachBackdrop} onMouseDown={(event) => { if (event.target === event.currentTarget) setCoachOpen(false); }}>
          <aside ref={coachDrawer} className={styles.coachDrawer} role="dialog" aria-modal="true" aria-labelledby="learning-coach-title" aria-describedby="learning-coach-description">
            <header>
              <div><p className="eyebrow">Your study coach</p><h2 id="learning-coach-title">Plan with Luna</h2><p id="learning-coach-description">Ask what to study, plan your week, or talk through a difficult ECG skill.</p></div>
              <button ref={coachClose} type="button" aria-label="Close Luna" onClick={() => setCoachOpen(false)}><X size={20} aria-hidden="true" /></button>
            </header>
            <TutorChat
              mode="freeform"
              roleLabel="Luna"
              lessonId="adaptive-mastery-plan"
              threadScope={coachThreadScope}
              openingPrompt="Ask why this comes first, how to practice it, or how your recent work connects to the next ECG skill."
              viewerState={{ activity: "adaptive_mastery_plan", surface: "learning-home" }}
              adaptiveContext={plan.coachContext}
              resetKey={plan.coachContext.contextId}
              draftPrompt={coachDraft}
              onAdaptiveContextExpired={(draft) => void refreshCoachContext(draft)}
            />
            {plan.calendarAction ? (
              <div className={styles.coachHandoff}>
                <div>
                  <strong>{recommendation.kind === "resume" ? "Add the follow-up to your week" : "Add this step to your week"}</strong>
                  <small>Choose a date and review it before anything is saved.</small>
                </div>
                <button className="button subtle" type="button" onClick={schedulePlanAction}>
                  <CalendarDays size={16} aria-hidden="true" /> Choose a time
                </button>
              </div>
            ) : null}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
