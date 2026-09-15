; Inno Setup script for Caissa's Windows installer. Build the application first, then:
;
;     .\build.ps1
;     iscc caissa.iss                      ; version falls back to the value below
;     iscc /DAppVersion=1.2.0 caissa.iss   ; the release workflow passes the tag
;
; An installer exists because a .zip does not survive the trip through a browser:
; Explorer stamps every file it extracts from a downloaded archive with the mark of the
; web, and .NET Framework then refuses to load the bundled Python.Runtime.dll out of
; the internet zone — see the comment at the foot of caissa.spec for the crash that
; causes. An installer copies its payload rather than extracting it, so nothing it
; writes carries that mark, and a Start menu entry and a working uninstaller come free.

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

#define AppName "Caissa"
#define AppExe "Caissa.exe"
#define AppPublisher "Hunter"
#define AppUrl "https://github.com/H-Bombmxpwr/caissa"
#define DocsUrl "https://h-bombmxpwr.github.io/caissa/"

[Setup]
; Generated once and never changed: this GUID is how Windows recognises an existing
; install to upgrade in place rather than leaving two copies behind.
AppId={{7C4E1F9A-3B62-4D58-9E0C-2A5F8D1B6E43}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#DocsUrl}
AppUpdatesURL={#AppUrl}/releases

; Installing per-user keeps the installer from raising a UAC prompt on top of the
; SmartScreen warning an unsigned build already gets. With PrivilegesRequired=lowest,
; {autopf} resolves to %LOCALAPPDATA%\Programs rather than Program Files.
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

; The engine and the opening book make this a ~150 MB payload; without solid
; compression the download is roughly twice the size for no reason.
Compression=lzma2/max
SolidCompression=yes
OutputDir=dist
OutputBaseFilename=Caissa-windows-x64-setup
SetupIconFile=assets\caissa.ico
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern

; The build is 64-bit, so refuse 32-bit Windows up front rather than failing at launch.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Upgrading while the app is open would otherwise fail on a locked Caissa.exe.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Everything PyInstaller collected, including the Caissa.exe.config that caissa.spec
; writes beside the executable. Excluding chess.com's sounds is belt and braces — the
; spec already strips them and the release workflow fails if any slip through — but
; this is the last place they could reach a user, so it is checked here too.
Source: "dist\{#AppName}\*"; DestDir: "{app}"; \
    Excludes: "assets\sound\chesscom\*"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller's bytecode caches are written next to the sources at runtime, so they did
; not come from [Files] and would otherwise strand the install directory. The game
; library is deliberately not listed here: it lives outside {app} precisely so that
; removing the application never touches a user's games.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
Type: dirifempty; Name: "{app}"
