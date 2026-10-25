; Delentia for Windows: a per-user installer (no administrator rights).
; Built by installer/windows/build_installer.py, which stages the files and calls the Inno Setup compiler:
;   ISCC.exe /DAppVersion=2.3.1 /DWheelName=delentia_os-2.3.1-py3-none-any.whl /DStageDir=<stage folder> delentia.iss
;
; What it installs: a private copy of Python (the "embeddable" package from python.org), the Delentia wheel, and the packages Delentia needs (pip downloads them while installing, unless an offline "wheels" folder is staged).
; Where: %LOCALAPPDATA%\Programs\Delentia. Your own data (memory, audit record, keys) lives in %USERPROFILE%\.delentia and is NEVER touched by install or uninstall.
; Start menu: Delentia (opens the Desk), Stop Delentia, Update Delentia. No service, no start-up entry, nothing that runs until you click it.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef WheelName
  #define WheelName "delentia_os-0.0.0-py3-none-any.whl"
#endif
#ifndef StageDir
  #define StageDir "stage"
#endif

[Setup]
AppId={{B7A1C3E4-5D26-4F0A-9E31-D3E71A7E0101}
AppName=Delentia
AppVersion={#AppVersion}
AppVerName=Delentia {#AppVersion}
AppPublisher=Delentia Labs
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

[Icons]
; pythonw.exe has no console window: the shortcut just opens the Desk in the browser (an error, if any, is shown in a message box).
Name: "{group}\Delentia"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m rct_control_plane.cli launch"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Comment: "Start Delentia and open it in your browser"
Name: "{group}\Stop Delentia"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m rct_control_plane.cli launch --stop"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Comment: "Stop what Delentia started"
Name: "{group}\Update Delentia"; Filename: "{app}\python\python.exe"; Parameters: "-m rct_control_plane.cli update --apply"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Comment: "Check for a newer version and install it (asks first)"
Name: "{autodesktop}\Delentia"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m rct_control_plane.cli launch"; WorkingDir: "{%USERPROFILE}"; IconFilename: "{app}\delentia.ico"; Tasks: desktopicon

[UninstallRun]
Filename: "{app}\python\pythonw.exe"; Parameters: "-m rct_control_plane.cli launch --stop"; Flags: runhidden; RunOnceId: "StopDelentia"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  RuntimeFailed: Boolean;

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
