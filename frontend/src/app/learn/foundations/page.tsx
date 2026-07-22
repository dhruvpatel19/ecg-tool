"use client";

import { CircleAlert, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { ProductionModuleExperience } from "@/components/learning/ProductionModuleExperience";
import { api, type FoundationsNativeMigration } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { M01_FOUNDATIONS_MODULE } from "@/lib/learning/modules/m01Foundations";
import { M02_LEADS_VECTORS_MODULE } from "@/lib/learning/modules/m02LeadsVectors";
import { isFoundationSceneId } from "@/lib/learning/modules/foundationsMigration";

export default function FoundationsModulePage() {
  const { user, loading: authLoading } = useAuth();
  const [migration, setMigration] = useState<FoundationsNativeMigration | null>(null);
  const [migrationError, setMigrationError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (authLoading || !user) return;
    let cancelled = false;
    setMigration(null);
    setMigrationError(null);
    api.migrateFoundationsNativeProgress(user.userId)
      .then((result) => {
        if (cancelled) return;
        const requested = new URLSearchParams(window.location.search).get("scene");
        if (!isFoundationSceneId(requested) && isFoundationSceneId(result.resumeSceneId)) {
          window.history.replaceState(
            null,
            "",
            `/learn/foundations?scene=${encodeURIComponent(result.resumeSceneId)}`,
          );
        }
        setMigration(result);
      })
      .catch(() => {
        if (!cancelled) {
          setMigrationError("Your saved Foundations history could not be prepared safely. Nothing was changed.");
        }
      });
    return () => { cancelled = true; };
  }, [authLoading, retryKey, user]);

  if (authLoading || (user && !migration && !migrationError)) {
    return (
      <main className="page" aria-busy="true">
        <section className="panel pad" role="status">Preparing your Foundations workspace…</section>
      </main>
    );
  }

  if (migrationError) {
    return (
      <main className="page">
        <section className="warning" role="alert">
          <CircleAlert size={18} aria-hidden="true" />
          <span><strong>Foundations is still safe.</strong> {migrationError}</span>
          <button className="button" type="button" onClick={() => setRetryKey((value) => value + 1)}>
            <RefreshCw size={15} aria-hidden="true" /> Retry
          </button>
        </section>
      </main>
    );
  }

  if (!user || !migration) return null;

  return (
    <>
      {migration.result === "source_conflict" ? (
        <div className="page" style={{ paddingBottom: 0 }}>
          <div className="selection-note warning" role="status">
            Your native Foundations work is unchanged. A newer earlier-version snapshot was preserved for support review and was not merged into current completion.
          </div>
        </div>
      ) : null}
      <ProductionModuleExperience
        module={M01_FOUNDATIONS_MODULE}
        totalModules={10}
        nextModule={{ id: M02_LEADS_VECTORS_MODULE.id, shortTitle: M02_LEADS_VECTORS_MODULE.shortTitle }}
      />
    </>
  );
}
