; Script do Inno Setup para o instalador Windows do OpenFolio PDF Suite.
;
; Espera que o build "onedir" do PyInstaller já exista em dist\OpenFolioPDFSuite
; (gerado por: pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm),
; rodando este script a partir da raiz do repositorio:
;
;   ISCC.exe packaging\windows\installer.iss
;
; A versão pode ser sobrescrita na hora do build (o workflow do GitHub Actions faz isso
; a partir da tag do release):
;
;   ISCC.exe /DAppVersion=0.2.0-beta.1 packaging\windows\installer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0-dev"
#endif

#define AppName "OpenFolio PDF Suite"
#define AppPublisher "dcCarreto"
#define AppURL "https://github.com/dcCarreto/openfolio-pdf-suite"
#define AppExeName "OpenFolioPDFSuite.exe"
#define RepoRoot "..\.."

[Setup]
AppId={{11DE5939-B472-4426-A60C-1BC43D637BCB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\OpenFolio PDF Suite
DefaultGroupName=OpenFolio PDF Suite
DisableProgramGroupPage=yes
LicenseFile={#RepoRoot}\LICENSE
OutputDir={#RepoRoot}\dist\installer
OutputBaseFilename=OpenFolioPDFSuite-Setup-{#AppVersion}
SetupIconFile={#RepoRoot}\packaging\icons\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#RepoRoot}\dist\OpenFolioPDFSuite\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\dist\OpenFolioPDFSuite\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OpenFolio PDF Suite"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,OpenFolio PDF Suite}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OpenFolio PDF Suite"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,OpenFolio PDF Suite}"; Flags: nowait postinstall skipifsilent
