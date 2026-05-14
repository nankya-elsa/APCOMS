// Shared dashboard utilities — tab switching and any cross-tab helpers.
// Tab-specific logic lives in monitoring.js, analytics.js, and settings.js.

function switchTab(tab, btn) {
  document
    .querySelectorAll(".tab-content")
    .forEach((t) => t.classList.remove("active"));
  document
    .querySelectorAll(".tab-btn")
    .forEach((b) => b.classList.remove("active"));
  document.getElementById("tab-" + tab).classList.add("active");
  if (btn) {
    btn.classList.add("active");
  }

  // analytics tab needs to fetch charts and preview data when first opened
  if (tab === "analytics") {
    loadAnalytics();
    refreshPreview();
  }
}
