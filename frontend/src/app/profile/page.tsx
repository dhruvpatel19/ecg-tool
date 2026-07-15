"use client";

import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  Search,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { StudyPlanPanel } from "@/components/my-learning/StudyPlanPanel";
import { ActivityPanel } from "@/components/my-learning/ActivityPanel";
import { PreferencesPanel } from "@/components/my-learning/PreferencesPanel";
import { api, type AdaptivePlan, type CompetencyObjective, type CompetencyState } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { conceptLabel } from "@/lib/coordinates";
import { competencyPracticeHref } from "@/lib/competencyRoutes";
import type { LearnerProfile } from "@/lib/types";
import styles from "./progress.module.css";

type ProgressView = "overview" | "plan" | "competencies" | "activity" | "preferences";

const progressViews: ProgressView[] = ["overview", "plan", "competencies", "activity", "preferences"];
const initialObjectiveCount = 10;

const stateLabels: Record<CompetencyState, string> = {
  unseen: "Not started",
  acquiring: "Starting",
  developing: "Building",
  consolidating: "Strengthening",
  durable: "Holding",
};

function dateLabel(value: string | null) {
  if (!value) return "Not yet";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(new Date(value));
}

function domainLabel(value: string) {
  const domainLabels: Record<string, string> = {
    st_t_mi: "ST–T / infarction",
  };
  if (domainLabels[value]) return domainLabels[value];
  const acronyms: Record<string, string> = {
    av: "AV",
    ecg: "ECG",
    mi: "MI",
    qt: "QT",
    st: "ST",
    t: "T",
  };
  return value.split("_").map((token) => acronyms[token] ?? token).join(" ");
}

function skillLabel(value: string) {
  const labels: Record<string, string> = {
    apply_in_context: "use in context",
    discriminate: "tell apart",
    localize: "locate",
    recognize: "identify",
    synthesize: "complete interpretation",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}

function objectiveHasStarted(objective: CompetencyObjective) {
  return objective.subskills.some((cell) => cell.state !== "unseen" || cell.attempts > 0);
}

function objectiveEvidenceLabel(objective: CompetencyObjective) {
  const independentlyObserved = objective.subskills.some((cell) => cell.independentAttempts > 0);
  const independentlyRunnable = objective.subskills.some((cell) => Boolean(cell.independentReceipt));
  if (independentlyObserved) return "Checked on real ECGs";
  if (independentlyRunnable) return "Real-ECG check available";
  return objective.evidenceCeiling === "eligible_real_case"
    ? "Formative practice only"
    : "Guided or simulated practice only";
}

function compareCompetencyObjectives(left: CompetencyObjective, right: CompetencyObjective) {
  const leftDue = left.subskills.some((cell) => cell.isDue);
  const rightDue = right.subskills.some((cell) => cell.isDue);
  const dueOrder = Number(rightDue) - Number(leftDue);
  if (dueOrder) return dueOrder;

  const startedOrder = Number(objectiveHasStarted(right)) - Number(objectiveHasStarted(left));
  if (startedOrder) return startedOrder;

  const confidenceOrder = Math.max(...right.subskills.map((cell) => cell.highConfidenceWrong), 0)
    - Math.max(...left.subskills.map((cell) => cell.highConfidenceWrong), 0);
  if (confidenceOrder) return confidenceOrder;

  const leftObserved = left.subskills.filter((cell) => cell.independentAttempts > 0);
  const rightObserved = right.subskills.filter((cell) => cell.independentAttempts > 0);
  const leftMastery = leftObserved.length
    ? Math.min(...leftObserved.map((cell) => cell.independentMastery))
    : 1;
  const rightMastery = rightObserved.length
    ? Math.min(...rightObserved.map((cell) => cell.independentMastery))
    : 1;
  return leftMastery - rightMastery || left.label.localeCompare(right.label);
}

function isProgressView(value: string | null): value is ProgressView {
  return progressViews.includes(value as ProgressView);
}

function progressViewLabel(view: ProgressView) {
  if (view === "overview") return "Overview";
  if (view === "plan") return "Study plan";
  if (view === "competencies") return "Competency map";
  if (view === "activity") return "Activity";
  return "Preferences";
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<div className="page"><div className={styles.loadingState} role="status">Loading your learning record…</div></div>}>
      <ProfileScreen />
    </Suspense>
  );
}

function ProfileScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [adaptivePlan, setAdaptivePlan] = useState<AdaptivePlan | null>(null);
  const [competencyObjectives, setCompetencyObjectives] = useState<CompetencyObjective[]>([]);
  const [profileFailed, setProfileFailed] = useState(false);
  const [planFailed, setPlanFailed] = useState(false);
  const [competenciesFailed, setCompetenciesFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const requestedView = searchParams.get("tab");
  const [view, setView] = useState<ProgressView>(isProgressView(requestedView) ? requestedView : "overview");
  const [query, setQuery] = useState("");
  const [domainFilter, setDomainFilter] = useState("all");
  const [stateFilter, setStateFilter] = useState<"all" | CompetencyState>("all");
  const [showAll, setShowAll] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const nextView = isProgressView(requestedView) ? requestedView : "overview";
    setView(nextView);
    if (requestedView !== nextView) router.replace(`/profile?tab=${nextView}`, { scroll: false });
  }, [requestedView, router]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setProfileFailed(false);
    setPlanFailed(false);
    setCompetenciesFailed(false);
    Promise.allSettled([api.profile(), api.adaptivePlan(), api.competencies()])
      .then(([profileResult, planResult, competenciesResult]) => {
        if (cancelled) return;
        setProfile(profileResult.status === "fulfilled" ? profileResult.value : null);
        setProfileFailed(profileResult.status === "rejected");
        setAdaptivePlan(planResult.status === "fulfilled" ? planResult.value : null);
        setPlanFailed(planResult.status === "rejected");
        setCompetencyObjectives(competenciesResult.status === "fulfilled" ? competenciesResult.value.objectives : []);
        setCompetenciesFailed(competenciesResult.status === "rejected");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [retryKey]);

  function selectView(nextView: ProgressView) {
    setView(nextView);
    router.push(`/profile?tab=${nextView}`, { scroll: false });
  }

  const allCells = useMemo(
    () => competencyObjectives.flatMap((objective) => objective.subskills.map((cell) => ({ objective, cell }))),
    [competencyObjectives],
  );
  const independentlyObserved = allCells.filter(({ cell }) => cell.independentAttempts > 0);
  const independentAverage = independentlyObserved.length
    ? Math.round(independentlyObserved.reduce((sum, { cell }) => sum + cell.independentMastery, 0) / independentlyObserved.length * 100)
    : null;
  const dueCells = allCells.filter(({ cell }) => cell.isDue);
  const calibrationFlags = allCells.reduce((sum, { cell }) => sum + cell.highConfidenceWrong, 0);
  const durableCells = allCells.filter(({ cell }) => cell.state === "durable").length;
  const observedCells = allCells.filter(({ cell }) => cell.state !== "unseen").length;
  const competencyDomains = useMemo(
    () => [...new Set(competencyObjectives.map((objective) => objective.domain))].sort(),
    [competencyObjectives],
  );
  const stateCounts = useMemo(
    () => allCells.reduce<Record<CompetencyState, number>>((counts, { cell }) => {
      counts[cell.state] += 1;
      return counts;
    }, { unseen: 0, acquiring: 0, developing: 0, consolidating: 0, durable: 0 }),
    [allCells],
  );

  const attentionRows = useMemo(() => {
    const observedByConcept = new Map((profile?.subskillMastery ?? []).map((row) => [`${row.concept}:${row.subskill}`, row]));
    return allCells
      .filter(({ objective, cell }) => cell.state !== "unseen" || observedByConcept.has(`${objective.objectiveId}:${cell.subskill}`))
      .sort((left, right) =>
        Number(right.cell.isDue) - Number(left.cell.isDue)
        || right.cell.highConfidenceWrong - left.cell.highConfidenceWrong
        || left.cell.independentMastery - right.cell.independentMastery
      )
      .slice(0, 6);
  }, [allCells, profile]);

  const filteredObjectives = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return competencyObjectives
      .filter((objective) => {
        if (domainFilter !== "all" && objective.domain !== domainFilter) return false;
        if (stateFilter !== "all" && !objective.subskills.some((cell) => cell.state === stateFilter)) return false;
        if (!normalized) return true;
        return objective.label.toLowerCase().includes(normalized)
          || objective.domain.toLowerCase().includes(normalized)
          || objective.subskills.some((cell) => cell.subskill.replaceAll("_", " ").includes(normalized));
      })
      .sort(compareCompetencyObjectives);
  }, [competencyObjectives, domainFilter, query, stateFilter]);
  const visibleObjectives = showAll ? filteredObjectives : filteredObjectives.slice(0, initialObjectiveCount);

  const guidedRemediation = adaptivePlan?.guidedRemediation?.href.trim()
    ? adaptivePlan.guidedRemediation
    : null;
  const primaryStage = adaptivePlan?.stages
    .filter((stage) => stage.href.trim().length > 0)
    .sort((left, right) => left.order - right.order)[0] ?? null;
  const baselineNeeded = !planFailed
    && !guidedRemediation
    && !primaryStage
    && Boolean(adaptivePlan?.basis.baselineNeeded);
  const overviewHref = guidedRemediation?.href
    ?? primaryStage?.href
    ?? (baselineNeeded
      ? "/rapid?pace=untimed&suggestedLength=10&returnTo=%2Fprofile%3Ftab%3Doverview"
      : "/rapid?pace=untimed&suggestedLength=5&returnTo=%2Fprofile%3Ftab%3Doverview");
  const overviewKicker = guidedRemediation || primaryStage
    ? "Recommended next"
    : baselineNeeded
      ? "Baseline · not yet personalized"
      : "General practice · not personalized";
  const overviewTitle = guidedRemediation?.title
    ?? primaryStage?.title
    ?? (baselineNeeded ? "Establish an independent baseline" : "Personalized step unavailable");
  const overviewCopy = guidedRemediation?.purpose
    ?? primaryStage?.purpose
    ?? (baselineNeeded
      ? "Complete a short untimed mixed set to create the first independent evidence for future recommendations."
      : "Your saved evidence is unchanged. This general untimed option is available while the personalized plan cannot provide a runnable step.");
  const overviewCta = guidedRemediation
    ? "Open guided review"
    : primaryStage
      ? "Open recommended step"
      : baselineNeeded
        ? "Start baseline"
        : "Start general practice";
  const warningMessage = [
    profileFailed ? "Your recent-attempt summary could not be loaded." : null,
    planFailed ? "Your personalized study plan could not be loaded." : null,
    competenciesFailed ? "Your competency detail could not be loaded." : null,
  ].filter(Boolean).join(" ");

  return (
    <div className={`page ${styles.page}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">My learning</p>
          <h1>{user ? `${profile?.displayName ?? user.displayName ?? user.username}’s learning` : "Your learning"}</h1>
          <p>One place for your next step, competency evidence, and completed practice.</p>
        </div>
      </header>

      {warningMessage ? (
        <div className={styles.warning} role="status" aria-live="polite">
          <span>{warningMessage} Everything that did load remains available below.</span>
          <button type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry</button>
        </div>
      ) : null}

      <div className={styles.tabs} role="tablist" aria-label="My learning sections" aria-orientation="horizontal">
        {progressViews.map((item) => (
          <button
            type="button"
            key={item}
            id={`progress-tab-${item}`}
            className={view === item ? styles.activeTab : ""}
            role="tab"
            aria-selected={view === item}
            aria-controls={`progress-panel-${item}`}
            tabIndex={view === item ? 0 : -1}
            onClick={() => selectView(item)}
            onKeyDown={(event) => {
              const currentIndex = progressViews.indexOf(item);
              let nextIndex = currentIndex;
              if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % progressViews.length;
              else if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + progressViews.length) % progressViews.length;
              else if (event.key === "Home") nextIndex = 0;
              else if (event.key === "End") nextIndex = progressViews.length - 1;
              else return;
              event.preventDefault();
              const nextView = progressViews[nextIndex];
              selectView(nextView);
              requestAnimationFrame(() => document.getElementById(`progress-tab-${nextView}`)?.focus());
            }}
          >
            {progressViewLabel(item)}
          </button>
        ))}
      </div>

      {loading && view !== "plan" && view !== "preferences" ? (
        <section
          className={styles.loadingState}
          role="tabpanel"
          id={`progress-panel-${view}`}
          aria-labelledby={`progress-tab-${view}`}
          aria-busy="true"
        >
          <span />
          <span />
          <span />
          <p role="status">Loading your saved practice and review schedule…</p>
        </section>
      ) : null}

      {view === "plan" ? (
        <section className={styles.tabPanel} role="tabpanel" id="progress-panel-plan" aria-labelledby="progress-tab-plan">
          <StudyPlanPanel plan={adaptivePlan} loading={loading} failed={planFailed} onRetry={() => setRetryKey((value) => value + 1)} />
        </section>
      ) : null}

      {!loading && view === "overview" ? (
        <div className={styles.tabPanel} role="tabpanel" id="progress-panel-overview" aria-labelledby="progress-tab-overview">
          <section className={styles.metrics} aria-label="Progress summary">
            <article>
              <span>Independent estimate</span>
              <strong>{competenciesFailed || independentAverage === null ? "—" : `${independentAverage}%`}</strong>
              <small>{competenciesFailed ? "temporarily unavailable" : `across ${independentlyObserved.length} independently checked skill${independentlyObserved.length === 1 ? "" : "s"}`}</small>
            </article>
            <article>
              <span>Review due</span>
              <strong>{competenciesFailed ? "—" : dueCells.length}</strong>
              <small>{competenciesFailed ? "temporarily unavailable" : `${dueCells.filter(({ cell }) => cell.dueState === "overdue").length} overdue`}</small>
            </article>
            <article>
              <span>Holding over time</span>
              <strong>{competenciesFailed ? "—" : durableCells}</strong>
              <small>{competenciesFailed ? "temporarily unavailable" : `of ${observedCells} started skills`}</small>
            </article>
            <article>
              <span>Confidence rechecks</span>
              <strong>{competenciesFailed ? "—" : calibrationFlags}</strong>
              <small>{competenciesFailed ? "temporarily unavailable" : "high-confidence misses recorded"}</small>
            </article>
          </section>

          <section className={styles.nextCard} aria-labelledby="next-progress-step">
            <span className={styles.nextIcon}><TrendingUp size={21} aria-hidden="true" /></span>
            <div>
              <p className="eyebrow">{overviewKicker}</p>
              <h2 id="next-progress-step">{overviewTitle}</h2>
              <p>{overviewCopy}</p>
            </div>
            <Link className="button primary" href={overviewHref}>{overviewCta} <ArrowRight size={16} aria-hidden="true" /></Link>
          </section>

          <div className={styles.overviewGrid}>
            <section className={styles.section} aria-labelledby="attention-heading">
              <div className={styles.sectionHeading}>
                <div><p className="eyebrow">Focus</p><h2 id="attention-heading">Needs attention</h2></div>
                <button type="button" onClick={() => selectView("competencies")}>View all</button>
              </div>
              <div className={styles.attentionList}>
                {competenciesFailed ? (
                  <div className={styles.empty}>Competency detail is temporarily unavailable. Retry to restore this queue.</div>
                ) : attentionRows.length ? attentionRows.map(({ objective, cell }) => {
                  const practiceHref = competencyPracticeHref(cell.independentReceipt);
                  return (
                    <article className={`profile-objective ${styles.attentionRow}`} key={`${objective.objectiveId}:${cell.subskill}`}>
                      <span className={styles.stateDot} data-state={cell.state} aria-hidden="true" />
                      <div>
                        <strong>{conceptLabel(objective.objectiveId)}</strong>
                        <small>{skillLabel(cell.subskill)} · {stateLabels[cell.state]}{cell.isDue ? " · due" : ""}</small>
                      </div>
                      <span>{cell.independentAttempts ? `${Math.round(cell.independentMastery * 100)}% est.` : "Practice"}</span>
                      {practiceHref ? <Link href={practiceHref} aria-label={`Practice ${conceptLabel(objective.objectiveId)}`}><ArrowRight size={15} /></Link> : null}
                    </article>
                  );
                }) : (
                  <div className={styles.empty}>Your first mixed ECG check will create a focused queue here.</div>
                )}
              </div>
            </section>

            <aside className={styles.sideStack}>
              <section className={styles.section}>
                <div className={styles.sectionHeading}><div><p className="eyebrow">Retention</p><h2>Coming due</h2></div><CalendarClock size={18} aria-hidden="true" /></div>
                {competenciesFailed ? (
                  <p className={styles.empty}>Review timing is temporarily unavailable.</p>
                ) : dueCells.length ? (
                  <div className={styles.miniList}>
                    {dueCells.slice(0, 4).map(({ objective, cell }) => {
                      const href = competencyPracticeHref(cell.independentReceipt);
                      const contents = <><span>{conceptLabel(objective.objectiveId)}</span><small>{cell.dueState === "overdue" ? `${Math.ceil(cell.overdueDays)}d overdue` : "Due now"}</small></>;
                      return href
                        ? <Link href={href} key={`${objective.objectiveId}:${cell.subskill}`}>{contents}</Link>
                        : <div key={`${objective.objectiveId}:${cell.subskill}`}>{contents}</div>;
                    })}
                  </div>
                ) : <p className={styles.empty}>Nothing is due yet. Spaced checks appear after a successful independent check.</p>}
              </section>
              <section className={styles.accountNote}>
                <CheckCircle2 size={18} aria-hidden="true" />
                <span>{`Saved to ${user?.displayName || user?.username || "your"} profile.`}</span>
              </section>
            </aside>
          </div>
        </div>
      ) : null}

      {!loading && view === "competencies" ? (
        <section className={styles.mapSection} role="tabpanel" id="progress-panel-competencies" aria-labelledby="progress-tab-competencies">
          <div className={styles.sectionHeading}>
            <div><p className="eyebrow">Finding by skill</p><h2 id="competency-map-heading"><BrainCircuit size={19} aria-hidden="true" /> Competency map</h2></div>
            <p>“Not started” means you have not been checked yet—not that you scored poorly.</p>
          </div>
          {competenciesFailed ? (
            <div className={styles.dataUnavailable} role="status">
              <div><strong>Competency detail is temporarily unavailable.</strong><p>No zero scores or “not started” states have been inferred from the failed request.</p></div>
              <button className="button subtle" type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry competency detail</button>
            </div>
          ) : (
            <>
              <div className={styles.stateSummary} aria-label="Skills by progress level">
                {(Object.keys(stateLabels) as CompetencyState[]).map((state) => (
                  <button type="button" key={state} className={stateFilter === state ? styles.selectedState : ""} aria-pressed={stateFilter === state} onClick={() => { setStateFilter(stateFilter === state ? "all" : state); setShowAll(false); }}>
                    <strong>{stateCounts[state]}</strong><span>{stateLabels[state]}</span>
                  </button>
                ))}
              </div>
              <div className={styles.tools}>
                <label htmlFor="competency-search"><Search size={15} aria-hidden="true" /><span className="sr-only">Search competencies</span></label>
                <input id="competency-search" type="search" value={query} onChange={(event) => { setQuery(event.target.value); setShowAll(false); }} placeholder="Search finding or skill" />
                <select aria-label="Filter by domain" value={domainFilter} onChange={(event) => { setDomainFilter(event.target.value); setShowAll(false); }}>
                  <option value="all">All domains</option>
                  {competencyDomains.map((domain) => <option value={domain} key={domain}>{domainLabel(domain)}</option>)}
                </select>
              </div>
              <div className={styles.objectiveList}>
                {visibleObjectives.map((objective) => {
                  const cells = stateFilter === "all" ? objective.subskills : objective.subskills.filter((cell) => cell.state === stateFilter);
                  const observed = objective.subskills.filter((cell) => cell.state !== "unseen").length;
                  return (
                    <details className={`profile-objective ${styles.objective}`} key={objective.objectiveId}>
                      <summary>
                        <span><strong>{conceptLabel(objective.objectiveId)}</strong><small>{domainLabel(objective.domain)} · {observed}/{objective.subskills.length} skills started</small></span>
                        <span>{objectiveEvidenceLabel(objective)}</span>
                      </summary>
                      <div className={styles.cells}>
                        {cells.map((cell) => {
                          const practiceHref = competencyPracticeHref(cell.independentReceipt);
                          return (
                            <article key={`${objective.objectiveId}:${cell.subskill}`} data-state={cell.state}>
                              <div><strong>{skillLabel(cell.subskill)}</strong><span>{stateLabels[cell.state]}{cell.isDue ? " · due" : ""}</span></div>
                              <p>{cell.independentAttempts
                                ? `${Math.round(cell.independentMastery * 100)}% independent estimate · ${cell.independentAttempts} scored attempt${cell.independentAttempts === 1 ? "" : "s"}`
                                : cell.attempts
                                  ? "Formative practice recorded; no independent estimate yet."
                                  : "No practice evidence recorded yet."}</p>
                              <small>{cell.independentAttempts
                                ? `Successful evidence on ${cell.distinctSuccessfulEcgs} distinct ECG${cell.distinctSuccessfulEcgs === 1 ? "" : "s"}${cell.nextDueAt ? ` · ${cell.isDue ? "due" : "next check"} ${dateLabel(cell.nextDueAt)}` : ""}`
                                : cell.evidenceUncertainty ?? "Use an available practice route to begin collecting evidence."}</small>
                              {practiceHref ? (
                                <Link href={practiceHref}>Practice <ArrowRight size={13} /></Link>
                              ) : (
                                <span className={styles.unavailable}>No independently scored real-ECG task yet</span>
                              )}
                            </article>
                          );
                        })}
                      </div>
                    </details>
                  );
                })}
              </div>
              {!visibleObjectives.length ? <div className={styles.empty}>No competencies match those filters.</div> : null}
              {filteredObjectives.length > initialObjectiveCount ? <button className={styles.showAll} type="button" onClick={() => setShowAll((value) => !value)}>{showAll ? "Show fewer" : `Show all ${filteredObjectives.length}`}</button> : null}
            </>
          )}
        </section>
      ) : null}

      {!loading && view === "activity" ? (
        <div className={styles.activityGrid} role="tabpanel" id="progress-panel-activity" aria-labelledby="progress-tab-activity">
          <ActivityPanel />
          <aside className={styles.section}>
            <div className={styles.sectionHeading}><div><p className="eyebrow">Patterns to revisit</p><h2><AlertTriangle size={18} aria-hidden="true" /> What to recheck</h2></div></div>
            <div className={styles.misconceptions}>
              {profileFailed ? (
                <p className={styles.empty}>Recent misconception patterns are temporarily unavailable.</p>
              ) : profile?.misconceptions.length ? profile.misconceptions.map((item) => (
                <div key={item.tag}><strong>{conceptLabel(item.tag)}</strong><span>{item.count} recent occurrence{item.count === 1 ? "" : "s"}</span></div>
              )) : <p className={styles.empty}>No repeated misconception pattern has been detected.</p>}
            </div>
          </aside>
        </div>
      ) : null}

      {view === "preferences" ? (
        <section className={styles.tabPanel} role="tabpanel" id="progress-panel-preferences" aria-labelledby="progress-tab-preferences">
          <PreferencesPanel />
        </section>
      ) : null}
    </div>
  );
}
