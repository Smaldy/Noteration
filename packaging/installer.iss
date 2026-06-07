; Inno Setup script for Noteration — builds the Windows installer.
;
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
;
; Produces packaging\installer_output\Noteration-Setup-<ver>.exe. Installs
; per-user (no admin / UAC prompt), adds Desktop + Start Menu shortcuts, and an
; uninstaller. User data lives in %LOCALAPPDATA%\Noteration and is intentionally
; left behind on uninstall (notes/DB), with an optional checkbox to wipe it.

#define AppName "Noteration"
#define AppVersion "0.1.0"
#define AppPublisher "Noteration"
#define AppExeName "Noteration.exe"
#define BundleDir "dist\Noteration"
#define IconFile "assets\noteration.ico"

[Setup]
; Stable AppId so upgrades replace, and uninstall finds, the same install.
AppId={{BC47AAC4-EF35-44DA-8D96-C8DD67669724}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
WizardStyle=modern
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no admin rights, no UAC prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer_output
OutputBaseFilename=Noteration-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
#if FileExists(AddBackslash(SourcePath) + IconFile)
SetupIconFile={#IconFile}
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; The entire PyInstaller one-folder bundle.
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; The end-user guide, shipped beside the app.
Source: "USER-GUIDE.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} User Guide"; Filename: "{app}\USER-GUIDE.md"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch right after install (unchecked in silent installs).
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The bundle dir only; user data under %LOCALAPPDATA%\Noteration is preserved.
Type: filesandordirs; Name: "{app}"

[Code]
// Optional: let the user delete their notes/database on uninstall.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Noteration');
    if DirExists(DataDir) then
    begin
      if MsgBox('Also delete your Noteration data (notes, database, cache) in'
        + #13#10 + DataDir + ' ?' + #13#10 + #13#10
        + 'Choose No to keep your notes for a future reinstall.',
        mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
