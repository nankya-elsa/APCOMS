// Live Bookings tab - auto-refreshes every 5 seconds by fetching
// /api/all_bookings. Renders a table sorted newest-first with
// color-coded status badges and a clear empty-state message.

setInterval(refreshBookings, 5000);
document.addEventListener("DOMContentLoaded", refreshBookings);

function refreshBookings() {
  fetch("/api/all_bookings")
    .then((r) => r.json())
    .then((data) => {
      const container = document.getElementById("bookings-table-container");
      if (!container) return;

      const bookings = data.bookings || [];
      if (bookings.length === 0) {
        container.innerHTML =
          '<p style="color: #8b8fa8; font-size: 13px">No bookings yet.</p>';
        return;
      }

      let html =
        '<table class="bookings-table"><thead><tr>' +
        "<th>Created</th>" +
        "<th>Booking</th>" +
        "<th>From</th>" +
        "<th>To</th>" +
        "<th>Status</th>" +
        "<th>Cancel Reason</th>" +
        "</tr></thead><tbody>";
      bookings.forEach((b) => {
        const shortId =
          b.booking_id.length > 10
            ? b.booking_id.slice(0, 10) + "..."
            : b.booking_id;
        const statusClass = "booking-status-" + b.status;
        const cancelReason = b.cancel_reason
          ? b.cancel_reason.replace(/_/g, " ")
          : "—";
        html +=
          "<tr>" +
          "<td>" +
          b.created_at_display +
          "</td>" +
          "<td>" +
          shortId +
          "</td>" +
          "<td>" +
          b.pickup_stop +
          "</td>" +
          "<td>" +
          b.destination_stop +
          "</td>" +
          '<td><span class="booking-status ' +
          statusClass +
          '">' +
          b.status +
          "</span></td>" +
          "<td>" +
          cancelReason +
          "</td>" +
          "</tr>";
      });
      html += "</tbody></table>";

      container.innerHTML = html;
    })
    .catch((err) => console.log("Bookings refresh error:", err));
}
