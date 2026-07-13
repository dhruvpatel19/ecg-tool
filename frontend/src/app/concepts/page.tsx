"use client";

import { CheckCircle2, Lock, PlayCircle, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ConceptGroup } from "@/lib/types";

export default function ConceptsPage() {
  const [groups, setGroups] = useState<ConceptGroup[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.concepts().then((data) => setGroups(data.practiceGroups)).catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Concept practice</p>
          <h1>Practice only what the data can support</h1>
          <p className="muted">Autonomous curation opens a concept only when enough Tier A/B cases can teach it without asking the tutor to invent missing evidence.</p>
        </div>
      </header>
      {error ? <div className="warning">{error}</div> : null}
      <section className="demo-banner">
        <div>
          <strong><ShieldCheck size={16} aria-hidden="true" /> Evidence-gated concept library</strong>
          <p className="muted">Unavailable subskills are intentionally locked until the case bundle has reliable labels, PTB-XL+ support, and concept-specific confidence.</p>
        </div>
      </section>
      <section className="grid three">
        {groups.map((group) => (
          <article className="panel pad" key={group.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
              <h2>{group.label}</h2>
              <span className={group.enabled ? "pill" : "pill disabled"}>
                {group.enabled ? <CheckCircle2 size={14} aria-hidden="true" /> : <Lock size={14} aria-hidden="true" />}
                {group.availableConceptCount}/{group.concepts.length} ready
              </span>
            </div>
            <p className="muted">
              {group.enabled
                ? `${group.reliableCaseCount} reliable case${group.reliableCaseCount === 1 ? "" : "s"} across this group.`
                : group.reason}
            </p>
            <div className="list" style={{ marginTop: 12 }}>
              {group.concepts.map((concept) => (
                <div className={`list-item objective-row${concept.available ? "" : " disabled"}`} key={concept.id}>
                  <div className="objective-meta">
                    <strong>{concept.label}</strong>
                    {concept.available ? (
                      <Link className="button subtle small" href={`/practice?concept=${encodeURIComponent(concept.id)}`}>
                        <PlayCircle size={15} aria-hidden="true" />
                        Practice
                      </Link>
                    ) : (
                      <span className="pill disabled">
                        <Lock size={13} aria-hidden="true" /> Needs more cases
                      </span>
                    )}
                  </div>
                  <p className="muted" style={{ margin: "6px 0 0" }}>
                    {concept.reliableCaseCount} reliable case{concept.reliableCaseCount === 1 ? "" : "s"}
                    {concept.available ? "" : " — locked until more reliable cases are curated"}
                  </p>
                </div>
              ))}
              {!group.concepts.length ? <p className="muted">No subskills curated for this group yet.</p> : null}
            </div>
            <div style={{ marginTop: 16 }}>
              {group.enabled && group.availableConceptCount > 0 ? (
                <Link
                  className="button primary"
                  href={`/practice?concept=${encodeURIComponent(group.concepts.find((c) => c.available)?.id ?? group.id)}`}
                >
                  <PlayCircle size={17} aria-hidden="true" />
                  Start adaptive practice
                </Link>
              ) : (
                <div className="status-line">
                  <Lock size={15} aria-hidden="true" /> Locked for learner safety
                </div>
              )}
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
