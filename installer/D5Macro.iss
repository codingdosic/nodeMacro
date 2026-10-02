#define AppName "D5 Macro"
#define AppVersion "1.0.5"
#define AppPublisher "d051c"
#define AppExeName "D5Macro.exe"

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Setup]
AppId={{B06F6C40-A7D4-4DC4-90E2-BB8EB01B7917}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\D5Macro
DefaultGroupName={#AppName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=D5Macro-Setup-{#AppVersion}
SetupIconFile=..\branding\d5macro.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=yes
LanguageDetectionMethod=none
UsePreviousLanguage=no
CloseApplications=yes
RestartApplications=no
AppMutex=D5Macro.App.Singleton.B06F6C40-A7D4-4DC4-90E2-BB8EB01B7917

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal\frontend\dist"

[Files]
Source: "..\dist\D5Macro\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Privacy and Security"; Filename: "{app}\_internal\docs\PRIVACY.md"
Name: "{group}\Third-Party Licenses"; Filename: "{app}\_internal\docs\THIRD_PARTY_LICENSES.txt"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Parameters: "--language={language}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[CustomMessages]
english.DeleteUserData=Also delete saved macros, settings, logs, and captured images?%nChoose No to preserve user data.
korean.DeleteUserData=사용자 매크로, 설정, 로그와 캡처 이미지도 함께 삭제하시겠습니까?%n선택하지 않으면 사용자 데이터는 보존됩니다.

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and (not UninstallSilent) then
    if MsgBox(ExpandConstant('{cm:DeleteUserData}'), mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\D5Macro'), True, True, True);
      DelTree(ExpandConstant('{userdocs}\D5Macro'), True, True, True);
    end;
end;
