; Inno Setup script for SF Poker.
; Build with: "C:\Users\shane\AppData\Local\Programs\Inno Setup 6\ISCC.exe" sf_poker_installer.iss
; (or run build_installer.bat, which builds the PyInstaller app first).
;
; Assumes dist\SF Poker\ already exists (see build.bat / SF Poker.spec) —
; this script only wraps that already-built app into a real installer with
; a Start Menu entry, optional Desktop shortcut, and a proper uninstaller.
; The install location is separate from the app's actual data — settings/
; database/log all live in %APPDATA%\SFPoker\ regardless of where the app
; itself is installed, so installing/uninstalling never touches a
; player's hand history data.
;
; Installs per-user (no admin/UAC prompt) rather than to Program Files —
; this is a single-player desktop tool typically run on someone's own
; PC, not shared multi-user software, so there's no real benefit to
; requiring admin rights just to install it (matches how e.g. Discord,
; VS Code, and Slack install by default on Windows).

#define MyAppName "SF Poker"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "SF Poker"
#define MyAppExeName "SF Poker.exe"

[Setup]
AppId={{8F6C6C8B-4C2E-4B9B-9B1E-6F4A9E7B1C1A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=SF-Poker-Setup-{#MyAppVersion}
SetupIconFile=assets\app_icon_chip.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
Source: "dist\SF Poker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
