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
        <h3>ECG Fragment Database for the Exploration of Dangerous Arrhythmia 1.0.0</h3>
        <p>Short, source-author-labelled, single-channel MLII fragments derived from the MIT-BIH Malignant Ventricular Ectopy Database and used only in the explicit Rapid Emergency lane for rhythm recognition and discrimination. A fragment does not establish pulse, stability, arrest, shockability, treatment, or management. The source VTTdP label is presented conservatively as polymorphic ventricular tachycardia unless preceding long-QT evidence is available. Licensed ODC-By 1.0. <a href="https://physionet.org/content/ecg-fragment-high-risk-label/1.0.0/">Official PhysioNet record</a>.</p>
        <h3>STAFF III Database 1.0.0</h3>
        <p>Offline, reviewer-locked comparison candidates grouped by the source protocol as baseline, controlled balloon occlusion, and recovery. STAFF III is not connected to learner routes and does not supply morphology answers, spontaneous acute-coronary-syndrome claims, treatment response, or management truth without separate adjudication. Licensed ODC-By 1.0. <a href="https://physionet.org/content/staffiii/1.0.0/">Official PhysioNet record</a>.</p>
      </section>
      <section>
        <h2>How TRACE changes source material</h2>
        <p>Waveforms may be normalized, downsampled, windowed, or joined with version-compatible derived evidence for efficient teaching display. These transformations are recorded in the corpus manifest.</p>
        <p>Clinical stems are authored teaching context. They did not occur with the people represented by the source ECGs and must not be attributed to the dataset authors.</p>
      </section>
      <section>
        <h2>License reminder</h2>
        <p>CC BY 4.0 and ODC-By 1.0 require attribution. Any redistribution must preserve the applicable source, version, license link, and indication of changes.</p>
        <p>TRACE displays transformed content from the <a href="https://physionet.org/content/ecg-fragment-high-risk-label/1.0.0/">ECG Fragment Database for the Exploration of Dangerous Arrhythmia 1.0.0</a>, made available under the <a href="https://physionet.org/content/ecg-fragment-high-risk-label/view-license/1.0.0/">Open Data Commons Attribution License v1.0</a>. TRACE creates the opaque learner packets and separately authored teaching context; the dataset authors do not endorse TRACE.</p>
      </section>
    </PublicInfoPage>
  );
}
