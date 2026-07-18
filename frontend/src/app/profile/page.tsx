import { redirect } from "next/navigation";

const PANEL_BY_LEGACY_TAB: Record<string, string> = {
  overview: "",
  plan: "plan",
  competencies: "competencies",
  activity: "activity",
};

/**
 * Preserve old My Learning deep links while keeping a single canonical
 * authenticated dashboard. Preferences now live with the rest of Account.
 */
export default async function ProfileRedirect({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string | string[] }>;
}) {
  const params = await searchParams;
  const tab = Array.isArray(params.tab) ? params.tab[0] : params.tab;
  if (tab === "preferences") redirect("/account#learning-preferences");
  const panel = tab ? PANEL_BY_LEGACY_TAB[tab] : "";
  redirect(panel ? `/home?panel=${panel}` : "/home");
}
