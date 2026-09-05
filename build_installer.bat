@echo off
rem Full release build: rebuilds the app with PyInstaller, then wraps it
rem into a real Windows installer with Inno Setup. Requires the dev
rem dependencies (pip install -r requirements-dev.txt) and Inno Setup 6
rem (https://jrsoftware.org/isinfo.php).
cd /d "%~dp0"

echo Building app with PyInstaller...
python -m PyInstaller "PokerForge.spec" --noconfirm
if errorlevel 1 goto :error

echo Building installer with Inno Setup...
set ISCC="%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
%ISCC% pokerforge_installer.iss
if errorlevel 1 goto :error

echo.
echo Done — installer is in installer_output\
goto :eof

:error
echo Build failed.
exit /b 1
