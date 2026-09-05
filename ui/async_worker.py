"""Generic background-thread worker so no stats computation ever blocks the
Qt UI thread — same pattern poker_dashboard_legacy.py used (VillainLoader/
DataLoader), just reusable for any callable instead of one-off per feature.

Includes a generation counter: if the user clicks a new villain (or changes
the period) before the previous computation finishes, the stale result is
silently discarded when it arrives instead of overwriting the newer request.
"""
from PyQt6.QtCore import QThread, pyqtSignal


class StatsWorker(QThread):
    done = pyqtSignal(object, int)
    error = pyqtSignal(str, int)

    def __init__(self, fn, generation: int):
        super().__init__()
        self.fn = fn
        self.generation = generation

    def run(self):
        try:
            result = self.fn()
        except Exception as exc:
            self.error.emit(str(exc), self.generation)
        else:
            self.done.emit(result, self.generation)


class AsyncRunner:
    """Mixin-style helper: call `self.run_async(fn, on_done)` from a QWidget.
    Keeps a reference to the current worker/generation so results can be
    matched to the request that triggered them.

    `key` names an independent channel — a widget that kicks off two
    unrelated background queries at once (e.g. StatsTab's main stats query
    plus its separate Trend-tab query) needs each on its own channel.
    Sharing one generation counter/worker slot between them would have the
    second call's run_async() drop the ONLY Python reference to the first
    worker while it's still running in its own QThread (that reference
    exists specifically to stop it being garbage-collected mid-run — see
    below) — a real crash this shape of bug produced when StatsTab started
    firing two concurrent queries through a single-channel version of
    this class."""

    def _init_async(self):
        self._async_generations: dict[str, int] = {}
        self._async_workers: dict[str, StatsWorker] = {}

    def run_async(self, fn, on_done, on_error=None, key: str = "default"):
        gen = self._async_generations.get(key, 0) + 1
        self._async_generations[key] = gen
        worker = StatsWorker(fn, gen)
        self._async_workers[key] = worker  # keep a reference so it isn't garbage-collected mid-run

        def _handle_done(result, result_gen):
            if result_gen == self._async_generations.get(key):
                on_done(result)

        def _handle_error(msg, result_gen):
            if result_gen == self._async_generations.get(key) and on_error:
                on_error(msg)

        worker.done.connect(_handle_done)
        worker.error.connect(_handle_error)
        worker.start()
