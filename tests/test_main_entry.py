"""main.py's entry point — specifically the multiprocessing guard.

database/repository.py spreads stat computation across a multiprocessing
Pool. On Windows that uses "spawn", which re-launches the program for each
worker. In a PyInstaller build there's no source module for the child to
import, so it re-runs the frozen executable with __name__ == "__main__"
still true: without multiprocessing.freeze_support() every worker starts
its own copy of the entire app, and the user gets a pile of "PokerForge is
already running" dialogs the first time hands import.

It only reproduces in a frozen build, never from source, so nothing in a
normal test run or a dev launch would catch a regression here.
"""
import ast
from pathlib import Path

MAIN = Path(__file__).resolve().parent.parent / "main.py"


def _main_guard():
    """The `if __name__ == "__main__":` block of main.py, as AST."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    for node in tree.body:
        if (isinstance(node, ast.If)
                and isinstance(node.test, ast.Compare)
                and getattr(node.test.left, "id", None) == "__name__"):
            return node
    raise AssertionError('main.py has no `if __name__ == "__main__"` block')


def _is_freeze_support(stmt):
    return (isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and getattr(stmt.value.func, "attr", None) == "freeze_support")


def test_freeze_support_is_the_first_thing_main_does():
    """Not merely present: first. Anything before it runs in every spawned
    worker too, and the whole point is that a worker never gets that far."""
    body = _main_guard().body
    assert _is_freeze_support(body[0]), (
        "multiprocessing.freeze_support() must be the first statement in "
        f"main.py's __main__ block, not {ast.unparse(body[0])!r}")


def test_the_ui_is_imported_after_freeze_support():
    """A spawned worker should exit inside freeze_support() without ever
    loading PyQt6. Importing the UI at module level would drag the whole
    toolkit into every worker before it had the chance."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    top_level_ui_import = [
        n for n in tree.body
        if isinstance(n, (ast.Import, ast.ImportFrom))
        and "ui." in (getattr(n, "module", "") or "")]
    assert not top_level_ui_import, (
        "main.py imports the UI at module level; move it inside the "
        "__main__ block, after freeze_support()")

    guard = _main_guard().body
    ui_import = next(
        (i for i, s in enumerate(guard)
         if isinstance(s, ast.ImportFrom) and "ui." in (s.module or "")), None)
    assert ui_import is not None, "main.py never imports the UI"
    freeze = next(i for i, s in enumerate(guard) if _is_freeze_support(s))
    assert freeze < ui_import, "freeze_support() must come before the UI import"


def test_main_is_called_inside_the_guard():
    """The guard itself is what stops a non-frozen spawned child (which
    imports this module as __mp_main__) from starting a second app."""
    guard = _main_guard().body
    assert any(isinstance(s, ast.Expr) and isinstance(s.value, ast.Call)
               and getattr(s.value.func, "id", None) == "main"
               for s in guard), "main() is not called inside the __main__ block"
