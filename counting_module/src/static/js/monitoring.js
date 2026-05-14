// Monitoring tab — auto-refreshes occupancy, system status, today's
// summary, and diagnostic logs every 5 seconds by fetching /api/status.
//
// Runs on every page load (the monitoring tab is the default view).

setInterval(function () {
  fetch("/api/status")
    .then((r) => r.json())
    .then((data) => {
      if (!data.occupancy) return;

      // OCCUPANCY CARDS
      document.getElementById("passenger-count").textContent =
        data.occupancy.current_count;
      const seatsEl = document.getElementById("available-seats");
      seatsEl.textContent = data.occupancy.available_seats;
      const seats = parseInt(data.occupancy.available_seats);
      seatsEl.className =
        "card-value " + (seats === 0 ? "red" : seats <= 5 ? "yellow" : "green");
      document.getElementById("current-stop").textContent =
        data.occupancy.current_stop;
      document.getElementById("last-updated").textContent =
        "Last updated: " + data.occupancy.last_updated;

      const status = data.occupancy.occupancy_status;
      let badgeClass = "status-active";
      let badgeText = "Available";
      if (status === "Nearly Full") {
        badgeClass = "status-warning";
        badgeText = "Nearly Full";
      } else if (status === "Full") {
        badgeClass = "status-error";
        badgeText = "Full";
      }
      document.getElementById("occupancy-status").innerHTML =
        `<span class="status-badge ${badgeClass}">${badgeText}</span>`;

      // SYSTEM STATUS PANEL
      const sys = data.system_status.system_status;
      let sysBadge = `<span class="status-badge status-warning">${sys}</span>`;
      if (sys === "Active")
        sysBadge = `<span class="status-badge status-active">Active</span>`;
      else if (sys === "Error")
        sysBadge = `<span class="status-badge status-error">Error</span>`;
      else if (sys === "At a stop")
        sysBadge = `<span class="status-badge status-warning">At a stop</span>`;
      else if (sys === "Offline")
        sysBadge = `<span class="status-badge status-offline">Offline</span>`;
      document.getElementById("system-status-val").innerHTML = sysBadge;

      const cam = data.system_status.camera_status;
      let camBadge = `<span class="status-badge status-warning">Unknown</span>`;
      if (cam === "ok")
        camBadge = `<span class="status-badge status-active">OK</span>`;
      else if (cam === "error")
        camBadge = `<span class="status-badge status-error">Error</span>`;
      document.getElementById("camera-status-val").innerHTML = camBadge;

      document.getElementById("fps-val").textContent =
        data.system_status.fps + " FPS";
      document.getElementById("latency-val").textContent =
        data.system_status.latency_ms + " ms";

      // TODAY'S SUMMARY BAR
      document.getElementById("summary-boardings").textContent =
        data.today_summary.boardings;
      document.getElementById("summary-alightings").textContent =
        data.today_summary.alightings;
      document.getElementById("summary-peak").textContent =
        data.today_summary.peak_hour;
      document.getElementById("summary-stop").textContent =
        data.today_summary.most_active_stop;

      // DIAGNOSTIC LOGS PANEL
      const logsPanel = document.getElementById("diagnostic-logs-panel");
      if (data.diagnostic_logs && data.diagnostic_logs.length > 0) {
        let html = `<table class="logs-table"><thead><tr><th>Time</th><th>Type</th><th>Message</th></tr></thead><tbody>`;
        data.diagnostic_logs.forEach((log) => {
          html += `<tr><td>${log.timestamp}</td><td><span class="log-type log-${log.log_type}">${log.log_type}</span></td><td>${log.message}</td></tr>`;
        });
        html += `</tbody></table>`;
        logsPanel.innerHTML = html;
      } else {
        logsPanel.innerHTML = `<p style="color: #8b8fa8; font-size: 13px">No diagnostic logs yet.</p>`;
      }
    })
    .catch((err) => console.log("Refresh error:", err));
}, 5000);
