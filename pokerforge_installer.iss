; Inno Setup script for PokerForge.
; Build with: "C:\Users\shane\AppData\Local\Programs\Inno Setup 6\ISCC.exe" pokerforge_installer.iss
; (or run build_installer.bat, which builds the PyInstaller app first).
;
; Assumes dist\PokerForge\ already exists (see build.bat / PokerForge.spec)
; — this script only wraps that already-built app into a real installer
; with a Start Menu entry, optional Desktop shortcut, and a proper
; uninstaller. The install location is separate from the app's actual
; data — settings/database/log all live in %APPDATA%\SFPoker\ regardless
; of where the app itself is installed (kept as the original internal
; folder name from before the app was renamed — see config/paths.py's
; app_data_dir() for why), so installing/uninstalling never touches a
; player's hand history data.
;
; Installs per-user (no admin/UAC prompt) rather than to Program Files —
; this is a single-player desktop tool typically run on someone's own
; PC, not shared multi-user software, so there's no real benefit to
; requiring admin rights just to install it (matches how e.g. Discord,
; VS Code, and Slack install by default on Windows).

#define MyAppName "PokerForge"
#define MyAppVersion "1.0.0-beta.1"
#define MyAppPublisher "PokerForge"
#define MyAppExeName "PokerForge.exe"

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
OutputBaseFilename=PokerForge-Setup-{#MyAppVersion}
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
Source: "dist\PokerForge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  // Program files are already gone by usPostUninstall — this asks
  // separately about the *data* folder (hand histories, database,
  // settings), which deliberately survives a plain uninstall by default
  // (see PRIVACY_POLICY.md's "Deleting your data" section). Opt-in only,
  // and defaults to No in the dialog itself, since deleting someone's
  // poker database by surprise on a routine reinstall/upgrade would be a
  // much worse outcome than leaving a small folder behind.
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\SFPoker');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete your PokerForge data (hand histories, database, and settings)?' + #13#10 + #13#10 +
                'Choose No to keep it — for example, if you plan to reinstall later.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
      end;
    end;
  end;
end;
