import { redirect } from "next/navigation";

type LegacySearchParams = Promise<Record<string, string | string[] | undefined>>;

// The backend tutorial selectors remain active because current Guided scenes use
// them to obtain eligible ECG packets. This table only retires the old learner UI
// and sends saved lesson URLs to the matching canonical Guided module.
const LESSON_DESTINATIONS: Record<string, string> = {
  orientation: "/learn/foundations",
  "lead-territories": "/learn/leads-vectors",
  axis: "/learn/leads-vectors",
  rate: "/learn/rhythm-ectopy",
  "rhythm-basics": "/learn/rhythm-ectopy",
  ectopy: "/learn/rhythm-ectopy",
  "pr-av-block": "/learn/av-brady",
  "qrs-conduction": "/learn/ventricular-conduction",
  "bundle-branch-blocks": "/learn/ventricular-conduction",
  "fascicular-preexcitation": "/learn/ventricular-conduction",
  paced: "/learn/ventricular-conduction",
  "af-flutter": "/learn/tachyarrhythmias",
  svt: "/learn/tachyarrhythmias",
  hypertrophy: "/learn/chambers-voltage",
  "qt-qtc": "/learn/repolarization-safety",
  "ischemia-st-t": "/learn/ischemia-infarction",
  "mi-localization": "/learn/ischemia-infarction",
  "integrated-interpretation": "/learn/integration-transfer",
};

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function LegacyTutorialsPage({ searchParams }: { searchParams: LegacySearchParams }) {
  const params = await searchParams;
  const lesson = first(params.lesson);
  redirect(lesson ? LESSON_DESTINATIONS[lesson] ?? "/learn" : "/learn");
}
