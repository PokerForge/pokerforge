"""Single entry point for SF Poker — used by Launch SF Poker.bat and by the
PyInstaller build (see sf_poker.spec). ui/app_window.py's own
`if __name__ == "__main__"` block still works for running it directly
during development."""
from ui.app_window import main

if __name__ == "__main__":
    main()
