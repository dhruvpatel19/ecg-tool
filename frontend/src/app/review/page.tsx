import { redirect } from "next/navigation";

export default function LegacyStudyPlanPage() {
  redirect("/home?panel=plan");
}
