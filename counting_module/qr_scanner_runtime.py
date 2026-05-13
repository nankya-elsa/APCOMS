"""
APCOMS QR Scanner Runtime — operator entry script.

This is what the shuttle operator runs to drive the entire
boarding flow. Replaces the old `python main.py` workflow:

  Old: operator runs main.py directly, one stop per invocation
  New: operator runs this script, it orchestrates everything

The orchestrator handles:
  - Reading the shuttle's current stop from SQLite
  - Running the QR scanner repeatedly for a queue of passengers
  - Validating each scan and marking bookings active in Firebase
  - Launching main.py as a subprocess to play the boarding scenario
  - Advancing the shuttle to its next stop after main.py finishes
  - Syncing the new state to Firebase so the mobile app stays accurate
  - Prompting the operator before starting the next boarding session

Usage:
  cd counting_module
  python qr_scanner_runtime.py

At the prompt between cycles, press Enter to continue or Ctrl+C
to shut down the boarding system.
"""

import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
load_dotenv()

from scanner_orchestrator import ScannerOrchestrator

# configure logging consistent with main.py so the operator sees
# the same format across the orchestrator and main.py subprocess
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    orchestrator = ScannerOrchestrator()
    orchestrator.run()


if __name__ == "__main__":
    main()
