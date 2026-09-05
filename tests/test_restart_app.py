"""ui/profile_dialog.py's restart_app() — must release this process's
single-instance lock BEFORE spawning the replacement process, or the new
process could spuriously see the old (soon-to-exit) one as still running."""
import pytest

import ui.profile_dialog as mod


def test_restart_releases_the_lock_before_spawning_the_new_process(monkeypatch):
    call_order = []
    monkeypatch.setattr("core.single_instance.release_held_lock", lambda: call_order.append("release"))
    monkeypatch.setattr(mod.subprocess, "Popen", lambda *a, **k: call_order.append("spawn"))
    monkeypatch.setattr(mod.sys, "exit", lambda *a: call_order.append("exit"))

    mod.restart_app()

    assert call_order == ["release", "spawn", "exit"]
