# ECG AI Learning Platform V1 Specification

## 1. Project Vision

Build a complete working V1 of an AI-native ECG learning platform for medical students preparing for clerkship. The platform should teach ECG interpretation better than static ECG websites, PDFs, videos, or simple case banks by combining:

- real PTB-XL waveform data
- PTB-XL metadata, labels, reports, diagnostic classes/subclasses, and folds
- PTB-XL+ structured features, fiducials, median beats, automatic diagnostic statements, and algorithm-derived measurements
- an interactive 12-lead ECG viewer
- guided tutorials
- rapid practice
- concept-specific practice
- learner profile and mastery tracking
- adaptive practice
- grounded LLM tutoring, feedback, and viewer control

The AI should be deeply embedded into the product. It should not feel like a chatbot attached to an ECG viewer. The AI should function as the learning operating system: guiding tutorials, controlling the ECG viewer, asking questions, giving feedback, identifying learner weaknesses, and selecting future cases.

However, the LLM must never be treated as the source of truth for ECG diagnoses, measurements, intervals, fiducials, lead-level findings, or ROIs. The LLM must only explain, tutor, quiz, summarize, grade, and recommend viewer actions based on grounded case packets built from deterministic data, PTB-XL, PTB-XL+, and rule-based curation.

This is an educational tool only. It must not be presented as a clinical diagnostic product.

---

## 2. Core Constraint: No Human Case Curation

There will be no human case curation or validation. Therefore, the platform must autonomously decide which ECGs are sufficiently reliable for teaching or practice.

Autonomous does not mean every ECG is safe to teach from. The app must build a confidence-gated autonomous curation engine that assigns reliability per ECG and per concept.

It is better to exclude many cases than to teach from unreliable ones.

---

## 3. Data Sources

### 3.1 PTB-XL

Use PTB-XL for:

- raw 12-lead ECG waveform records
- metadata
- SCP-ECG labels
- diagnostic superclass/subclass labels
- clinical reports
- train/validation/test folds
- signal quality fields when available

Expected files may include:

- `ptbxl_database.csv`
- `scp_statements.csv`
- `records100/`
- `records500/`

Do not hardcode exact paths. Inspect the actual dataset structure.

Environment variable:

```bash
PTBXL_DATA_ROOT=/path/to/ptb-xl
```

### 3.2 PTB-XL+

Use PTB-XL+ as a core grounding layer for:

- structured ECG features
- median beats
- fiducial points
- automatic diagnostic statements
- interval measurements
- axis/rate/voltage measurements
- algorithm-derived features
- lead-specific or morphology-related information when available

Environment variable:

```bash
PTBXL_PLUS_DATA_ROOT=/path/to/ptb-xl-plus
```

The app should inspect the actual PTB-XL+ folder structure and gracefully support whatever subset of PTB-XL+ files is present.

---

## 4. Technology Stack

Use this stack unless the existing repo strongly suggests otherwise:

### Frontend

- Next.js
- React
- TypeScript
- SVG or Canvas ECG rendering
- Modern responsive UI
- Desktop/tablet primary; mobile-aware but not necessarily mobile-first

### Backend

- Python FastAPI
- wfdb for ECG waveform reading
- pandas, numpy, scipy for processing
- SQLite for local V1
- Clean schema that can later move to Postgres

### LLM

- Mock provider by default
- OpenAI-compatible provider adapter using environment variables
- Future extensibility for other providers

### Testing

- pytest for backend/data
- TypeScript typecheck
- frontend build/lint
- ECG coordinate mapping tests
- curation tests
- case packet tests
- LLM schema validation tests
- at least one scripted or end-to-end flow if feasible

---

## 5. Environment Variables

Create `.env.example` with:

```bash
PTBXL_DATA_ROOT=/absolute/path/to/ptb-xl
PTBXL_PLUS_DATA_ROOT=/absolute/path/to/ptb-xl-plus
DATABASE_URL=sqlite:///./ecg_learning.db

LLM_PROVIDER=mock
LLM_API_KEY=
LLM_MODEL=
LLM_BASE_URL=

APP_ENV=development
```

Security requirements:

- Do not commit dataset files.
- Do not commit API keys.
- Do not commit secrets.
- Do not commit generated large artifacts.
- Do not commit local database files.
- Keep LLM API keys server-side only.
- The app must work with the mock LLM provider without any API key.

---

## 6. Autonomous Confidence-Gated Curation

### 6.1 Reliability Tiers

Each ECG must be assigned reliability tiers globally and per concept.

#### Tier A: High-Confidence Teaching Case

Use for:

- guided tutorials
- detailed feedback
- explicit visual explanation
- ROI/highlight-based teaching

Requires concordance between:

- PTB-XL SCP labels
- PTB-XL diagnostic superclass/subclass
- PTB-XL report text where available
- PTB-XL+ diagnostic statements
- PTB-XL+ structured features/fiducials/measurements
- acceptable signal quality
- concept-specific inclusion rules

#### Tier B: Usable Practice Case

Use for:

- rapid practice
- broad interpretation practice
- cautious AI feedback

Criteria:

- broad label/concept likely reliable
- enough evidence to give educational feedback
- fine-grained lead-level/ROI feedback may be incomplete

#### Tier C: Uncertain or Discordant Case

Use for:

- internal testing only
- not shown in default student-facing workflows

Criteria:

- conflicting evidence
- missing critical features
- noisy signal
- ambiguous concept mapping

#### Tier D: Unsupported Concept/Case

Use for:

- not surfaced in V1

Criteria:

- concept cannot be inferred reliably from available PTB-XL/PTB-XL+ data

### 6.2 Per-Concept Scoring

A single ECG may be:

- Tier A for bundle branch block
- Tier B for general conduction disturbance
- Tier C for MI localization
- Tier D for QT teaching

Do not assign only one global reliability score. Store concept-specific scores and reasons.

Example case curation output:

```json
{
  "ecg_id": 12345,
  "global_tier": "B",
  "concept_scores": {
    "normal_ecg": 0.12,
    "anterior_mi": 0.91,
    "st_elevation": 0.84,
    "left_bundle_branch_block": 0.08,
    "qt_prolongation": 0.31
  },
  "usable_for": ["rapid_practice_mi", "st_t_change_practice"],
  "not_usable_for": ["qt_lesson", "bundle_branch_block_lesson"],
  "evidence": {
    "ptbxl_labels": ["MI"],
    "ptbxl_report": "...",
    "ptbxl_plus_statements": ["..."],
    "features": {
      "qrs_ms": {
        "value": 92,
        "source": "ptbxl_plus",
        "confidence": "available"
      },
      "qtc_ms": {
        "value": 431,
        "source": "ptbxl_plus",
        "confidence": "available"
      },
      "axis_deg": {
        "value": 45,
        "source": "ptbxl_plus",
        "confidence": "available"
      }
    }
  },
  "warnings": [
    "No reliable lead-level ROI for exact ST-elevation annotation",
    "Use broad MI feedback rather than precise culprit-vessel teaching"
  ]
}
```

### 6.3 Concordance Checks

The autonomous curation engine must check concordance across:

- PTB-XL SCP labels
- PTB-XL diagnostic superclass/subclass
- PTB-XL report text
- PTB-XL+ automatic diagnostic statements
- PTB-XL+ features
- PTB-XL+ fiducials
- signal quality fields
- missingness
- concept-specific inclusion rules

### 6.4 Source Hierarchy

Use this hierarchy:

1. Raw waveform availability and signal quality
2. PTB-XL+ measurements/fiducials/features where available
3. PTB-XL+ automatic diagnostic statements
4. PTB-XL SCP labels and diagnostic classes
5. PTB-XL report text
6. Deterministic local calculations
7. LLM explanation only, never as source of truth

The LLM cannot override the curation engine.

---

## 7. Concept Ontology

Create a normalized educational ECG concept ontology. At minimum include:

- normal_ecg
- rate
- sinus_rhythm
- atrial_fibrillation
- atrial_flutter
- supraventricular_tachycardia
- wide_complex_tachycardia
- bradycardia
- av_block_first_degree
- av_block_second_degree_mobitz_i
- av_block_second_degree_mobitz_ii
- av_block_third_degree
- axis_normal
- left_axis_deviation
- right_axis_deviation
- qrs_duration
- right_bundle_branch_block
- left_bundle_branch_block
- nonspecific_intraventricular_conduction_delay
- r_wave_progression
- left_ventricular_hypertrophy
- right_ventricular_hypertrophy
- atrial_enlargement
- st_elevation
- st_depression
- t_wave_inversion
- nonspecific_st_t_change
- myocardial_infarction
- anterior_mi
- inferior_mi
- lateral_mi
- septal_mi
- posterior_mi
- qt_interval
- qtc_prolongation
- electrolyte_drug_pattern
- pericarditis_pattern

Only enable student-facing concept practice for concepts with enough Tier A/B cases. Sparse or unreliable concepts should be disabled or marked as not yet available.

---

## 8. Concept-Specific Inclusion Rules

Implement conservative rule-based validators. These rules can be expanded over time.

### 8.1 Normal ECG

Requires:

- concordant normal label/statement
- no major abnormal PTB-XL+ diagnostic statements
- acceptable signal quality
- normal or near-normal rate, QRS, QTc, and axis if available
- no major conduction, MI, ST-T, hypertrophy, or rhythm abnormality labels

### 8.2 Rate and Rhythm

Requires:

- reliable rate measurement or deterministic rate estimate
- rhythm statement or label if teaching rhythm
- no severe signal-quality issue

### 8.3 Axis

Requires:

- axis measurement from PTB-XL+ or reliable derived frontal plane evidence
- no major conflict between feature and statements

### 8.4 PR Interval / AV Block

Requires:

- PR interval or fiducial evidence
- supporting diagnostic statement/label
- absence of contradictory rhythm classification where relevant

### 8.5 QRS / Bundle Branch Block

Requires:

- QRS duration
- compatible diagnostic statement or label
- morphology support from features/fiducials when available
- if morphology is not available, teach cautiously and avoid over-specific lead claims

### 8.6 MI / ST-T

Requires:

- concordant PTB-XL diagnostic class or label
- compatible PTB-XL+ diagnostic statement
- ST/T or infarction-related feature evidence where available
- lead/territory evidence if teaching localization
- if no lead-level evidence, only broad MI/ST-T practice is allowed

### 8.7 Hypertrophy

Requires:

- voltage/axis/statement support
- no contradictory statement indicating normal ECG
- use cautiously if only one weak criterion is present

### 8.8 QT/QTc

Requires:

- QT and QTc measurement source
- confidence/source field
- rate context
- no missingness in required measurement

### 8.9 AF/Flutter

Requires:

- rhythm statement/label support
- absence of contradictory sinus rhythm statement
- if possible, evidence of irregularity/atrial activity/fiducials
- no overclaiming if signal quality is poor

---

## 9. Case Packet Schema

Every case used by the app should have a grounded case packet.

Example:

```json
{
  "case_id": "00001",
  "waveform": {
    "path": "...",
    "sampling_frequency": 100,
    "duration_sec": 10,
    "leads": ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
  },
  "ptbxl": {
    "scp_codes": {},
    "diagnostic_superclass": [],
    "diagnostic_subclass": [],
    "report": "...",
    "fold": 1,
    "metadata": {}
  },
  "ptbxl_plus": {
    "statements": [],
    "features": {},
    "fiducials": {},
    "median_beats": {},
    "measurements": {}
  },
  "signal_quality": {
    "status": "acceptable",
    "reasons": []
  },
  "concept_confidence": {
    "myocardial_infarction": {
      "score": 0.91,
      "tier": "A",
      "evidence": ["ptbxl_label", "ptbxl_plus_statement", "feature_support"],
      "warnings": []
    }
  },
  "supported_objectives": [],
  "unsupported_objectives": [],
  "teaching_tier": "A",
  "inclusion_reasons": [],
  "exclusion_reasons": [],
  "llm_allowed_claims": [],
  "llm_forbidden_claims": []
}
```

The LLM should only receive case packets, not raw unstructured files, unless explicitly needed for a tool action.

---

## 10. ECG Viewer

Build a real interactive ECG viewer, not a static image.

### 10.1 Viewer Requirements

The viewer must:

- render actual ECG waveform data
- support 12-lead layout
- show ECG grid
- show lead labels
- use correct time axis
- use correct amplitude axis
- support zoom
- support pan
- support reset view
- support lead highlighting
- support ROI boxes/circles/highlights
- support calipers for time/amplitude measurement
- support click annotation
- support drag annotation
- map selected point to lead/timeSec/amplitudeMv
- execute structured AI viewer actions
- support records100 by default
- optionally support records500
- use PTB-XL+ median beats/fiducials/features when available

### 10.2 Coordinate Mapping

Every click should produce:

```json
{
  "lead": "II",
  "timeSec": 3.42,
  "amplitudeMv": 0.64
}
```

Every ROI should be represented as:

```json
{
  "lead": "V2",
  "timeStartSec": 2.1,
  "timeEndSec": 2.28,
  "ampMinMv": -0.2,
  "ampMaxMv": 0.8,
  "label": "ST segment",
  "concept": "st_elevation",
  "source": "ptbxl_plus_or_curated_or_user",
  "confidence": "high_or_medium_or_low"
}
```

### 10.3 AI Viewer Actions

The LLM should return structured viewer actions. Validate actions with a schema before execution.

Supported actions:

```json
[
  {
    "type": "zoom",
    "leads": ["V1", "V6"],
    "timeStart": 2.0,
    "timeEnd": 4.0
  },
  {
    "type": "highlightLead",
    "lead": "V1"
  },
  {
    "type": "highlightROI",
    "lead": "V2",
    "timeStart": 2.1,
    "timeEnd": 2.28,
    "ampMin": -0.2,
    "ampMax": 0.8,
    "label": "ST segment"
  },
  {
    "type": "circleROI",
    "lead": "II",
    "timeStart": 1.0,
    "timeEnd": 1.2,
    "label": "P wave"
  },
  {
    "type": "drawCaliper",
    "lead": "II",
    "timeStart": 1.0,
    "timeEnd": 1.16,
    "label": "PR interval"
  },
  {
    "type": "showFiducial",
    "lead": "V5",
    "timeSec": 3.25,
    "label": "QRS onset"
  },
  {
    "type": "resetView"
  }
]
```

If requested action references unavailable or invalid data, ignore safely and show a warning.

---

## 11. Guided Tutorials

Build a fixed curriculum with AI tutor support.

Each lesson should include:

- concise explanation
- ECG viewer interaction
- AI-driven highlight/zoom/annotation when useful
- click/annotation task or text question
- immediate feedback
- mastery/profile update

Minimum curriculum:

1. ECG orientation
   - paper speed
   - calibration
   - amplitude
   - time
   - 12-lead layout

2. Lead anatomy
   - limb leads
   - precordial leads
   - territories
   - contiguous leads

3. Rate

4. Rhythm
   - P waves
   - regularity
   - sinus rhythm

5. PR interval

6. Axis

7. QRS duration and conduction delay

8. Bundle branch blocks

9. R-wave progression

10. Chamber enlargement/hypertrophy basics if supported

11. ST elevation/depression and T-wave changes

12. MI localization

13. Bradyarrhythmias and AV block

14. Tachyarrhythmias
   - AF/flutter
   - SVT
   - wide-complex tachycardia
   - only if supported by reliable cases

15. QT/QTc and electrolyte/drug patterns if supported

16. Integrated clerkship-style ECG interpretation

---

## 12. Structured Interpretation Frameworks

Support at least two approaches.

### 12.1 Standard Clerkship Framework

- rate
- rhythm
- axis
- intervals
- conduction/QRS
- ST-T/ischemia
- hypertrophy/chambers
- final synthesis

### 12.2 HEARTS-Style Framework

Define this explicitly in the app as a teachable approach. The exact expansion can be adjusted, but it should be coherent and useful for students. For example:

- H: Heart rate and rhythm
- E: Electrical axis
- A: Atria and intervals
- R: R-wave progression and QRS/conduction
- T: T waves and ST segments
- S: Synthesis

The learner should be able to use either framework. The AI tutor should adapt to the selected framework.

---

## 13. Rapid Practice Mode

Workflow:

1. Show ECG plus optional clinical stem.
2. Hide diagnosis initially.
3. Learner submits structured interpretation and/or free text.
4. Learner records confidence.
5. App grades against grounded case packet, concept scores, and rubric.
6. AI gives concise feedback with viewer highlights.
7. App updates learner profile.
8. Reveal diagnosis/teaching points after submission.
9. Suggest next case adaptively.

Rapid practice should support:

- general mixed ECG practice
- high-yield clerkship cases
- weak-area remediation
- confidence calibration

---

## 14. Concept-Specific Practice

Allow practice by concept:

- normal ECG
- MI/infarction
- ST-T changes
- conduction disturbance
- bundle branch block
- axis
- hypertrophy/chamber enlargement
- bradyarrhythmias
- tachyarrhythmias
- AF/flutter
- AV block
- QT/QTc

Only enable concepts with enough sufficiently reliable Tier A/B cases.

If a concept has insufficient reliable cases, show it as unavailable or “needs more reliable cases” rather than forcing weak examples.

---

## 15. Learner Profile and Mastery Tracking

Track:

- learner id
- attempts
- correctness by objective/concept/disease
- confidence
- time spent
- hints used
- clicked/annotated ROI accuracy
- common misconception tags
- last practiced date
- mastery score per objective
- streaks or recent trend if useful

### 15.1 Mastery Model

Implement a simple mastery model:

- score 0 to 1 per objective
- increase with correct independent answers
- smaller increase with correct answer after hints
- decrease for wrong answers
- larger decrease for high-confidence wrong answers
- stale objectives get priority through spaced repetition
- repeatedly missed objectives get priority

### 15.2 Adaptive Practice

Adaptive case selection should prioritize:

- low mastery
- high yield
- stale objectives
- repeatedly missed objectives
- high-confidence wrong answers
- misconceptions
- concepts the learner has not seen enough

Avoid excessive duplicate cases.

---

## 16. Misconception Tracking

Track common ECG learning errors, including:

- confusing atrial flutter with sinus tachycardia
- missing AF because of focusing only on rate
- overcalling MI from nonspecific ST-T changes
- recognizing ST elevation but localizing incorrectly
- ignoring reciprocal changes
- confusing LBBB and RBBB
- measuring QT instead of QTc
- misusing limb leads for axis
- confusing AV block types
- missing wide QRS
- confusing paced rhythm or artifact with arrhythmia if relevant
- under-recognizing normal variants

Misconceptions should feed adaptive practice.

---

## 17. LLM Tutor and Grader

### 17.1 Provider Abstraction

Implement:

- `MockProvider`
- `OpenAICompatibleProvider`

The mock provider must allow a full local demo without an API key.

The OpenAI-compatible provider should use:

```bash
LLM_PROVIDER=openai-compatible
LLM_API_KEY=...
LLM_MODEL=...
LLM_BASE_URL=...
```

### 17.2 LLM Input

LLM input should include:

- system instructions
- current app mode
- current lesson/module
- current case packet
- PTB-XL evidence
- PTB-XL+ evidence
- learner profile summary
- current viewer state
- learner message or answer
- allowed viewer action schema
- safety/grounding constraints

### 17.3 LLM Output

LLM output must be structured JSON and schema-validated:

```json
{
  "tutorMessage": "...",
  "feedback": "...",
  "viewerActions": [],
  "objectiveUpdates": [],
  "misconceptions": [],
  "uncertaintyWarnings": [],
  "suggestedNextStep": "..."
}
```

If JSON parsing fails:

- recover gracefully
- show fallback message
- log the schema error
- do not crash the app

### 17.4 LLM Rules

The tutor must:

- explain at medical-student/clerkship level
- reference leads, segments, intervals, waves, fiducials, and measurements only when available
- never invent unavailable measurements
- never invent diagnoses
- never invent ROIs
- distinguish PTB-XL labels, PTB-XL+ statements, deterministic features, and uncertain findings
- use viewer actions when explaining visual ECG findings
- ask Socratic questions during tutorials
- provide concise feedback during rapid practice
- explicitly say when a feature is unavailable or uncertain
- avoid clinical advice beyond educational interpretation

---

## 18. Backend/API Requirements

Implement endpoints for:

- health check
- dataset status
- ingest/build case index
- list/search cases
- fetch case metadata
- fetch ECG waveform window/lead data
- fetch full case packet
- fetch PTB-XL+ feature/fiducial data for a case
- create/update learner profile
- save interpretation attempt
- grade structured interpretation
- grade text answer
- grade click/annotation answer
- get next adaptive practice case
- tutor chat
- tutor viewer actions
- concept taxonomy
- module/tutorial list
- current learner mastery summary

---

## 19. Database Schema Requirements

Store:

- PTB-XL case id
- waveform path/reference
- sampling frequency
- PTB-XL labels
- PTB-XL report
- PTB-XL diagnostic superclass/subclass
- PTB-XL+ statements
- PTB-XL+ features
- PTB-XL+ fiducials
- PTB-XL+ median beat references
- signal quality fields
- concept confidence scores
- teaching tier
- inclusion reasons
- exclusion reasons
- supported teaching objectives
- unsupported/uncertain objectives
- learner profiles
- attempts
- structured answers
- free-text answers
- confidence ratings
- hints used
- feedback
- objective mastery
- misconception tags
- timestamps

---

## 20. Frontend Pages

Build these user-facing areas.

### 20.1 Landing/Dashboard

Should show:

- app title and purpose
- continue current lesson
- start rapid practice
- start concept-specific practice
- learner progress
- mastery cards
- weak objectives
- recent activity

Avoid unnecessary backend/admin UI.

### 20.2 Tutorial Page

Should show:

- ECG viewer
- lesson step
- AI tutor panel
- question/quiz area
- feedback area
- progress through module
- next/previous controls

### 20.3 Rapid Practice Page

Should show:

- ECG viewer
- optional clinical stem
- structured interpretation form
- free-text answer box
- confidence selector
- submit button
- feedback
- revealed teaching points after submission
- next case button

### 20.4 Concept Practice Page

Should show:

- available concepts
- disabled concepts if insufficient reliable cases
- number of reliable cases per concept
- start practice button

### 20.5 Profile/Mastery Page

Should show:

- mastery by concept
- missed objectives
- misconception tags
- confidence calibration
- recent attempts
- recommended next practice

---

## 21. UI/UX Requirements

The UI should be:

- polished
- modern
- clean
- medical-student friendly
- not cluttered
- not admin-heavy
- focused on ECG mastery
- highly usable on laptop/tablet

The ECG viewer should be the visual focus during learning and practice.

The AI tutor panel should feel integrated, not pasted on.

---

## 22. Documentation Requirements

Create/update:

- `README.md`
- `docs/RESEARCH_AND_PRODUCT_PLAN.md`
- `docs/DATA_SCHEMA.md`
- `docs/AUTONOMOUS_CURATION.md`
- `docs/AI_GROUNDING_AND_SAFETY.md`
- `docs/ECG_VIEWER_COORDINATE_SYSTEM.md`
- `docs/TESTING_AND_VERIFICATION.md`

### README Must Include

- project overview
- setup instructions
- expected PTB-XL path
- expected PTB-XL+ path
- env variables
- ingestion command
- backend run command
- frontend run command
- mock LLM usage
- real provider key usage
- test commands
- limitations
- roadmap

---

## 23. Testing and Verification

Completion requires evidence, not just claims.

Add and run:

- backend unit tests
- PTB-XL ingestion tests
- PTB-XL+ ingestion tests
- fixture fallback tests
- autonomous curation tests
- case packet tests
- LLM schema validation tests
- ECG coordinate mapping tests
- frontend typecheck
- frontend build
- at least one end-to-end or scripted flow if feasible

End-to-end flow should test:

1. launch app
2. load dashboard
3. open ECG case
4. render ECG
5. perform viewer interaction
6. submit interpretation
7. receive mock AI feedback
8. update learner profile
9. get adaptive next case

Add a `scripts/verify` command or clearly documented verification commands.

If PTB-XL/PTB-XL+ paths are missing:

- do not fail completely
- create a realistic synthetic/demo fixture
- preserve real ingestion path
- clearly label fixture as non-clinical demo data

---

## 24. Definition of Done

The V1 is done only when:

- the app runs locally
- dashboard/landing page is polished
- PTB-XL/PTB-XL+ ingestion works or fixture fallback works
- autonomous curation assigns reliability tiers
- concept-specific confidence scores are implemented
- unreliable cases are excluded from student-facing workflows
- case packets contain PTB-XL and PTB-XL+ evidence
- ECG viewer renders real or fixture waveform data
- viewer supports zoom, pan, reset, lead highlighting, ROI annotation, calipers, click-to-coordinate mapping, and AI viewer actions
- guided tutorials work
- rapid practice works
- concept-specific practice works
- learner profile/mastery tracking works
- adaptive case selection works
- mock AI tutor works without API key
- OpenAI-compatible provider can be configured through env variables
- LLM outputs are schema-validated
- LLM does not act as source of truth
- README and docs are accurate
- verification commands pass, or true blockers are documented with logs and attempted fixes

---

## 25. Iteration Policy for Codex

Do not stop after planning or scaffolding.

Required workflow:

1. Inspect repo and datasets.
2. Write/update docs.
3. Implement backend/data layer.
4. Implement curation and case packets.
5. Implement ECG viewer.
6. Implement tutorials/practice/profile/adaptive logic.
7. Implement LLM provider abstraction and schema validation.
8. Implement UI polish.
9. Run tests/build.
10. Fix failures.
11. Rerun verification.
12. Continue until definition of done is met or a true blocker remains.

At final response, report:

- what was built
- exact run commands
- exact env vars needed
- tests/checks run
- test results
- limitations
- remaining blockers
- next recommended improvements
