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
