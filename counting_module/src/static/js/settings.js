// Settings tab — handles saving shuttle configuration and the
// danger-zone "reset count" action. Both call backend Flask routes
// and surface success/error feedback to the operator.

function saveSettings() {
  const shuttleId = document.getElementById("shuttle-id").value;
  const shuttleName = document.getElementById("shuttle-name").value;
  const capacity = parseInt(document.getElementById("total-capacity").value);
  const stopsText = document.getElementById("designated-stops").value;
  const stops = stopsText
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s);
  const dayStart = document.getElementById("day-start-time").value;
  const dayEnd = document.getElementById("day-end-time").value;

  fetch("/setup_shuttle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      shuttle_id: shuttleId,
      shuttle_name: shuttleName,
      total_capacity: capacity,
      designated_stops: stops,
      day_start_time: dayStart,
      day_end_time: dayEnd,
    }),
  })
    .then((r) => r.json())
    .then((data) => {
      const alertEl = document.getElementById("settings-alert");
      if (data.status === "success") {
        alertEl.className = "alert alert-success";
        alertEl.textContent =
          "Settings saved successfully! Restart system to apply changes.";
      } else {
        alertEl.className = "alert alert-error";
        alertEl.textContent =
          "Failed to save settings. Please check all fields.";
      }
      alertEl.style.display = "block";
      setTimeout(() => (alertEl.style.display = "none"), 4000);
    });
}

function confirmReset() {
  if (
    confirm(
      "Are you sure you want to reset the passenger count to zero? This action cannot be undone.",
    )
  ) {
    fetch("/reset_count", { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        alert("Count reset successfully!");
      })
      .catch((err) => alert("Reset failed. Please try again."));
  }
}
