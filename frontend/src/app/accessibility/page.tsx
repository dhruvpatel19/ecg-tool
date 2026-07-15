import type { Metadata } from "next";
import { PublicInfoPage } from "@/components/public/PublicInfoPage";

export const metadata: Metadata = {
  title: "Accessibility",
  description: "Accessibility approach and current interaction support in TRACE.",
};

export default function AccessibilityPage() {
  return (
    <PublicInfoPage
      eyebrow="Accessibility"
      title="ECG learning should remain usable across abilities and devices."
      intro="TRACE is being tested against WCAG 2.2 AA interaction principles, including keyboard access, visible focus, meaningful structure, responsive layouts, and accessible authentication."
    >
      <section>
        <h2>Current interaction support</h2>
        <ul>
          <li>Keyboard-operable navigation, forms, dialogs, and learning controls with visible focus.</li>
          <li>Semantic headings, form labels, status announcements, and non-color-only feedback.</li>
          <li>Responsive layouts and touch targets designed for phone, tablet, and desktop use.</li>
          <li>Password-manager-compatible fields and show/hide password controls.</li>
          <li>Reduced-motion handling for nonessential movement.</li>
        </ul>
      </section>
      <section>
        <h2>ECG-specific limits</h2>
        <p>Waveform interpretation is inherently visual. TRACE pairs ECGs with lead labels, textual prompts, structured measurements, and descriptions where they do not reveal an active answer. Some annotation tasks may require an equivalent non-pointer response path before they can claim full accessibility.</p>
      </section>
      <section>
        <h2>Reporting a barrier</h2>
        <p>Until a public support address is approved, use the support channel provided by your course or deployment administrator. Include the page, device, browser, assistive technology, and what you were trying to do; never include a password or patient information.</p>
      </section>
    </PublicInfoPage>
  );
}
