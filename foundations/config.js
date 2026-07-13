// Route embedded tutor requests through the same-origin Next.js backend proxy.
// A standalone foundations server keeps the local API fallback in ui.js.
if (window.self !== window.top) {
  window.FOUNDATIONS_LLM_URL = "/api/backend/tutor/foundations";
}
