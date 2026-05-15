"""
Tests for the BookingDashboardService component.

The BookingDashboardService aggregates booking data from Firebase
to power the admin dashboard's monitoring and analytics views. It
exposes four query methods:

  - get_pickups_expected(stop)
      Live count of reserved bookings whose pickup is the given stop.
      Used on the Monitoring tab to show "X people booked to board here".

  - get_boarded_from_stop(stop)
      Live count of bookings transitioned from reserved to active or
      completed at the given stop today. Used on the Monitoring tab
      to show "X people have already scanned at this stop".

  - get_booking_funnel()
      Aggregate counts across the full booking lifecycle:
      reserved, active, completed, cancelled. Used on the Analytics
      tab as a funnel chart.

  - get_no_show_rate_by_stop()
      Per-stop no-show percentage, calculated as
      (cancelled_no_show / total_bookings_at_stop) × 100. Used on the
      Analytics tab as a bar chart to inform scheduling decisions.

All Firebase calls are mocked so the service can be verified in pure
isolation. The service reads Firebase directly because the dashboard
is online by definition (Flask runs alongside operations with network).
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from booking_dashboard_service import BookingDashboardService


class TestBookingDashboardServiceInitialization:
    """Tests covering BookingDashboardService construction."""

    def test_service_initializes_with_defaults(self):
        """
        BookingDashboardService should instantiate without arguments
        and be ready to use. Firebase initialization is lazy so the
        class can be constructed in tests without real credentials.
        """
        service = BookingDashboardService()
        assert service is not None
        assert hasattr(service, "shuttle_id")

    def test_service_uses_shuttle_id_from_env(self):
        """
        Mirrors the pattern used by every other component in the
        counting module — reads SHUTTLE_ID from environment so
        shuttle identification stays consistent across the system.
        """
        with patch.dict(os.environ, {"SHUTTLE_ID": "shuttle_test_42"}):
            service = BookingDashboardService()
            assert service.shuttle_id == "shuttle_test_42"

    def test_service_accepts_explicit_shuttle_id(self):
        """
        Tests need to override the shuttle ID at construction time
        to verify shuttle-filtering behaviour without requiring
        environment manipulation per test.
        """
        service = BookingDashboardService(shuttle_id="custom_shuttle")
        assert service.shuttle_id == "custom_shuttle"


class TestGetPickupsExpected:
    """Tests covering the count of reserved bookings at a given stop."""

    @patch("booking_dashboard_service.db")
    def test_counts_reserved_bookings_at_stop(self, mock_db):
        """
        With multiple reserved bookings whose pickup is the given
        stop, the method returns the correct count. Active,
        completed, and cancelled bookings at the same stop must
        NOT be counted — only 'reserved' status qualifies.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "CONAS",
            },
            "b4": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "pickup_stop": "CONAS",
            },
            "b5": {
                "shuttle_key": "shuttle_001",
                "status": "cancelled",
                "pickup_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_pickups_expected(stop="CONAS")

        assert count == 2

    @patch("booking_dashboard_service.db")
    def test_filters_out_other_stops(self, mock_db):
        """
        Bookings reserved for a different pickup stop must not be
        counted when querying for a specific stop. We verify this
        with two reserved bookings at different stops and confirm
        only the matching one is counted.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "Main Library",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_pickups_expected(stop="CONAS")

        assert count == 1

    @patch("booking_dashboard_service.db")
    def test_filters_by_shuttle_id(self, mock_db):
        """
        Reserved bookings for OTHER shuttles at the same stop must
        not be counted. This is critical for multi-shuttle
        deployments — each shuttle's dashboard shows only its own
        expected pickups.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
            "b2": {
                "shuttle_key": "shuttle_002",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_pickups_expected(stop="CONAS")

        assert count == 1

    @patch("booking_dashboard_service.db")
    def test_returns_zero_when_no_bookings_match(self, mock_db):
        """
        With no reserved bookings at the given stop (everyone
        already boarded, or nobody booked here), the method
        returns 0 cleanly. The dashboard then shows "Expected
        here: 0" which is the correct user-facing display.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_pickups_expected(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_returns_zero_when_firebase_empty(self, mock_db):
        """
        Fresh deployment with no bookings at all — Firebase returns
        None. The method handles this cleanly and returns 0 rather
        than crashing.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService()
        count = service.get_pickups_expected(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_returns_zero_on_firebase_error(self, mock_db):
        """
        If Firebase is unreachable (network glitch, permission
        issue), the method catches the exception and returns 0
        rather than crashing the dashboard. A transient outage
        should NOT take the dashboard offline.
        """
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase down")
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService()
        count = service.get_pickups_expected(stop="CONAS")

        assert count == 0


class TestGetBoardedFromStop:
    """
    Tests covering the count of bookings that scanned at a given
    stop — only those currently in 'active' status.
    """

    @patch("booking_dashboard_service.db")
    def test_counts_only_active_at_stop(self, mock_db):
        """
        Only bookings with status 'active' and pickup_stop matching
        the given stop are counted. 'Completed' bookings are
        excluded because a completed status means the passenger
        has already alighted — and during normal shuttle loops, a
        passenger who boarded at CEDAT on a prior trip and is
        now completed would otherwise pollute a future CEDAT
        boarded-count query. Counting only 'active' keeps the card
        scoped strictly to "passengers currently onboard who
        boarded at this stop", which is the operator's mental model.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "CONAS",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "CONAS",
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "pickup_stop": "CONAS",
            },
            "b4": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
            "b5": {
                "shuttle_key": "shuttle_001",
                "status": "cancelled",
                "pickup_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_boarded_from_stop(stop="CONAS")

        # only the 2 active bookings count, completed/reserved/cancelled excluded
        assert count == 2

    @patch("booking_dashboard_service.db")
    def test_excludes_other_stops(self, mock_db):
        """
        Active bookings with a different pickup_stop must not be
        counted. Verifies the pickup_stop filter is applied.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "Main Library",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_boarded_from_stop(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_filters_by_shuttle_id(self, mock_db):
        """
        Active bookings on OTHER shuttles at the same pickup stop
        must not be counted on this shuttle's dashboard. Critical
        for multi-shuttle accuracy.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "pickup_stop": "CONAS",
            },
            "b2": {
                "shuttle_key": "shuttle_002",
                "status": "active",
                "pickup_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_boarded_from_stop(stop="CONAS")

        assert count == 1

    @patch("booking_dashboard_service.db")
    def test_returns_zero_when_no_one_has_boarded(self, mock_db):
        """
        At a fresh stop where nobody has scanned yet — only
        reserved bookings exist — the boarded count is 0. The
        dashboard displays this honestly so the operator knows
        the scanner queue is still pending.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "pickup_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_boarded_from_stop(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_returns_zero_on_firebase_error(self, mock_db):
        """
        Firebase failure must not crash the dashboard. Return 0
        cleanly so the card simply displays zero while the rest
        of the dashboard continues operating.
        """
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase down")
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService()
        count = service.get_boarded_from_stop(stop="CONAS")

        assert count == 0


class TestGetBookingFunnel:
    """
    Tests covering the cumulative booking funnel used to drive the
    Analytics tab's funnel chart.

    The funnel uses CUMULATIVE counting — each step counts bookings
    that EVER REACHED that state, not bookings currently at that
    state. This is critical because 'active' is a transient status
    (a booking is active only between scan and alight, ~20 minutes
    typically). By using cumulative counts, the funnel tells a
    stable story:

      Total Booked      = all bookings ever (any status)
      Boarded           = active + completed (everyone who scanned)
      Completed Trips   = completed only (full lifecycle done)
      Cancelled         = cancelled only (never boarded)

    At any time of day this funnel gives an accurate picture of how
    the booking flow is performing since deployment.
    """

    @patch("booking_dashboard_service.db")
    def test_returns_cumulative_counts_for_each_step(self, mock_db):
        """
        With a realistic mix of bookings across all lifecycle states,
        the funnel returns cumulative counts. 'Boarded' includes both
        active (currently onboard) and completed (already alighted)
        because both groups successfully scanned at pickup.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {"shuttle_key": "shuttle_001", "status": "reserved"},
            "b2": {"shuttle_key": "shuttle_001", "status": "reserved"},
            "b3": {"shuttle_key": "shuttle_001", "status": "active"},
            "b4": {"shuttle_key": "shuttle_001", "status": "completed"},
            "b5": {"shuttle_key": "shuttle_001", "status": "completed"},
            "b6": {"shuttle_key": "shuttle_001", "status": "completed"},
            "b7": {"shuttle_key": "shuttle_001", "status": "cancelled"},
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        funnel = service.get_booking_funnel()

        assert funnel["total_booked"] == 7
        # boarded = active + completed = 1 + 3 = 4
        assert funnel["boarded"] == 4
        # completed only = 3
        assert funnel["completed"] == 3
        # cancelled only = 1
        assert funnel["cancelled"] == 1

    @patch("booking_dashboard_service.db")
    def test_filters_by_shuttle_id(self, mock_db):
        """
        Bookings for OTHER shuttles must be excluded from the funnel.
        Each shuttle's dashboard shows only its own booking lifecycle.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {"shuttle_key": "shuttle_001", "status": "completed"},
            "b2": {"shuttle_key": "shuttle_002", "status": "completed"},
            "b3": {"shuttle_key": "shuttle_002", "status": "active"},
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        funnel = service.get_booking_funnel()

        assert funnel["total_booked"] == 1
        assert funnel["boarded"] == 1
        assert funnel["completed"] == 1

    @patch("booking_dashboard_service.db")
    def test_returns_zeros_when_no_bookings(self, mock_db):
        """
        Fresh deployment with no bookings — funnel returns zeros
        for every field. The Analytics chart renders an empty
        funnel rather than crashing.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService()
        funnel = service.get_booking_funnel()

        assert funnel["total_booked"] == 0
        assert funnel["boarded"] == 0
        assert funnel["completed"] == 0
        assert funnel["cancelled"] == 0

    @patch("booking_dashboard_service.db")
    def test_ignores_unknown_status_values(self, mock_db):
        """
        Bookings with status values outside the four known states
        (data corruption, future schema changes) are skipped and
        logged. The funnel still aggregates correctly for the
        well-formed bookings, preventing one corrupt record from
        breaking the entire chart.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {"shuttle_key": "shuttle_001", "status": "active"},
            "b2": {"shuttle_key": "shuttle_001", "status": "unknown_state"},
            "b3": {"shuttle_key": "shuttle_001", "status": "completed"},
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        funnel = service.get_booking_funnel()

        # unknown_state ignored; only 2 well-formed bookings count
        assert funnel["total_booked"] == 2
        # active + completed = boarded
        assert funnel["boarded"] == 2
        assert funnel["completed"] == 1

    @patch("booking_dashboard_service.db")
    def test_returns_zeros_on_firebase_error(self, mock_db):
        """
        Firebase failure must not crash the dashboard. Return a
        zero-funnel dict so the chart shows an empty state while
        the rest of the dashboard continues operating.
        """
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase down")
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService()
        funnel = service.get_booking_funnel()

        assert funnel["total_booked"] == 0
        assert funnel["boarded"] == 0


class TestGetNoShowRateByStop:
    """
    Tests covering the per-stop no-show rate query used to drive
    the Analytics tab's no-show bar chart.

    A no-show is specifically a booking that was auto-cancelled
    because the passenger didn't scan at pickup — i.e. status is
    'cancelled' AND cancel_reason is 'no_show_at_pickup'. User-
    initiated cancellations (different cancel_reason) do NOT count
    as no-shows.

    The rate is calculated as a percentage:
      (no_shows at stop / total bookings at stop) * 100

    Returns a list of per-stop dicts, one entry per stop that has
    any bookings. Stops with zero bookings are omitted entirely.
    """

    @patch("booking_dashboard_service.db")
    def test_calculates_rate_per_stop(self, mock_db):
        """
        With bookings spread across multiple stops, the method
        returns one entry per stop with the correct total,
        no_shows count, and rate percentage. CONAS has 4 total
        bookings of which 1 is a no-show = 25% rate. Western
        Gate has 2 total of which 1 is no-show = 50% rate.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "active",
            },
            "b4": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
            },
            "b5": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "Western Gate",
                "status": "completed",
            },
            "b6": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "Western Gate",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        result = service.get_no_show_rate_by_stop()

        # find each entry
        conas = next(r for r in result if r["stop"] == "CONAS")
        wg = next(r for r in result if r["stop"] == "Western Gate")

        assert conas["total"] == 4
        assert conas["no_shows"] == 1
        assert conas["rate"] == 25.0

        assert wg["total"] == 2
        assert wg["no_shows"] == 1
        assert wg["rate"] == 50.0

    @patch("booking_dashboard_service.db")
    def test_excludes_user_cancellations(self, mock_db):
        """
        Only cancel_reason='no_show_at_pickup' counts as a no-show.
        User-initiated cancellations (different cancel_reason or
        no cancel_reason field) are counted in the total but NOT
        in the no_shows count. This distinguishes "system caught
        a no-show" from "user cancelled before arriving" which
        are operationally different situations.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "user_cancelled",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        result = service.get_no_show_rate_by_stop()

        conas = next(r for r in result if r["stop"] == "CONAS")
        # 2 total bookings at CONAS, but 0 no-shows (cancellation was user-initiated)
        assert conas["total"] == 2
        assert conas["no_shows"] == 0
        assert conas["rate"] == 0.0

    @patch("booking_dashboard_service.db")
    def test_filters_by_shuttle_id(self, mock_db):
        """
        Bookings on OTHER shuttles must not pollute this shuttle's
        per-stop rates. Each shuttle's dashboard shows only its
        own no-show patterns.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
            },
            "b2": {
                "shuttle_key": "shuttle_002",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        result = service.get_no_show_rate_by_stop()

        conas = next(r for r in result if r["stop"] == "CONAS")
        # only shuttle_001's data: 1 completed, 0 no-shows
        assert conas["total"] == 1
        assert conas["no_shows"] == 0
        assert conas["rate"] == 0.0

    @patch("booking_dashboard_service.db")
    def test_returns_empty_list_when_no_bookings(self, mock_db):
        """
        Fresh deployment with no bookings — return an empty list.
        The chart renders an empty state rather than crashing.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService()
        result = service.get_no_show_rate_by_stop()

        assert result == []

    @patch("booking_dashboard_service.db")
    def test_returns_empty_list_on_firebase_error(self, mock_db):
        """
        Firebase failure must not crash the dashboard. Return an
        empty list so the chart renders an empty state.
        """
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase down")
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService()
        result = service.get_no_show_rate_by_stop()

        assert result == []

    @patch("booking_dashboard_service.db")
    def test_rate_calculation_rounds_to_two_decimals(self, mock_db):
        """
        A stop with 3 total bookings and 1 no-show should report
        rate=33.33 (not 33.333333). Two decimals is enough
        precision for a percentage display in the bar chart.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        result = service.get_no_show_rate_by_stop()

        conas = next(r for r in result if r["stop"] == "CONAS")
        assert conas["total"] == 3
        assert conas["no_shows"] == 1
        assert conas["rate"] == 33.33


class TestBookingFunnelWithDateFilter:
    """
    Tests covering date-range filtering on the booking funnel.

    Filtering uses the booking's created_at field (Unix timestamp
    in milliseconds, set when the mobile app first created the
    booking). This is the right field to filter on because it
    represents when the user EXPRESSED INTENT — independent of
    when the booking later transitioned through its lifecycle.

    A booking created last Tuesday that completed today should
    count in last Tuesday's funnel, not today's. The funnel
    answers "of the bookings made in this window, how did they
    flow through the system?"

    Timestamps in test data are computed from datetime strings at
    test time so the tests are self-verifying — no hand-calculated
    Unix milliseconds that could drift from the intended dates.
    """

    @staticmethod
    def _ms(date_str):
        """Convert 'YYYY-MM-DD' to Unix ms timestamp at start of day."""
        from datetime import datetime
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)

    @patch("booking_dashboard_service.db")
    def test_filters_by_start_date(self, mock_db):
        """
        With a start_date provided, only bookings created on or
        after that date are counted. Bookings created BEFORE the
        start_date are excluded entirely, regardless of their
        current status.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-01"),
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-05"),
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        # only bookings on/after March 3
        funnel = service.get_booking_funnel(start_date="2026-03-03")

        assert funnel["total_booked"] == 1
        assert funnel["completed"] == 1

    @patch("booking_dashboard_service.db")
    def test_filters_by_end_date(self, mock_db):
        """
        With an end_date provided, only bookings created on or
        before that date are counted. Bookings created AFTER the
        end_date are excluded — useful for closing out a reporting
        period.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-01"),
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-05"),
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        # only bookings on/before March 3
        funnel = service.get_booking_funnel(end_date="2026-03-03")

        assert funnel["total_booked"] == 1
        assert funnel["completed"] == 1

    @patch("booking_dashboard_service.db")
    def test_filters_by_date_range(self, mock_db):
        """
        With both start_date and end_date, only bookings whose
        created_at falls within the inclusive range are counted.
        Bookings outside the window in either direction are excluded.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-01"),
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-05"),
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-09"),
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        # March 3-7 window — only b2 falls inside
        funnel = service.get_booking_funnel(
            start_date="2026-03-03", end_date="2026-03-07"
        )

        assert funnel["total_booked"] == 1
        assert funnel["completed"] == 1

    @patch("booking_dashboard_service.db")
    def test_no_filter_counts_everything(self, mock_db):
        """
        Calling without any date filter should behave identically
        to the unfiltered version — all bookings count, regardless
        of when they were created. Preserves backward compatibility.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-01"),
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "created_at": self._ms("2026-03-05"),
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        funnel = service.get_booking_funnel()

        assert funnel["total_booked"] == 2

    @patch("booking_dashboard_service.db")
    def test_missing_created_at_excluded_when_filter_active(self, mock_db):
        """
        Bookings that don't have a created_at field can't be placed
        on the timeline, so they must be EXCLUDED when a date filter
        is active. Better to undercount than to include data that
        can't be verified to be in the window. When no filter is
        active, they're still counted (consistent with the unfiltered
        behaviour).
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "created_at": self._ms("2026-03-05"),
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                # no created_at field
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")

        # without filter: both count
        unfiltered = service.get_booking_funnel()
        assert unfiltered["total_booked"] == 2

        # with filter: only b1 (b2 has no created_at to verify)
        filtered = service.get_booking_funnel(start_date="2026-01-01")
        assert filtered["total_booked"] == 1


class TestNoShowRateWithDateFilter:
    """
    Tests covering date-range filtering on the per-stop no-show rate.

    Uses the same created_at filtering approach as the booking
    funnel. Filtering by created_at means a no-show rate calculated
    for a given window is the rate among bookings MADE during that
    window — regardless of when the cancellation later happened.

    This gives operators the right answer for time-windowed analysis:
    "of the bookings made last week, what percentage no-showed?"
    rather than "how many cancellations happened last week?"
    """

    @staticmethod
    def _ms(date_str):
        """Convert 'YYYY-MM-DD' to Unix ms timestamp at start of day."""
        from datetime import datetime
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)

    @patch("booking_dashboard_service.db")
    def test_filters_by_start_date(self, mock_db):
        """
        With start_date filter, only bookings created on or after
        that date contribute to per-stop totals and no-show counts.
        Bookings older than the filter are excluded from BOTH
        numerator and denominator of the rate calculation.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
                "created_at": self._ms("2026-03-01"),  # before window
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
                "created_at": self._ms("2026-03-05"),  # inside window
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        result = service.get_no_show_rate_by_stop(start_date="2026-03-03")

        conas = next(r for r in result if r["stop"] == "CONAS")
        # only b2 in window: 1 booking, 1 no-show, 100% rate
        assert conas["total"] == 1
        assert conas["no_shows"] == 1
        assert conas["rate"] == 100.0

    @patch("booking_dashboard_service.db")
    def test_filters_by_date_range(self, mock_db):
        """
        Both start_date and end_date applied together produce an
        inclusive window. Bookings outside in either direction are
        excluded. This is how operators ask 'what happened in this
        specific reporting period?'
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
                "created_at": self._ms("2026-02-25"),  # before
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
                "created_at": self._ms("2026-03-05"),  # inside
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
                "created_at": self._ms("2026-03-06"),  # inside
            },
            "b4": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
                "created_at": self._ms("2026-03-15"),  # after
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        result = service.get_no_show_rate_by_stop(
            start_date="2026-03-01", end_date="2026-03-10"
        )

        conas = next(r for r in result if r["stop"] == "CONAS")
        # in window: b2 (completed), b3 (no-show) = 2 total, 1 no-show, 50%
        assert conas["total"] == 2
        assert conas["no_shows"] == 1
        assert conas["rate"] == 50.0

    @patch("booking_dashboard_service.db")
    def test_no_filter_counts_everything(self, mock_db):
        """
        Without any filter, every booking contributes regardless of
        creation date. Preserves backward-compatible behaviour for
        callers who don't pass dates.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
                "created_at": self._ms("2026-03-01"),
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
                "created_at": self._ms("2026-03-05"),
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        result = service.get_no_show_rate_by_stop()

        conas = next(r for r in result if r["stop"] == "CONAS")
        assert conas["total"] == 2
        assert conas["no_shows"] == 1
        assert conas["rate"] == 50.0

    @patch("booking_dashboard_service.db")
    def test_missing_created_at_excluded_when_filter_active(self, mock_db):
        """
        Bookings without created_at can't be timestamped on the
        timeline, so when a filter is active they're excluded from
        both the total and the no-show count. Unfiltered queries
        still include them. Same defensive policy as the funnel.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "completed",
                "created_at": self._ms("2026-03-05"),
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "pickup_stop": "CONAS",
                "status": "cancelled",
                "cancel_reason": "no_show_at_pickup",
                # no created_at
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")

        # without filter: both count, 50% rate
        unfiltered = service.get_no_show_rate_by_stop()
        conas_unfiltered = next(r for r in unfiltered if r["stop"] == "CONAS")
        assert conas_unfiltered["total"] == 2
        assert conas_unfiltered["no_shows"] == 1

        # with filter: only b1 counts, 0% rate
        filtered = service.get_no_show_rate_by_stop(start_date="2026-01-01")
        conas_filtered = next(r for r in filtered if r["stop"] == "CONAS")
        assert conas_filtered["total"] == 1
        assert conas_filtered["no_shows"] == 0
        assert conas_filtered["rate"] == 0.0


class TestGetAlightingsExpected:
    """
    Tests covering the count of bookings currently onboard whose
    destination is the given stop.

    These are passengers expected to alight HERE. By counting only
    bookings with status 'active' (not 'completed', not 'reserved'),
    we get a self-resetting count that automatically refreshes when
    the shuttle moves to a new stop — once they alight, status flips
    to 'completed' and they're excluded.
    """

    @patch("booking_dashboard_service.db")
    def test_counts_only_active_with_destination(self, mock_db):
        """
        Only bookings with status 'active' AND destination_stop
        matching the given stop are counted. Reserved bookings are
        excluded because those passengers haven't boarded yet — they
        can't alight if they haven't boarded. Completed bookings are
        excluded because those passengers have already alighted.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "CONAS",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "CONAS",
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "destination_stop": "CONAS",
            },
            "b4": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "destination_stop": "CONAS",
            },
            "b5": {
                "shuttle_key": "shuttle_001",
                "status": "cancelled",
                "destination_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_alightings_expected(stop="CONAS")

        assert count == 2

    @patch("booking_dashboard_service.db")
    def test_excludes_other_destinations(self, mock_db):
        """
        Active bookings with a different destination_stop must not
        be counted at this stop. Confirms the destination_stop
        filter is correctly applied.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "Main Library",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_alightings_expected(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_filters_by_shuttle_id(self, mock_db):
        """
        Active bookings on OTHER shuttles destined here must not be
        counted on this shuttle's dashboard. Critical for
        multi-shuttle accuracy.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "CONAS",
            },
            "b2": {
                "shuttle_key": "shuttle_002",
                "status": "active",
                "destination_stop": "CONAS",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_alightings_expected(stop="CONAS")

        assert count == 1

    @patch("booking_dashboard_service.db")
    def test_returns_zero_when_nobody_alighting_here(self, mock_db):
        """
        When all active bookings have OTHER destinations (passengers
        are onboard but none of them want to alight at this stop),
        the count is 0. Honestly empty card so the operator knows
        nobody is alighting here.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "Main Library",
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "Africa Hall",
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_alightings_expected(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_returns_zero_when_firebase_empty(self, mock_db):
        """
        Fresh deployment with zero bookings — return 0 cleanly
        without crashing.
        """
        mock_ref = MagicMock()
        mock_ref.get.return_value = None
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_alightings_expected(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_returns_zero_on_firebase_error(self, mock_db):
        """
        Firebase failure must not crash the dashboard. Return 0
        cleanly so the card displays zero while the rest of the
        dashboard continues operating.
        """
        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase down")
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(shuttle_id="shuttle_001")
        count = service.get_alightings_expected(stop="CONAS")

        assert count == 0


class TestGetAlightedAtStop:
    """
    Tests covering the count of bookings that have actually
    completed (passenger alighted) at the given stop DURING the
    current visit.

    The "current visit" boundary is critical because the shuttle
    loops through stops all day. A booking completed at CONAS in
    the morning trip must NOT be counted again when the shuttle
    returns to CONAS in the afternoon trip. Self-scoping is
    achieved by comparing the booking's completed_at timestamp
    against current_stop_arrived_at_ms (read from SQLite) — only
    completions that happened during this specific visit count.

    A second guard uses current_stop_arrived_date (also from
    SQLite) to filter by calendar date. This is a belt-and-
    suspenders safety net: even if the timestamp logic somehow
    fails (e.g. orchestrator restarts mid-day with stale
    timestamp from yesterday), the date filter still excludes
    yesterday's data.
    """

    def setup_method(self):
        """Set up a clean SQLite database for each test."""
        import os
        import sqlite3
        os.makedirs("local_database", exist_ok=True)
        self.test_db = "local_database/test_apcoms.db"
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("DELETE FROM system_state")
        conn.commit()
        conn.close()

    def _seed_arrival(self, arrived_at_ms, arrived_date):
        """Helper to seed the arrival timestamp + date into SQLite."""
        import sqlite3
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO system_state (key, value) "
            "VALUES ('current_stop_arrived_at_ms', ?)",
            (str(arrived_at_ms),)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO system_state (key, value) "
            "VALUES ('current_stop_arrived_date', ?)",
            (arrived_date,)
        )
        conn.commit()
        conn.close()

    @patch("booking_dashboard_service.db")
    def test_counts_completions_within_current_visit(self, mock_db):
        """
        Completions that happened AFTER the arrival timestamp (i.e.
        during this visit) are counted. The arrival timestamp is
        seeded into SQLite by advance_and_sync; this test mocks it.
        """
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        # arrival was 5 minutes ago
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        arrived_at_ms = now_ms - 5 * 60 * 1000  # 5 min before now
        self._seed_arrival(arrived_at_ms, today)

        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "destination_stop": "CONAS",
                "completed_at": now_ms - 2 * 60 * 1000,  # 2 min ago, within visit
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "destination_stop": "CONAS",
                "completed_at": now_ms - 1 * 60 * 1000,  # 1 min ago, within visit
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(
            shuttle_id="shuttle_001", db_path=self.test_db
        )
        count = service.get_alighted_at_stop(stop="CONAS")

        assert count == 2

    @patch("booking_dashboard_service.db")
    def test_excludes_completions_before_current_visit(self, mock_db):
        """
        Completions BEFORE the arrival timestamp are excluded. This
        is the core "previous visits don't pollute current visit"
        guard. A booking completed at CONAS this morning must NOT
        be counted when the shuttle returns to CONAS this afternoon.
        """
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        # arrival was 5 minutes ago
        arrived_at_ms = now_ms - 5 * 60 * 1000
        self._seed_arrival(arrived_at_ms, today)

        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            # this one completed 30 min ago, BEFORE we arrived
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "destination_stop": "CONAS",
                "completed_at": now_ms - 30 * 60 * 1000,
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(
            shuttle_id="shuttle_001", db_path=self.test_db
        )
        count = service.get_alighted_at_stop(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_excludes_completions_from_yesterday_via_date_guard(
        self, mock_db
    ):
        """
        Even if a booking's completed_at timestamp happens to be
        AFTER current_stop_arrived_at_ms (e.g. stale timestamp), the
        date safety net excludes completions whose date doesn't
        match current_stop_arrived_date. This guarantees yesterday's
        data never pollutes today's counts.
        """
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        # seed arrival as today
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        self._seed_arrival(now_ms - 5 * 60 * 1000, today)

        # but the completed booking has YESTERDAY's date
        # (its completed_at timestamp could still be "after" our
        # arrival because of some clock weirdness, but the date
        # check should still reject it)
        yesterday = (
            datetime.datetime.now() - datetime.timedelta(days=1)
        )
        yesterday_ms = int(yesterday.timestamp() * 1000)

        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "destination_stop": "CONAS",
                "completed_at": yesterday_ms,
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(
            shuttle_id="shuttle_001", db_path=self.test_db
        )
        count = service.get_alighted_at_stop(stop="CONAS")

        # yesterday's completion excluded by both timestamp AND date
        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_excludes_non_completed_statuses(self, mock_db):
        """
        Only bookings with status 'completed' are counted. Active
        bookings haven't alighted yet; reserved bookings haven't
        even boarded yet; cancelled bookings never trip.
        """
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        arrived_at_ms = now_ms - 5 * 60 * 1000
        self._seed_arrival(arrived_at_ms, today)

        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "active",
                "destination_stop": "CONAS",
                "completed_at": now_ms - 1 * 60 * 1000,
            },
            "b2": {
                "shuttle_key": "shuttle_001",
                "status": "reserved",
                "destination_stop": "CONAS",
                "completed_at": now_ms - 1 * 60 * 1000,
            },
            "b3": {
                "shuttle_key": "shuttle_001",
                "status": "cancelled",
                "destination_stop": "CONAS",
                "completed_at": now_ms - 1 * 60 * 1000,
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(
            shuttle_id="shuttle_001", db_path=self.test_db
        )
        count = service.get_alighted_at_stop(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_filters_by_shuttle_id(self, mock_db):
        """
        Completions on OTHER shuttles must not be counted on this
        shuttle's dashboard.
        """
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        arrived_at_ms = now_ms - 5 * 60 * 1000
        self._seed_arrival(arrived_at_ms, today)

        mock_ref = MagicMock()
        mock_ref.get.return_value = {
            "b1": {
                "shuttle_key": "shuttle_001",
                "status": "completed",
                "destination_stop": "CONAS",
                "completed_at": now_ms - 1 * 60 * 1000,
            },
            "b2": {
                "shuttle_key": "shuttle_002",
                "status": "completed",
                "destination_stop": "CONAS",
                "completed_at": now_ms - 1 * 60 * 1000,
            },
        }
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(
            shuttle_id="shuttle_001", db_path=self.test_db
        )
        count = service.get_alighted_at_stop(stop="CONAS")

        assert count == 1

    @patch("booking_dashboard_service.db")
    def test_returns_zero_when_arrival_state_missing(self, mock_db):
        """
        If current_stop_arrived_at_ms hasn't been written yet
        (e.g. fresh deployment, advance_and_sync never called),
        the method returns 0 cleanly rather than crashing. The
        dashboard simply shows zero alightings until the first
        stop transition.
        """
        # don't seed arrival — system_state is empty
        mock_ref = MagicMock()
        mock_ref.get.return_value = {}
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(
            shuttle_id="shuttle_001", db_path=self.test_db
        )
        count = service.get_alighted_at_stop(stop="CONAS")

        assert count == 0

    @patch("booking_dashboard_service.db")
    def test_returns_zero_on_firebase_error(self, mock_db):
        """
        Firebase failure must not crash the dashboard. Return 0
        cleanly so the card displays zero while the rest of the
        dashboard continues operating.
        """
        import datetime
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        self._seed_arrival(now_ms - 5 * 60 * 1000, today)

        mock_ref = MagicMock()
        mock_ref.get.side_effect = Exception("Firebase down")
        mock_db.reference.return_value = mock_ref

        service = BookingDashboardService(
            shuttle_id="shuttle_001", db_path=self.test_db
        )
        count = service.get_alighted_at_stop(stop="CONAS")

        assert count == 0
