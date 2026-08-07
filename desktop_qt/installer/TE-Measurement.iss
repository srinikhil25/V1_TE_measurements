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

[Code]
{ ---- Hardware prerequisite detection (informational, non-blocking) ---- }

function NiVisaInstalled(): Boolean;
begin
  Result := FileExists(ExpandConstant('{sys}\visa64.dll'))
         or FileExists(ExpandConstant('{sys}\visa32.dll'))
         or RegKeyExists(HKLM64, 'SOFTWARE\National Instruments\NI-VISA')
         or RegKeyExists(HKLM,   'SOFTWARE\National Instruments\NI-VISA');
end;

function OptrisInstalled(): Boolean;
var
  Otc: String;
begin
  Otc := GetEnv('OTC_SDK_DIR');
  Result := ((Otc <> '') and DirExists(Otc))
         or DirExists(ExpandConstant('{commonpf}\Optris\otcsdk'))
         or FileExists('C:\IrDirectSDK\sdk\x64\libirimager.dll');
end;

procedure InitializeWizard();
var
  Msg: String;
begin
  Msg := '';
  if not NiVisaInstalled() then
    Msg := Msg
      + '- NI-VISA runtime + GPIB driver  (REQUIRED for the Keithley 2401 / 2182A / 2700'  + #13#10
      + '  and the Matsusada P4K-80M).  Without it the app cannot talk to any instrument.' + #13#10
      + '  Get it from ni.com  (search "NI-VISA download").'                                + #13#10#13#10;
  if not OptrisInstalled() then
    Msg := Msg
      + '- Optris IR camera SDK  (only needed for the thermal camera).'                     + #13#10
      + '  OTC SDK 10.x, or the legacy IrDirectSDK.'                                         + #13#10#13#10;
  if Msg <> '' then
    MsgBox('Some hardware prerequisites were not detected on this PC:'  + #13#10#13#10
      + Msg
      + 'The application will still install and run normally, but the features above stay '
      + 'unavailable until these are installed. See PREREQUISITES.txt in the install folder.',
      mbInformation, MB_OK);
end;
