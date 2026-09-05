"""Single-instance enforcement — a second launch (e.g. double-clicking the
desktop shortcut twice by accident) would otherwise open a second process
against the same SQLite database, which can produce confusing "database
is locked" errors rather than a clear message.

Uses QSharedMemory rather than a PID lock file: the OS releases a shared
memory segment automatically when its owning process exits — including a
crash — so there's no stale-lock cleanup to get wrong. The tradeoff is
this only refuses the second launch with a message; it doesn't (yet)
forward an "activate my window" request to the first instance, which
would need a small QLocalServer/QLocalSocket IPC layer on top of this."""
from PyQt6.QtCore import QSharedMemory

_KEY = "SFPoker-SingleInstance-8f6c6c8b-4c2e-4b9b-9b1e-6f4a9e7b1c1a"

# Tracked at module level (not just returned to the caller) so
# ui/profile_dialog.py's restart_app() can release it before spawning the
# replacement process — otherwise there's a brief window where both the
# exiting and the newly-spawned process are alive at once, and the new
# one could spuriously see the old one as "still running".
_held_lock: QSharedMemory | None = None


def acquire_single_instance_lock() -> QSharedMemory | None:
    """Returns a QSharedMemory holding the lock if this is the only
    running instance — keep a reference alive for the app's whole
    lifetime, since releasing/garbage-collecting it frees the lock early.
    Returns None if another instance already holds it."""
    global _held_lock
    shared_mem = QSharedMemory(_KEY)
    if shared_mem.attach():
        shared_mem.detach()
        return None
    if not shared_mem.create(1):
        return None
    _held_lock = shared_mem
    return shared_mem


def release_held_lock():
    """Releases this process's own lock early, ahead of a deliberate
    restart — see the _held_lock comment above for why that matters."""
    global _held_lock
    if _held_lock is not None:
        _held_lock.detach()
        _held_lock = None
