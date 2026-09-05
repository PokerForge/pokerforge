"""core/single_instance.py — a second acquisition attempt against the same
key must fail while the first is still held, and must succeed again once
the first is released (simulating "first instance closed normally")."""
import uuid

import pytest

import core.single_instance as mod


@pytest.fixture(autouse=True)
def _unique_key(monkeypatch):
    # A fresh key per test, so runs never collide with each other or with
    # a real PokerForge instance that happens to be running on this machine.
    monkeypatch.setattr(mod, "_KEY", f"SFPoker-Test-{uuid.uuid4()}")
    # _held_lock is module-level global state — reset it so one test's
    # leftover reference (possibly to an already-deleted Qt object once
    # this test's own QSharedMemory goes out of scope) can't leak into
    # the next test.
    monkeypatch.setattr(mod, "_held_lock", None)


@pytest.fixture()
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_first_acquisition_succeeds(qapp):
    lock = mod.acquire_single_instance_lock()
    assert lock is not None
    assert lock.isAttached()


def test_second_acquisition_while_first_is_held_fails(qapp):
    first = mod.acquire_single_instance_lock()
    assert first is not None

    second = mod.acquire_single_instance_lock()
    assert second is None


def test_acquisition_succeeds_again_after_the_first_is_released(qapp):
    first = mod.acquire_single_instance_lock()
    assert first is not None
    first.detach()

    second = mod.acquire_single_instance_lock()
    assert second is not None


def test_release_held_lock_frees_it_for_a_subsequent_acquisition(qapp):
    first = mod.acquire_single_instance_lock()
    assert first is not None
    assert mod._held_lock is first

    mod.release_held_lock()
    assert mod._held_lock is None

    second = mod.acquire_single_instance_lock()
    assert second is not None


def test_release_held_lock_is_a_safe_no_op_when_nothing_is_held(qapp):
    mod.release_held_lock()  # must not raise
    assert mod._held_lock is None
