"use client";

import {
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  ExternalLink,
  Pencil,
  Plus,
  RefreshCw,
  RotateCcw,
  Settings2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  type AdaptiveCalendarAction,
  type StudyCalendarItem,
  type StudyCalendarMode,
  type StudyCalendarReviewItem,
  type StudyCalendarSnapshot,
} from "@/lib/api";
import { competencySkillLabel as subskillLabel } from "@/lib/learning/skillLabels";
import styles from "./CalendarPanel.module.css";

type CalendarPanelProps = {
  selectedDate?: string;
  onSelectedDateChange?: (date: string) => void;
  planAction?: AdaptiveCalendarAction | null;
  planScheduleRequest?: number;
};

type EditorState = {
  kind: "new" | "edit" | "plan";
  item: StudyCalendarItem | null;
  planAction: AdaptiveCalendarAction | null;
  title: string;
  notes: string;
  scheduledDate: string;
  startTime: string;
  durationMinutes: string;
  mode: StudyCalendarMode | "";
};

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const DEFAULT_DURATION = "30";

function isDateKey(value: string | undefined) {
  if (!value || !DATE_PATTERN.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  return parsed.getUTCFullYear() === year && parsed.getUTCMonth() === month - 1 && parsed.getUTCDate() === day;
}

function dateFromKey(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
}

function dateKey(value: Date) {
  return `${value.getUTCFullYear()}-${String(value.getUTCMonth() + 1).padStart(2, "0")}-${String(value.getUTCDate()).padStart(2, "0")}`;
}

function addDays(value: string, amount: number) {
  const date = dateFromKey(value);
  date.setUTCDate(date.getUTCDate() + amount);
  return dateKey(date);
}

function addMonths(monthKey: string, amount: number) {
  const [year, month] = monthKey.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1 + amount, 1, 12));
  return dateKey(date).slice(0, 7);
}

function moveDateByMonth(value: string, amount: number) {
  const nextMonth = addMonths(value.slice(0, 7), amount);
  const [year, month] = nextMonth.split("-").map(Number);
  const finalDay = new Date(Date.UTC(year, month, 0, 12)).getUTCDate();
  return `${nextMonth}-${String(Math.min(Number(value.slice(8, 10)), finalDay)).padStart(2, "0")}`;
}

function todayInTimeZone(timeZone: string) {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${value.year}-${value.month}-${value.day}`;
  } catch {
    return dateKey(new Date());
  }
}

function detectedTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function validTimeZone(value: string) {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: value }).format();
    return true;
  } catch {
    return false;
  }
}

function timeZoneLabel(value: string) {
  try {
    const city = value === "UTC" ? "UTC" : (value.split("/").at(-1) ?? value).replaceAll("_", " ");
    const zoneName = new Intl.DateTimeFormat(undefined, { timeZone: value, timeZoneName: "short" })
      .formatToParts(new Date())
      .find((part) => part.type === "timeZoneName")?.value;
    return zoneName && zoneName !== city ? `${city} (${zoneName})` : city;
  } catch {
    return value.replaceAll("_", " ");
  }
}

function monthRange(monthKey: string, weekStartsOn: 0 | 1) {
  const first = dateFromKey(`${monthKey}-01`);
  const offset = (first.getUTCDay() - weekStartsOn + 7) % 7;
  first.setUTCDate(first.getUTCDate() - offset);
  const days = Array.from({ length: 42 }, (_, index) => addDays(dateKey(first), index));
  return { days, startDate: days[0], endDate: days.at(-1)! };
}

function fullDateLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(dateFromKey(value));
}

function monthLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(dateFromKey(`${value}-01`));
}

function shortDayLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(dateFromKey(value));
}

function startMinuteToInput(value: number | null) {
  if (value === null) return "";
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

function inputToStartMinute(value: string) {
  if (!value) return null;
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}

function timeLabel(value: number | null) {
  if (value === null) return "Any time";
  const date = new Date(Date.UTC(2000, 0, 1, Math.floor(value / 60), value % 60));
  return new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit", timeZone: "UTC" }).format(date);
}

function modeLabel(value: StudyCalendarMode) {
  if (value === "guided") return "Guided learning";
  if (value === "train") return "Focused practice";
  if (value === "rapid") return "Rapid practice";
  return "Clinical cases";
}

function clientRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `calendar-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function mutationErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.status === 409) {
    return "That calendar item changed in another tab. The latest calendar has been reloaded; review it before trying again.";
  }
  if (error instanceof ApiError && error.status === 404) {
    return "That calendar item is no longer available. The latest calendar has been reloaded.";
  }
  return fallback;
}

function itemSort(left: StudyCalendarItem, right: StudyCalendarItem) {
  return Number(left.status === "completed") - Number(right.status === "completed")
    || (left.startMinute ?? 1_500) - (right.startMinute ?? 1_500)
    || left.title.localeCompare(right.title);
}

export function CalendarPanel({
  selectedDate: requestedDate,
  onSelectedDateChange,
  planAction,
  planScheduleRequest = 0,
}: CalendarPanelProps) {
  const initialTimeZone = useMemo(() => detectedTimeZone(), []);
  const initialDate = requestedDate && isDateKey(requestedDate) ? requestedDate : todayInTimeZone(initialTimeZone);
  const [timeZone, setTimeZone] = useState(initialTimeZone);
  const [weekStartsOn, setWeekStartsOn] = useState<0 | 1>(1);
  const [selectedDate, setSelectedDate] = useState(initialDate);
  const [viewMonth, setViewMonth] = useState(initialDate.slice(0, 7));
  const [snapshot, setSnapshot] = useState<StudyCalendarSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [editorError, setEditorError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [settingsDraft, setSettingsDraft] = useState({ timeZone: initialTimeZone, weekStartsOn: 1 as 0 | 1 });
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [pendingFocusDate, setPendingFocusDate] = useState<string | null>(null);
  const editorTitleRef = useRef<HTMLInputElement | null>(null);
  const editorReturnFocusRef = useRef<HTMLElement | null>(null);
  const deleteReturnFocusRef = useRef<HTMLButtonElement | null>(null);
  const agendaAddRef = useRef<HTMLButtonElement | null>(null);
  const handledPlanScheduleRequest = useRef(0);
  const adoptedServerToday = useRef(false);
  const requestedDateRef = useRef(requestedDate);
  const selectedDateChangeRef = useRef(onSelectedDateChange);
  const range = useMemo(() => monthRange(viewMonth, weekStartsOn), [viewMonth, weekStartsOn]);

  useEffect(() => {
    requestedDateRef.current = requestedDate;
    selectedDateChangeRef.current = onSelectedDateChange;
  }, [onSelectedDateChange, requestedDate]);

  useEffect(() => {
    if (!requestedDate || !isDateKey(requestedDate) || requestedDate === selectedDate) return;
    setSelectedDate(requestedDate);
    setViewMonth(requestedDate.slice(0, 7));
  }, [requestedDate, selectedDate]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    api.learningCalendar(range.startDate, range.endDate, timeZone)
      .then((value) => {
        if (cancelled) return;
        if (value.version !== "study-calendar-v1") throw new Error("Unsupported calendar response");
        setSnapshot(value);
        setTimeZone(value.settings.timeZone);
        setWeekStartsOn(value.settings.weekStartsOn);
        setSettingsDraft({ timeZone: value.settings.timeZone, weekStartsOn: value.settings.weekStartsOn });
        if (!requestedDateRef.current && !adoptedServerToday.current && isDateKey(value.today)) {
          adoptedServerToday.current = true;
          setSelectedDate(value.today);
          setViewMonth(value.today.slice(0, 7));
          selectedDateChangeRef.current?.(value.today);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError("Your schedule could not be loaded. Nothing was changed.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [range.endDate, range.startDate, reloadKey, timeZone]);

  useEffect(() => {
    if (!editor) return;
    editorTitleRef.current?.focus();
  }, [editor]);

  useEffect(() => {
    if (!planAction || planScheduleRequest <= 0 || handledPlanScheduleRequest.current === planScheduleRequest) return;
    handledPlanScheduleRequest.current = planScheduleRequest;
    editorReturnFocusRef.current = null;
    setEditorError(null);
    setMutationError(null);
    setEditor({
      kind: "plan",
      item: null,
      planAction,
      title: planAction.title,
      notes: "",
      scheduledDate: selectedDate,
      startTime: "",
      durationMinutes: String(planAction.suggestedDurationMinutes),
      mode: planAction.mode,
    });
  }, [planAction, planScheduleRequest, selectedDate]);

  useEffect(() => {
    if (!pendingFocusDate) return;
    const target = document.getElementById(`calendar-day-${pendingFocusDate}`);
    if (target) {
      target.focus();
      setPendingFocusDate(null);
    }
  }, [pendingFocusDate, viewMonth]);

  const currentSnapshot = snapshot?.range.startDate === range.startDate && snapshot.range.endDate === range.endDate
    ? snapshot
    : null;
  const items = useMemo(() => currentSnapshot?.items ?? [], [currentSnapshot]);
  const itemsByDate = useMemo(() => {
    const grouped = new Map<string, StudyCalendarItem[]>();
    for (const item of items) grouped.set(item.scheduledDate, [...(grouped.get(item.scheduledDate) ?? []), item]);
    for (const dayItems of grouped.values()) dayItems.sort(itemSort);
    return grouped;
  }, [items]);
  const reviewsByDate = useMemo(
    () => new Map((currentSnapshot?.reviewDays ?? []).map((day) => [day.date, day])),
    [currentSnapshot?.reviewDays],
  );
  const selectedItems = itemsByDate.get(selectedDate) ?? [];
  const selectedReviews = reviewsByDate.get(selectedDate)?.items ?? [];
  const priorityReviews = selectedReviews.slice(0, 3);
  const additionalReviews = selectedReviews.slice(3);
  const today = todayInTimeZone(timeZone);
  const mobileDates = Array.from({ length: 7 }, (_, index) => addDays(selectedDate, index - 3));
  const weekdayLabels = Array.from({ length: 7 }, (_, index) => {
    const sunday = dateFromKey("2026-07-12");
    sunday.setUTCDate(sunday.getUTCDate() + ((weekStartsOn + index) % 7));
    return new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" }).format(sunday);
  });

  function chooseDate(nextDate: string, focus = false) {
    setSelectedDate(nextDate);
    setViewMonth(nextDate.slice(0, 7));
    onSelectedDateChange?.(nextDate);
    setEditor((current) => current?.kind === "new" ? { ...current, scheduledDate: nextDate } : current);
    if (focus) setPendingFocusDate(nextDate);
  }

  function moveMonth(amount: number) {
    const nextMonth = addMonths(viewMonth, amount);
    chooseDate(`${nextMonth}-01`);
  }

  function handleDayKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, day: string) {
    let nextDate: string | null = null;
    if (event.key === "ArrowLeft") nextDate = addDays(day, -1);
    else if (event.key === "ArrowRight") nextDate = addDays(day, 1);
    else if (event.key === "ArrowUp") nextDate = addDays(day, -7);
    else if (event.key === "ArrowDown") nextDate = addDays(day, 7);
    else if (event.key === "PageUp") nextDate = moveDateByMonth(day, -1);
    else if (event.key === "PageDown") nextDate = moveDateByMonth(day, 1);
    else if (event.key === "Home" || event.key === "End") {
      const weekday = dateFromKey(day).getUTCDay();
      const fromStart = (weekday - weekStartsOn + 7) % 7;
      nextDate = addDays(day, event.key === "Home" ? -fromStart : 6 - fromStart);
    }
    if (!nextDate) return;
    event.preventDefault();
    chooseDate(nextDate, true);
  }

  function startNewItem() {
    editorReturnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    setEditorError(null);
    setMutationError(null);
    setEditor({
      kind: "new",
      item: null,
      planAction: null,
      title: "",
      notes: "",
      scheduledDate: selectedDate,
      startTime: "",
      durationMinutes: DEFAULT_DURATION,
      mode: "",
    });
  }

  function startEditing(item: StudyCalendarItem) {
    editorReturnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    setEditorError(null);
    setMutationError(null);
    setEditor({
      kind: "edit",
      item,
      planAction: null,
      title: item.title,
      notes: item.notes ?? "",
      scheduledDate: item.scheduledDate,
      startTime: startMinuteToInput(item.startMinute),
      durationMinutes: item.durationMinutes === null ? "" : String(item.durationMinutes),
      mode: item.activity?.mode ?? "",
    });
  }

  function closeEditor() {
    setEditor(null);
    requestAnimationFrame(() => {
      const target = editorReturnFocusRef.current;
      if (target?.isConnected) target.focus();
      else agendaAddRef.current?.focus();
      editorReturnFocusRef.current = null;
    });
  }

  function openDeleteConfirmation(itemId: string, trigger: HTMLButtonElement) {
    deleteReturnFocusRef.current = trigger;
    setDeleteConfirmId(itemId);
    requestAnimationFrame(() => document.getElementById(`calendar-delete-yes-${itemId}`)?.focus());
  }

  function cancelDeleteConfirmation() {
    const itemId = deleteConfirmId;
    setDeleteConfirmId(null);
    requestAnimationFrame(() => {
      const replacementTrigger = itemId
        ? document.getElementById(`calendar-delete-${itemId}`)
        : null;
      if (replacementTrigger instanceof HTMLButtonElement) replacementTrigger.focus();
      else if (deleteReturnFocusRef.current?.isConnected) deleteReturnFocusRef.current.focus();
      else agendaAddRef.current?.focus();
      deleteReturnFocusRef.current = null;
    });
  }

  function replaceItem(item: StudyCalendarItem) {
    setSnapshot((current) => current ? {
      ...current,
      items: [...current.items.filter((candidate) => candidate.itemId !== item.itemId), item],
    } : current);
  }

  async function submitEditor(event: React.FormEvent) {
    event.preventDefault();
    if (!editor || busyKey) return;
    const title = editor.title.trim();
    const notes = editor.notes.trim();
    const duration = editor.durationMinutes ? Number(editor.durationMinutes) : null;
    if (!title) {
      setEditorError("Add a short title for this study block.");
      editorTitleRef.current?.focus();
      return;
    }
    if (!isDateKey(editor.scheduledDate)) {
      setEditorError("Choose a valid calendar date.");
      return;
    }
    if (duration !== null && (!Number.isInteger(duration) || duration < 5 || duration > 480)) {
      setEditorError("Choose a duration between 5 minutes and 8 hours, or leave it flexible.");
      return;
    }
    setBusyKey("editor");
    setEditorError(null);
    setMutationError(null);
    try {
      const startMinute = inputToStartMinute(editor.startTime);
      const item = editor.kind === "new"
        ? await api.createLearningCalendarItem({
          title,
          notes,
          scheduledDate: editor.scheduledDate,
          startMinute,
          durationMinutes: duration,
          mode: editor.mode || null,
          clientRequestId: clientRequestId(),
        })
        : editor.kind === "plan"
          ? await api.createLearningCalendarItemFromPlan({
            expectedActionKey: editor.planAction!.actionKey,
            notes,
            scheduledDate: editor.scheduledDate,
            startMinute,
            durationMinutes: duration,
            clientRequestId: clientRequestId(),
          })
        : await api.updateLearningCalendarItem(editor.item!.itemId, {
          revision: editor.item!.revision,
          title,
          notes,
          scheduledDate: editor.scheduledDate,
          startMinute,
          durationMinutes: duration,
        });
      replaceItem(item);
      chooseDate(item.scheduledDate);
      closeEditor();
      setAnnouncement(editor.kind === "new" ? "Study block added." : editor.kind === "plan" ? "Recommended practice added to your calendar." : "Study block updated.");
      setReloadKey((value) => value + 1);
    } catch (error) {
      const message = error instanceof ApiError && error.code === "calendar_plan_changed"
        ? "Luna's suggestion changed before this was saved. Return to My plan to see the latest step."
        : mutationErrorMessage(error, "That study block could not be saved. Your existing calendar is unchanged.");
      setEditorError(message);
      if (error instanceof ApiError && (error.status === 409 || error.status === 404)) setReloadKey((value) => value + 1);
    } finally {
      setBusyKey(null);
    }
  }

  async function changeCompletion(item: StudyCalendarItem) {
    if (busyKey) return;
    const reopening = item.status === "completed";
    setBusyKey(`completion:${item.itemId}`);
    setMutationError(null);
    try {
      const updated = reopening
        ? await api.reopenLearningCalendarItem(item.itemId, item.revision)
        : await api.completeLearningCalendarItem(item.itemId, item.revision);
      replaceItem(updated);
      setAnnouncement(reopening ? "Study block reopened." : "Study block marked complete.");
      setReloadKey((value) => value + 1);
    } catch (error) {
      setMutationError(mutationErrorMessage(error, reopening
        ? "That study block could not be reopened. Its current status is unchanged."
        : "That study block could not be completed. Its current status is unchanged."));
      if (error instanceof ApiError && (error.status === 409 || error.status === 404)) setReloadKey((value) => value + 1);
    } finally {
      setBusyKey(null);
    }
  }

  async function deleteItem(item: StudyCalendarItem) {
    if (busyKey) return;
    setBusyKey(`delete:${item.itemId}`);
    setMutationError(null);
    try {
      await api.deleteLearningCalendarItem(item.itemId, item.revision);
      setSnapshot((current) => current ? {
        ...current,
        items: current.items.filter((candidate) => candidate.itemId !== item.itemId),
      } : current);
      setDeleteConfirmId(null);
      if (editor?.item?.itemId === item.itemId) setEditor(null);
      setAnnouncement("Study block deleted.");
      setReloadKey((value) => value + 1);
      requestAnimationFrame(() => agendaAddRef.current?.focus());
      deleteReturnFocusRef.current = null;
    } catch (error) {
      setMutationError(mutationErrorMessage(error, "That study block could not be deleted. Your calendar is unchanged."));
      if (error instanceof ApiError && (error.status === 409 || error.status === 404)) setReloadKey((value) => value + 1);
    } finally {
      setBusyKey(null);
    }
  }

  async function planReview(review: StudyCalendarReviewItem) {
    if (busyKey) return;
    setBusyKey(`review:${review.key}`);
    setMutationError(null);
    try {
      const item = await api.createLearningCalendarItemFromCompetency({
        objectiveId: review.objectiveId,
        subskill: review.subskill,
        expectedNextDueAt: review.nextDueAt,
        scheduledDate: selectedDate,
        durationMinutes: 30,
        clientRequestId: clientRequestId(),
      });
      replaceItem(item);
      setAnnouncement(`${review.objectiveLabel} review added to ${fullDateLabel(selectedDate)}.`);
      setReloadKey((value) => value + 1);
    } catch (error) {
      setMutationError(mutationErrorMessage(error, "That suggested review could not be added. No calendar item was created."));
      if (error instanceof ApiError && (error.status === 409 || error.status === 404)) setReloadKey((value) => value + 1);
    } finally {
      setBusyKey(null);
    }
  }

  async function saveSettings(event: React.FormEvent) {
    event.preventDefault();
    const nextTimeZone = settingsDraft.timeZone.trim();
    if (!nextTimeZone || !validTimeZone(nextTimeZone)) {
      setSettingsError("Choose a valid time zone from the list.");
      return;
    }
    setSettingsSaving(true);
    setSettingsError(null);
    try {
      const value = await api.updateLearningCalendarSettings({
        timeZone: nextTimeZone,
        weekStartsOn: settingsDraft.weekStartsOn,
      });
      setTimeZone(value.timeZone);
      setWeekStartsOn(value.weekStartsOn);
      setSettingsDraft({ timeZone: value.timeZone, weekStartsOn: value.weekStartsOn });
      setAnnouncement("Schedule display saved.");
      setReloadKey((current) => current + 1);
    } catch {
      setSettingsError("Display settings could not be saved. Your previous choices are still in use.");
    } finally {
      setSettingsSaving(false);
    }
  }

  function renderReview(review: StudyCalendarReviewItem) {
    return (
      <article key={review.key}>
        <div>
          <strong>{review.objectiveLabel}</strong>
          <small>{subskillLabel(review.subskill)} · {review.dueState === "overdue" ? `${review.overdueDays} day${review.overdueDays === 1 ? "" : "s"} overdue` : "due for a check"}</small>
          {review.planPriority ? <small className={styles.planPriority}>{review.planPriority === 1 ? "Luna's top pick" : "In your plan"}</small> : null}
        </div>
        {review.plannedFor ? (
          <button type="button" onClick={() => chooseDate(review.plannedFor!)}>Planned {shortDayLabel(review.plannedFor)}</button>
        ) : (
          <span className={styles.reviewActions}>
            <button type="button" onClick={() => void planReview(review)} disabled={Boolean(busyKey)}>{busyKey === `review:${review.key}` ? "Adding…" : "Add 30 min"}</button>
            {review.launchHref ? <Link href={review.launchHref}>Start now <ExternalLink size={13} aria-hidden="true" /></Link> : null}
          </span>
        )}
      </article>
    );
  }

  return (
    <section className={styles.calendar} aria-labelledby="study-calendar-heading" aria-busy={loading || Boolean(busyKey)}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">Schedule</p>
          <h2 id="study-calendar-heading">Plan your week</h2>
          <p>Set aside study time and add Luna&apos;s suggested reviews when they fit.</p>
        </div>
        <button className="button primary" type="button" onClick={startNewItem} disabled={Boolean(busyKey) || !currentSnapshot}>
          <Plus size={16} aria-hidden="true" /> Add study time
        </button>
      </header>

      <div className={styles.toolbar}>
        <div className={styles.monthNavigation} aria-label="Calendar month">
          <span className={styles.viewLabel}>Month</span>
          <button type="button" aria-label="Previous month" onClick={() => moveMonth(-1)}><ChevronLeft size={18} aria-hidden="true" /></button>
          <h3 aria-live="polite">{monthLabel(viewMonth)}</h3>
          <button type="button" aria-label="Next month" onClick={() => moveMonth(1)}><ChevronRight size={18} aria-hidden="true" /></button>
          <button type="button" onClick={() => chooseDate(today)}>Today</button>
        </div>
        <details className={styles.settings}>
          <summary><Settings2 size={15} aria-hidden="true" /> Display</summary>
          <form onSubmit={saveSettings}>
            <label>
              <span>Time zone</span>
              <select
                value={settingsDraft.timeZone}
                onChange={(event) => setSettingsDraft((current) => ({ ...current, timeZone: event.target.value }))}
              >
                {[settingsDraft.timeZone, detectedTimeZone(), "UTC", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "Europe/London", "Asia/Kolkata", "Asia/Tokyo", "Australia/Sydney"].filter((value, index, values) => values.indexOf(value) === index).map((value) => <option value={value} key={value}>{timeZoneLabel(value)}</option>)}
              </select>
            </label>
            <label>
              <span>Week begins</span>
              <select value={settingsDraft.weekStartsOn} onChange={(event) => setSettingsDraft((current) => ({ ...current, weekStartsOn: Number(event.target.value) as 0 | 1 }))}>
                <option value={1}>Monday</option>
                <option value={0}>Sunday</option>
              </select>
            </label>
            {settingsError ? <p role="alert">{settingsError}</p> : null}
            <button className="button small" type="submit" disabled={settingsSaving}>{settingsSaving ? "Saving…" : "Save display"}</button>
          </form>
        </details>
      </div>

      {loadError ? (
        <div className={styles.loadError} role="alert">
          <CircleAlert size={20} aria-hidden="true" />
          <div><strong>Schedule unavailable</strong><p>{loadError}</p></div>
          <button className="button small" type="button" onClick={() => setReloadKey((value) => value + 1)}><RefreshCw size={15} aria-hidden="true" /> Retry</button>
        </div>
      ) : null}
      {mutationError ? <div className={styles.mutationError} role="alert"><CircleAlert size={17} aria-hidden="true" /> {mutationError}</div> : null}
      <p className="sr-only" role="status" aria-live="polite">{announcement}</p>

      {currentSnapshot ? <div className={styles.mobileWeek}>
        <div className={styles.mobileWeekHeading}><strong>Week</strong><span>{monthLabel(viewMonth)}</span></div>
        <div className={styles.mobileStrip} aria-label="Selected week">
        {mobileDates.map((day) => {
          const planned = itemsByDate.get(day)?.length ?? 0;
          const reviews = reviewsByDate.get(day)?.total ?? 0;
          return (
            <button type="button" key={day} data-selected={day === selectedDate} aria-pressed={day === selectedDate} onClick={() => chooseDate(day)}>
              <span>{new Intl.DateTimeFormat(undefined, { weekday: "short", timeZone: "UTC" }).format(dateFromKey(day))}</span>
              <strong>{Number(day.slice(8))}</strong>
              <small>{planned ? `${planned} stud${planned === 1 ? "y" : "ies"}` : reviews ? `${reviews} review${reviews === 1 ? "" : "s"}` : "Free"}</small>
            </button>
          );
        })}
        </div>
      </div> : loading ? <div className={styles.loading} role="status">Loading your schedule…</div> : null}

      {currentSnapshot ? <div className={styles.workspace}>
        <section className={styles.monthGrid} aria-label={`${monthLabel(viewMonth)} calendar`}>
          <div className={styles.weekdays} aria-hidden="true">
            {weekdayLabels.map((label) => <span key={label}>{label}</span>)}
          </div>
          <div className={styles.days}>
            {range.days.map((day) => {
              const planned = itemsByDate.get(day)?.length ?? 0;
              const reviewDay = reviewsByDate.get(day);
              const outside = day.slice(0, 7) !== viewMonth;
              const label = `${fullDateLabel(day)}. ${planned ? `${planned} scheduled study item${planned === 1 ? "" : "s"}.` : "No study time scheduled."} ${reviewDay?.total ? `${reviewDay.total} suggested review${reviewDay.total === 1 ? "" : "s"}.` : ""}`;
              return (
                <button
                  id={`calendar-day-${day}`}
                  type="button"
                  data-calendar-day="true"
                  key={day}
                  className={outside ? styles.outsideMonth : undefined}
                  data-selected={day === selectedDate}
                  aria-pressed={day === selectedDate}
                  aria-current={day === today ? "date" : undefined}
                  aria-label={label}
                  tabIndex={day === selectedDate ? 0 : -1}
                  onClick={() => chooseDate(day)}
                  onKeyDown={(event) => handleDayKeyDown(event, day)}
                >
                  <span className={styles.dayNumber}>{Number(day.slice(8))}</span>
                  <span className={styles.daySignals} aria-hidden="true">
                    {planned ? <span data-kind="planned">{planned} study</span> : null}
                    {reviewDay?.total ? <span data-kind={reviewDay.overdue ? "overdue" : "review"}>{reviewDay.total} review</span> : null}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <aside className={styles.agenda} aria-labelledby="calendar-agenda-heading">
          <header>
            <div><p className="eyebrow">Day plan</p><h3 id="calendar-agenda-heading">{fullDateLabel(selectedDate)}</h3></div>
            <button ref={agendaAddRef} type="button" onClick={startNewItem} disabled={Boolean(busyKey)}><Plus size={15} aria-hidden="true" /> Add</button>
          </header>

          {editor ? (
            <form className={styles.editor} onSubmit={submitEditor}>
              <div className={styles.editorHeading}>
                <div>
                  <strong>{editor.kind === "new" ? "Add study time" : editor.kind === "plan" ? "Add Luna's next step" : "Edit study time"}</strong>
                  <small>{editor.kind === "plan" ? `${modeLabel(editor.mode as StudyCalendarMode)} · review before adding` : editor.kind === "edit" && editor.item?.source === "retention_review" ? "Suggested review" : editor.kind === "edit" && editor.item?.source === "study_plan" ? "From My plan" : "Your study time"}</small>
                </div>
                <button type="button" aria-label="Close study-time editor" onClick={closeEditor}><X size={17} aria-hidden="true" /></button>
              </div>
              <label>
                <span>Title</span>
                <input ref={editorTitleRef} value={editor.title} maxLength={120} readOnly={editor.kind === "plan"} onChange={(event) => setEditor((current) => current ? { ...current, title: event.target.value } : current)} required />
              </label>
              {editor.kind === "new" ? (
                <label>
                  <span>Learning mode <small>optional</small></span>
                  <select value={editor.mode} onChange={(event) => setEditor((current) => current ? { ...current, mode: event.target.value as StudyCalendarMode | "" } : current)}>
                    <option value="">Planning only</option>
                    <option value="guided">Guided learning</option>
                    <option value="train">Focused practice</option>
                    <option value="rapid">Rapid practice</option>
                    <option value="clinical">Clinical cases</option>
                  </select>
                </label>
              ) : editor.mode ? <p className={styles.modeSummary}><strong>{modeLabel(editor.mode as StudyCalendarMode)}</strong> stays linked if you move this study time.</p> : null}
              <label>
                <span>Notes <small>optional</small></span>
                <textarea value={editor.notes} maxLength={1_000} rows={2} onChange={(event) => setEditor((current) => current ? { ...current, notes: event.target.value } : current)} />
              </label>
              <div className={styles.editorRow}>
                <label><span>Date</span><input type="date" value={editor.scheduledDate} onChange={(event) => setEditor((current) => current ? { ...current, scheduledDate: event.target.value } : current)} required /></label>
                <label><span>Start <small>optional</small></span><input type="time" step={900} value={editor.startTime} onChange={(event) => setEditor((current) => current ? { ...current, startTime: event.target.value } : current)} /></label>
                <label><span>Minutes</span><input type="number" min={5} max={480} step={5} placeholder="Flexible" value={editor.durationMinutes} onChange={(event) => setEditor((current) => current ? { ...current, durationMinutes: event.target.value } : current)} /></label>
              </div>
              {editorError ? <p role="alert">{editorError}</p> : null}
              <div className={styles.editorActions}>
                <button className="button primary" type="submit" disabled={busyKey === "editor"}>{busyKey === "editor" ? "Saving…" : editor.kind === "new" ? "Add to schedule" : editor.kind === "plan" ? "Confirm and add" : "Save changes"}</button>
                <button className="button subtle" type="button" onClick={closeEditor} disabled={busyKey === "editor"}>Cancel</button>
              </div>
            </form>
          ) : null}

          <section className={styles.agendaSection} aria-labelledby="planned-blocks-heading">
            <div className={styles.sectionHeading}><h4 id="planned-blocks-heading">Study time</h4><span>{selectedItems.length}</span></div>
            {loading && !currentSnapshot ? <div className={styles.loading} role="status">Loading this month…</div> : selectedItems.length ? (
              <div className={styles.itemList}>
                {selectedItems.map((item) => (
                  <article key={item.itemId} className={item.status === "completed" ? styles.completedItem : undefined}>
                    <div className={styles.itemTop}>
                      <span className={styles.itemIcon} data-source={item.source} aria-hidden="true">{item.status === "completed" ? <Check size={16} /> : item.source === "retention_review" ? <RotateCcw size={16} /> : item.source === "study_plan" ? <Sparkles size={16} /> : <CalendarDays size={16} />}</span>
                      <div><strong>{item.title}</strong><small><Clock3 size={13} aria-hidden="true" /> {timeLabel(item.startMinute)}{item.durationMinutes ? ` · ${item.durationMinutes} min` : " · flexible length"}</small></div>
                      <span className={styles.status} data-complete={item.status === "completed"}>{item.status === "completed" ? "Done" : "Scheduled"}</span>
                    </div>
                    {item.notes ? <p>{item.notes}</p> : null}
                    {item.competency ? (
                      <div className={styles.competencyNote} data-current={item.competency.sourceCurrent}>
                        <span>{item.competency.objectiveLabel} · {subskillLabel(item.competency.subskill)}</span>
                        {!item.competency.sourceCurrent ? <small>This review timing has changed. Keep it or move it if it still helps.</small> : null}
                      </div>
                    ) : null}
                    {item.activity && item.activity.kind !== "retention_review" ? (
                      <div className={styles.activityNote} data-current={item.activity.sourceCurrent ?? undefined}>
                        <span><strong>{modeLabel(item.activity.mode)}</strong>{item.activity.objectiveLabel ? ` · ${item.activity.objectiveLabel}` : ""}{item.activity.subskill ? ` · ${subskillLabel(item.activity.subskill)}` : ""}</span>
                        {item.activity.kind === "study_plan" && item.activity.sourceCurrent === false ? <small>Luna has a newer suggestion. This activity still works if you want to keep it.</small> : null}
                        {item.activity.kind === "manual_mode" && item.activity.mode === "guided" ? <small>Opens Guided learning so you can choose a lesson.</small> : null}
                      </div>
                    ) : null}
                    {item.status === "completed" && item.completionSource === "verified_practice" ? <small className={styles.verifiedCompletion}>Completed through practice.</small> : null}
                    {item.status === "completed" && item.completionSource === "manual" && item.source === "retention_review" ? <small className={styles.manualCompletion}>Marked done on your schedule. Start practice when you are ready to check the skill.</small> : null}
                    <div className={styles.itemActions}>
                      {item.status === "scheduled" ? <button type="button" onClick={() => void changeCompletion(item)} disabled={Boolean(busyKey)}><Check size={14} aria-hidden="true" /> Mark done</button> : item.completionSource === "manual" ? <button type="button" onClick={() => void changeCompletion(item)} disabled={Boolean(busyKey)}><RotateCcw size={14} aria-hidden="true" /> Reopen</button> : null}
                      <button type="button" onClick={() => startEditing(item)} disabled={Boolean(busyKey)}><Pencil size={14} aria-hidden="true" /> Edit / reschedule</button>
                      {item.activity?.launchHref ? <Link href={item.activity.launchHref}>Start {item.activity.mode === "train" ? "focused practice" : item.activity.mode === "rapid" ? "rapid practice" : item.activity.mode === "clinical" ? "clinical cases" : "guided learning"} <ExternalLink size={13} aria-hidden="true" /></Link> : null}
                      {deleteConfirmId === item.itemId ? (
                        <span className={styles.deleteConfirm}><span>Delete?</span><button id={`calendar-delete-yes-${item.itemId}`} type="button" onClick={() => void deleteItem(item)} disabled={Boolean(busyKey)}>Yes</button><button type="button" onClick={cancelDeleteConfirmation}>No</button></span>
                      ) : <button id={`calendar-delete-${item.itemId}`} type="button" className={styles.deleteButton} onClick={(event) => openDeleteConfirmation(item.itemId, event.currentTarget)} disabled={Boolean(busyKey)}><Trash2 size={14} aria-hidden="true" /> Delete</button>}
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className={styles.empty}><CalendarDays size={20} aria-hidden="true" /><div><strong>Nothing scheduled.</strong><p>Keep this day open or add study time.</p></div></div>
            )}
          </section>

          <section className={styles.agendaSection} aria-labelledby="suggested-reviews-heading">
            <div className={styles.sectionHeading}><h4 id="suggested-reviews-heading">Suggested review</h4><span>{selectedReviews.length}</span></div>
            {selectedReviews.length ? (
              <>
                <div className={styles.reviewList}>{priorityReviews.map(renderReview)}</div>
                {additionalReviews.length ? (
                  <details className={styles.reviewOverflow}>
                    <summary>Show {additionalReviews.length} more due skill{additionalReviews.length === 1 ? "" : "s"}</summary>
                    <div className={styles.reviewList}>{additionalReviews.map(renderReview)}</div>
                  </details>
                ) : null}
              </>
            ) : <p className={styles.noReviews}>No suggested review for this day.</p>}
          </section>
        </aside>
      </div> : null}

      <details className={styles.boundaryNote}>
        <summary><CalendarDays size={16} aria-hidden="true" /> How this schedule works</summary>
        <p>Your schedule stays inside TRACE and does not send reminders. Marking study time complete checks it off here; your skill progress updates after completed practice.</p>
      </details>
    </section>
  );
}
