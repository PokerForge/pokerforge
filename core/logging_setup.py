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


def install_crash_handler():
    """Replaces the default sys.excepthook so an unhandled exception — at
    startup, or later from inside a Qt slot while the app is running —
    gets logged with a full traceback and shown to the user as a short,
    non-technical message instead of PyInstaller's raw "Unhandled
    exception in script" dialog (which dumps a Python stack trace on a
    customer who has no Python installed and no idea what to do with it).
    Call this once, right after configure_logging()."""
    logger = logging.getLogger("sf_poker.crash")

    def _handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None, "SF Poker",
                    "SF Poker ran into an unexpected problem and needs to close.\n\n"
                    f"Details were saved to:\n{LOG_PATH}\n\n"
                    "If this keeps happening, please include that file when asking for help."
                )
        except Exception:
            pass  # the crash handler itself must never be the thing that crashes

    sys.excepthook = _handle_exception
