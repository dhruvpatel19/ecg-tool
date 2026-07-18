export type LearningReturnSurface =
  | "lesson"
  | "study_plan"
  | "profile"
  | "calendar"
  | "rapid"
  | "clinical"
  | "session_review";

export type LearningReturnDestination = {
  href: string;
  label: string;
  surface: LearningReturnSurface;
};

const INTERNAL_ORIGIN = "https://ecg-learning.invalid";
const ALL_SURFACES: readonly LearningReturnSurface[] = [
  "lesson",
  "study_plan",
  "profile",
  "calendar",
  "rapid",
  "clinical",
  "session_review",
];

function isCalendarDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (year < 1 || month < 1 || month > 12 || day < 1) return false;
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day <= daysInMonth[month - 1];
}

function destination(
  href: string,
  surface: LearningReturnSurface,
  label: string,
): LearningReturnDestination {
  return { href, surface, label };
}

/**
 * Parse a learner-facing return target without permitting arbitrary internal
 * paths, redirect chains, protocol-relative URLs, or backslash URL tricks.
 * Callers may further narrow the surfaces appropriate to their mode.
 */
export function parseLearningReturn(
  value: string | null | undefined,
  allowedSurfaces: readonly LearningReturnSurface[] = ALL_SURFACES,
): LearningReturnDestination | null {
  if (!value || value !== value.trim() || value.length > 2_048) return null;
  if (!value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(value)) return null;

  let parsed: URL;
  try {
    parsed = new URL(value, INTERNAL_ORIGIN);
  } catch {
    return null;
  }
  const suppliedPath = value.split(/[?#]/, 1)[0];
  if (parsed.origin !== INTERNAL_ORIGIN || parsed.hash || parsed.pathname !== suppliedPath) return null;

  const allowed = new Set(allowedSurfaces);
  const href = `${parsed.pathname}${parsed.search}`;
  const params = [...parsed.searchParams.entries()];

  if (/^\/learn\/[a-z0-9][a-z0-9-]*$/i.test(parsed.pathname)) {
    const validLessonQuery = params.length === 0
      || (params.length === 1 && params[0][0] === "scene" && Boolean(params[0][1]));
    return validLessonQuery && allowed.has("lesson")
      ? destination(href, "lesson", "Return to lesson")
      : null;
  }

  if (parsed.pathname === "/profile") {
    if (params.length === 1 && params[0][0] === "tab" && params[0][1] === "plan") {
      return allowed.has("study_plan")
        ? destination("/profile?tab=plan", "study_plan", "Return to study plan")
        : null;
    }
    return params.length === 0 && allowed.has("profile")
      ? destination("/profile", "profile", "Return to My learning")
      : null;
  }

  if (parsed.pathname === "/home") {
    if (params.length === 0) {
      return allowed.has("profile")
        ? destination("/home", "profile", "Return to dashboard")
        : null;
    }
    if (
      params.length === 2
      && params[0][0] === "panel"
      && params[0][1] === "calendar"
      && params[1][0] === "date"
      && isCalendarDate(params[1][1])
    ) {
      return allowed.has("calendar")
        ? destination(
            `/home?panel=calendar&date=${params[1][1]}`,
            "calendar",
            "Return to calendar",
          )
        : null;
    }
    if (params.length !== 1 || params[0][0] !== "panel") return null;
    if (params[0][1] === "plan") {
      return allowed.has("study_plan")
        ? destination("/home?panel=plan", "study_plan", "Return to study plan")
        : null;
    }
    if (params[0][1] === "competencies" || params[0][1] === "activity") {
      return allowed.has("profile")
        ? destination(
            `/home?panel=${params[0][1]}`,
            "profile",
            params[0][1] === "competencies" ? "Return to competencies" : "Return to activity",
          )
        : null;
    }
    return null;
  }

  if (/^\/home\/review\/[A-Za-z0-9_-]{1,160}$/.test(parsed.pathname)) {
    return params.length === 0 && allowed.has("session_review")
      ? destination(parsed.pathname, "session_review", "Return to session review")
      : null;
  }

  if (params.length > 0) return null;
  if (parsed.pathname === "/review" && allowed.has("study_plan")) {
    return destination("/review", "study_plan", "Return to study plan");
  }
  if (parsed.pathname === "/rapid" && allowed.has("rapid")) {
    return destination("/rapid", "rapid", "Return to Rapid");
  }
  if (parsed.pathname === "/practice" && allowed.has("clinical")) {
    return destination("/practice", "clinical", "Return to clinical cases");
  }
  return null;
}

export function safeLearningReturn(
  value: string | null | undefined,
  allowedSurfaces?: readonly LearningReturnSurface[],
): string {
  return parseLearningReturn(value, allowedSurfaces)?.href ?? "";
}

export function learningReturnLabel(
  value: string | null | undefined,
  allowedSurfaces?: readonly LearningReturnSurface[],
): string {
  return parseLearningReturn(value, allowedSurfaces)?.label ?? "Return";
}
