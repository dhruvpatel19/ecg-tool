import { redirect } from "next/navigation";

/** Compatibility route for bookmarks and older emailed links. */
export default function DashboardRedirect() {
  redirect("/home");
}
