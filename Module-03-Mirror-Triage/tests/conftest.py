"""
Shared test setup: lets the tests import the app's modules (red_flags.py,
triage_pipeline.py, ...) from the project folder one level up.

Run all tests from the project folder with:   python -m pytest
No API key and no internet connection are needed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
