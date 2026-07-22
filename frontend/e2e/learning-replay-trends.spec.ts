import { expect, test, type Page } from "@playwright/test";
import { collectConsoleErrors } from "./helpers";

const sessionRef = "lsr1_frontend_replay_contract";
const ecgRef = `ec_${"A".repeat(43)}`;
const comparisonRef = `ec_${"B".repeat(43)}`;

function waveformPayload(reference: string) {
  return {
    caseId: reference,
    samplingFrequency: 100,
    durationSec: 10,
    startSec: 0,
    endSec: 10,
    leads: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"].map((lead) => ({
      lead,
      points: [{ timeSec: 0, amplitudeMv: 0 }, { timeSec: 0.5, amplitudeMv: lead === "II" ? 0.8 : 0.2 }, { timeSec: 1, amplitudeMv: 0 }],
    })),
  };
}

const competencyCell = {
  subskill: "recognize",
  state: "developing",
  formativeScore: 0.7,
  independentMastery: 0.65,
  attempts: 3,
  independentAttempts: 2,
  highConfidenceWrong: 0,
  lastPracticedAt: "2026-07-14T12:00:00Z",
  lastIndependentAt: "2026-07-14T12:00:00Z",
  lastIndependentCorrect: true,
  nextDueAt: "2026-07-18T12:00:00Z",
  dueState: "scheduled",
  isDue: false,
  overdueDays: 0,
  daysUntilDue: 4,
  stabilityDays: 4,
  lapses: 0,
  spacedRetrievals: 1,
  distinctEligibleEcgs: 12,
  distinctSuccessfulEcgs: 2,
  distinctModes: 1,
  distinctMorphologies: 2,
  independentEvidenceAvailable: true,
  independentReceipt: { mode: "rapid", caseConcept: "sinus_rhythm", receiptConcept: "sinus_rhythm", subskill: "recognize" },
  evidenceUncertainty: null,
};

const competencies = {
  learnerId: "demo",
  registryVersion: "replay-trend-ui-v1",
  calendarProjection: {
    timeZone: "America/New_York",
    today: new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" }),
    reviewDays: [],
  },
  objectives: [{
    objectiveId: "sinus_rhythm",
    label: "Sinus rhythm",
    domain: "rhythm",
    caseConcepts: ["sinus_rhythm"],
    evidenceCeiling: "eligible_real_case",
    subskills: [competencyCell],
  }],
};

async function routeAuth(page: Page) {
  await page.route("**/api/backend/auth/me", (route) => route.fulfill({ json: {
    authenticated: true,
    user: { userId: "u_replay_ui", username: "student", displayName: "Student", accountStatus: "verified", emailVerified: true },
  } }));
  await page.route("**/api/backend/learning/preferences", (route) => route.fulfill({ json: {
    trainingStage: "not_set",
    primaryGoal: "build_fundamentals",
    defaultSessionLength: 10,
    rapidPace: "untimed",
    guidanceLevel: "balanced",
    reduceMotion: false,
    largeControls: false,
    updatedAt: null,
  } }));
  await page.route("**/api/backend/auth/guest-progress", (route) => route.fulfill({ json: { hasProgress: false, claimable: false } }));
}

async function routeHomeReads(page: Page) {
  await routeAuth(page);
  await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ json: competencies }));
  await page.route("**/api/backend/adaptive/plan", (route) => route.fulfill({ json: {
    learnerId: "demo",
    coachContext: null,
    generatedAt: "2026-07-15T12:00:00Z",
    plannerKind: "verified_competency_scheduler",
    generativeTutorUsed: false,
    basis: { independentCompetencyObservations: 2, independentAttempts: 2, independentAttemptUnit: "competency_observation", dueCompetencies: 0, overdueCompetencies: 0, highConfidenceMisses: 0, eligibleConcepts: 12, baselineNeeded: false },
    primary: null,
    priorities: [],
    stages: [],
    guidedRemediation: null,
    integration: null,
    clinicalApplication: null,
    explanation: "No review is due.",
  } }));
  await page.route("**/api/backend/learning/resume", (route) => route.fulfill({ json: { version: "learning-resume-v1", generatedAt: "2026-07-15T12:00:00Z", primary: null, additional: [] } }));
  await page.route("**/api/backend/learning/sessions?*", (route) => route.fulfill({ json: { version: "learning-sessions-v1", items: [], hasMore: false, nextOffset: null, totalSavedItems: 0 } }));
}

test.describe("completed work review and skill timelines", () => {
  test("opens replay lazily with the scoped ECG and no assessment controls", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await routeAuth(page);
    let replayRequests = 0;
    await page.route(`**/api/backend/learning/sessions/${sessionRef}`, (route) => route.fulfill({ json: {
      version: "learning-session-review-v1",
      session: {
        sessionRef,
        mode: "training",
        status: "complete",
        attempted: 1,
        total: 1,
        score: 1,
        correctCount: 1,
        flaggedCount: 0,
        focusCompetencies: [{ objectiveId: "sinus_rhythm", subskill: "recognize", mappingSource: "session_focus" }],
        startedAt: "2026-07-14T11:58:00Z",
        completedAt: "2026-07-14T12:00:00Z",
        reviewAvailable: true,
      },
      attempts: [{ index: 1, score: 1, confidence: 4, assistance: { hintsUsed: 0 }, flagged: false, competencies: [{ objectiveId: "sinus_rhythm", subskill: "recognize", mappingSource: "committed_event", score: 1 }] }],
    } }));
    await page.route("**/api/backend/learners/demo/competencies", (route) => route.fulfill({ json: competencies }));
    await page.route(`**/api/backend/learning/sessions/${sessionRef}/attempts/1/replay`, (route) => {
      replayRequests += 1;
      return route.fulfill({ json: {
        version: "learning-session-replay-v1",
        fidelity: "reconstructed",
        sessionRef,
        attemptIndex: 1,
        mode: "training",
        sessionStatus: "complete",
        displayId: "Training ECG 0001",
        submittedAt: "2026-07-14T12:00:00Z",
        ecgRef,
        waveformAvailable: true,
        waveformPresentation: { kind: "twelve_lead", leads: [] },
        comparison: null,
        question: {
          kind: "training",
          prompt: "Decide whether sinus rhythm is supported by this ECG.",
          target: {
            objectiveId: "rhythm_basics",
            objectiveLabel: "Rhythm Basics",
            caseConceptId: "sinus_rhythm",
            caseConceptLabel: "Sinus rhythm",
            subskill: "recognize",
          },
          classificationOptions: [{ id: "present", label: "Target supported" }, { id: "absent", label: "Target not supported" }],
          phase: "transfer",
          questionSnapshot: {
            version: "focused-question-v1",
            privateSnapshotMarker: "snapshot fields must not be rendered generically",
          },
          subskillTask: {
            kind: "single_choice",
            subskill: "recognize",
            variant: 2,
            prompt: "Which finding best supports the rhythm classification?",
            options: [
              { id: "internal_choice_regular_p", label: "A consistent P wave precedes each QRS" },
              { id: "internal_choice_no_atrial", label: "No organized atrial activity is visible" },
            ],
            required: true,
            gradingBoundary: "Internal scoring boundary that should never appear in learner review.",
          },
        },
        submission: {
          selectedAnswer: "present",
          confidence: 4,
          hintsUsed: 0,
          evidenceNote: "Regular P waves precede each QRS.",
          subskillTaskAnswer: "internal_choice_regular_p",
          subskillTaskMatches: {},
          subskillTaskValue: null,
          viewerTaskEvidence: { mode: "point", point: { lead: "II", timeSec: 0.5, amplitudeMv: 0.8 } },
        },
        feedback: { score: 1, feedback: "Correct. The rhythm is sinus.", classificationCorrect: true, skillCorrect: true },
        answerGuide: {
          expectedAnswer: "present",
          subskillTaskResult: {
            kind: "single_choice",
            complete: true,
            correct: true,
            score: 1,
            submittedAnswer: "internal_choice_regular_p",
            correctAnswer: "internal_choice_regular_p",
          },
        },
        provenance: { tracing: "real_deidentified_ecg", learningEvidence: "independent_assessment" },
      } });
    });
    await page.route(`**/api/backend/learning/sessions/${sessionRef}/attempts/1/waveform/${ecgRef}?*`, (route) => route.fulfill({ json: {
      caseId: ecgRef,
      samplingFrequency: 100,
      durationSec: 10,
      startSec: 0,
      endSec: 10,
      leads: ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"].map((lead) => ({ lead, points: [{ timeSec: 0, amplitudeMv: 0 }, { timeSec: 0.5, amplitudeMv: lead === "II" ? 0.8 : 0.2 }, { timeSec: 1, amplitudeMv: 0 }] })),
    } }));

    await page.goto(`/home/review/${sessionRef}`);
    await expect(page.getByRole("heading", { name: "Questions" })).toBeVisible();
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.locator("main main")).toHaveCount(0);
    await expect(page.getByRole("main").getByRole("heading", { name: "Focused practice", level: 1 })).toBeVisible();
    expect(replayRequests).toBe(0);
    await page.getByText("Question 1", { exact: true }).click();
    await page.getByRole("link", { name: "Review question & ECG" }).click();

    await expect(page.getByRole("heading", { name: "Training ECG 0001" })).toBeVisible();
    await expect(page.getByRole("main")).toHaveCount(1);
    await expect(page.locator("main main")).toHaveCount(0);
    await expect(page.getByRole("main").getByRole("heading", { name: "Training ECG 0001", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "ECG replay" })).toBeVisible();
    await expect(page.getByText("Regular P waves precede each QRS.")).toBeVisible();
    await expect(page.getByText("Correct. The rhythm is sinus.")).toBeVisible();
    await expect(page.getByText("Your response", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("Your response · Recommended", { exact: true })).toBeVisible();
    const practiceContext = page.getByLabel("Focused practice context");
    await expect(practiceContext.getByText("Practice objective", { exact: true })).toBeVisible();
    await expect(practiceContext.getByText("Rhythm Basics", { exact: true })).toBeVisible();
    await expect(practiceContext.getByText("ECG example", { exact: true })).toBeVisible();
    await expect(practiceContext.getByText("Sinus rhythm", { exact: true })).toBeVisible();
    const skillReview = page.getByLabel("Focused skill review");
    await expect(skillReview.getByRole("heading", { name: "Which finding best supports the rhythm classification?" })).toBeVisible();
    await expect(skillReview.getByText("A consistent P wave precedes each QRS", { exact: true })).toBeVisible();
    await expect(skillReview.getByText("Your selection · Reviewed answer", { exact: true })).toBeVisible();
    await expect(page.getByRole("note", { name: "Your saved ECG evidence" })).toContainText("Point · Lead II · 0.500 s");
    await expect(page.locator('[data-evidence-mode="point"]')).not.toHaveCount(0);
    await expect(page.getByRole("button", { name: /submit/i })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Identify a feature on the ECG" })).toHaveCount(0);
    await expect(page.getByText("Additional question details", { exact: true })).toHaveCount(0);
    await expect(page.getByText("Confidence", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/internal_choice|Internal scoring boundary|Grading boundary|Variant|Transfer|rhythm_basics|sinus_rhythm|focused-question-v1|privateSnapshotMarker|snapshot fields must not/i, { exact: false })).toHaveCount(0);
    expect(replayRequests).toBeGreaterThanOrEqual(1);
    expect(replayRequests).toBeLessThanOrEqual(2);
    expect(consoleErrors).toEqual([]);
  });

  test("renders Focused matching, measurement, synthesis, and calibration reviews without raw task ids", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await routeAuth(page);
    const replayPayload = (
      subskill: string,
      task: Record<string, unknown>,
      submission: Record<string, unknown>,
      taskResult: Record<string, unknown>,
      reviewActions: Array<Record<string, unknown>> = [],
    ) => ({
      version: "learning-session-replay-v1",
      fidelity: "reconstructed",
      sessionRef,
      attemptIndex: 1,
      mode: "training",
      sessionStatus: "complete",
      displayId: "Focused ECG review",
      submittedAt: "2026-07-14T12:00:00Z",
      ecgRef,
      waveformAvailable: true,
      waveformPresentation: { kind: "twelve_lead", leads: [] },
      comparison: null,
      question: {
        kind: "training",
        prompt: "Decide whether the selected pattern is supported, then complete the skill challenge.",
        target: { objectiveId: "sinus_rhythm", subskill },
        phase: "internal_transfer_phase",
        classificationOptions: [{ id: "present", label: "Target supported" }, { id: "absent", label: "Target not supported" }],
        subskillTask: task,
      },
      submission: {
        selectedAnswer: "present",
        hintsUsed: 0,
        evidenceNote: "I used the most discriminating visible feature.",
        ...submission,
      },
      feedback: { score: 1, selectedSkillFeedback: "The selected skill task was met.", classificationCorrect: true, skillCorrect: true },
      answerGuide: { expectedAnswer: "present", subskillTaskResult: taskResult },
      reviewActions,
      provenance: { tracing: "real_deidentified_ecg", learningEvidence: "independent_assessment" },
    });

    let payload = replayPayload(
      "explain_mechanism",
      {
        kind: "matching",
        subskill: "explain_mechanism",
        variant: 1,
        prompt: "Match each observation to the best explanation.",
        choices: [
          { id: "internal_choice_conduction", label: "Orderly atrial-to-ventricular conduction" },
          { id: "internal_choice_reentry", label: "Re-entry without organized atrial activation" },
        ],
        rows: [
          { id: "internal_row_p_qrs", clause: "A P wave consistently precedes each QRS" },
          { id: "internal_row_regular", clause: "The R-R intervals remain regular" },
        ],
        required: true,
        gradingBoundary: "Private matching rubric.",
      },
      {
        confidence: 5,
        subskillTaskMatches: {
          internal_row_p_qrs: "internal_choice_conduction",
          internal_row_regular: "internal_choice_reentry",
        },
      },
      {
        kind: "matching",
        complete: true,
        correct: false,
        score: 0.5,
        rows: [
          { rowId: "internal_row_p_qrs", submittedChoiceId: "internal_choice_conduction", correctChoiceId: "internal_choice_conduction", correct: true },
          { rowId: "internal_row_regular", submittedChoiceId: "internal_choice_reentry", correctChoiceId: "internal_choice_conduction", correct: false },
        ],
      },
    );
    await page.route(`**/api/backend/learning/sessions/${sessionRef}/attempts/1/replay`, (route) => route.fulfill({ json: payload }));
    await page.route(`**/api/backend/learning/sessions/${sessionRef}/attempts/1/waveform/${ecgRef}?*`, (route) => route.fulfill({ json: waveformPayload(ecgRef) }));

    await page.goto(`/home/review/${sessionRef}/attempt/1`);
    let skillReview = page.getByLabel("Focused skill review");
    await expect(skillReview.getByText("A P wave consistently precedes each QRS", { exact: true })).toBeVisible();
    await expect(skillReview.getByText("Orderly atrial-to-ventricular conduction", { exact: true })).toHaveCount(3);
    await expect(skillReview.getByText("Re-entry without organized atrial activation", { exact: true })).toBeVisible();
    await expect(skillReview.getByText("Your match", { exact: true }).first()).toBeVisible();
    await expect(skillReview.getByText("Reviewed match", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/internal_row|internal_choice|Private matching rubric|internal transfer phase/i)).toHaveCount(0);
    await expect(page.getByText("Confidence", { exact: true })).toHaveCount(0);

    payload = replayPayload(
      "measure",
      {
        kind: "numeric_fill_in",
        subskill: "measure",
        variant: 0,
        prompt: "Measure the QRS duration.",
        responseLabel: "QRS duration",
        unit: "ms",
        minValue: 40,
        maxValue: 240,
        step: 1,
        required: true,
        gradingBoundary: "Private numeric rubric.",
      },
      {
        confidence: 5,
        subskillTaskValue: 150,
        viewerTaskEvidence: { mode: "caliper", lead: "I", timeStartSec: 0.44, timeEndSec: 0.59, valueMs: 150 },
      },
      {
        kind: "numeric_fill_in",
        complete: true,
        correct: false,
        score: 0,
        submittedValue: 150,
        expectedValue: 120,
        tolerance: 10,
        absoluteError: 30,
        unit: "ms",
      },
      [{ type: "drawCaliper", lead: "I", timeStart: 0.44, timeEnd: 0.56, label: "Reviewed interval" }],
    );
    await page.reload();
    skillReview = page.getByLabel("Focused skill review");
    await expect(skillReview.getByText("Your measurement", { exact: true })).toBeVisible();
    await expect(skillReview.getByText("150 ms", { exact: true })).toBeVisible();
    await expect(skillReview.getByText("Reviewed measurement", { exact: true })).toBeVisible();
    await expect(skillReview.getByText("120 ms", { exact: true })).toBeVisible();
    await expect(skillReview.getByText("±10 ms", { exact: true })).toBeVisible();
    const evidenceLegend = page.getByLabel("ECG evidence legend");
    await expect(evidenceLegend.getByText("Your saved mark / measurement", { exact: true })).toBeVisible();
    await expect(evidenceLegend.getByText("Reviewed reference", { exact: true })).toBeVisible();
    await expect(page.locator("svg text").filter({ hasText: "Your measurement · 150 ms" })).toHaveCount(1);
    await expect(page.locator("svg text").filter({ hasText: "Reviewed interval" })).toHaveCount(1);
    await expect(page.getByText("Confidence", { exact: true })).toHaveCount(0);
    await expect(page.getByText(/Private numeric rubric|Variant|Required/, { exact: false })).toHaveCount(0);

    const frameworkSteps = [
      { key: "rate", label: "Rate", prompt: "State the ventricular rate.", placeholder: "Rate" },
      { key: "rhythm", label: "Rhythm", prompt: "Describe rhythm and atrial activity.", placeholder: "Rhythm" },
      { key: "axis", label: "Axis", prompt: "Classify the frontal QRS axis.", placeholder: "Axis" },
      { key: "intervals", label: "Intervals", prompt: "Review PR, QRS, and QT.", placeholder: "Intervals" },
      { key: "conduction", label: "Conduction", prompt: "Describe conduction findings.", placeholder: "Conduction" },
      { key: "st_t", label: "ST–T", prompt: "Describe repolarization findings.", placeholder: "ST–T" },
      { key: "hypertrophy", label: "Chamber pattern", prompt: "Assess chamber enlargement patterns.", placeholder: "Chambers" },
      { key: "synthesis", label: "Synthesis", prompt: "Prioritize the final ECG impression.", placeholder: "Synthesis" },
    ];
    const structuredInterpretation = {
      rate: "About 72 bpm",
      rhythm: "Regular sinus rhythm with one P wave before each QRS",
      axis: "Normal frontal axis",
      intervals: "PR and QRS are within expected limits",
      conduction: "No bundle-branch delay",
      st_t: "No acute ST elevation or depression",
      hypertrophy: "No convincing chamber enlargement pattern",
      synthesis: "Sinus rhythm without a dominant acute ECG abnormality",
    };
    const reviewedFramework = frameworkSteps.map((step, index) => ({
      key: step.key,
      label: step.label,
      review: index === 0 ? "Reviewed rate: approximately 70–75 bpm." : `Reviewed ${step.label.toLocaleLowerCase()} statement for this tracing.`,
      grounded: index < 7,
    }));
    payload = replayPayload(
      "synthesize",
      {
        kind: "matching",
        subskill: "synthesize",
        prompt: "Build a complete ECG read, then match each synthesis role.",
        choices: [{ id: "private_role_evidence", label: "Waveform evidence" }],
        rows: [{ id: "private_statement_one", clause: "Lead with the visible ECG evidence" }],
        frameworkVersion: "systematic-interpretation-v1",
        frameworkSteps,
      },
      {
        subskillTaskMatches: { private_statement_one: "private_role_evidence" },
        structuredInterpretation,
      },
      {
        kind: "matching",
        complete: true,
        correct: true,
        score: 1,
        rows: [{ rowId: "private_statement_one", submittedChoiceId: "private_role_evidence", correctChoiceId: "private_role_evidence", correct: true }],
        systematicInterpretationComplete: true,
        systematicInterpretation: structuredInterpretation,
        reviewedFramework,
      },
    );
    Object.assign(payload.answerGuide, {
      systematicInterpretationComplete: true,
      reviewedFramework,
    });
    await page.reload();
    const systematicReview = page.getByLabel("Systematic ECG interpretation review");
    await expect(systematicReview.getByRole("heading", { name: "Review your eight-step read" })).toBeVisible();
    await expect(systematicReview.getByText("All 8 steps recorded", { exact: true })).toBeVisible();
    await expect(systematicReview.getByRole("listitem")).toHaveCount(8);
    await expect(systematicReview.getByText("Your interpretation", { exact: true })).toHaveCount(8);
    await expect(systematicReview.getByText("About 72 bpm", { exact: true })).toBeVisible();
    await expect(systematicReview.getByText("Reviewed rate: approximately 70–75 bpm.", { exact: true })).toBeVisible();
    await expect(systematicReview.getByText("Sinus rhythm without a dominant acute ECG abnormality", { exact: true })).toBeVisible();
    await expect(page.getByText(/st_t|frameworkVersion|frameworkSteps|systematicInterpretation|reviewedFramework/)).toHaveCount(0);

    payload = replayPayload(
      "calibrate_confidence",
      {
        kind: "confidence_commit",
        subskill: "calibrate_confidence",
        variant: 0,
        prompt: "Commit your certainty after making the pattern decision.",
        options: [],
        required: true,
        gradingBoundary: "Private calibration rubric.",
      },
      { confidence: 4 },
      { kind: "confidence_commit", complete: true, correct: true, score: 1 },
    );
    await page.reload();
    skillReview = page.getByLabel("Focused skill review");
    await expect(skillReview.getByText("Your confidence", { exact: true })).toBeVisible();
    await expect(skillReview.getByText("4 of 5", { exact: true })).toBeVisible();
    await expect(page.getByText(/Private calibration rubric|internal_transfer_phase/)).toHaveCount(0);
    expect(consoleErrors).toEqual([]);
  });

  test("replays the original mixed Rapid task, response, and feedback", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await routeAuth(page);
    await page.route(`**/api/backend/learning/sessions/${sessionRef}/attempts/1/replay`, (route) => route.fulfill({ json: {
      version: "learning-session-replay-v1",
      fidelity: "reconstructed",
      sessionRef,
      attemptIndex: 1,
      mode: "rapid",
      sessionStatus: "abandoned",
      displayId: "Rapid ECG 0001",
      submittedAt: "2026-07-14T12:00:00Z",
      ecgRef,
      waveformAvailable: true,
      waveformPresentation: { kind: "twelve_lead", leads: [] },
      comparison: null,
      question: {
        kind: "rapid",
        pace: "untimed",
        assessmentScope: "dominant_finding",
        testedObjectiveManifest: { taskKind: "mixed_v2", assessmentScope: "dominant_finding", objectives: [] },
        taskPacket: {
          version: "rapid-task-packet-v1",
          display: { kind: "twelve_lead" },
          tasks: [{
            id: "task_replay_one",
            type: "single_choice",
            prompt: "Which rhythm is best supported by this ECG?",
            options: [{ id: "option_1", label: "Atrial flutter" }, { id: "option_2", label: "Sinus rhythm" }],
            skillId: "recognize",
            required: true,
          }],
        },
      },
      submission: { taskResponses: { task_replay_one: "option_2" } },
      feedback: { score: 1, taskFeedback: [{ taskId: "task_replay_one", correct: true, correctChoiceId: "option_2", feedback: "The rhythm choice matched the ECG." }] },
      answerGuide: { correctObjectives: ["sinus_rhythm"] },
      provenance: { tracing: "real_deidentified_ecg", learningEvidence: "independent_assessment" },
    } }));
    await page.route(`**/api/backend/learning/sessions/${sessionRef}/attempts/1/waveform/${ecgRef}?*`, (route) => route.fulfill({ json: waveformPayload(ecgRef) }));

    await page.goto(`/home/review/${sessionRef}/attempt/1`);

    await expect(page.getByRole("heading", { name: "Rapid ECG 0001" })).toBeVisible();
    await expect(page.getByText(/Partial Rapid round · Submitted/)).toBeVisible();
    await expect(page.getByText(/explore this submitted ECG/)).toBeVisible();
    await expect(page.getByRole("heading", { name: "Which rhythm is best supported by this ECG?" })).toBeVisible();
    await expect(page.getByLabel("Recorded Rapid questions").getByText("Sinus rhythm", { exact: true })).toBeVisible();
    await expect(page.getByText("Your response · Recommended", { exact: true })).toBeVisible();
    await expect(page.getByText("The rhythm choice matched the ECG.", { exact: true })).toBeVisible();
    await expect(page.getByText("Commit the dominant finding supported by this ECG.")).toHaveCount(0);
    expect(consoleErrors).toEqual([]);
  });

  test("shows the authenticated comparison ECG and sourced Clinical episode stages", async ({ page }) => {
    const consoleErrors = collectConsoleErrors(page);
    await routeAuth(page);
    await page.route(`**/api/backend/learning/sessions/${sessionRef}/attempts/1/replay`, (route) => route.fulfill({ json: {
      version: "learning-session-replay-v1",
      fidelity: "reconstructed",
      sessionRef,
      attemptIndex: 1,
      mode: "clinical",
      sessionStatus: "complete",
      displayId: "Clinical ECG 0001",
      submittedAt: "2026-07-14T12:00:00Z",
      ecgRef,
      waveformAvailable: true,
      waveformPresentation: { kind: "twelve_lead", leads: [] },
      comparison: {
        role: "prior",
        label: "Earlier comparison ECG",
        ecgRef: comparisonRef,
        waveformAvailable: true,
        waveformPresentation: { kind: "twelve_lead", leads: [] },
        provenance: "same_patient_time_ordered_real_ecgs",
      },
      question: {
        kind: "clinical",
        stem: "A patient returns for reassessment after an earlier ECG.",
        prompt: "Choose the safest integrated plan.",
        steps: [
          {
            stageKind: "ecg",
            stageTitle: "Compare the two ECGs",
            elapsedLabel: "About 24 hours later",
            clinicalUpdate: "The current tracing is now regular.",
            dataPoints: [{ label: "Recording relationship", value: "Same patient", source: "source_metadata" }],
            prompt: "What changed?",
            options: [{ text: "The rhythm changed" }, { text: "Nothing changed" }],
          },
          {
            stageKind: "reassessment",
            stageTitle: "Reassess modifiable risk",
            elapsedLabel: "During observation",
            clinicalUpdate: "Potassium is 3.3 mmol/L.",
            dataPoints: [{ label: "Potassium", value: "3.3 mmol/L", source: "authored_simulation" }],
            prompt: "What matters next?",
            options: [{ text: "Correct reversible risk" }, { text: "Ignore the result" }],
          },
        ],
      },
      submission: { stepAnswers: [0, 0] },
      feedback: {
        score: 1,
        feedback: "The sequence was defensible.",
        stepFeedback: [
          { stageIndex: 0, correct: true, supportedAnswer: "The rhythm changed", explanation: "The authenticated pair supports a real rhythm transition." },
          { stageIndex: 1, correct: true, supportedAnswer: "Correct reversible risk", explanation: "The authored electrolyte result changes the medication-safety plan." },
        ],
        competencyOutcomes: [{ concept: "sinus_rhythm", subskill: "synthesize", score: 1, correct: true, stageIndex: 0, stageTitle: "Compare the two ECGs", stageKind: "ecg", evidenceSource: "clinical_step_server_grade" }],
      },
      answerGuide: { correctStepAnswers: [[0], [0]] },
      provenance: {
        tracing: "real_deidentified_ecg",
        context: "authored_simulation",
        comparison: "same_patient_time_ordered_real_ecgs",
        learningEvidence: "formative_only",
        contentLabel: "Authenticated same-patient ECG comparison · authored simulated clinical timeline",
      },
    } }));
    await page.route(`**/api/backend/learning/sessions/${sessionRef}/attempts/1/waveform/*`, (route) => {
      const reference = route.request().url().includes(comparisonRef) ? comparisonRef : ecgRef;
      return route.fulfill({ json: waveformPayload(reference) });
    });

    await page.goto(`/home/review/${sessionRef}/attempt/1`);

    await expect(page.getByRole("heading", { name: "Serial ECG replay" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Earlier comparison ECG" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Current ECG" })).toBeVisible();
    await expect(page.getByText("Authenticated comparison", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Compare the two ECGs" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Reassess modifiable risk" })).toBeVisible();
    await expect(page.getByText("Source-verified ECG metadata", { exact: true })).toBeVisible();
    await expect(page.getByText("Authored simulation update", { exact: true })).toBeVisible();
    await expect(page.getByText("Potassium is 3.3 mmol/L.", { exact: true })).toBeVisible();
    await expect(page.getByText("The authenticated pair supports a real rhythm transition.", { exact: true })).toBeVisible();
    await expect(page.getByText("Supported response: Correct reversible risk", { exact: true })).toBeVisible();
    expect(consoleErrors).toEqual([]);
  });

  test("loads an exact competency timeline only when the learner opens it", async ({ page }) => {
    await routeHomeReads(page);
    let trendRequests = 0;
    await page.route("**/api/backend/learners/demo/competencies/sinus_rhythm/recognize/trend?*", (route) => {
      trendRequests += 1;
      return route.fulfill({ json: {
        version: "competency-trend-v1",
        objectiveId: "sinus_rhythm",
        subskill: "recognize",
        pointCount: 3,
        hasMore: false,
        interpretation: "Scored evidence over time; this is not a historical mastery estimate.",
        points: [
          { occurredAt: "2026-07-01T12:00:00Z", score: 0.4, mode: "clinical", evidenceLevel: "formative_guided", independent: false, recordStatus: "verified" },
          { occurredAt: "2026-07-08T12:00:00Z", score: 0.7, mode: "training", evidenceLevel: "independent_transfer", independent: true, recordStatus: "verified" },
          { occurredAt: "2026-07-14T12:00:00Z", score: 1, mode: "rapid", evidenceLevel: "independent_transfer", independent: true, recordStatus: "verified" },
        ],
      } });
    });

    await page.goto("/home?panel=competencies");
    await page.locator("summary").filter({ hasText: /^Rhythm/ }).first().click();
    await page.locator("summary").filter({ hasText: /^Sinus rhythm/ }).first().click();
    await page.getByText("Practice details", { exact: true }).click();
    expect(trendRequests).toBe(0);
    await page.getByText("Progress over time", { exact: true }).click();

    await expect(page.getByText("Each point is one completed skill observation. Filled dots are scored ECG checks.")).toBeVisible();
    await expect(page.getByText("Clinical scenario · Formative practice", { exact: true })).toBeVisible();
    await expect(page.getByRole("list", { name: "Sinus rhythm: Recognize and name check history" }).getByRole("listitem")).toHaveCount(3);
    await expect(page.getByText("40%", { exact: true })).toBeVisible();
    await expect(page.getByRole("list", { name: "Sinus rhythm: Recognize and name check history" }).getByText("100%", { exact: true })).toBeVisible();
    expect(trendRequests).toBe(1);
  });
});
