"""App-wide logging — replaces bare print() statements, which are silently
lost when the app is launched via pythonw (no console attached, so
sys.stdout is None and a write to it would raise). Every run now leaves a
real log file behind, so a customer's "it says 0 hands were found" can
actually be diagnosed after the fact instead of needing them to somehow
capture console output that was never there."""
import logging
import sys
from logging.handlers import RotatingFileHandler

from config.paths import app_data_dir

LOG_PATH = app_data_dir() / "sf_poker.log"


def configure_logging(level=logging.INFO):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level)

    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s"))
    root.addHandler(file_handler)

    if sys.stdout is not None:
        # Only present when launched from a real terminal (python, not
        # pythonw) — a write to a None stdout would raise.
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(console_handler)
