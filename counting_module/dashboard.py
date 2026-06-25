import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

from flask_dashboard import FlaskDashboard

# configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("APCOMS - Flask Monitoring Dashboard")
    logger.info("Makerere University Driverless E-Shuttle")
    logger.info("BSE26-8 | Nankya Elsa & Musiimenta Cissylyn")
    logger.info("=" * 60)

    dashboard = FlaskDashboard()
    dashboard.initialize()

    # Start the booking listener as a background service. The
    # dashboard is the canonical home for the listener because
    # it runs 24/7, unlike the orchestrator which only runs
    # during service hours. With the listener here, bookings
    # made from the mobile app flow into the seat pool continuously
    # regardless of whether the shuttle is operating. The
    # orchestrator does NOT start its own listener so there is
    # only ever one listener active at a time, eliminating the
    # double-decrement race that two concurrent listeners would
    # create.
    from booking_listener_setup import start_booking_listener
    shuttle_id = os.getenv("SHUTTLE_ID", "shuttle_001")
    db_path = "local_database/apcoms.db"
    _booking_listener = start_booking_listener(
        shuttle_id=shuttle_id,
        db_path=db_path,
    )
    logger.info(
        f"Booking listener active for {shuttle_id} "
        f"-- bookings flow into seat pool continuously"
    )

    logger.info("Starting Flask server...")
    logger.info("Dashboard is accessible 24/7 - independent of shuttle operation")
    logger.info("=" * 60)

    dashboard.app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )


if __name__ == "__main__":
    main()
