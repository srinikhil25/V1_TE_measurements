; Inno Setup script for TE Measurement
; Compile with:  ISCC.exe installer\TE-Measurement.iss
; (or run installer\build_installer.ps1 which builds the app first, then this)
;
; Produces:  installer\Output\TE-Measurement-Setup-1.0.0.exe
; Installs the PyInstaller one-folder build from dist\TE-Measurement\.

#define AppName        "TE Measurement"
#define AppVersion     "1.0.0"
#define AppPublisher   "Ikeda-Hamasaki Laboratory - MX-Energy Team"
#define AppExeName     "TE-Measurement.exe"
; SourceDir = project root (this .iss lives in installer\, so one level up)
#define SourceRoot     "..\dist\TE-Measurement"

[Setup]
; A fixed GUID keeps upgrades/uninstall consistent across versions. Do not change it.
AppId={{8F3C6A21-4B7E-4E2A-9F1D-2C7B5E9A1D40}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\TE Measurement
DefaultGroupName=TE Measurement
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=TE-Measurement-Setup-{#AppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Per-machine install (Program Files) needs admin; use lowest for per-user instead.
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The entire PyInstaller one-folder output.
Source: "{#SourceRoot}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\*";             DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "PREREQUISITES.txt";          DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
Name: "{group}\{#AppName}";          Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";    Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
