"""Single entry point for PokerForge — used by Launch PokerForge.bat and by the
PyInstaller build (see PokerForge.spec). ui/app_window.py's own
`if __name__ == "__main__"` block still works for running it directly
during development."""
import multiprocessing

if __name__ == "__main__":
    # MUST come before the UI import, and before anything else runs.
    #
    # database/repository.py spreads stat computation across a
    # multiprocessing Pool. On Windows that uses "spawn", which
    # re-launches this program to create each worker. From source that's
    # harmless: the child imports this module as __mp_main__, so the
    # guard below stops it starting a second app.
    #
    # In a PyInstaller build there is no source file to import — the
    # child re-runs the frozen executable with __name__ == "__main__"
    # still true, so without this call every worker starts its own copy
    # of the whole app. The symptom is a pile of "PokerForge is already
    # running" dialogs, one per worker, the first time hands import.
    #
    # freeze_support() spots the arguments multiprocessing passes a
    # child, runs the task, and exits without returning — so the import
    # below and main() only ever execute in the real main process.
    multiprocessing.freeze_support()

    from ui.app_window import main

    main()
