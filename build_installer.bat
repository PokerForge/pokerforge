@echo off
rem Full release build: rebuilds the app with PyInstaller, then wraps it
rem into a real Windows installer with Inno Setup. Requires the dev
rem dependencies (pip install -r requirements-dev.txt) and Inno Setup 6
rem (https://jrsoftware.org/isinfo.php).
cd /d "%~dp0"

echo Building app with PyInstaller...
python -m PyInstaller "PokerForge.spec" --noconfirm
if errorlevel 1 goto :error

call :sign "dist\PokerForge\PokerForge.exe"
if errorlevel 1 goto :error

echo Building installer with Inno Setup...
set ISCC="%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
%ISCC% pokerforge_installer.iss
if errorlevel 1 goto :error

rem installer_output\PokerForge-Setup-{#MyAppVersion}.exe per the .iss's
rem OutputBaseFilename - APP_VERSION here must stay in sync with that
rem file's MyAppVersion (two separately hardcoded strings; nothing
rem auto-syncs them today).
for /f "usebackq delims=" %%V in (`python -c "from config.version import APP_VERSION; print(APP_VERSION)"`) do set APP_VERSION=%%V
call :sign "installer_output\PokerForge-Setup-%APP_VERSION%.exe"
if errorlevel 1 goto :error

echo.
echo Done - installer is in installer_output\
goto :eof

:sign
rem Signs %~1 if a certificate is configured via environment variables -
rem a no-op (not a failure) otherwise, so an unsigned dev build keeps
rem working exactly as it does today. Two credential styles, since a CA
rem hasn't been chosen yet: a PFX file + password (typical for a
rem downloaded OV certificate), or a certificate thumbprint already
rem installed in the Windows certificate store (typical for a
rem hardware-token EV certificate or Microsoft Trusted Signing's local
rem signing proxy). Set exactly one pair before running this script:
rem   set POKERFORGE_CERT_PFX=C:\path\to\cert.pfx
rem   set POKERFORGE_CERT_PASSWORD=...
rem or:
rem   set POKERFORGE_CERT_THUMBPRINT=<sha1 thumbprint, no spaces>
if "%POKERFORGE_CERT_PFX%"=="" if "%POKERFORGE_CERT_THUMBPRINT%"=="" (
    echo Skipping code signing for %~1 - no POKERFORGE_CERT_PFX/THUMBPRINT set.
    exit /b 0
)

set SIGNTOOL=
for /f "delims=" %%S in ('dir /b /s /o-n "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" 2^>nul') do if "%SIGNTOOL%"=="" set SIGNTOOL="%%S"
if "%SIGNTOOL%"=="" (
    echo Couldn't find signtool.exe under Windows Kits - install the Windows 10/11 SDK.
    exit /b 1
)

echo Signing %~1...
if not "%POKERFORGE_CERT_PFX%"=="" (
    %SIGNTOOL% sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /f "%POKERFORGE_CERT_PFX%" /p "%POKERFORGE_CERT_PASSWORD%" "%~1"
) else (
    %SIGNTOOL% sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /sha1 %POKERFORGE_CERT_THUMBPRINT% "%~1"
)
exit /b %errorlevel%

:error
echo Build failed.
exit /b 1
