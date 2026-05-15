"""
Scanner Orchestrator Component for APCOMS

Coordinates the full passenger boarding flow at a shuttle stop:
  - Reads the shuttle's current stop from SQLite
  - Runs the QR scanner repeatedly to handle a queue of passengers
  - Validates each scan against Firebase bookings
  - Launches main.py to process the actual scenario after the queue
  - Advances the shuttle's stop after main.py finishes
  - Pushes the new state to Firebase so the mobile app stays accurate

This component is the operator's main entry point. Rather than
running main.py directly (which is now a sub-step), the operator
runs the orchestrator and lets it drive everything else.

The orchestrator is purely a conductor — it doesn't open the
camera, validate bookings, or count passengers itself. Each of
those responsibilities lives in its dedicated component. The
orchestrator just decides WHEN each component runs and feeds it
the right state.
"""

import os
import sys
import time
import sqlite3
import subprocess
import logging
import firebase_admin
from firebase_admin import credentials, db

from booking_validator import BookingValidator
from qr_scanner import QRScanner
from counting_logic import CountingLogic
from firebase_sync import FirebaseSyncComponent
from no_show_canceller import NoShowCanceller
from service_day_manager import ServiceDayManager

logger = logging.getLogger(__name__)


class ScannerOrchestrator:
    """
    Top-level conductor for the booking + counting + advance flow.

    Attributes:
        db_path:    Path to the SQLite database used for reading
                    current_stop and persisting state. Defaults to
                    the production database; tests override this.
        shuttle_id: Identifier for this shuttle, used when pushing
                    state to Firebase. Read from SHUTTLE_ID env var
                    so configuration stays consistent with the rest
                    of the counting module.
    """

    def __init__(self, db_path=None):
        """
        Initialize the ScannerOrchestrator.

        Underlying components (scanner, validator, firebase_sync,
        counting_logic) are NOT constructed here. They are created
        on demand inside run() so this class stays cheap to
        instantiate in tests and so any failure during their setup
        doesn't break the orchestrator's lifecycle management.

        Args:
            db_path: Optional override for the SQLite database
                     path. Defaults to 'local_database/apcoms.db'.
        """
        self.db_path = db_path or "local_database/apcoms.db"
        self.shuttle_id = os.getenv("SHUTTLE_ID", "shuttle_001")

    def _ensure_firebase(self):
        """
        Lazily initialize Firebase Admin SDK on first use.

        Idempotent and safe to call repeatedly. Mirrors the pattern
        used by BookingValidator, BookingCompleter, NoShowCanceller,
        and BookingDashboardService so the whole counting module
        shares one Firebase app and credential set.
        """
        if firebase_admin._apps:
            return

        cred_path = os.getenv(
            "FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json"
        )
        database_url = os.getenv("FIREBASE_DATABASE_URL")

        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(
                cred, {"databaseURL": database_url}
            )
            logger.info("Firebase initialized for ScannerOrchestrator")
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")

    def should_stop_here(self, stop):
        """
        Decide whether the shuttle should pause at the given stop
        to run the scanner queue.

        The shuttle physically visits every stop on its route (real
        shuttles don't teleport). What this method controls is
        whether we open the scanner queue and run main.py here, or
        skip those costly steps and advance immediately.

        A stop is worth pausing at if EITHER:
          - A reserved booking has pickup_stop == this stop
            (a passenger is waiting to board here)
          - An active booking has destination_stop == this stop
            (a passenger onboard is expecting to alight here)

        On Firebase failure, returns True as a conservative
        fallback: better to waste a few seconds at an empty stop
        than to silently skip past a passenger waiting in real
        life. Network glitches must never cause missed pickups.

        Args:
            stop: The shuttle stop name being evaluated.

        Returns:
            True if the shuttle should pause here, False if it
            can pass through and advance immediately.
        """
        self._ensure_firebase()

        try:
            ref = db.reference("bookings")
            all_bookings = ref.get()
        except Exception as e:
            logger.error(
                f"Error querying bookings for stop check ({stop}): {e}"
            )
            return True  # safe fallback

        if not all_bookings:
            return False

        for _, booking in all_bookings.items():
            if not isinstance(booking, dict):
                continue
            if booking.get("shuttle_key") != self.shuttle_id:
                continue

            status = booking.get("status")
            pickup = booking.get("pickup_stop")
            destination = booking.get("destination_stop")

            # passenger waiting to board here
            if status == "reserved" and pickup == stop:
                return True
            # passenger onboard expecting to alight here
            if status == "active" and destination == stop:
                return True

        return False

    def read_current_stop(self):
        """
        Read the shuttle's current stop from SQLite system_state.

        This is how the orchestrator knows where the shuttle is
        right now, which it then feeds to BookingValidator so
        QR scans are validated against the correct pickup stop.

        Returns 'Western Gate' (the first stop in the route loop)
        when no current_stop row exists yet, so the orchestrator
        can run on a fresh deployment without manual SQLite setup.
        Resilient to database errors — same default returned
        rather than crashing the boarding session.

        Returns:
            The shuttle's current stop name as a string.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM system_state WHERE key='current_stop'"
            )
            row = cursor.fetchone()
            conn.close()
            if row is None or row[0] is None:
                return "Western Gate"
            return row[0]
        except sqlite3.Error as e:
            logger.error(f"Error reading current_stop: {e}")
            return "Western Gate"

    def process_scan(self, payload, current_stop):
        """
        Process a single QR scan: validate, then mark active.

        This is the action taken every time the camera detects a
        QR code. It runs the full Phase 3 validation pipeline
        (parse, lookup, status check, pickup match, token match)
        and, if validation passes, transitions the booking from
        'reserved' to 'active' in Firebase.

        Resilient to mark_active failure: if validation succeeds
        but the Firebase write fails (network blip, permissions),
        the result is downgraded to a failure with reason
        'mark_active_failed'. The booking stays in 'reserved'
        state, the passenger can retry, and the operator sees a
        clear message rather than silently passing a broken state.

        Args:
            payload:      Raw QR payload string from the scanner.
            current_stop: The shuttle's current stop, used for
                          pickup validation.

        Returns:
            A result dict with shape:
              {
                  "valid": bool,
                  "booking": dict or None,
                  "reason": str    (only when valid is False)
              }
        """
        validator = BookingValidator()
        result = validator.validate_scan(payload, current_stop=current_stop)

        if not result["valid"]:
            return result

        success = validator.mark_as_active(result["booking"])
        if not success:
            return {
                "valid": False,
                "booking": result["booking"],
                "reason": "mark_active_failed",
            }

        return result

    def run_scan_queue(self, current_stop):
        """
        Run the scanner repeatedly to handle a queue of passengers.

        Each iteration opens the camera, waits for a single QR
        scan (the single-scan-per-run contract from Phase 2), and
        processes the result. The loop continues until the operator
        presses 'q' to end the queue, signaling that all passengers
        for this stop have scanned and the shuttle is ready to
        process the boarding scenario.

        Between successful scans, the loop pauses briefly to let
        the next passenger step up and ready their phone. Rejected
        scans (invalid payload, wrong stop, etc) do NOT end the
        queue — the loop continues so the passenger can retry or
        the operator can move on to the next person.

        Args:
            current_stop: The shuttle's current stop. Used to
                          validate that each scanned QR was issued
                          for THIS stop.

        Returns:
            The number of successful boardings (valid scans that
            transitioned a booking to 'active'). Useful for
            logging and for the next phase to coordinate with
            main.py's expected passenger count.
        """
        scanner = QRScanner()
        scan_count = 0

        while True:
            scan_result = {"happened": False, "valid": False, "reason": None}

            def on_qr(payload):
                # this callback fires inside scanner.run() when a QR
                # is detected. we record what happened so the outer
                # loop can decide whether to continue or exit.
                scan_result["happened"] = True
                result = self.process_scan(payload, current_stop)
                scan_result["valid"] = result["valid"]
                scan_result["reason"] = result.get("reason")
                self._log_scan_result(result)

            scanner.run(on_qr_detected=on_qr)

            if not scan_result["happened"]:
                # scanner exited without firing the callback,
                # meaning the operator pressed 'q' to end the queue
                logger.info(f"Queue ended for stop: {current_stop}")
                break

            if scan_result["valid"]:
                scan_count += 1

            # brief pause before reopening the camera so the next
            # passenger has time to step up and unlock their phone
            time.sleep(2)

        return scan_count

    def _log_scan_result(self, result):
        """
        Pretty-print the result of a single scan to the terminal.

        Internal helper used by run_scan_queue. Separated out so
        the queue loop reads cleanly and so logging style can be
        tweaked in one place without touching the loop logic.

        Args:
            result: The result dict returned by process_scan.
        """
        if result["valid"]:
            booking = result["booking"]
            logger.info(
                f"[VALID SCAN] Booking {booking.get('booking_id')} "
                f"(user: {booking.get('user_uid')}) marked active, "
                f"destination: {booking.get('destination_stop')}"
            )
        else:
            logger.warning(
                f"[REJECTED SCAN] Reason: {result.get('reason')}"
                )

    def advance_and_sync(self):
        """
        Advance the shuttle to its next stop and push the new
        state to Firebase.

        Called by the orchestrator AFTER main.py finishes the
        boarding scenario at a stop. This is the moment the
        shuttle is conceptually pulling away from the curb and
        heading to the next stop.

        Three things must happen, in this order:
          1. NoShowCanceller.cancel_no_shows() — cancel any
             reserved bookings whose passengers didn't scan at
             this stop. Must happen BEFORE advance_stop because
             we need to know which stop is being left.
          2. CountingLogic.advance_stop() — moves current_stop_index
             forward (with wrap-around) and persists it to SQLite
          3. FirebaseSyncComponent.sync_to_firebase() — pushes the
             updated current_stop and next_stop to Firebase so the
             mobile app reflects that the shuttle has moved

        Without step 2, the mobile app would show stale stop data
        until the next main.py run wrote new occupancy updates,
        which could be many seconds during transit. The transit
        sync keeps the user experience accurate end-to-end.

        Occupancy values (current_count, available_seats) come
        from SQLite system_state where main.py wrote them. The
        orchestrator does not modify counts here — it only
        relocates the shuttle and reports the new location.
        """
        counting = CountingLogic(db_path=self.db_path)
        counting.initialize()
        # capture the stop being LEFT before we advance — we need
        # it to find no-show bookings at this pickup stop
        stop_being_left = counting.get_current_stop()
        # cancel any reserved bookings whose passengers didn't scan
        # at this stop. Drains the retry queue too, so accumulated
        # cancellations from previous Firebase outages also get
        # applied this cycle.
        canceller = NoShowCanceller(
            shuttle_id=self.shuttle_id, db_path=self.db_path
        )
        cancelled_count = canceller.cancel_no_shows(stop=stop_being_left)
        if cancelled_count > 0:
            logger.info(
                f"[NO-SHOWS] Cancelled {cancelled_count} booking(s) "
                f"at {stop_being_left}"
            )
        counting.advance_stop()

        firebase = FirebaseSyncComponent(shuttle_id=self.shuttle_id)
        firebase.initialize()

        current_stop = counting.get_current_stop()
        next_index = (counting.current_stop_index + 1) % len(
            counting.designated_stops_list
        )
        next_stop = counting.designated_stops_list[next_index]

        occupancy = self._read_occupancy_from_sqlite()
        payload = {
            "passenger_count": occupancy["passenger_count"],
            "available_seats": occupancy["available_seats"],
            "occupancy_status": occupancy["occupancy_status"],
            "current_stop": current_stop,
            "next_stop": next_stop,
        }

        firebase.sync_to_firebase(payload)

        # Record arrival timestamp + date for this visit. Downstream
        # queries (Alightings Expected / Alighted Here cards) use
        # these values to count ONLY bookings completed during the
        # current visit, not previous visits earlier in the day.
        # The date is a belt-AND-suspenders safety net: even if
        # the timestamp logic somehow fails (e.g. shuttle restarts
        # mid-day with stale timestamp), the date filter still
        # excludes yesterday's data.
        try:
            import datetime
            now = datetime.datetime.now()
            arrived_at_ms = int(now.timestamp() * 1000)
            arrived_date = now.strftime("%Y-%m-%d")

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('current_stop_arrived_at_ms', ?)
                """,
                (str(arrived_at_ms),),
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO system_state (key, value)
                VALUES ('current_stop_arrived_date', ?)
                """,
                (arrived_date,),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to record stop arrival timestamp: {e}")

        logger.info(
            f"Shuttle advanced to {current_stop}, next stop: {next_stop}"
        )

    def _read_occupancy_from_sqlite(self):
        """
        Read the most recent occupancy snapshot from SQLite.

        Internal helper used by advance_and_sync to build the
        Firebase payload. Reads passenger_count, available_seats,
        and computes occupancy_status. Returns sensible defaults
        if any value is missing so the sync never fails on a
        fresh deployment.

        Returns:
            A dict with passenger_count, available_seats, and
            occupancy_status keys.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT key, value FROM system_state "
                "WHERE key IN ('current_count', 'available_seats')"
            )
            rows = dict(cursor.fetchall())
            conn.close()

            count = int(rows.get("current_count", 0))
            seats = int(rows.get("available_seats", 0))
        except (sqlite3.Error, ValueError, TypeError) as e:
            logger.error(f"Error reading occupancy from SQLite: {e}")
            count = 0
            seats = 0

        # derive occupancy_status from available_seats using the
        # same thresholds firebase_sync expects elsewhere
        if seats == 0:
            status = "Full"
        elif seats <= 5:
            status = "Nearly Full"
        else:
            status = "Available"

        return {
            "passenger_count": count,
            "available_seats": seats,
            "occupancy_status": status,
        }

    def run(self):
        """
        Run the full orchestrator loop until the operator quits.

        Each iteration represents one shuttle stop:
          1. Read current_stop from SQLite
          2. Run the scan queue for that stop (passengers board)
          3. Launch main.py as a subprocess and WAIT for it to
             finish (the boarding scenario plays out)
          4. Advance the shuttle to its next stop and sync the
             new state to Firebase
          5. Prompt the operator to press Enter to continue, or
             Ctrl+C to exit the boarding system entirely

        The subprocess call is blocking — the orchestrator waits
        for main.py to fully exit before advancing. This ensures
        we never advance the stop while counting is still in
        progress, which would corrupt the audit trail.

        Ctrl+C at any point exits the loop cleanly. This is how
        the operator shuts the system down at the end of service
        hours.
        """
        logger.info("=" * 60)
        logger.info("APCOMS Scanner Orchestrator started")
        logger.info("Press Ctrl+C at the prompt to exit")
        logger.info("=" * 60)

        service_day_manager = ServiceDayManager(db_path=self.db_path)
        reset_date = service_day_manager.reset_if_needed()
        if reset_date:
            logger.info(f"Service-day reset performed for {reset_date}")

        try:
            while True:
                current_stop = self.read_current_stop()
                logger.info(
                    f"\n{'-' * 60}\n"
                    f"Shuttle at stop: {current_stop}\n"
                    f"{'-' * 60}"
                )

                # SKIP-EMPTY-STOP CHECK: if no passengers are waiting
                # to board AND nobody onboard is expecting to alight
                if not self.should_stop_here(current_stop):
                    logger.info(
                        f"[SKIPPING] No pickups or alightings at "
                        f"{current_stop} - passing through"
                    )
                    self.advance_and_sync()
                    # brief pause so this isn't a tight loop that
                    # blasts through 11 stops in milliseconds
                    time.sleep(1)
                    continue

                # phase 1: scan the queue of boarding passengers
                scan_count = self.run_scan_queue(current_stop)
                logger.info(
                    f"[QUEUE COMPLETE] {scan_count} passenger(s) "
                    f"scanned at {current_stop}"
                )

                # phase 2: launch main.py and wait for the boarding
                # scenario to play through. subprocess.run is
                # blocking so we never advance until main.py exits.
                main_script = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "..",
                    "main.py",
                )
                logger.info("[LAUNCHING MAIN.PY] Boarding scenario...")
                subprocess.run([sys.executable, main_script])
                logger.info("[MAIN.PY COMPLETE] Boarding scenario finished")

                # phase 3: shuttle pulls away from this stop
                self.advance_and_sync()

                # phase 4: wait for the operator before next cycle
                logger.info(
                    f"\n{'=' * 60}\n"
                    f"Press [Enter] to start next boarding session\n"
                    f"Press [Ctrl+C] to exit"
                )
                input()
        except KeyboardInterrupt:
            logger.info("\n[ORCHESTRATOR EXITING] Shutdown requested")


