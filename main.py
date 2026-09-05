"""Single entry point for PokerForge — used by Launch PokerForge.bat and by the
PyInstaller build (see PokerForge.spec). ui/app_window.py's own
`if __name__ == "__main__"` block still works for running it directly
during development."""
from ui.app_window import main

if __name__ == "__main__":
    main()
