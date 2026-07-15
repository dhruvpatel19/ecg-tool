import type { Metadata } from "next";
import { PublicInfoPage } from "@/components/public/PublicInfoPage";

export const metadata: Metadata = {
  title: "Data sources and attribution",
  description: "Versioned ECG datasets, licenses, provenance, and teaching-context boundaries used by TRACE.",
};

export default function DataSourcesPage() {
  return (
    <PublicInfoPage
      eyebrow="Data sources and attribution"
      title="Real ECGs, versioned sources, visible limits."
      intro="TRACE preserves dataset identity, version, license, and provenance so a teaching claim is never silently presented as source truth. Dataset authors do not endorse TRACE."
    >
      <section>
        <h2>Currently registered sources</h2>
        <h3>PTB-XL 1.0.3</h3>
        <p>10-second 12-lead ECGs, cardiologist-reviewed statements, reports, and metadata. Licensed CC BY 4.0. <a href="https://physionet.org/content/ptb-xl/1.0.3/">Official PhysioNet record</a>.</p>
        <h3>PTB-XL+ 1.0.1</h3>
        <p>Derived measurements, features, fiducials, median beats, and diagnostic statements joined by PTB-XL ECG identifier. Licensed CC BY 4.0. <a href="https://physionet.org/content/ptb-xl-plus/1.0.1/">Official PhysioNet record</a>.</p>
        <h3>Leipzig Heart Center ECG-Database 1.0.0</h3>
        <p>Expert-labelled rhythm windows used only in source-permitted focused and rapid-practice lanes. Licensed ODC-By 1.0. <a href="https://physionet.org/content/leipzig-heart-center-ecg/1.0.0/">Official PhysioNet record</a>.</p>
        <h3>MIT-BIH Malignant Ventricular Ectopy Database 1.0.0</h3>
        <p>Version-pinned rhythm material held in a disconnected foundation store for future reviewed resuscitation teaching. It does not supply pulse, perfusion, treatment, or action-sequence truth. Licensed ODC-By 1.0. <a href="https://physionet.org/content/vfdb/1.0.0/">Official PhysioNet record</a>.</p>
      </section>
      <section>
        <h2>How TRACE changes source material</h2>
        <p>Waveforms may be normalized, downsampled, windowed, or joined with version-compatible derived evidence for efficient teaching display. These transformations are recorded in the corpus manifest.</p>
        <p>Clinical stems are authored teaching context. They did not occur with the people represented by the source ECGs and must not be attributed to the dataset authors.</p>
      </section>
      <section>
        <h2>License reminder</h2>
        <p>CC BY 4.0 and ODC-By 1.0 require attribution. Any redistribution must preserve the applicable source, version, license link, and indication of changes.</p>
      </section>
    </PublicInfoPage>
  );
}
