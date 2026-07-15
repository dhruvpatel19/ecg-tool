import { redirect } from "next/navigation";

export default function LegacyStudyPlanPage() {
  redirect("/profile?tab=plan");
}
