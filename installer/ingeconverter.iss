; Script Inno Setup para IngeConverter.
;
; Genera un instalador .exe para Windows con wizard en espanol,
; EULA, accesos directos y desinstalador.
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

; Instalacion per-user sin UAC (no necesita admin).
; LocalDB se instala por separado (requiere admin, pero es un MSI aparte).
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest

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


[UninstallDelete]
Type: filesandordirs; Name: "{app}\__pycache__"
