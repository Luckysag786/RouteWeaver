#define MyAppName "路由织网 RouteWeaver"
#define MyAppVersion "1.3.1"
#define MyAppPublisher "RouteWeaver"
#define MyAppExeName "RouteWeaver.exe"

[Setup]
AppId={{9C9037E8-EA55-42D4-B941-58128E8EF5A6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\RouteWeaver
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\artifacts
OutputBaseFilename=RouteWeaver-Windows-Setup-1.3.1
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "开机自动启动（推荐）"; GroupDescription: "启动选项："; Flags: checkedonce
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
Source: "..\artifacts\RouteWeaver-Windows-1.3.1.exe"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README_EN.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\PLATFORM_LIMITS.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "RouteWeaver"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\RouteWeaverPreferences"; ValueType: dword; ValueName: "InstallerAutostart"; ValueData: "1"; Tasks: autostart; Flags: uninsdeletevalue uninsdeletekeyifempty
Root: HKCU; Subkey: "Software\RouteWeaverPreferences"; ValueType: dword; ValueName: "InstallerAutostart"; ValueData: "0"; Tasks: not autostart; Flags: uninsdeletevalue uninsdeletekeyifempty

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'RouteWeaver');
    RegDeleteValue(HKCU, 'Software\RouteWeaverPreferences', 'InstallerAutostart');
    RegDeleteKeyIfEmpty(HKCU, 'Software\RouteWeaverPreferences');
  end;
end;
