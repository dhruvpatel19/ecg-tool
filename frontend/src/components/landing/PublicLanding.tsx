import {
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  Check,
  CircleGauge,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  Stethoscope,
  TimerReset,
} from "lucide-react";
import Link from "next/link";
import styles from "./PublicLanding.module.css";

const learningModes = [
  {
    number: "01",
    title: "Guided learning",
    short: "Learn a reliable sequence",
    description: "Build the mental model with interactive explanations and support when you get stuck.",
    href: "/login?mode=register&next=%2Flearn",
    icon: BookOpenCheck,
  },
  {
    number: "02",
    title: "Focused practice",
    short: "Repeat one visual skill",
    description: "Compare one finding across real ECGs, normal tracings, and close look-alikes.",
    href: "/login?mode=register&next=%2Ftrain",
    icon: BrainCircuit,
  },
  {
    number: "03",
    title: "Rapid practice",
    short: "Build speed through varied reads",
    description: "Answer focused or complete ECG questions with adaptive selection and fair, task-sized timing.",
    href: "/login?mode=register&next=%2Frapid",
    icon: TimerReset,
  },
  {
    number: "04",
    title: "Clinical cases",
    short: "Use the ECG in context",
    description: "Work through evolving patient scenarios and decide what information or action comes next.",
    href: "/login?mode=register&next=%2Fpractice",
    icon: Stethoscope,
  },
];

// A deidentified Lead II rhythm strip from PTB-XL case 3 (CC BY 4.0),
// downsampled in the existing Foundations teaching corpus. Keeping the small
// approved sample here avoids loading the full case file on the public page.
const ptbPreviewLeadII = [
  -0.079,-0.057,-0.061,0.251,0.248,-0.092,-0.09,-0.075,-0.067,-0.096,-0.073,-0.025,-0.02,0.015,0.089,0.095,0.145,0.187,0.244,0.249,0.156,0.073,0.062,0.047,0.008,0.04,0.027,0.012,-0.021,-0.031,-0.024,-0.057,-0.063,-0.092,-0.086,-0.055,-0.034,-0.08,-0.067,-0.073,-0.053,-0.034,-0.044,-0.015,0.011,0.095,0.098,0.057,0.055,0.029,-0.003,0.033,0.542,0.103,-0.021,-0.058,-0.03,-0.034,-0.055,-0.049,-0.042,-0.019,-0.002,0.018,0.026,0.004,0.029,-0.007,0.045,-0.002,-0.067,-0.123,-0.148,-0.172,-0.167,-0.14,-0.161,-0.15,-0.139,-0.113,-0.125,-0.117,-0.112,-0.105,-0.106,-0.057,-0.045,-0.036,-0.044,-0.074,-0.052,0.003,-0.023,0.013,0.083,0.06,0.006,-0.046,-0.021,-0.058,0.127,0.639,0.016,-0.062,-0.059,-0.031,0.003,-0.016,-0.028,-0.012,0.033,0.036,0.041,0.11,0.112,0.132,0.144,0.138,0.083,0.094,0.084,0.076,0.126,0.132,0.135,0.159,0.127,0.115,0.102,0.099,0.06,0.076,0.066,0.071,0.084,0.101,0.093,0.085,0.085,0.128,0.134,0.144,0.22,0.234,0.144,0.112,0.071,0.034,0.156,0.701,0.122,0.07,0.054,0.073,0.058,0.055,0.104,0.13,0.119,0.104,0.087,0.141,0.128,0.169,0.184,0.139,0.06,0.026,-0.049,-0.059,-0.07,-0.059,-0.018,0.03,0.033,0.028,0.018,0.004,-0.014,-0.043,-0.005,-0.011,-0.042,-0.029,-0.023,-0.034,-0.036,-0.06,-0.051,-0.034,0.055,0.049,-0.029,-0.028,-0.009,-0.04,0.097,0.621,0.015,0.022,0.004,0.023,0.001,-0.051,-0.084,-0.096,-0.129,-0.145,-0.093,-0.075,-0.066,-0.059,-0.023,-0.066,-0.079,-0.15,-0.187,-0.226,-0.221,-0.258,-0.191,-0.163,-0.208,-0.173,-0.199,-0.217,-0.16,-0.177,-0.204,-0.193,-0.185,-0.176,-0.162,-0.161,-0.16,-0.147,-0.136,-0.135,-0.177,-0.235,-0.202,-0.188,0.089,0.251,-0.099,-0.16,-0.159,-0.114,-0.155,-0.133,-0.123,-0.126,-0.095,-0.075,-0.077,-0.048,-0.02,0.042,0.051,-0.029,-0.09,-0.132,-0.142,-0.159,-0.183,-0.17,-0.169,-0.176,-0.183,-0.2,-0.192,-0.176,-0.205,-0.209,-0.231,-0.204,-0.222,-0.206,-0.184,-0.249,-0.225,-0.167,-0.119,-0.15,-0.192,-0.249,-0.256,-0.241,-0.04,0.225,-0.198,-0.206,-0.201,-0.192,-0.181,-0.168,-0.159,-0.164,-0.13,-0.101,
];

const ptbPreviewPoints = ptbPreviewLeadII
  .map((value, index) => {
    const x = index * 760 / (ptbPreviewLeadII.length - 1);
    const y = 110 - value * 100;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  })
  .join(" ");

export function PublicLanding() {
  return (
    <div className={styles.landing}>
      <section className={styles.hero} aria-labelledby="landing-title">
        <div className={styles.heroCopy}>
          <p className={styles.kicker}>ECG learning for medical students</p>
          <h1 id="landing-title">Read ECGs with a method you can trust.</h1>
          <p className={styles.heroLead}>
            Learn the framework, strengthen specific findings, practice complete interpretations,
            and use the ECG inside realistic patient scenarios.
          </p>
          <div className={styles.heroActions}>
            <Link className={styles.primaryAction} href="/login?mode=register">
              Create your account <ArrowRight size={17} aria-hidden="true" />
            </Link>
            <Link className={styles.secondaryAction} href="/login">Sign in</Link>
          </div>
          <p className={styles.accountNote}>
            <LockKeyhole size={17} aria-hidden="true" />
            <span>An account is required so every attempt, competency, and recommendation stays connected.</span>
          </p>
          <ul className={styles.heroChecks} aria-label="Platform highlights">
            <li><Check size={15} aria-hidden="true" /> Real deidentified ECGs</li>
            <li><Check size={15} aria-hidden="true" /> Skill-level feedback</li>
            <li><Check size={15} aria-hidden="true" /> Adaptive practice</li>
          </ul>
        </div>

        <div className={styles.preview} aria-label="TRACE practice workspace preview using a real deidentified PTB-XL ECG">
          <div className={styles.previewTopline}>
            <span><i aria-hidden="true" /> Practice preview</span>
            <span className={styles.realBadge}><ShieldCheck size={13} aria-hidden="true" /> Real teaching ECG</span>
          </div>
          <div className={styles.previewWorkspace}>
            <div className={styles.traceArea}>
              <div className={styles.traceMeta}>
                <span>Focused read · ECG 2 of 10</span>
                <small>Tracing ready</small>
              </div>
              <svg viewBox="0 0 760 220" role="img" aria-label="Lead II rhythm strip from a deidentified PTB-XL ECG" preserveAspectRatio="none">
                <defs>
                  <pattern id="ptb-small-grid" width="12" height="12" patternUnits="userSpaceOnUse">
                    <path d="M 12 0 L 0 0 0 12" fill="none" stroke="#f2dedd" strokeWidth="0.7" />
                  </pattern>
                  <pattern id="ptb-grid" width="60" height="60" patternUnits="userSpaceOnUse">
                    <rect width="60" height="60" fill="url(#ptb-small-grid)" />
                    <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#e8c4c1" strokeWidth="1" />
                  </pattern>
                </defs>
                <rect width="760" height="220" fill="url(#ptb-grid)" />
                <polyline
                  points={ptbPreviewPoints}
                  fill="none"
                  stroke="#a73532"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  vectorEffect="non-scaling-stroke"
                />
              </svg>
              <div className={styles.traceSource}>PTB-XL · CC BY 4.0</div>
            </div>
            <div className={styles.previewQuestion}>
              <div>
                <span>Question 1 of 3</span>
                <strong>Which rhythm best explains this tracing?</strong>
              </div>
              <div className={styles.previewChoices} aria-hidden="true">
                <span>Sinus rhythm</span>
                <span className={styles.choiceSelected}>Atrial fibrillation</span>
                <span>Atrial flutter</span>
                <span>Multifocal atrial tachycardia</span>
              </div>
              <small>Next: rate response · closest mimic</small>
            </div>
          </div>
          <div className={styles.previewFooter}>
            <CircleGauge size={15} aria-hidden="true" />
            <span>Your reasoning—not just the final answer—shapes what you practice next.</span>
          </div>
        </div>
      </section>

      <section className={styles.pathSection} id="learning-modes" aria-labelledby="modes-title">
        <div className={styles.sectionIntro}>
          <p className={styles.kicker}>One learning record, four ways to build it</p>
          <h2 id="modes-title">Move from first principles to clinical context.</h2>
          <p>Choose the kind of work you need today. Evidence from every mode contributes to the same skill picture.</p>
        </div>
        <ol className={styles.modePath}>
          {learningModes.map(({ number, title, short, description, href, icon: Icon }) => (
            <li key={title}>
              <Link href={href} aria-label={`Create an account to start ${title.toLowerCase()}`}>
                <span className={styles.modeNumber}>{number}</span>
                <span className={styles.modeIcon}><Icon size={20} aria-hidden="true" /></span>
                <span className={styles.modeCopy}>
                  <h3>{title}</h3>
                  <small>{short}</small>
                  <em>{description}</em>
                </span>
                <ArrowRight size={17} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ol>
      </section>

      <section className={styles.methodSection} id="how-it-works" aria-labelledby="method-title">
        <div className={styles.methodCopy} id="why-trace">
          <p className={styles.kicker}>Practice with a purpose</p>
          <h2 id="method-title">The tracing stays at the center of the work.</h2>
          <p>
            TRACE tracks the evidence underneath an answer: what you recognized, measured,
            localized, or used correctly in context.
          </p>
          <ul>
            <li><span>01</span><div><strong>Look before labeling</strong><p>Mark regions, compare leads, and enter measurements instead of guessing from a list.</p></div></li>
            <li><span>02</span><div><strong>Learn from the miss</strong><p>Feedback separates a recognition error from a measurement, localization, or reasoning error.</p></div></li>
            <li><span>03</span><div><strong>Return at the right time</strong><p>Future practice responds to recurring misses, confidence, retention, and transfer to new ECGs.</p></div></li>
          </ul>
        </div>

        <aside className={styles.coachCard} aria-label="Example of an adaptive learning recommendation">
          <div className={styles.coachHeading}><Sparkles size={18} aria-hidden="true" /><span>Adaptive learning coach</span></div>
          <p className={styles.coachLead}>You identify atrial fibrillation reliably, but fast irregular rhythms still lower your confidence.</p>
          <div className={styles.coachPlan}>
            <span>Suggested next</span>
            <strong>Compare AF with rapid ventricular response against regular narrow-complex tachycardia.</strong>
            <small>10 focused ECGs · then 5 mixed reads</small>
          </div>
          <p className={styles.coachBoundary}>
            <ShieldCheck size={15} aria-hidden="true" />
            The coach explains recommendations and supports questions. It cannot award mastery or make clinical diagnoses.
          </p>
        </aside>
      </section>

      <section className={styles.finalCta} aria-labelledby="final-cta-title">
        <div>
          <p className={styles.kicker}>Start with one account</p>
          <h2 id="final-cta-title">Build an ECG approach you can carry onto the wards.</h2>
        </div>
        <div>
          <Link className={styles.primaryAction} href="/login?mode=register">Create your account <ArrowRight size={17} aria-hidden="true" /></Link>
          <Link href="/login">Already have an account?</Link>
        </div>
      </section>

      <footer className={styles.footer} role="contentinfo">
        <span>TRACE · ECG learning for medical students</span>
        <nav aria-label="Legal and product information">
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
          <Link href="/accessibility">Accessibility</Link>
          <Link href="/data-sources">Data sources</Link>
        </nav>
        <span>For education only. Not for clinical diagnosis or patient care.</span>
      </footer>
    </div>
  );
}
