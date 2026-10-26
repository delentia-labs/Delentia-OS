; Delentia for Windows: a per-user installer (no administrator rights).
; Built by installer/windows/build_installer.py, which stages the files and calls the Inno Setup compiler:
;   ISCC.exe /DAppVersion=2.4.0 /DFileVersion=2.4.0.0 /DWheelName=delentia_os-2.4.0-py3-none-any.whl /DStageDir=<stage folder> delentia.iss
; Version: the installer has the number of the runtime it installs (AppVersion). The Windows file version is that number plus an installer revision (FileVersion, 0 unless the installer was rebuilt
; without a runtime change). The name of the milestone ("Public Technical Preview 0.1") is a label for what is opened to whom (docs/release/VERSIONING_POLICY.md), not a version: it is never in the file
; name, AppVersion or the Windows file version. Once the owner has declared the milestone, build_installer.py writes milestone.iss (UTF-8 with a byte-order mark, because the Thai text must not travel on a
; command line) and the label is shown, in English and Thai, in the installer's welcome page and in the program's comments.
;
; What it installs: a private copy of Python (the "embeddable" package from python.org), the Delentia wheel, and the packages Delentia needs (pip downloads them while installing, unless an offline "wheels" folder is staged).
; Where: %LOCALAPPDATA%\Programs\Delentia. Your own data (memory, audit record, keys) lives in %USERPROFILE%\.delentia and is NEVER touched by install or uninstall.
; Start menu: Delentia (opens the Desk), Stop Delentia, Update Delentia. No service, no start-up entry, nothing that runs until you click it.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef FileVersion
  #define FileVersion "0.0.0.0"
#endif
#ifndef WheelName
  #define WheelName "delentia_os-0.0.0-py3-none-any.whl"
#endif
#ifndef StageDir
  #define StageDir "stage"
#endif
#define MilestoneEN ""
#define MilestoneTH ""
#ifexist AddBackslash(StageDir) + "milestone.iss"
  #include AddBackslash(StageDir) + "milestone.iss"
#endif

[Setup]
AppId={{B7A1C3E4-5D26-4F0A-9E31-D3E71A7E0101}
AppName=Delentia
AppVersion={#AppVersion}
AppVerName=Delentia {#AppVersion}
VersionInfoVersion={#FileVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoProductName=Delentia
VersionInfoCompany=Delentia Labs
VersionInfoDescription=Delentia Setup
AppPublisher=Delentia Labs
#if MilestoneEN != ""
AppComments={#MilestoneEN} / {#MilestoneTH}
#endif
AppPublisherURL=https://delentia.com
AppSupportURL=https://github.com/delentia-labs/Delentia-OS/issues
AppUpdatesURL=https://github.com/delentia-labs/Delentia-OS/releases
DefaultDirName={localappdata}\Programs\Delentia
DefaultGroupName=Delentia
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=Delentia-Setup-{#AppVersion}
SetupIconFile=delentia.ico
UninstallDisplayIcon={app}\delentia.ico
UninstallDisplayName=Delentia
WizardImageFile=wizard.bmp
WizardSmallImageFile=wizard_small.bmp
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
CloseApplications=no
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

#if MilestoneEN != ""
[Messages]
WelcomeLabel2=This will install Delentia {#AppVersion} on your computer.%n%n{#MilestoneEN}%n{#MilestoneTH}%n%nThis build is not code-signed yet, so Windows may warn you. Close other programs before you continue.%n%nการติดตั้งนี้ยังไม่ได้ลงนามรหัสโปรแกรม Windows จึงอาจแสดงคำเตือน ปิดโปรแกรมอื่นก่อนดำเนินการต่อ
#endif

[Tasks]
Name: "desktopicon"; Description: "Put a Delentia icon on the desktop"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "{#StageDir}\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\wheel\*"; DestDir: "{app}\wheel"; Flags: ignoreversion
Source: "{#StageDir}\wheels\*"; DestDir: "{app}\wheels"; Flags: recursesubdirs createallsubdirs ignoreversion skipifsourcedoesntexist
Source: "{#StageDir}\get-pip.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\install_runtime.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\SOURCES.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "delentia.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "check_install.py"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; pythonw.exe has no console window: the shortcut just opens the Desk in the browser (an error, if any, is shown in a message box).
Name: "{group}\Delentia"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m rct_control_plane.cli launch"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Comment: "Start Delentia and open it in your browser"
Name: "{group}\Stop Delentia"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m rct_control_plane.cli launch --stop"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Comment: "Stop what Delentia started"
Name: "{group}\Update Delentia"; Filename: "{app}\python\python.exe"; Parameters: "-m rct_control_plane.cli update --apply"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Comment: "Check for a newer version and install it (asks first)"
Name: "{group}\Check Delentia installation"; Filename: "{app}\python\python.exe"; Parameters: """{app}\check_install.py"" --pause"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Comment: "Test that Delentia starts and answers on this computer (writes a report you can send to someone who helps)"
Name: "{autodesktop}\Delentia"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m rct_control_plane.cli launch"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Tasks: desktopicon

[UninstallRun]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m rct_control_plane.cli launch --stop"; Flags: runhidden; RunOnceId: "StopDelentia"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure ExitProcess(uExitCode: Integer); external 'ExitProcess@kernel32.dll stdcall';

var
  RuntimeFailed: Boolean;
  RuntimeCode: Integer;

{ A silent install (/SILENT or /VERYSILENT) shows no message and, without this, ends with exit code 0 even when the parts could not be installed (measured: RaiseException and Abort both leave 0).
  WizardSilent is false under /VERYSILENT in Inno 6.7, so the command line is read. }
function IsSilentRun: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if (CompareText(ParamStr(I), '/VERYSILENT') = 0) or (CompareText(ParamStr(I), '/SILENT') = 0) then
      Result := True;
end;

procedure DeinitializeSetup();
begin
  { the very last step: the uninstaller and its registry entry already exist, so a failed install can be re-run or removed as usual }
  if RuntimeFailed and IsSilentRun then
    ExitProcess(RuntimeCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Command: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := 'Installing Delentia and the parts it needs (this takes a few minutes and needs the internet)...';
    WizardForm.FilenameLabel.Caption := '';
    Command := '/C ""' + ExpandConstant('{app}\install_runtime.cmd') + '" "{#WheelName}""';
    if (not Exec(ExpandConstant('{cmd}'), Command, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      RuntimeFailed := True;
      RuntimeCode := ResultCode;
      if RuntimeCode = 0 then RuntimeCode := 10;
      MsgBox('Delentia was copied, but its parts could not be installed (code ' + IntToStr(ResultCode) + ').' + #13#10 + #13#10 +
             'The most common reason is no internet connection. Connect, then run this installer again.' + #13#10 +
             'The details are in: ' + ExpandConstant('{app}\install.log'), mbError, MB_OK);
    end;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and RuntimeFailed then
    WizardForm.FinishedLabel.Caption := 'Delentia was NOT installed completely. Please read the message that was shown, then run this installer again.';
end;
