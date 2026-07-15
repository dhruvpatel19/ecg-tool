import type { Metadata } from "next";
import { PublicInfoPage } from "@/components/public/PublicInfoPage";

export const metadata: Metadata = {
  title: "Terms of use",
  description: "Educational-use, account, and responsible-use terms for TRACE.",
};

export default function TermsPage() {
  return (
    <PublicInfoPage
      eyebrow="Terms of use"
      title="Use TRACE for learning—not patient care."
      intro="These product terms describe the intended educational use of this pre-release platform. They require owner and legal review before public enrollment."
    >
      <section>
        <h2>Educational purpose</h2>
        <p>TRACE supports ECG education and formative practice. It does not provide medical advice, a clinical diagnosis, certification of competence, or instructions for the care of a real patient. Always follow institutional policies, supervisors, and validated clinical systems.</p>
      </section>
      <section>
        <h2>Your account</h2>
        <p>Provide accurate registration information, keep credentials private, use your own account, and promptly revoke sessions you do not recognize. Do not attempt to access another learner’s record or bypass assessment controls.</p>
      </section>
      <section>
        <h2>Responsible use</h2>
        <ul>
          <li>Do not enter protected health information or identifiable patient data.</li>
          <li>Do not scrape, redistribute, or reidentify source ECG records contrary to their dataset licenses.</li>
          <li>Do not use automation to manipulate scores, mastery evidence, availability, or another learner’s experience.</li>
          <li>Do not present AI responses or TRACE feedback as clinical authority.</li>
        </ul>
      </section>
      <section>
        <h2>Content, AI, and availability</h2>
        <p>Educational content and model output can be incomplete or wrong. TRACE separates source-dataset labels from authored teaching context, but no label set is exhaustive. Features may change while the platform is under active development.</p>
      </section>
      <section>
        <h2>Licenses</h2>
        <p>ECG datasets retain their source licenses and required attribution. TRACE source code, teaching material, and dataset-derived material may have different licenses; one does not replace another.</p>
      </section>
    </PublicInfoPage>
  );
}
