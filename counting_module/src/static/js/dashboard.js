// Shared dashboard utilities — tab switching, tab persistence,
// and any cross-tab helpers. Tab-specific logic lives in
// monitoring.js, analytics.js, and settings.js.

// Save the active tab in sessionStorage so a page refresh returns
// the user to the same tab they were on. Lives only for the
// duration of the browser tab session, so closing/reopening
// returns to the default landing tab (monitoring).
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

  // remember which tab the user is on for the next page load
  try {
    sessionStorage.setItem("apcoms_active_tab", tab);
  } catch (e) {
    // sessionStorage might be disabled in some browser modes; harmless
  }

  // analytics tab needs to fetch charts and preview data when first opened
  if (tab === "analytics") {
    loadAnalytics();
    refreshPreview();
  }
}

// On page load, restore the previously-active tab if one exists.
document.addEventListener("DOMContentLoaded", function () {
  let savedTab = null;
  try {
    savedTab = sessionStorage.getItem("apcoms_active_tab");
  } catch (e) {
    // sessionStorage might be disabled; just use default
  }

  if (savedTab && savedTab !== "monitoring") {
    const btn = document.querySelector(`.tab-btn[onclick*="'${savedTab}'"]`);
    switchTab(savedTab, btn);
  }

  // FOUC-prevention attribute has served its purpose; remove it so
  // subsequent JS-driven switches aren't fighting CSS overrides.
  document.documentElement.removeAttribute("data-active-tab");
});
