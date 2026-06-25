"""
Helper for starting the BookingFirebaseListener as a background
service in any Python process.

The listener observes Firebase /bookings and applies seat-pool
mutations (decrement on reserved, increment on user cancellation)
in response to events. It used to live exclusively inside
ScannerOrchestrator.run(), which meant booking events were only
processed while the orchestrator was running. That left a gap:
the dashboard is always-on, but the orchestrator only runs during
service hours, so bookings made outside service hours sat
unprocessed (reserved status visible in Firebase but available
seats never decremented) until the next orchestrator startup
caught up.

Moving the listener startup into a standalone helper that the
dashboard process calls fixes this gap. To avoid double-counting
under concurrent access (two listeners in two processes both
receiving the same Firebase event and both mutating the seat
pool), the orchestrator no longer starts its own listener at all.
The dashboard is the canonical observer; the orchestrator focuses
on shuttle operation and reads seat-pool state from the persisted
SQLite + Firebase records the dashboard's listener keeps in sync.
"""

import logging
import os
import threading
import time

from firebase_admin import db

from firebase_sync import FirebaseSyncComponent
from seat_pool_manager import SeatPoolManager
from booking_firebase_listener import BookingFirebaseListener

logger = logging.getLogger(__name__)


def start_booking_listener(shuttle_id, db_path, poll_interval=2.0):
    """
    Start the booking listener stack as a background service.

    Builds a SeatPoolManager + BookingFirebaseListener wired through
    FirebaseSync, attaches the listener to Firebase /bookings, and
    starts a daemon polling thread as a safety net for the
    firebase-admin SDK's missing child_changed semantics. Returns
    the listener instance so the caller can hold a reference (the
    streaming thread and the poller both keep the listener alive,
    but a held reference makes the architectural ownership explicit).

    Args:
        shuttle_id:     The shuttle identifier to filter bookings on.
        db_path:        Path to the local SQLite database used by
                        BookingFirebaseListener for idempotency
                        tracking and by SeatPoolManager for persisting
                        the seat pool.
        poll_interval:  Seconds between safety-net polls of /bookings.
                        Defaults to 2.0.

    Returns:
        The BookingFirebaseListener instance.
    """
    firebase_sync = FirebaseSyncComponent(shuttle_id=shuttle_id)
    firebase_sync.initialize()

    seat_pool = SeatPoolManager(
        total_capacity=int(os.getenv("TOTAL_CAPACITY", "20")),
        db_path=db_path,
        firebase_sync=firebase_sync,
    )
    listener = BookingFirebaseListener(
        shuttle_id=shuttle_id,
        db_path=db_path,
        seat_pool_manager=seat_pool,
    )

    def _handler(event):
        # Firebase delivers updates in several shapes:
        #   path=/                       initial full snapshot
        #   path=/<booking_id>           whole booking or partial dict
        #   path=/<booking_id>/<field>   single field update
        #
        # We can't trust event.data to be complete on multi-field
        # updates, so always re-fetch the full booking when we have
        # a specific id. That way the downstream listener always
        # sees shuttle_key + status + cancel_reason together.
        path = (event.path or "").lstrip("/")
        data = event.data

        if not path:
            if isinstance(data, dict):
                for booking_id, booking_data in data.items():
                    listener.on_booking_event(booking_id, booking_data)
            return

        booking_id = path.split("/")[0]

        try:
            full = db.reference(f"bookings/{booking_id}").get()
            if isinstance(full, dict):
                listener.on_booking_event(booking_id, full)
        except Exception as e:
            logger.error(
                f"Failed to fetch full booking {booking_id}: {e}"
            )

    try:
        db.reference("bookings").listen(_handler)
        logger.info("BookingFirebaseListener attached to /bookings")
    except Exception as e:
        logger.error(f"Failed to attach booking listener: {e}")

    def _poll_loop():
        # Safety net for firebase-admin's missing child_changed:
        # every poll_interval seconds, route the full /bookings
        # snapshot through the listener. The SQLite-backed
        # idempotency check in BookingFirebaseListener ensures
        # we only act on actual status transitions.
        while True:
            try:
                all_bookings = db.reference("bookings").get()
                if isinstance(all_bookings, dict):
                    for booking_id, booking_data in all_bookings.items():
                        if isinstance(booking_data, dict):
                            listener.on_booking_event(
                                booking_id, booking_data
                            )
            except Exception as e:
                logger.error(f"Booking poller error: {e}")
            time.sleep(poll_interval)

    thread = threading.Thread(target=_poll_loop, daemon=True)
    thread.start()
    logger.info(
        f"Booking poller started (every {poll_interval}s)"
    )

    return listener
