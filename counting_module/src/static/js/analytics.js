// Analytics tab — fetches /api/analytics and /api/passenger_events on
// demand, renders four Chart.js visualizations, generates concise
// data-driven insights, populates a filterable preview table, and
// triggers CSV exports.

// Chart instances are kept module-level so we can destroy and re-create
// them when filters change. Re-creating is simpler than mutating in place.
let adoptionChartInstance = null;
let peakHoursChartInstance = null;
let stopPopularityChartInstance = null;
let dayOfWeekChartInstance = null;
let bookingFunnelChartInstance = null;
let noShowRateChartInstance = null;

// ANALYTICS - LOAD AND RENDER CHARTS
function loadAnalytics(
  startDate = null,
  endDate = null,
  startTime = null,
  endTime = null,
) {
  // Show loading overlays on all chart containers while fetches are
  // in flight. Each chart's render function will hide its own overlay
  // when the canvas is populated.
  const chartIds = [
    "adoption-chart",
    "peak-hours-chart",
    "stop-popularity-chart",
    "day-of-week-chart",
    "booking-funnel-chart",
    "no-show-rate-chart",
  ];
  chartIds.forEach((id) => {
    const overlay = document.getElementById(id + "-loading");
    if (overlay) overlay.style.display = "flex";
  });

  let url = "/api/analytics";

  const params = [];
  if (startDate) params.push("start_date=" + startDate);
  if (endDate) params.push("end_date=" + endDate);
  if (startTime) params.push("start_time=" + startTime);
  if (endTime) params.push("end_time=" + endTime);
  if (params.length) url += "?" + params.join("&");

  fetch(url)
    .then((r) => r.json())
    .then((data) => {
      document.getElementById("analytics-total-boardings").textContent =
        data.total_boardings;
      document.getElementById("analytics-avg-occupancy").textContent =
        data.average_occupancy;
      document.getElementById("analytics-popular-stop").textContent =
        data.most_popular_stop;

      updateSuggestions(data);
      renderAdoptionChart(data.adoption_data);
      renderPeakHoursChart(data.peak_hours_data);
      renderStopPopularityChart(data.stop_popularity_data);
      renderDayOfWeekChart(data.day_of_week_data);
    })
    .catch((err) => console.log("Analytics load error:", err));

  // Booking insights are fetched separately because they come from
  // Firebase (not SQLite passenger events). They accept the same
  // start_date / end_date filter as the passenger traffic charts so
  // the entire Analytics tab refreshes consistently when the operator
  // applies a date range. Time filters (start_time / end_time) don't
  // apply to bookings — they're stored as ms timestamps and grouped
  // by the date the user created the booking, not the time-of-day.
  let bookingUrl = "/api/booking_analytics";
  const bookingParams = [];
  if (startDate) bookingParams.push("start_date=" + startDate);
  if (endDate) bookingParams.push("end_date=" + endDate);
  if (bookingParams.length) bookingUrl += "?" + bookingParams.join("&");

  fetch(bookingUrl)
    .then((r) => r.json())
    .then((data) => {
      renderBookingFunnelChart(data.funnel);
      renderNoShowRateChart(data.no_show_rates);
      updateBookingSuggestions(data);
    })
    .catch((err) => console.log("Booking analytics load error:", err));
}

function applyAnalyticsFilter() {
  const start = document.getElementById("analytics-start").value;
  const end = document.getElementById("analytics-end").value;
  const startTime = document.getElementById("analytics-start-time").value;
  const endTime = document.getElementById("analytics-end-time").value;
  const status = document.getElementById("filter-status");

  let parts = [];
  if (start || end) parts.push(`${start || "beginning"} to ${end || "today"}`);
  if (startTime || endTime)
    parts.push(`${startTime || "00:00"}–${endTime || "23:59"} daily`);

  if (parts.length > 0) {
    status.textContent = "Showing data: " + parts.join(", ");
  } else {
    status.textContent = "Showing all data since deployment";
  }

  loadAnalytics(start, end, startTime, endTime);
}

function clearAnalyticsFilter() {
  document.getElementById("analytics-start").value = "";
  document.getElementById("analytics-end").value = "";
  document.getElementById("analytics-start-time").value = "";
  document.getElementById("analytics-end-time").value = "";
  document.getElementById("filter-status").textContent =
    "Showing all data since deployment";
  loadAnalytics();
}

// SMART SUGGESTIONS - concise insight + recommendation
function updateSuggestions(data) {
  // peak hours - fact + actionable insight
  const hours = data.peak_hours_data.values;
  const labels = data.peak_hours_data.labels;
  if (hours.length > 0 && Math.max(...hours) > 0) {
    const max = Math.max(...hours);
    const peakIdx = hours.indexOf(max);
    const peakHour = labels[peakIdx];
    const nonZero = hours.filter((v) => v > 0);
    const total = hours.reduce((a, b) => a + b, 0);
    const peakPct = total > 0 ? Math.round((max / total) * 100) : 0;

    if (nonZero.length > 1) {
      const minVal = Math.min(...nonZero);
      const quietIdx = hours.indexOf(minVal);
      const quietHour = labels[quietIdx];
      document.getElementById("peak-hours-suggestion").innerHTML =
        `🔴 Peak: <strong>${peakHour}</strong> (${peakPct}% of daily volume), ensure shuttle availability. ` +
        `🔵 Quietest: <strong>${quietHour}</strong>, ideal for charging or maintenance.`;
    } else {
      document.getElementById("peak-hours-suggestion").innerHTML =
        `🔴 All boardings concentrated at <strong>${peakHour}</strong>.`;
    }
  } else {
    document.getElementById("peak-hours-suggestion").innerHTML =
      `No boardings in the selected window.`;
  }

  // stop popularity - top stop + percentage + recommendation
  const stops = data.stop_popularity_data.labels;
  const stopValues = data.stop_popularity_data.values;
  if (stops.length > 0) {
    const total = stopValues.reduce((a, b) => a + b, 0);
    const topPct = total > 0 ? Math.round((stopValues[0] / total) * 100) : 0;
    let suggestion = `<strong>${stops[0]}</strong> handles ${topPct}% of all boardings,`;
    if (stops.length > 1) {
      const bottom = stops[stops.length - 1];
      suggestion += ` consider extending dwell time here. <strong>${bottom}</strong> is least used; review route necessity.`;
    } else {
      suggestion += `.`;
    }
    document.getElementById("stop-popularity-suggestion").innerHTML =
      suggestion;
  } else {
    document.getElementById("stop-popularity-suggestion").innerHTML =
      `No stop activity in the selected window.`;
  }

  // adoption trend - growth percentage + projection
  const days = data.adoption_data.values;
  if (days.length >= 2) {
    const recent = days[days.length - 1];
    const first = days[0];
    if (first > 0) {
      const growth = Math.round(((recent - first) / first) * 100);
      if (growth > 10) {
        document.getElementById("adoption-suggestion").innerHTML =
          `📈 Strong growth: <strong>+${growth}%</strong> (${first} → ${recent} daily). Plan for capacity expansion.`;
      } else if (growth < -10) {
        document.getElementById("adoption-suggestion").innerHTML =
          `📉 Adoption declined <strong>${growth}%</strong> (${first} → ${recent}). Investigate possible causes.`;
      } else {
        document.getElementById("adoption-suggestion").innerHTML =
          `Adoption is steady at ~<strong>${recent}</strong> daily boardings.`;
      }
    } else {
      document.getElementById("adoption-suggestion").innerHTML =
        `Adoption is starting to build, more data needed for trends.`;
    }
  } else if (days.length === 1) {
    document.getElementById("adoption-suggestion").innerHTML =
      `<strong>${days[0]}</strong> boardings recorded, more data needed to detect a trend.`;
  } else {
    document.getElementById("adoption-suggestion").innerHTML =
      `No daily data in the selected window.`;
  }

  // day of week - busiest weekday + weekend comparison
  const dows = data.day_of_week_data.values;
  const dowLabels = data.day_of_week_data.labels;
  if (dows.length > 0 && Math.max(...dows) > 0) {
    const maxDow = Math.max(...dows);
    const peakDayIdx = dows.indexOf(maxDow);
    const peakDay = dowLabels[peakDayIdx];
    const weekdayTotal = dows.slice(0, 5).reduce((a, b) => a + b, 0);
    const weekendTotal = dows.slice(5, 7).reduce((a, b) => a + b, 0);
    const weekdayAvg = weekdayTotal / 5;
    const weekendAvg = weekendTotal / 2;
    let suggestion = `<strong>${peakDay}</strong> is busiest with ${maxDow} boardings.`;
    if (weekdayAvg > 0 && weekendAvg < weekdayAvg * 0.5) {
      const ratio = Math.round((weekendAvg / weekdayAvg) * 100);
      suggestion += ` Weekends only ${ratio}% of weekday volume, consider reduced weekend service.`;
    }
    document.getElementById("day-of-week-suggestion").innerHTML = suggestion;
  } else {
    document.getElementById("day-of-week-suggestion").innerHTML =
      `No weekday activity in the selected window.`;
  }
}

function renderAdoptionChart(adoptionData) {
  const loader = document.getElementById("adoption-chart-loading");
  if (loader) loader.style.display = "none";
  const ctx = document.getElementById("adoption-chart").getContext("2d");
  if (adoptionChartInstance) adoptionChartInstance.destroy();
  adoptionChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: adoptionData.labels,
      datasets: [
        {
          label: "Boardings",
          data: adoptionData.values,
          borderColor: "#4f9ef7",
          backgroundColor: "rgba(79, 158, 247, 0.1)",
          borderWidth: 2,
          tension: 0.3,
          fill: true,
          pointBackgroundColor: "#4f9ef7",
          pointRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: "#d1d5db" } } },
      scales: {
        x: { ticks: { color: "#8b8fa8" }, grid: { color: "#1f2230" } },
        y: {
          ticks: { color: "#8b8fa8" },
          grid: { color: "#1f2230" },
          beginAtZero: true,
        },
      },
    },
  });
}

function renderPeakHoursChart(peakData) {
  const loader = document.getElementById("peak-hours-chart-loading");
  if (loader) loader.style.display = "none";
  const ctx = document.getElementById("peak-hours-chart").getContext("2d");
  if (peakHoursChartInstance) peakHoursChartInstance.destroy();
  const values = peakData.values;
  const max = Math.max(...values);
  const peakThreshold = max * 0.6;
  const lowThreshold = max * 0.2;
  const colors = values.map((v) => {
    if (v >= peakThreshold && v > 0) return "#ef4444";
    if (v <= lowThreshold) return "#4f9ef7";
    return "#8b8fa8";
  });
  peakHoursChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: peakData.labels,
      datasets: [
        {
          label: "Boardings",
          data: peakData.values,
          backgroundColor: colors,
          borderColor: colors,
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8b8fa8" }, grid: { color: "#1f2230" } },
        y: {
          ticks: { color: "#8b8fa8" },
          grid: { color: "#1f2230" },
          beginAtZero: true,
        },
      },
    },
  });
}

function renderStopPopularityChart(stopData) {
  const loader = document.getElementById("stop-popularity-chart-loading");
  if (loader) loader.style.display = "none";
  const ctx = document.getElementById("stop-popularity-chart").getContext("2d");
  if (stopPopularityChartInstance) stopPopularityChartInstance.destroy();
  stopPopularityChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: stopData.labels,
      datasets: [
        {
          label: "Boardings",
          data: stopData.values,
          backgroundColor: "#22c55e",
          borderColor: "#16a34a",
          borderWidth: 1,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: "#8b8fa8" },
          grid: { color: "#1f2230" },
          beginAtZero: true,
        },
        y: { ticks: { color: "#8b8fa8" }, grid: { color: "#1f2230" } },
      },
    },
  });
}

function renderDayOfWeekChart(dayData) {
  const loader = document.getElementById("day-of-week-chart-loading");
  if (loader) loader.style.display = "none";
  const ctx = document.getElementById("day-of-week-chart").getContext("2d");
  if (dayOfWeekChartInstance) dayOfWeekChartInstance.destroy();
  // weekend lighter, weekday brighter
  const colors = dayData.labels.map((day) => {
    if (day === "Saturday" || day === "Sunday") return "#8b8fa8";
    return "#a855f7";
  });
  dayOfWeekChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: dayData.labels,
      datasets: [
        {
          label: "Boardings",
          data: dayData.values,
          backgroundColor: colors,
          borderColor: colors,
          borderWidth: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: "#8b8fa8" }, grid: { color: "#1f2230" } },
        y: {
          ticks: { color: "#8b8fa8" },
          grid: { color: "#1f2230" },
          beginAtZero: true,
        },
      },
    },
  });
}

// DATA PREVIEW TABLE - fetches from /api/passenger_events with current filters
function refreshPreview() {
  const start = document.getElementById("start-date").value;
  const end = document.getElementById("end-date").value;
  const startTime = document.getElementById("start-time").value;
  const endTime = document.getElementById("end-time").value;
  const direction = document.getElementById("direction").value;
  const stop = document.getElementById("stop-location").value;

  let url = "/api/passenger_events?";
  if (start) url += "start_date=" + start + "&";
  if (end) url += "end_date=" + end + "&";
  if (startTime) url += "start_time=" + startTime + "&";
  if (endTime) url += "end_time=" + endTime + "&";
  if (direction) url += "direction=" + direction + "&";
  if (stop) url += "stop_location=" + encodeURIComponent(stop) + "&";

  fetch(url)
    .then((r) => r.json())
    .then((data) => {
      const tbody = document.getElementById("preview-tbody");
      const countEl = document.getElementById("preview-count");

      countEl.textContent = `${data.total} event${data.total === 1 ? "" : "s"}`;

      if (!data.events || data.events.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #8b8fa8;">No events match the current filters.</td></tr>`;
        return;
      }

      let html = "";
      data.events.forEach((ev) => {
        const dirClass =
          ev.direction === "boarding"
            ? "direction-boarding"
            : "direction-alighting";
        html += `<tr>
          <td>${ev.timestamp}</td>
          <td><span class="direction-pill ${dirClass}">${ev.direction}</span></td>
          <td>${ev.passenger_count}</td>
          <td>${ev.available_seats}</td>
          <td>${ev.stop_location}</td>
        </tr>`;
      });
      tbody.innerHTML = html;
    })
    .catch((err) => {
      console.log("Preview load error:", err);
      document.getElementById("preview-tbody").innerHTML =
        `<tr><td colspan="5" style="text-align: center; color: #ef4444;">Error loading events.</td></tr>`;
    });
}

// BOOKING FUNNEL CHART - horizontal bar chart showing cumulative
// booking lifecycle counts: Total Booked, Boarded, Completed, Cancelled.
// Bars shrink left-to-right showing drop-off through the funnel.
function renderBookingFunnelChart(funnelData) {
  const loader = document.getElementById("booking-funnel-chart-loading");
  if (loader) loader.style.display = "none";
  const ctx = document.getElementById("booking-funnel-chart").getContext("2d");
  if (bookingFunnelChartInstance) bookingFunnelChartInstance.destroy();

  // Funnel steps in narrative order — booked first, then those who
  // boarded, then those who completed. Cancelled shown separately
  // as the exit branch.
  const labels = ["Total Booked", "Boarded", "Completed", "Cancelled"];
  const values = [
    funnelData.total_booked,
    funnelData.boarded,
    funnelData.completed,
    funnelData.cancelled,
  ];
  // Color-code: funnel progression in blue shades, cancellation in red
  const colors = ["#4f9ef7", "#3b82f6", "#22c55e", "#ef4444"];

  bookingFunnelChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Bookings",
          data: values,
          backgroundColor: colors,
          borderColor: colors,
          borderWidth: 1,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: { color: "#8b8fa8" },
          grid: { color: "#1f2230" },
          beginAtZero: true,
        },
        y: { ticks: { color: "#8b8fa8" }, grid: { color: "#1f2230" } },
      },
    },
  });
}

// NO-SHOW RATE BY STOP CHART - bar chart of % no-show per stop,
// sorted descending so worst stops appear first. Red bars draw
// the eye to problem stops needing operational attention.
function renderNoShowRateChart(rateData) {
  const loader = document.getElementById("no-show-rate-chart-loading");
  if (loader) loader.style.display = "none";
  const ctx = document.getElementById("no-show-rate-chart").getContext("2d");
  if (noShowRateChartInstance) noShowRateChartInstance.destroy();

  // Sort descending by rate so worst offenders are at the top
  const sorted = [...rateData].sort((a, b) => b.rate - a.rate);
  const labels = sorted.map((r) => r.stop);
  const values = sorted.map((r) => r.rate);

  // Color severity: high no-show rate = red, medium = orange, low = green
  const colors = values.map((v) => {
    if (v >= 30) return "#ef4444";
    if (v >= 15) return "#eab308";
    return "#22c55e";
  });

  noShowRateChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "No-Show Rate (%)",
          data: values,
          backgroundColor: colors,
          borderColor: colors,
          borderWidth: 1,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: function (context) {
              const idx = context.dataIndex;
              const stop = sorted[idx];
              return `${stop.no_shows} of ${stop.total} bookings (${stop.rate}%)`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "#8b8fa8",
            callback: function (value) {
              return value + "%";
            },
          },
          grid: { color: "#1f2230" },
          beginAtZero: true,
          max: 100,
        },
        y: { ticks: { color: "#8b8fa8" }, grid: { color: "#1f2230" } },
      },
    },
  });
}

// BOOKING SUGGESTIONS - data-driven insights below each booking chart.
// Translates raw numbers into actionable narrative for the operator.
function updateBookingSuggestions(data) {
  // Funnel suggestion — surface the biggest drop-off in the funnel
  const f = data.funnel;
  const funnelSugEl = document.getElementById("booking-funnel-suggestion");
  if (f.total_booked === 0) {
    funnelSugEl.innerHTML = "No bookings yet, waiting for first reservations.";
  } else {
    const boardRate = Math.round((f.boarded / f.total_booked) * 100);
    const cancelRate = Math.round((f.cancelled / f.total_booked) * 100);
    const inTransit = f.boarded - f.completed;
    let parts = [];
    parts.push(
      `<strong>${boardRate}%</strong> of bookings made it to boarding`,
    );
    if (cancelRate > 0) {
      parts.push(`<strong>${cancelRate}%</strong> cancelled`);
    }
    if (inTransit > 0) {
      parts.push(`<strong>${inTransit}</strong> currently onboard`);
    }
    funnelSugEl.innerHTML = parts.join(" · ");
  }

  // No-show rate suggestion — highlight worst stop or congratulate clean ops
  const rates = data.no_show_rates;
  const rateSugEl = document.getElementById("no-show-rate-suggestion");
  if (!rates || rates.length === 0) {
    rateSugEl.innerHTML = "No booking activity at any stop yet.";
  } else {
    const sorted = [...rates].sort((a, b) => b.rate - a.rate);
    const worst = sorted[0];
    if (worst.rate === 0) {
      rateSugEl.innerHTML =
        "Zero no-shows across all stops, bookings are converting cleanly.";
    } else if (worst.rate >= 30) {
      rateSugEl.innerHTML =
        `🔴 <strong>${worst.stop}</strong> has a ${worst.rate}% no-show rate ` +
        `(${worst.no_shows} of ${worst.total} bookings). ` +
        `Consider reminder notifications or schedule review.`;
    } else if (worst.rate >= 15) {
      rateSugEl.innerHTML = `🟡 <strong>${worst.stop}</strong> has a ${worst.rate}% no-show rate. Worth monitoring.`;
    } else {
      rateSugEl.innerHTML = `🟢 Worst stop is <strong>${worst.stop}</strong> at ${worst.rate}%, booking conversion is healthy overall.`;
    }
  }
}

// EXPORT DATA - uses the same filters as the preview table
function exportData() {
  const start = document.getElementById("start-date").value;
  const end = document.getElementById("end-date").value;
  const startTime = document.getElementById("start-time").value;
  const endTime = document.getElementById("end-time").value;
  const direction = document.getElementById("direction").value;
  const stop = document.getElementById("stop-location").value;

  let url = "/export?";
  if (start) url += "start_date=" + start + "&";
  if (end) url += "end_date=" + end + "&";
  if (startTime) url += "start_time=" + startTime + "&";
  if (endTime) url += "end_time=" + endTime + "&";
  if (direction) url += "direction=" + direction + "&";
  if (stop) url += "stop_location=" + encodeURIComponent(stop) + "&";

  window.location.href = url;
}
