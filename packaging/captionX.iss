; Inno Setup script. Compile from the repo root after PyInstaller has produced dist-win\captionX:
;   ISCC.exe /DAppVersion=1.0.0 packaging\captionX.iss      ->  dist-installer\captionX-Setup-1.0.0.exe
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{7D3B6F2E-4A59-4C1B-9E0D-5C2A8F61B7A4}
AppName=captionX
AppVersion={#AppVersion}
AppVerName=captionX {#AppVersion}
AppPublisher=Harmain.dev
AppPublisherURL=https://harmain-dev.vercel.app/
AppSupportURL=https://github.com/Harmain-Ali/
DefaultDirName={autopf}\captionX
DefaultGroupName=captionX
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist-installer
OutputBaseFilename=captionX-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\captionX.exe
UninstallDisplayName=captionX
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist-win\captionX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\captionX"; Filename: "{app}\captionX.exe"
Name: "{autodesktop}\captionX"; Filename: "{app}\captionX.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\captionX.exe"; Description: "Start captionX"; Flags: nowait postinstall skipifsilent

; Your settings, API key and history live in %LOCALAPPDATA%\captionX and are kept when you uninstall or update.
