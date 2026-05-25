; Script Inno Setup para IngeConverter.
;
; Genera un instalador .exe para Windows con wizard en espanol,
; EULA, accesos directos, desinstalador Y prerequisitos bundleados
; (SQL Server LocalDB + ODBC Driver 18).
;
; Compilar local:
;     iscc /DMyAppVersion=0.1.0 installer\ingeconverter.iss
;
; Compilar desde GitHub Actions: ver .github/workflows/build-windows.yml
;
; El AppId es un GUID FIJO — NO cambiarlo entre versiones.

#define MyAppName "IngeConverter"
#define MyAppPublisher "Ing. Marco Sumari Tellez"
#define MyAppURL "https://ingepresupuestos.com"
#define MyAppExeName "ingeconverter.exe"

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif

[Setup]
; AppId GUID FIJO — cambiar esto rompe upgrades.
AppId={{A3B7E924-6F81-4D2C-9E5A-8C1F3D7B0E42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Convertidor de presupuestos S10 a IngePresupuestos
VersionInfoProductName={#MyAppName}

; Admin requerido para instalar LocalDB + ODBC Driver silenciosamente.
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=admin

LicenseFile=..\LICENSE.txt

OutputDir=..\dist
OutputBaseFilename=ingeconverter-setup-v{#MyAppVersion}

WizardStyle=modern
ShowLanguageDialog=no
DisableWelcomePage=no
DisableDirPage=auto
DisableProgramGroupPage=auto

Compression=lzma2/max
SolidCompression=yes

SetupIconFile=..\resources\icons\ingeconverter.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

CloseApplications=force
RestartApplications=no
MinVersion=10.0


[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"


[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el {cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked


[Files]
; PyInstaller genera un solo .exe (onefile) o carpeta.
; Si es onefile:
Source: "..\dist\ingeconverter.exe"; DestDir: "{app}"; Flags: ignoreversion; Check: IsOneFile
; Si es carpeta (onedir):
Source: "..\dist\ingeconverter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: not IsOneFile

; Prerequisitos bundleados (descargados en GitHub Actions).
Source: "prereqs\SqlLocalDB.msi"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
Source: "prereqs\msodbcsql18.msi"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall


[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Convertidor de presupuestos S10"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon


[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Ejecutar {#MyAppName}"; Flags: nowait postinstall skipifsilent


[Code]
function IsOneFile: Boolean;
begin
  Result := FileExists(ExpandConstant('{src}\..\dist\ingeconverter.exe'));
end;

function IsLocalDBInstalled: Boolean;
var
  ResultCode: Integer;
begin
  // SqlLocalDB.exe esta en PATH si LocalDB esta instalado
  Result := Exec('cmd.exe', '/c SqlLocalDB.exe info >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
            and (ResultCode = 0);
  if not Result then
  begin
    // Fallback: buscar en Program Files
    Result := FileExists(ExpandConstant('{pf}\Microsoft SQL Server\160\Tools\Binn\SqlLocalDB.exe'))
           or FileExists(ExpandConstant('{pf}\Microsoft SQL Server\150\Tools\Binn\SqlLocalDB.exe'))
           or FileExists(ExpandConstant('{pf}\Microsoft SQL Server\140\Tools\Binn\SqlLocalDB.exe'));
  end;
end;

function IsODBCDriverInstalled: Boolean;
var
  Names: TArrayOfString;
  I: Integer;
begin
  Result := False;
  if RegGetSubkeyNames(HKEY_LOCAL_MACHINE,
       'SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers', Names) then
  begin
    // Si hay subkeys, buscar en los valores del key padre
  end;
  // Verificar directamente si alguno de los drivers conocidos existe
  Result := RegValueExists(HKEY_LOCAL_MACHINE,
              'SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers',
              'ODBC Driver 18 for SQL Server')
         or RegValueExists(HKEY_LOCAL_MACHINE,
              'SOFTWARE\ODBC\ODBCINST.INI\ODBC Drivers',
              'ODBC Driver 17 for SQL Server');
end;

procedure InstallPrerequisites;
var
  ResultCode: Integer;
  StatusText: String;
begin
  // Instalar LocalDB si no esta presente
  if not IsLocalDBInstalled then
  begin
    StatusText := WizardForm.StatusLabel.Caption;
    WizardForm.StatusLabel.Caption := 'Instalando SQL Server LocalDB (puede tardar un momento)...';
    WizardForm.ProgressGauge.Style := npbstMarquee;
    try
      if not Exec('msiexec.exe',
                  ExpandConstant('/i "{tmp}\SqlLocalDB.msi" /qn IACCEPTSQLLOCALDBLICENSETERMS=YES'),
                  '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      begin
        MsgBox('No se pudo instalar SQL Server LocalDB (error de ejecucion).'#13#10 +
               'IngeConverter funcionara, pero necesitaras instalarlo manualmente.'#13#10#13#10 +
               'Descargalo de: https://learn.microsoft.com/sql/database-engine/configure-windows/sql-server-express-localdb',
               mbInformation, MB_OK);
      end
      else if ResultCode <> 0 then
      begin
        MsgBox('SQL Server LocalDB: el instalador termino con codigo ' + IntToStr(ResultCode) + '.'#13#10 +
               'Si ya esta instalado, puedes ignorar este mensaje.',
               mbInformation, MB_OK);
      end;
    finally
      WizardForm.StatusLabel.Caption := StatusText;
      WizardForm.ProgressGauge.Style := npbstNormal;
    end;
  end;

  // Instalar ODBC Driver 18 si no esta presente
  if not IsODBCDriverInstalled then
  begin
    StatusText := WizardForm.StatusLabel.Caption;
    WizardForm.StatusLabel.Caption := 'Instalando ODBC Driver 18 para SQL Server...';
    WizardForm.ProgressGauge.Style := npbstMarquee;
    try
      if not Exec('msiexec.exe',
                  ExpandConstant('/i "{tmp}\msodbcsql18.msi" /qn IACCEPTMSODBCSQLLICENSETERMS=YES'),
                  '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      begin
        MsgBox('No se pudo instalar el driver ODBC 18 (error de ejecucion).'#13#10 +
               'IngeConverter funcionara, pero necesitaras instalarlo manualmente.'#13#10#13#10 +
               'Descargalo de: https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server',
               mbInformation, MB_OK);
      end
      else if ResultCode <> 0 then
      begin
        MsgBox('ODBC Driver 18: el instalador termino con codigo ' + IntToStr(ResultCode) + '.'#13#10 +
               'Si ya esta instalado, puedes ignorar este mensaje.',
               mbInformation, MB_OK);
      end;
    finally
      WizardForm.StatusLabel.Caption := StatusText;
      WizardForm.ProgressGauge.Style := npbstNormal;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    InstallPrerequisites;
  end;
end;


[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
