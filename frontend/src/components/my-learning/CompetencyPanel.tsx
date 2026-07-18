"use client";

import {
  AlertTriangle,
  ArrowRight,
  BrainCircuit,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  RefreshCw,
  Search,
  Target,
} from "lucide-react";
import Link from "next/link";
import { useId, useMemo, useState } from "react";
import type { CompetencyObjective, CompetencyState } from "@/lib/api";
import { conceptLabel } from "@/lib/coordinates";
import { competencyPracticeHref } from "@/lib/competencyRoutes";
import { competencySkillLabel as skillLabel } from "@/lib/learning/skillLabels";
import { CompetencyTrend } from "./CompetencyTrend";
import styles from "./CompetencyPanel.module.css";

type CompetencyCell = CompetencyObjective["subskills"][number];

export type CompetencyPanelProps = {
  objectives: CompetencyObjective[];
  loading: boolean;
  failed: boolean;
  onRetry: () => void;
};

const competencyStates: CompetencyState[] = [
  "durable",
  "consolidating",
  "developing",
  "acquiring",
  "unseen",
];

const statePresentation: Record<CompetencyState, { label: string; detail: string }> = {
  unseen: { label: "Not started", detail: "Not practiced yet" },
  acquiring: { label: "Getting started", detail: "A little practice so far" },
  developing: { label: "Building", detail: "Improving with practice" },
  consolidating: { label: "Consistent", detail: "Steady across checks" },
  durable: { label: "Retained", detail: "Staying strong over time" },
};

const domainLabels: Record<string, string> = {
  st_t_mi: "ST–T / infarction",
};

const acronyms: Record<string, string> = {
  av: "AV",
  ecg: "ECG",
  mi: "MI",
  qt: "QT",
  st: "ST",
  t: "T",
};

const INITIAL_DOMAIN_COUNT = 4;
const INITIAL_OBJECTIVE_COUNT = 4;

function domainLabel(value: string) {
  if (domainLabels[value]) return domainLabels[value];
  return value
    .split("_")
    .map((token) => acronyms[token] ?? `${token.slice(0, 1).toUpperCase()}${token.slice(1)}`)
    .join(" ");
}

function dateLabel(value: string | null, includeYear = false) {
  if (!value) return "Not yet";
  const instant = new Date(value);
  if (Number.isNaN(instant.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" as const } : {}),
  }).format(instant);
}

function objectiveHasStarted(objective: CompetencyObjective) {
  return objective.subskills.some((cell) => cell.state !== "unseen" || cell.attempts > 0);
}

function objectiveCheckLabel(objective: CompetencyObjective) {
  const independentlyObserved = objective.subskills.some((cell) => cell.independentAttempts > 0);
  const independentlyRunnable = objective.subskills.some((cell) => Boolean(cell.independentReceipt));
  if (independentlyObserved) return "Scored ECG check completed";
  if (independentlyRunnable) return "Scored check available";
  return objective.evidenceCeiling === "eligible_real_case"
    ? "Practice only so far"
    : "Formative practice only";
}

function objectiveSummaryState(cells: CompetencyCell[]): CompetencyState | "mixed" {
  const states = new Set(cells.map((cell) => cell.state));
  if (states.size === 1) return cells[0]?.state ?? "unseen";
  return "mixed";
}

function objectiveProgressLabel(objective: CompetencyObjective) {
  const observed = objective.subskills.filter((cell) => cell.state !== "unseen").length;
  if (!observed) return "No skills practiced yet";
  if (observed === objective.subskills.length) {
    return `${observed} skill${observed === 1 ? "" : "s"} practiced`;
  }
  return `${observed} of ${objective.subskills.length} skills practiced`;
}

function compareObjectives(left: CompetencyObjective, right: CompetencyObjective) {
  const dueOrder = Number(right.subskills.some((cell) => cell.isDue))
    - Number(left.subskills.some((cell) => cell.isDue));
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

function attentionReason(cell: CompetencyCell) {
  if (cell.dueState === "overdue") {
    const days = Math.ceil(cell.overdueDays);
    return days > 0
      ? `Review ${days} day${days === 1 ? "" : "s"} overdue`
      : "Review overdue";
  }
  if (cell.isDue) return "Ready to review again";
  if (cell.highConfidenceWrong > 0) {
    return `Revisit ${cell.highConfidenceWrong} confident miss${cell.highConfidenceWrong === 1 ? "" : "es"}`;
  }
  if (cell.state === "acquiring") return "Another example will help this feel familiar";
  return "Keep building with a few more examples";
}

function compareAttention(
  left: { objective: CompetencyObjective; cell: CompetencyCell },
  right: { objective: CompetencyObjective; cell: CompetencyCell },
) {
  const overdueOrder = Number(right.cell.dueState === "overdue") - Number(left.cell.dueState === "overdue");
  if (overdueOrder) return overdueOrder;
  if (left.cell.dueState === "overdue" && right.cell.dueState === "overdue") {
    const overdueDaysOrder = right.cell.overdueDays - left.cell.overdueDays;
    if (overdueDaysOrder) return overdueDaysOrder;
  }
  const dueOrder = Number(right.cell.isDue) - Number(left.cell.isDue);
  if (dueOrder) return dueOrder;
  const confidenceOrder = right.cell.highConfidenceWrong - left.cell.highConfidenceWrong;
  if (confidenceOrder) return confidenceOrder;
  const stateRank: Record<CompetencyState, number> = {
    acquiring: 0,
    developing: 1,
    consolidating: 2,
    durable: 3,
    unseen: 4,
  };
  return stateRank[left.cell.state] - stateRank[right.cell.state]
    || left.cell.independentMastery - right.cell.independentMastery
    || left.objective.label.localeCompare(right.objective.label);
}

function nextReviewLabel(cell: CompetencyCell) {
  if (cell.dueState === "overdue") {
    const days = Math.ceil(cell.overdueDays);
    return days > 0 ? `${days}d overdue` : "Overdue";
  }
  if (cell.isDue) return "Due now";
  if (cell.nextDueAt) return dateLabel(cell.nextDueAt, true);
  return "Not scheduled";
}

function EvidenceRail({ cell, label, objectiveId }: { cell: CompetencyCell; label: string; objectiveId: string }) {
  const lastCheckAt = cell.lastIndependentAt ?? cell.lastPracticedAt;
  const lastCheckLabel = cell.lastIndependentAt ? "Last scored check" : "Last practice";

  return (
    <div className={styles.evidenceStack}>
      <details className={styles.evidenceBlock}>
        <summary className={styles.evidenceHeading}>
          <strong>Practice details</strong>
          <span>Checks, ECGs, and next review</span>
        </summary>
        <ol className={styles.evidenceRail} aria-label={`${label} practice summary`}>
          <li>
            <span className={styles.railNode} aria-hidden="true" />
            <span className={styles.railLabel}>Times practiced</span>
            <strong>{cell.attempts}</strong>
            <small>{cell.independentAttempts} scored ECG check{cell.independentAttempts === 1 ? "" : "s"}</small>
          </li>
          <li>
            <span className={styles.railNode} aria-hidden="true" />
            <span className={styles.railLabel}>ECGs answered correctly</span>
            <strong>{cell.distinctSuccessfulEcgs}</strong>
            <small>different ECGs</small>
          </li>
          <li>
            <span className={styles.railNode} aria-hidden="true" />
            <span className={styles.railLabel}>{lastCheckLabel}</span>
            <strong>{dateLabel(lastCheckAt, true)}</strong>
            <small>{lastCheckAt ? "most recent activity" : "no activity yet"}</small>
          </li>
          <li data-due={cell.isDue || undefined}>
            <span className={styles.railNode} aria-hidden="true" />
            <span className={styles.railLabel}>Next review</span>
            <strong>{nextReviewLabel(cell)}</strong>
            <small>{cell.nextDueAt
              ? `planned for ${dateLabel(cell.nextDueAt, true)}`
              : cell.independentAttempts
                ? "no review planned yet"
                : "planned after a scored check"}</small>
          </li>
        </ol>
      </details>
      {cell.attempts > 0 ? (
        <CompetencyTrend objectiveId={objectiveId} subskill={cell.subskill} label={label} />
      ) : null}
    </div>
  );
}

export function CompetencyPanel({ objectives, loading, failed, onRetry }: CompetencyPanelProps) {
  const generatedId = useId().replaceAll(":", "");
  const headingId = `${generatedId}-competencies-heading`;
  const [query, setQuery] = useState("");
  const [domainFilter, setDomainFilter] = useState("all");
  const [stateFilter, setStateFilter] = useState<"all" | CompetencyState>("all");
  const [showAllDomains, setShowAllDomains] = useState(false);
  const [expandedDomainLists, setExpandedDomainLists] = useState<Set<string>>(() => new Set());

  const allCells = useMemo(
    () => objectives.flatMap((objective) => objective.subskills.map((cell) => ({ objective, cell }))),
    [objectives],
  );

  const stateCounts = useMemo(
    () => allCells.reduce<Record<CompetencyState, number>>((counts, { cell }) => {
      counts[cell.state] += 1;
      return counts;
    }, { unseen: 0, acquiring: 0, developing: 0, consolidating: 0, durable: 0 }),
    [allCells],
  );

  const domains = useMemo(
    () => [...new Set(objectives.map((objective) => objective.domain))].sort((left, right) => (
      domainLabel(left).localeCompare(domainLabel(right))
    )),
    [objectives],
  );

  const attentionRows = useMemo(
    () => allCells
      .filter(({ cell }) => Boolean(competencyPracticeHref(cell.independentReceipt)) && (
          cell.isDue
          || (cell.highConfidenceWrong > 0 && cell.state !== "durable")
          || cell.state === "acquiring"
          || cell.state === "developing"
        ))
      .sort(compareAttention)
      .slice(0, 4),
    [allCells],
  );

  const filteredObjectives = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return objectives
      .filter((objective) => {
        if (domainFilter !== "all" && objective.domain !== domainFilter) return false;
        if (stateFilter !== "all" && !objective.subskills.some((cell) => cell.state === stateFilter)) return false;
        if (!normalized) return true;
        const searchable = [
          objective.label,
          conceptLabel(objective.objectiveId),
          domainLabel(objective.domain),
          ...objective.subskills.map((cell) => skillLabel(cell.subskill)),
        ].join(" ").toLocaleLowerCase();
        return searchable.includes(normalized);
      })
      .sort(compareObjectives);
  }, [domainFilter, objectives, query, stateFilter]);

  const domainGroups = useMemo(() => {
    const grouped = new Map<string, CompetencyObjective[]>();
    filteredObjectives.forEach((objective) => {
      const current = grouped.get(objective.domain) ?? [];
      current.push(objective);
      grouped.set(objective.domain, current);
    });
    return [...grouped.entries()]
      .map(([domain, domainObjectives]) => ({ domain, objectives: domainObjectives }))
      .sort((left, right) => {
        const leftDue = left.objectives.some((objective) => objective.subskills.some((cell) => cell.isDue));
        const rightDue = right.objectives.some((objective) => objective.subskills.some((cell) => cell.isDue));
        return Number(rightDue) - Number(leftDue)
          || domainLabel(left.domain).localeCompare(domainLabel(right.domain));
      });
  }, [filteredObjectives]);

  const hasActiveFilters = Boolean(query.trim()) || domainFilter !== "all" || stateFilter !== "all";
  const visibleDomainGroups = showAllDomains || hasActiveFilters
    ? domainGroups
    : domainGroups.slice(0, INITIAL_DOMAIN_COUNT);
  const startedCount = allCells.filter(({ cell }) => cell.state !== "unseen").length;
  const independentlyCheckedCount = allCells.filter(({ cell }) => cell.independentAttempts > 0).length;
  const dueCount = allCells.filter(({ cell }) => cell.isDue).length;

  function resetProgressiveDisclosure() {
    setShowAllDomains(false);
    setExpandedDomainLists(new Set());
  }

  function clearFilters() {
    setQuery("");
    setDomainFilter("all");
    setStateFilter("all");
    resetProgressiveDisclosure();
  }

  function toggleExpandedDomain(domain: string) {
    setExpandedDomainLists((current) => {
      const next = new Set(current);
      if (next.has(domain)) next.delete(domain);
      else next.add(domain);
      return next;
    });
  }

  return (
    <section className={styles.panel} aria-labelledby={headingId}>
      <header className={styles.header}>
        <span className={styles.headerIcon} aria-hidden="true"><BrainCircuit size={21} /></span>
        <div className={styles.headerCopy}>
          <p className="eyebrow">Progress</p>
          <h2 id={headingId}>See what&apos;s strong and what to practice next</h2>
          <p>Start with the skills that need you now, then explore your full ECG skill map when you want more detail.</p>
        </div>
        {!loading && !failed ? (
          <dl className={styles.headerStats} aria-label="Skill progress totals">
            <div><dd>{startedCount}</dd><dt>Practiced</dt></div>
            <div><dd>{independentlyCheckedCount}</dd><dt>Tested</dt></div>
            <div><dd>{dueCount}</dd><dt>Due now</dt></div>
          </dl>
        ) : null}
      </header>

      {loading ? (
        <div className={styles.loading} role="status" aria-live="polite" aria-busy="true">
          <span className={styles.loadingLead} />
          <span /><span /><span />
          <p>Loading your skill progress and review schedule…</p>
        </div>
      ) : null}

      {!loading && failed ? (
        <div className={styles.failure} role="status">
          <AlertTriangle size={22} aria-hidden="true" />
          <div>
            <strong>We couldn&apos;t load your skill progress.</strong>
            <p>Nothing below will be guessed while this information is unavailable.</p>
          </div>
          <button className="button subtle" type="button" onClick={onRetry}>
            <RefreshCw size={15} aria-hidden="true" /> Try again
          </button>
        </div>
      ) : null}

      {!loading && !failed ? (
        <>
          <section className={styles.attentionSection} aria-labelledby={`${generatedId}-attention-heading`}>
            <div className={styles.sectionHeading}>
              <div>
                <p className="eyebrow">Start here</p>
                <h3 id={`${generatedId}-attention-heading`}><Target size={18} aria-hidden="true" /> Practice next</h3>
              </div>
              <p>Reviews due now come first, followed by skills that will benefit from another example.</p>
            </div>
            {attentionRows.length ? (
              <ol className={styles.attentionList}>
                {attentionRows.map(({ objective, cell }, index) => {
                  const practiceHref = competencyPracticeHref(cell.independentReceipt);
                  const objectiveName = conceptLabel(objective.objectiveId);
                  return (
                    <li key={`${objective.objectiveId}:${cell.subskill}`} data-state={cell.state}>
                      <span className={styles.priorityNumber} aria-label={`Priority ${index + 1}`}>{index + 1}</span>
                      <div className={styles.priorityCopy}>
                        <strong>{objectiveName}</strong>
                        <span>{skillLabel(cell.subskill)} · {statePresentation[cell.state].label}</span>
                        <small><CalendarClock size={13} aria-hidden="true" /> {attentionReason(cell)}</small>
                      </div>
                      <div className={styles.priorityEvidence}>
                        <span>{cell.attempts} time{cell.attempts === 1 ? "" : "s"} practiced</span>
                        <span>{cell.distinctSuccessfulEcgs} ECG{cell.distinctSuccessfulEcgs === 1 ? "" : "s"} answered correctly</span>
                      </div>
                      {practiceHref ? (
                        <Link href={practiceHref} aria-label={`Practice ${objectiveName}: ${skillLabel(cell.subskill)}`}>
                          Practice <ArrowRight size={14} aria-hidden="true" />
                        </Link>
                      ) : (
                        <span className={styles.noRoute}>A scored check is not available yet</span>
                      )}
                    </li>
                  );
                })}
              </ol>
            ) : (
              <div className={styles.attentionEmpty}>
                {startedCount === 0 ? <Target size={20} aria-hidden="true" /> : <CheckCircle2 size={20} aria-hidden="true" />}
                <div>
                  <strong>{startedCount === 0 ? "Your progress starts with a quick check." : "You’re caught up."}</strong>
                  <p>{startedCount === 0
                    ? "Complete the 5-ECG starting check from Home. Luna will use it to suggest what to practice next."
                    : "No practiced skill is due for review right now."}</p>
                </div>
                {startedCount === 0 ? <Link href="/rapid?pace=untimed&suggestedLength=5&returnTo=%2Fhome">Start 5-ECG check <ArrowRight size={14} aria-hidden="true" /></Link> : null}
              </div>
            )}
          </section>

          <section className={styles.stateSection} aria-labelledby={`${generatedId}-state-heading`}>
            <div className={styles.sectionHeading}>
              <div>
                <p className="eyebrow">At a glance</p>
                <h3 id={`${generatedId}-state-heading`}>Your progress</h3>
              </div>
              {stateFilter !== "all" ? (
                <button className={styles.textButton} type="button" onClick={() => { setStateFilter("all"); resetProgressiveDisclosure(); }}>
                  Show every skill
                </button>
              ) : null}
            </div>
            <div className={styles.distributionBar} aria-hidden="true">
              {competencyStates.map((state) => stateCounts[state] > 0 ? (
                <span key={state} data-state={state} style={{ flexGrow: stateCounts[state] }} />
              ) : null)}
            </div>
            <div className={styles.stateGrid} role="group" aria-label="Filter skills by progress">
              {competencyStates.map((state) => (
                <button
                  type="button"
                  key={state}
                  className={stateFilter === state ? styles.selectedState : ""}
                  data-state={state}
                  aria-pressed={stateFilter === state}
                  onClick={() => {
                    setStateFilter((current) => current === state ? "all" : state);
                    resetProgressiveDisclosure();
                  }}
                >
                  <span className={styles.stateMarker} aria-hidden="true" />
                  <span className={styles.stateCopy}>
                    <strong>{statePresentation[state].label}</strong>
                    <small>{statePresentation[state].detail}</small>
                  </span>
                  <span className={styles.stateCount}>{stateCounts[state]}</span>
                </button>
              ))}
            </div>
          </section>

          <section className={styles.mapSection} aria-labelledby={`${generatedId}-map-heading`}>
            <div className={styles.mapHeading}>
              <div>
                <p className="eyebrow">Full skill map</p>
                <h3 id={`${generatedId}-map-heading`}>Browse all skills</h3>
                <p>Search by finding or open a domain to see practice history, upcoming reviews, and available checks.</p>
              </div>
              <div className={styles.tools}>
                <label htmlFor={`${generatedId}-competency-search`}>
                  <span>Search skills</span>
                  <span className={styles.searchControl}>
                    <Search size={16} aria-hidden="true" />
                    <input
                      id={`${generatedId}-competency-search`}
                      type="search"
                      value={query}
                      onChange={(event) => { setQuery(event.target.value); resetProgressiveDisclosure(); }}
                      placeholder="Finding or skill"
                    />
                  </span>
                </label>
                <label htmlFor={`${generatedId}-domain-filter`}>
                  <span>Domain</span>
                  <select
                    id={`${generatedId}-domain-filter`}
                    value={domainFilter}
                    onChange={(event) => { setDomainFilter(event.target.value); resetProgressiveDisclosure(); }}
                  >
                    <option value="all">All domains</option>
                    {domains.map((domain) => <option value={domain} key={domain}>{domainLabel(domain)}</option>)}
                  </select>
                </label>
                {hasActiveFilters ? (
                  <button className={styles.clearButton} type="button" onClick={clearFilters}>Clear filters</button>
                ) : null}
              </div>
            </div>

            {hasActiveFilters ? (
              <p className="sr-only" role="status" aria-live="polite">
                {filteredObjectives.length} matching finding{filteredObjectives.length === 1 ? "" : "s"} across {domainGroups.length} domain{domainGroups.length === 1 ? "" : "s"}.
              </p>
            ) : null}

            {visibleDomainGroups.length ? (
              <div className={styles.domainList}>
                {visibleDomainGroups.map(({ domain, objectives: domainObjectives }) => {
                  const domainCells = domainObjectives.flatMap((objective) => objective.subskills);
                  const domainDue = domainCells.filter((cell) => cell.isDue).length;
                  const domainStarted = domainCells.filter((cell) => cell.state !== "unseen").length;
                  const showEveryObjective = expandedDomainLists.has(domain) || hasActiveFilters;
                  const visibleObjectives = showEveryObjective
                    ? domainObjectives
                    : domainObjectives.slice(0, INITIAL_OBJECTIVE_COUNT);
                  return (
                    <details className={styles.domain} key={domain}>
                      <summary>
                        <span className={styles.domainIcon} aria-hidden="true"><BrainCircuit size={18} /></span>
                        <span className={styles.domainCopy}>
                          <strong>{domainLabel(domain)}</strong>
                          <small>{domainStarted
                            ? `${domainStarted} skill${domainStarted === 1 ? "" : "s"} practiced`
                            : "No skills practiced yet"}</small>
                        </span>
                        <span className={styles.domainMeta}>
                          {domainDue ? <span data-due="true">{domainDue} due</span> : <span>No review due</span>}
                          <span>{domainObjectives.length} finding{domainObjectives.length === 1 ? "" : "s"}</span>
                        </span>
                        <ChevronDown className={styles.chevron} size={18} aria-hidden="true" />
                      </summary>
                      <div className={styles.domainBody}>
                        <div className={styles.objectiveList}>
                          {visibleObjectives.map((objective) => {
                            const cells = stateFilter === "all"
                              ? objective.subskills
                              : objective.subskills.filter((cell) => cell.state === stateFilter);
                            const objectiveName = conceptLabel(objective.objectiveId);
                            return (
                              <details className={styles.objective} key={objective.objectiveId}>
                                <summary>
                                  <span className={styles.objectiveState} data-state={objectiveSummaryState(cells)} aria-hidden="true" />
                                  <span className={styles.objectiveCopy}>
                                    <strong>{objectiveName}</strong>
                                    <small>{objectiveProgressLabel(objective)}</small>
                                  </span>
                                  <span className={styles.evidenceBadge}>{objectiveCheckLabel(objective)}</span>
                                  <ChevronDown className={styles.chevron} size={17} aria-hidden="true" />
                                </summary>
                                <div className={styles.subskillList}>
                                  {cells.map((cell) => {
                                    const practiceHref = competencyPracticeHref(cell.independentReceipt);
                                    const subskillName = skillLabel(cell.subskill);
                                    return (
                                      <article className={styles.subskill} key={`${objective.objectiveId}:${cell.subskill}`} data-state={cell.state}>
                                        <header>
                                          <div>
                                            <span className={styles.subskillState}>{statePresentation[cell.state].label}</span>
                                            <h4>{subskillName}</h4>
                                          </div>
                                          {cell.isDue ? <span className={styles.dueBadge}>{cell.dueState === "overdue" ? "Overdue" : "Due now"}</span> : null}
                                        </header>
                                        <p>{cell.independentAttempts
                                          ? `${statePresentation[cell.state].label} after ${cell.independentAttempts} scored ECG check${cell.independentAttempts === 1 ? "" : "s"} across ${cell.distinctEligibleEcgs} different ECG${cell.distinctEligibleEcgs === 1 ? "" : "s"}.`
                                          : cell.attempts
                                            ? "You've completed formative practice for this skill. Complete a scored ECG check to measure your progress."
                                            : "You haven't practiced this skill yet."}</p>
                                        <EvidenceRail cell={cell} label={`${objectiveName}: ${subskillName}`} objectiveId={objective.objectiveId} />
                                        <footer>
                                          {practiceHref ? (
                                            <>
                                              <span>{cell.independentAttempts
                                                ? `${cell.distinctSuccessfulEcgs} different ECG${cell.distinctSuccessfulEcgs === 1 ? "" : "s"} answered correctly.`
                                                : "Start a scored ECG check for this skill."}</span>
                                              <Link href={practiceHref}>Practice this skill <ArrowRight size={14} aria-hidden="true" /></Link>
                                            </>
                                          ) : (
                                            <span className={styles.unavailable}>A scored ECG check isn&apos;t available for this skill yet.</span>
                                          )}
                                        </footer>
                                      </article>
                                    );
                                  })}
                                </div>
                              </details>
                            );
                          })}
                        </div>
                        {!hasActiveFilters && domainObjectives.length > INITIAL_OBJECTIVE_COUNT ? (
                          <button className={styles.showMore} type="button" onClick={() => toggleExpandedDomain(domain)}>
                            {showEveryObjective ? "Show fewer findings" : `Show all ${domainObjectives.length} findings`}
                          </button>
                        ) : null}
                      </div>
                    </details>
                  );
                })}
              </div>
            ) : (
              <div className={styles.noResults}>
                <Search size={20} aria-hidden="true" />
                {hasActiveFilters ? (
                  <div><strong>No findings or skills match those filters.</strong><p>Clear a filter or try a broader finding or skill name.</p></div>
                ) : (
                  <div><strong>No skills are available yet.</strong><p>Your skill list is empty right now, so we won&apos;t guess which ones you&apos;ve started.</p></div>
                )}
                {hasActiveFilters ? <button className="button subtle" type="button" onClick={clearFilters}>Clear filters</button> : null}
              </div>
            )}

            {!hasActiveFilters && domainGroups.length > INITIAL_DOMAIN_COUNT ? (
              <button className={styles.showAllDomains} type="button" onClick={() => setShowAllDomains((current) => !current)}>
                {showAllDomains ? "Show fewer domains" : `Show all ${domainGroups.length} domains`}
              </button>
            ) : null}
          </section>
        </>
      ) : null}
    </section>
  );
}
