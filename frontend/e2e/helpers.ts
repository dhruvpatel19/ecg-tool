import type { Page } from "@playwright/test";

/**
 * Subscribe to console + page errors and return a growing array of error strings.
 * Filters out benign noise (favicon 404s, React DevTools hint, HMR chatter) so a
 * non-empty result is a real regression.
 */
export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  const ignore = [
    /favicon/i,
    /Download the React DevTools/i,
    /\[Fast Refresh\]/i,
    /websocket/i,
  ];
  const keep = (text: string) => !ignore.some((re) => re.test(text));

  page.on("console", (message) => {
    if (message.type() === "error") {
      const text = message.text();
      if (keep(text)) errors.push(text);
    }
  });
  page.on("pageerror", (error) => {
    const text = error.message;
    if (keep(text)) errors.push(text);
  });
  return errors;
}

/** A username unlikely to collide across runs, for the auth registration test. */
export function randomUsername(prefix = "e2e"): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}
