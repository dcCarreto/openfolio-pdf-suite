; Script do Inno Setup para o instalador Windows do OpenFolio PDF Suite.
;
; Espera que o build "onedir" do PyInstaller já exista em dist\OpenFolioPDFSuite
; (gerado por: pyinstaller packaging/pyinstaller/openfolio.spec --noconfirm),
; rodando este script a partir da raiz do repositorio:
;
;   ISCC.exe packaging\windows\installer.iss
;
; O usuário não vê número de versão: o assistente e o arquivo se chamam só "OpenFolio PDF
; Suite". AppVersion é o identificador interno da atualização (a data, como no pyproject.toml),
; que o Windows guarda no registro da instalação; o workflow de release o passa a partir da tag:
;
;   ISCC.exe /DAppVersion=2026.10.21 packaging\windows\installer.iss
;
; O app instala as atualizações rodando este instalador com /SILENT (ui/main_window.py): ele
; atualiza por cima, apaga os arquivos da versão anterior e abre o app de novo.

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
AppVerName={#AppName}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\OpenFolio PDF Suite
DefaultGroupName=OpenFolio PDF Suite
DisableProgramGroupPage=yes
LicenseFile={#RepoRoot}\LICENSE
OutputDir={#RepoRoot}\dist\installer
OutputBaseFilename=OpenFolioPDFSuite-Setup
SetupIconFile={#RepoRoot}\packaging\icons\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}
; A tarefa "associatepdf" registra o app como leitor de PDF ("Abrir com" e aplicativos padrão).
ChangesAssociations=yes
; A tarefa "addtopath" põe a pasta do app (com o openfolio.exe, a linha de comando) no PATH.
ChangesEnvironment=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
brazilianportuguese.AssociatePdf=Registrar o OpenFolio como leitor de PDF ("Abrir com" e aplicativos padrão do Windows)
english.AssociatePdf=Register OpenFolio as a PDF reader ("Open with" and Windows default apps)
brazilianportuguese.DefaultPdf=Escolher o OpenFolio como programa padrão para PDF
english.DefaultPdf=Choose OpenFolio as the default program for PDF
brazilianportuguese.PdfFile=Documento PDF
english.PdfFile=PDF document
brazilianportuguese.AppDescription=Visualizador e editor de PDF, 100% local
english.AppDescription=PDF viewer and editor, 100% local
brazilianportuguese.AddToPath=Adicionar o comando openfolio ao PATH (linha de comando, para scripts)
english.AddToPath=Add the openfolio command to PATH (command line, for scripts)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associatepdf"; Description: "{cm:AssociatePdf}"
Name: "addtopath"; Description: "{cm:AddToPath}"; Flags: unchecked

[Registry]
; Entra na lista "Abrir com" do .pdf sem tomar o lugar do leitor padrão do usuário.
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "OpenFolioPDFSuite.pdf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associatepdf
Root: HKA; Subkey: "Software\Classes\OpenFolioPDFSuite.pdf"; ValueType: string; ValueName: ""; ValueData: "{cm:PdfFile}"; Flags: uninsdeletekey; Tasks: associatepdf
Root: HKA; Subkey: "Software\Classes\OpenFolioPDFSuite.pdf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; Tasks: associatepdf
Root: HKA; Subkey: "Software\Classes\OpenFolioPDFSuite.pdf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; Tasks: associatepdf
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExeName}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey; Tasks: associatepdf
; Aparece em Configurações > Aplicativos > Aplicativos padrão, onde o usuário pode torná-lo o padrão
; para .pdf. O Windows não deixa o instalador fazer essa escolha por ele.
Root: HKA; Subkey: "Software\OpenFolioPDFSuite"; Flags: uninsdeletekey; Tasks: associatepdf
Root: HKA; Subkey: "Software\OpenFolioPDFSuite\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Tasks: associatepdf
Root: HKA; Subkey: "Software\OpenFolioPDFSuite\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{cm:AppDescription}"; Tasks: associatepdf
Root: HKA; Subkey: "Software\OpenFolioPDFSuite\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#AppExeName},0"; Tasks: associatepdf
Root: HKA; Subkey: "Software\OpenFolioPDFSuite\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "OpenFolioPDFSuite.pdf"; Tasks: associatepdf
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "OpenFolioPDFSuite"; ValueData: "Software\OpenFolioPDFSuite\Capabilities"; Flags: uninsdeletevalue; Tasks: associatepdf
; PATH do usuário (ou do sistema, na instalação para todos); sai na desinstalação ([Code]).
Root: HKA; Subkey: "{code:EnvironmentKey}"; ValueType: expandsz; ValueName: "Path"; ValueData: "{code:PathWithApp}"; Tasks: addtopath; Check: NeedsAddPath

[InstallDelete]
; Numa atualização, as bibliotecas da instalação anterior saem antes: uma DLL que a versão nova
; não usa mais poderia ser carregada no lugar da certa.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#RepoRoot}\dist\OpenFolioPDFSuite\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\dist\OpenFolioPDFSuite\openfolio.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\dist\OpenFolioPDFSuite\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\OpenFolio PDF Suite"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,OpenFolio PDF Suite}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\OpenFolio PDF Suite"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,OpenFolio PDF Suite}"; Flags: nowait postinstall skipifsilent
; Abre a página do OpenFolio nos aplicativos padrão (Windows 11; no 10, a lista geral), onde um
; clique o torna o padrão para .pdf.
Filename: "ms-settings:defaultapps?registeredAppMachine=OpenFolioPDFSuite"; Description: "{cm:DefaultPdf}"; Flags: shellexec nowait postinstall skipifsilent runasoriginaluser; Tasks: associatepdf; Check: IsAdminInstallMode
Filename: "ms-settings:defaultapps?registeredAppUser=OpenFolioPDFSuite"; Description: "{cm:DefaultPdf}"; Flags: shellexec nowait postinstall skipifsilent runasoriginaluser; Tasks: associatepdf; Check: not IsAdminInstallMode
; Atualização feita pelo app (/SILENT): ele fechou para instalar e abre de novo.
Filename: "{app}\{#AppExeName}"; Flags: nowait skipifnotsilent

[Code]
function EnvironmentKey(Param: String): String;
begin
  if IsAdminInstallMode then
    Result := 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'
  else
    Result := 'Environment';
end;

function CurrentPath: String;
begin
  if not RegQueryStringValue(HKA, EnvironmentKey(''), 'Path', Result) then
    Result := '';
end;

{ Posição da pasta do app no PATH, entre ";" (0 se não estiver). }
function AppPosInPath(Paths: String): Integer;
begin
  Result := Pos(';' + Uppercase(ExpandConstant('{app}')) + ';', ';' + Uppercase(Paths) + ';');
end;

{ Uma atualização (que repete a tarefa) não duplica a pasta no PATH. }
function NeedsAddPath: Boolean;
begin
  Result := AppPosInPath(CurrentPath) = 0;
end;

function PathWithApp(Param: String): String;
begin
  Result := CurrentPath;
  if (Result <> '') and (Result[Length(Result)] <> ';') then
    Result := Result + ';';
  Result := Result + ExpandConstant('{app}');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Paths: String;
  P, Size: Integer;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  Paths := CurrentPath;
  P := AppPosInPath(Paths);
  if P = 0 then
    exit;
  { A pasta começa em Paths[P]; sai com o ";" de antes (ou o de depois, se for a primeira). }
  Size := Length(ExpandConstant('{app}')) + 1;
  if P > 1 then
    P := P - 1;
  Delete(Paths, P, Size);
  RegWriteExpandStringValue(HKA, EnvironmentKey(''), 'Path', Paths);
end;
