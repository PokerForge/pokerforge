@echo off
rem Builds the standalone Windows app into dist\SF Poker\ — no Python
rem install needed on the machine that runs it. Requires the dev
rem dependencies first: pip install -r requirements-dev.txt
cd /d "%~dp0"
python -m PyInstaller "SF Poker.spec" --noconfirm
