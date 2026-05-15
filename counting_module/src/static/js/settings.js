// Settings tab — handles saving the editable Service Hours, resetting
// to defaults, and the emergency "reset count" action.

function saveSettings() {
  const dayStart = document.getElementById("day-start-time").value;
  const dayEnd = document.getElementById("day-end-time").value;

  if (!dayStart && !dayEnd) {
    showAlert("error", "Please set at least one service time before saving.");
    return;
  }

  fetch("/setup_shuttle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      day_start_time: dayStart,
      day_end_time: dayEnd,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        showAlert("success", "Service hours saved successfully.");
      } else {
        showAlert("error", "Failed to save settings.");
      }
    })
    .catch(() => showAlert("error", "Failed to save settings."));
}

function resetServiceHoursToDefaults() {
  const defaultStart = "06:00";
  const defaultEnd = "23:59";
  document.getElementById("day-start-time").value = defaultStart;
  document.getElementById("day-end-time").value = defaultEnd;

  fetch("/setup_shuttle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      day_start_time: defaultStart,
      day_end_time: defaultEnd,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "success") {
        showAlert(
          "success",
          "Service hours reset to defaults (06:00 to 23:59).",
        );
      } else {
        showAlert("error", "Failed to reset service hours.");
      }
    })
    .catch(() => showAlert("error", "Failed to reset service hours."));
}

function openResetCountModal() {
  document.getElementById("reset-count-modal").style.display = "flex";
}

function closeResetCountModal() {
  document.getElementById("reset-count-modal").style.display = "none";
}

function performResetCount() {
  closeResetCountModal();
  fetch("/reset_count", { method: "POST" })
    .then((r) => r.json())
    .then((data) => {
      showAlert("success", "Passenger count reset to zero.");
    })
    .catch(() => showAlert("error", "Reset failed. Please try again."));
}

function showAlert(type, text) {
  const alertEl = document.getElementById("settings-alert");
  alertEl.className =
    type === "success" ? "alert alert-success" : "alert alert-error";
  alertEl.textContent = text;
  alertEl.style.display = "block";
  setTimeout(() => (alertEl.style.display = "none"), 4000);
}
