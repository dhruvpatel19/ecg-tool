"use client";

import { Activity, AlertTriangle, ArrowRight, BrainCircuit, Search, Target } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api, type AdaptivePlan, type CompetencyObjective, type CompetencyState } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { conceptLabel } from "@/lib/coordinates";
import type { LearnerProfile } from "@/lib/types";

function masteryClass(value: number) {
  if (value < 0.45) return "low";
  if (value < 0.7) return "medium";
  return "";
}

export default function ProfilePage() {
  const { user } = useAuth();
  const [profile, setProfile] = useState<LearnerProfile | null>(null);
  const [adaptivePlan, setAdaptivePlan] = useState<AdaptivePlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subskillQuery, setSubskillQuery] = useState("");
  const [showAllSubskills, setShowAllSubskills] = useState(false);
  const [competencyObjectives, setCompetencyObjectives] = useState<CompetencyObjective[]>([]);
  const [domainFilter, setDomainFilter] = useState("all");
  const [stateFilter, setStateFilter] = useState<"all" | CompetencyState>("all");
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.allSettled([api.profile(), api.adaptivePlan(), api.competencies()])
      .then(([profileResult, planResult, competenciesResult]) => {
        if (cancelled) return;
        if (profileResult.status === "fulfilled") setProfile(profileResult.value);
        else setProfile(null);
        if (planResult.status === "fulfilled") setAdaptivePlan(planResult.value);
        else setAdaptivePlan(null);
        if (competenciesResult.status === "fulfilled") setCompetencyObjectives(competenciesResult.value.objectives);
        else setCompetencyObjectives([]);
        const failures = [profileResult, planResult, competenciesResult].filter((result) => result.status === "rejected");
        if (failures.length) setError(`${failures.length} profile section${failures.length === 1 ? "" : "s"} could not be loaded.`);
      });
    return () => { cancelled = true; };
  }, [retryKey]);

  const practiced = useMemo(
    () =>
      [...(profile?.mastery ?? [])]
        .filter((row) => row.attempts > 0)
        .sort((a, b) => {
          const aTime = a.lastPracticedAt ? Date.parse(a.lastPracticedAt) : 0;
          const bTime = b.lastPracticedAt ? Date.parse(b.lastPracticedAt) : 0;
          return bTime - aTime;
        }),
    [profile],
  );

  const priorityObjectives = useMemo(
    () =>
      [...(profile?.mastery ?? [])].filter((row) => row.attempts > 0).sort((a, b) => {
        if (a.mastery !== b.mastery) return a.mastery - b.mastery;
        return b.highConfidenceWrong - a.highConfidenceWrong;
      }),
    [profile],
  );
  const totalAttempts = profile?.attemptCount ?? 0;
  const highConfidenceMisses = profile?.mastery.reduce((sum, row) => sum + row.highConfidenceWrong, 0) ?? 0;
  const subskillRows = useMemo(
    () => [...(profile?.subskillMastery ?? [])].sort((a, b) => {
      if (a.independentMastery !== b.independentMastery) return a.independentMastery - b.independentMastery;
      return b.highConfidenceWrong - a.highConfidenceWrong;
    }),
    [profile],
  );
  const independentlyObservedRows = subskillRows.filter((row) => row.independentAttempts > 0);
  const independentAverage = independentlyObservedRows.length
    ? Math.round((independentlyObservedRows.reduce((sum, row) => sum + row.independentMastery, 0) / independentlyObservedRows.length) * 100)
    : null;
  const competencyDomains = useMemo(() => [...new Set(competencyObjectives.map((objective) => objective.domain))].sort(), [competencyObjectives]);
  const competencyCounts = useMemo(() => competencyObjectives
    .flatMap((objective) => objective.subskills)
    .reduce<Record<CompetencyState, number>>((counts, cell) => {
      counts[cell.state] += 1;
      return counts;
    }, { unseen: 0, acquiring: 0, developing: 0, consolidating: 0, durable: 0 }), [competencyObjectives]);
  const retentionDue = competencyObjectives.flatMap((objective) => objective.subskills).filter((cell) => cell.isDue);
  const overdueRetention = retentionDue.filter((cell) => cell.dueState === "overdue").length;
  const filteredCompetencyObjectives = useMemo(() => {
    const query = subskillQuery.trim().toLowerCase();
    return competencyObjectives.filter((objective) => {
      if (domainFilter !== "all" && objective.domain !== domainFilter) return false;
      if (stateFilter !== "all" && !objective.subskills.some((cell) => cell.state === stateFilter)) return false;
      if (!query) return true;
      return objective.label.toLowerCase().includes(query)
        || objective.objectiveId.toLowerCase().includes(query)
        || objective.domain.toLowerCase().includes(query)
        || objective.subskills.some((cell) => cell.subskill.replaceAll("_", " ").includes(query));
    });
  }, [competencyObjectives, domainFilter, stateFilter, subskillQuery]);
  const visibleCompetencyObjectives = showAllSubskills
    ? filteredCompetencyObjectives
    : filteredCompetencyObjectives.slice(0, 18);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Learner profile</p>
          <h1>{profile?.displayName ?? "Guest learner"} progress</h1>
          <p className="muted">Independent accuracy and spaced retention are tracked separately. Repeating cases today cannot substitute for successful retrieval across later dates and distinct real ECGs.</p>
        </div>
        <Link className="button primary" href="/practice">
          <Activity size={17} aria-hidden="true" />
          Practice now
        </Link>
      </header>
      {error ? <div className="warning">Learner evidence is incomplete. {error} <button className="button subtle small" type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry</button></div> : null}
      <section className="progress-summary" style={{ marginBottom: 16 }}>
        <div className="metric">
          <span className="metric-label">Independent competency</span>
          <strong>{independentAverage === null ? "Not yet assessed" : `${independentAverage}%`}</strong>
          <span className="metric-subtext">Only independently observed concept × subskill transfer.</span>
        </div>
        <div className="metric">
          <span className="metric-label">Recent attempts</span>
          <strong>{totalAttempts}</strong>
          <span className="metric-subtext">{user ? `Saved to ${user.displayName || user.username}'s profile.` : "Guest mode is not a private student record; sign in for private, durable tracking."}</span>
        </div>
        <div className="metric">
          <span className="metric-label">Retention checks due</span>
          <strong>{retentionDue.length}</strong>
          <span className="metric-subtext">{overdueRetention ? `${overdueRetention} overdue. ` : ""}{highConfidenceMisses} high-confidence misses remain weighted for review.</span>
        </div>
      </section>
      <section className="panel pad profile-subskill-panel" style={{ marginBottom: 16 }}>
        <div className="section-heading-row">
          <div><p className="eyebrow">Objective explorer</p><h2><BrainCircuit size={18} aria-hidden="true" /> Every objective, every eligible subskill</h2></div>
          <p>Unseen means no observation—not a low score. Formative understanding and independent transfer stay separate.</p>
        </div>
        {competencyObjectives.length ? <>
          <div className="profile-state-summary" aria-label="Competency cells by state">
            {(Object.entries(competencyCounts) as Array<[CompetencyState, number]>).map(([state, count]) => (
              <button key={state} type="button" className={stateFilter === state ? "active" : ""} aria-pressed={stateFilter === state} onClick={() => { setStateFilter(stateFilter === state ? "all" : state); setShowAllSubskills(false); }}>
                <strong>{count}</strong><span>{state}</span>
              </button>
            ))}
          </div>
          <div className="profile-competency-tools">
            <label htmlFor="profile-competency-search"><Search size={15} aria-hidden="true" /> Find a competency</label>
            <input
              id="profile-competency-search"
              type="search"
              value={subskillQuery}
              onChange={(event) => { setSubskillQuery(event.target.value); setShowAllSubskills(false); }}
              placeholder="Search concept or subskill"
            />
            <select aria-label="Filter objectives by domain" value={domainFilter} onChange={(event) => { setDomainFilter(event.target.value); setShowAllSubskills(false); }}>
              <option value="all">All domains</option>
              {competencyDomains.map((domain) => <option value={domain} key={domain}>{domain}</option>)}
            </select>
            <select aria-label="Filter competencies by state" value={stateFilter} onChange={(event) => { setStateFilter(event.target.value as "all" | CompetencyState); setShowAllSubskills(false); }}>
              <option value="all">All evidence states</option>
              {(Object.keys(competencyCounts) as CompetencyState[]).map((state) => <option value={state} key={state}>{state} · {competencyCounts[state]}</option>)}
            </select>
            <span className="muted">Showing {visibleCompetencyObjectives.length} of {filteredCompetencyObjectives.length} objectives</span>
          </div>
          <div className="profile-objective-list">
          {visibleCompetencyObjectives.map((objective) => {
            const visibleCells = stateFilter === "all" ? objective.subskills : objective.subskills.filter((cell) => cell.state === stateFilter);
            const observed = objective.subskills.filter((cell) => cell.state !== "unseen").length;
            return <details className="profile-objective" key={objective.objectiveId}>
              <summary>
                <span><strong>{objective.label}</strong><small>{objective.domain} · {observed}/{objective.subskills.length} subskills observed</small></span>
                <span className="pill">{objective.evidenceCeiling.replaceAll("_", " ")}</span>
              </summary>
              <div className="profile-objective-cells">
                {visibleCells.map((cell) => {
                  const trainConcept = objective.caseConcepts[0] ?? objective.objectiveId;
                  return <article key={`${objective.objectiveId}:${cell.subskill}`} className={`profile-objective-cell state-${cell.state}`}>
                    <div><strong>{cell.subskill.replaceAll("_", " ")}</strong><span>{cell.state}{cell.isDue ? ` · ${cell.dueState}` : ""}</span></div>
                    {cell.state === "unseen" ? <p>No observation yet.</p> : <p>{Math.round(cell.independentMastery * 100)}% independent · {Math.round(cell.formativeScore * 100)}% formative · {cell.attempts} attempts</p>}
                    {cell.independentAttempts ? <small>
                      {cell.distinctSuccessfulEcgs} distinct successful ECG{cell.distinctSuccessfulEcgs === 1 ? "" : "s"} · {cell.spacedRetrievals} spaced retrieval{cell.spacedRetrievals === 1 ? "" : "s"} · {cell.stabilityDays.toFixed(1)}d stability
                      {cell.nextDueAt ? ` · ${cell.isDue ? "due" : "next"} ${new Date(cell.nextDueAt).toLocaleDateString()}` : ""}
                    </small> : null}
                    {cell.evidenceUncertainty ? <small>{cell.evidenceUncertainty}</small> : null}
                    {objective.caseConcepts.length ? <Link href={`/train?concept=${encodeURIComponent(trainConcept)}&subskill=${encodeURIComponent(cell.subskill)}`}>Train this skill <ArrowRight size={13} /></Link> : null}
                  </article>;
                })}
              </div>
            </details>;
          })}
          </div>
          {!visibleCompetencyObjectives.length ? <div className="selection-note">No objectives match those filters.</div> : null}
          {filteredCompetencyObjectives.length > 18 ? (
            <button className="button subtle profile-show-all" type="button" onClick={() => setShowAllSubskills((current) => !current)}>
              {showAllSubskills ? "Show priority objectives" : `Show all ${filteredCompetencyObjectives.length} objectives`}
            </button>
          ) : null}
        </> : <div className="selection-note">Loading the complete objective registry…</div>}
      </section>
      <div className="grid two">
        <section className="panel pad">
          <h2><Target size={18} aria-hidden="true" /> Legacy concept-level signal</h2>
          <p className="muted">This aggregate remains for existing Rapid and Clinical attempts; the competency cards above are the production learning model.</p>
          {profile?.weakObjectives.length && practiced.length ? (
            <div className="selection-note" style={{ marginBottom: 14 }}>
              <strong>Focus queue</strong>
              <div className="pill-row" style={{ marginTop: 8 }}>
                {profile.weakObjectives.slice(0, 8).map((objective) => (
                  <span className="pill" key={objective}>{conceptLabel(objective)}</span>
                ))}
              </div>
            </div>
          ) : null}
          {practiced.length ? (
            <div className="profile-highlight">
              <h3>Recent mastery movement</h3>
              <div className="list">
                {practiced.slice(0, 4).map((row) => (
                  <div className="list-item objective-row" key={row.objective}>
                    <div className="objective-meta">
                      <strong>{conceptLabel(row.objective)}</strong>
                      <span className="muted">{Math.round(row.mastery * 100)}%</span>
                    </div>
                    <div className={`mastery-bar ${masteryClass(row.mastery)}`} aria-hidden="true"><span style={{ width: `${Math.round(row.mastery * 100)}%` }} /></div>
                    <p className="muted" style={{ margin: "8px 0 0" }}>{row.attempts} attempts, {row.correct} correct</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          <div className="list">
            {priorityObjectives.length ? priorityObjectives.slice(0, 24).map((row) => (
              <div className="list-item objective-row" key={row.objective}>
                <div className="objective-meta">
                  <strong>{conceptLabel(row.objective)}</strong>
                  <span className="muted">{Math.round(row.mastery * 100)}%</span>
                </div>
                <div className={`mastery-bar ${masteryClass(row.mastery)}`} aria-hidden="true"><span style={{ width: `${Math.round(row.mastery * 100)}%` }} /></div>
                <p className="muted" style={{ margin: "8px 0 0" }}>{row.attempts} attempts, {row.correct} correct, {row.highConfidenceWrong} high-confidence misses</p>
              </div>
            )) : <p className="muted">No concept-level evidence has been recorded yet. Complete a baseline read to establish a starting point.</p>}
          </div>
        </section>

        <aside className="grid">
          <section className="panel pad">
            <h2>Recommended Next</h2>
            {adaptivePlan ? (
              <>
                <strong>{adaptivePlan.basis.baselineNeeded
                  ? "Untimed mixed baseline"
                  : adaptivePlan.primary
                    ? `${adaptivePlan.primary.label} · ${adaptivePlan.primary.subskill.replaceAll("_", " ")}`
                    : "No eligible target yet"}</strong>
                <p className="muted">{adaptivePlan.primary?.reason ?? adaptivePlan.explanation}</p>
                <div className="pill-row">
                  <span className="pill">{adaptivePlan.basis.dueCompetencies} due</span>
                  <span className="pill">{adaptivePlan.basis.highConfidenceMisses} calibration flags</span>
                  {adaptivePlan.primary ? <span className="pill">{adaptivePlan.primary.eligibleDistinct.toLocaleString()} eligible ECGs</span> : null}
                </div>
                <Link
                  className="button primary"
                  href="/review"
                  style={{ marginTop: 14 }}
                >
                  <Activity size={17} aria-hidden="true" />
                  Open full mastery plan
                </Link>
              </>
            ) : (
              <p className="muted">Loading recommendation...</p>
            )}
          </section>
          <section className="panel pad">
            <h2><AlertTriangle size={18} aria-hidden="true" /> Misconceptions</h2>
            <div className="list">
              {profile?.misconceptions.length ? (
                profile.misconceptions.map((item) => (
                  <div className="list-item" key={item.tag}>
                    <strong>{item.tag.replaceAll("_", " ")}</strong>
                    <p className="muted">{item.count} recent occurrence{item.count === 1 ? "" : "s"}; reinforce with targeted ECG evidence before increasing difficulty.</p>
                  </div>
                ))
              ) : (
                <p className="muted">No misconception tags yet. They appear after missed or overcalled grounded objectives.</p>
              )}
            </div>
          </section>
          <section className="panel pad">
            <h2>Recent Attempts</h2>
            <div className="list">
              {profile?.recentAttempts.length ? (
                profile.recentAttempts.map((attempt) => (
                  <div className="list-item" key={`${attempt.caseId}-${attempt.createdAt}`}>
                    <strong>{attempt.caseId}</strong>
                    <p className="muted">{attempt.mode} · score {Math.round(attempt.score * 100)}% · confidence {attempt.confidence}</p>
                  </div>
                ))
              ) : (
                <p className="muted">Submit a practice case to populate recent attempts.</p>
              )}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
