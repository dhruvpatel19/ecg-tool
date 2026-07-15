import type { Metadata } from "next";
import { PublicInfoPage } from "@/components/public/PublicInfoPage";

export const metadata: Metadata = {
  title: "Privacy and learning data",
  description: "How TRACE stores, protects, and uses account and ECG learning data.",
};

export default function PrivacyPage() {
  return (
    <PublicInfoPage
      eyebrow="Privacy and learning data"
      title="Your learning record should help you—not surprise you."
      intro="TRACE uses account and learning data to secure your account, preserve your work, and choose useful practice. It is an educational platform, not a clinical record system."
    >
      <section>
        <h2>What TRACE stores</h2>
        <ul>
          <li>Your display name, verified email address, password hash, and account-security settings.</li>
          <li>Your answers, confidence, measurements, annotations, attempts, session history, and competency evidence.</li>
          <li>Your learning preferences, saved work, recommendations, and conversations with the learning coach.</li>
          <li>Limited technical and security events needed to protect sessions, enforce rate limits, and diagnose failures.</li>
        </ul>
        <p>TRACE does not store your password in readable form. Authentication sessions use secure, browser-protected cookies.</p>
      </section>
      <section>
        <h2>How the data is used</h2>
        <p>Learning evidence is used to restore your work, explain feedback, estimate skill development, and select the next useful activity. Email is used for sign-in, verification, account recovery, and important security messages—not advertising.</p>
        <p>When an AI learning feature is enabled, the minimum relevant learning context, your question, and the applicable teaching material may be sent to the configured AI provider. Do not enter patient names, record numbers, dates of birth, or other identifiable patient information.</p>
      </section>
      <section>
        <h2>Your controls</h2>
        <p>Account settings provide a password-protected progress export, session revocation, password changes, and permanent deletion of the live account record. Authenticated learning records are not removed automatically merely because you stop studying.</p>
        <p>Deleting your account removes the live account and learning record. Protected application backups expire after 90 days and disk snapshots after 14 days, so deletion cannot be described as immediate erasure from every backup.</p>
      </section>
      <section>
        <h2>Public datasets and patient privacy</h2>
        <p>Teaching ECGs come from versioned, publicly released research datasets and are presented without learner-visible patient identifiers. TRACE-authored case context is educational and must not be treated as the history of the person whose ECG is shown.</p>
      </section>
    </PublicInfoPage>
  );
}
