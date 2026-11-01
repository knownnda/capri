; =====================================================================================
;  CAPRI SETUP  -  one installer for everything (Inno Setup 6.3+)
;
;  * The language you pick in the very first setup window is the language Capri speaks
;    (and listens in). It is written to install_language.json, which Capri reads on start.
;  * Downloads what's missing: Python 3.12, Ollama (her brain), the AI model for your
;    language, the speech-recognition model, a speaking voice, all Python packages.
;  * Optional: Minecraft autopilot (Fabric + AltoClef) and Spotify auto-play setup.
;
;  Build:  double-click build_installer.bat   ->  installer\Output\CapriSetup.exe
;  Web installer (tiny exe that downloads Capri itself from your own link):
;          build_installer.bat web https://your.host/capri.zip
; =====================================================================================

#define AppName      "Capri"
#define AppVersion   "4.0"
#define AppPublisher "Capri"
#define PyVersion    "3.12.10"
#define PyUrl        "https://www.python.org/ftp/python/" + PyVersion + "/python-" + PyVersion + "-amd64.exe"
#define OllamaUrl    "https://ollama.com/download/OllamaSetup.exe"

; ---- language files: official ones ship with Inno Setup, the rest are fetched by build_installer.bat into installer\languages
#define LangFile(str Base) FileExists(CompilerPath + "Languages\" + Base) ? "compiler:Languages\" + Base : (FileExists(SourcePath + "languages\" + Base) ? "languages\" + Base : "")
#define L_fr LangFile("French.isl")
#define L_de LangFile("German.isl")
#define L_es LangFile("Spanish.isl")
#define L_it LangFile("Italian.isl")
#define L_pt LangFile("BrazilianPortuguese.isl")
#define L_nl LangFile("Dutch.isl")
#define L_pl LangFile("Polish.isl")
#define L_ru LangFile("Russian.isl")
#define L_tr LangFile("Turkish.isl")
#define L_uk LangFile("Ukrainian.isl")
#define L_ja LangFile("Japanese.isl")
#define L_ko LangFile("Korean.isl")
#define L_ar LangFile("Arabic.isl")
#define L_zh LangFile("ChineseSimplified.isl")
#define L_hi LangFile("Hindi.islu") == "" ? LangFile("Hindi.isl") : LangFile("Hindi.islu")

[Setup]
AppId={{6C1A9F3E-CA9B-4E0A-9B7D-CAPRI0000004}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Capri
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
UsePreviousLanguage=no
OutputDir=Output
#ifdef AppZipUrl
OutputBaseFilename=CapriWebSetup
#else
OutputBaseFilename=CapriSetup
#endif
SetupIconFile=capri.ico
UninstallDisplayIcon={app}\installer\capri.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
SetupLogging=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl,lang\en.isl"
#if L_fr != ""
Name: "fr"; MessagesFile: "{#L_fr},lang\fr.isl"
#endif
#if L_de != ""
Name: "de"; MessagesFile: "{#L_de},lang\de.isl"
#endif
#if L_es != ""
Name: "es"; MessagesFile: "{#L_es},lang\es.isl"
#endif
#if L_it != ""
Name: "it"; MessagesFile: "{#L_it},lang\it.isl"
#endif
#if L_pt != ""
Name: "pt"; MessagesFile: "{#L_pt},lang\pt.isl"
#endif
#if L_nl != ""
Name: "nl"; MessagesFile: "{#L_nl},lang\nl.isl"
#endif
#if L_pl != ""
Name: "pl"; MessagesFile: "{#L_pl},lang\pl.isl"
#endif
#if L_ru != ""
Name: "ru"; MessagesFile: "{#L_ru},lang\ru.isl"
#endif
#if L_tr != ""
Name: "tr"; MessagesFile: "{#L_tr},lang\tr.isl"
#endif
#if L_uk != ""
Name: "uk"; MessagesFile: "{#L_uk},lang\uk.isl"
#endif
#if L_ja != ""
Name: "ja"; MessagesFile: "{#L_ja},lang\ja.isl"
#endif
#if L_ko != ""
Name: "ko"; MessagesFile: "{#L_ko},lang\ko.isl"
#endif
#if L_ar != ""
Name: "ar"; MessagesFile: "{#L_ar},lang\ar.isl"
#endif
#if L_zh != ""
Name: "zh"; MessagesFile: "{#L_zh},lang\zh.isl"
#endif
#if L_hi != ""
Name: "hi"; MessagesFile: "{#L_hi},lang\hi.isl"
#endif

[Types]
Name: "custom"; Description: "{cm:TypeCustom}"; Flags: iscustom

[Components]
Name: "core";      Description: "{cm:CompCore}";      Types: custom; Flags: fixed
Name: "brain";     Description: "{cm:CompBrain}";     Types: custom
Name: "ears";      Description: "{cm:CompEars}";      Types: custom
Name: "voice";     Description: "{cm:CompVoice}";     Types: custom
Name: "minecraft"; Description: "{cm:CompMinecraft}"
Name: "spotify";   Description: "{cm:CompSpotify}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup";     Description: "{cm:TaskStartup}";       GroupDescription: "{cm:AutoStartProgramGroupDescription}"

[Files]
; the installer's own helpers (always)
Source: "postinstall.py"; DestDir: "{app}\installer"; Flags: ignoreversion; AfterInstall: WritePlan
Source: "capri.ico";      DestDir: "{app}\installer"; Flags: ignoreversion
#ifndef AppZipUrl
; ---- offline installer: Capri herself is inside this exe
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "\installer,\venv,\voices,\dist,\build,__pycache__,*.pyc,*.spec,capri_log.txt,capri_crash.txt,capri_memory.json,capri_settings.json,capri_translations.json,reminders.json,spotify.json,.spotify_cache,spotapi_session.json,\voice_api.json,providers.json.tmp,voice_api.json.tmp,install_plan.json,install_log.txt,\providers.json,capri_backups,build_installer.bat,mc_vision.json,mc_vision_test.png,clip_audio_failed.txt,\.git,\tests,.gitignore"
; your AI-brain config is never overwritten on an update
Source: "..\providers.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist
#endif

[Icons]
Name: "{group}\{#AppName}";                 Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\installer\capri.ico"
Name: "{group}\{cm:IconMate}";              Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.py"" --mate"; WorkingDir: "{app}"; IconFilename: "{app}\installer\capri.ico"
Name: "{group}\{cm:IconCheck}";             Filename: "{app}\venv\Scripts\python.exe";  Parameters: """{app}\check.py"""; WorkingDir: "{app}"; IconFilename: "{app}\installer\capri.ico"
Name: "{group}\{cm:IconRepair}";            Filename: "{code:BasePython}";               Parameters: """{app}\installer\postinstall.py"" ""{app}\install_plan.json"""; WorkingDir: "{app}"; IconFilename: "{app}\installer\capri.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";           Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; IconFilename: "{app}\installer\capri.ico"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";           Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.py"" --tray"; WorkingDir: "{app}"; IconFilename: "{app}\installer\capri.ico"; Tasks: startup

[Run]
; 1) Python, only if you don't already have 3.10 - 3.13
Filename: "{tmp}\python-setup.exe"; Parameters: "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=0 Include_test=0 Include_doc=0"; \
  StatusMsg: "{cm:StPython}"; Check: NeedPython; Flags: waituntilterminated
; 2) Ollama (her brain), only if it's missing and you ticked it
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART"; \
  StatusMsg: "{cm:StOllama}"; Check: NeedOllama; Flags: waituntilterminated
; 3) everything else: packages, AI model, speech model, voice (a console window shows the download progress)
Filename: "{code:BasePython}"; Parameters: """{app}\installer\postinstall.py"" ""{app}\install_plan.json"""; WorkingDir: "{app}"; \
  StatusMsg: "{cm:StSetup}"; Flags: waituntilterminated
; 4) optional extras, then start her
Filename: "{app}\venv\Scripts\python.exe"; Parameters: """{app}\minecraft_setup.py"""; WorkingDir: "{app}"; Description: "{cm:RunMinecraft}"; \
  Components: minecraft; Flags: postinstall waituntilterminated
Filename: "{app}\venv\Scripts\python.exe"; Parameters: """{app}\spotify_setup.py"""; WorkingDir: "{app}"; Description: "{cm:RunSpotify}"; \
  Components: spotify; Flags: postinstall waituntilterminated
Filename: "{app}\venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.py"""; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: postinstall nowait skipifsilent

[UninstallRun]
; ask a running Capri to quit (so her files aren't locked)
Filename: "{sys}\curl.exe"; Parameters: "-s -m 3 -X POST -d {{}} http://127.0.0.1:7777/api/quit"; Flags: runhidden skipifdoesntexist; RunOnceId: "QuitCapri"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\voices"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files;          Name: "{app}\install_plan.json"
Type: files;          Name: "{app}\install_log.txt"
Type: files;          Name: "{app}\capri_log.txt"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  FoundPython: String;
  PythonChecked: Boolean;

{ ---------------------------------------------------------------- finding Python / Ollama }
function TryPyKey(Root: Integer; Ver: String; var Path: String): Boolean;
var Key, P: String;
begin
  Result := False;
  Key := 'Software\Python\PythonCore\' + Ver + '\InstallPath';
  if RegQueryStringValue(Root, Key, 'ExecutablePath', P) and FileExists(P) then begin Path := P; Result := True; exit; end;
  if RegQueryStringValue(Root, Key, '', P) and FileExists(AddBackslash(P) + 'python.exe') then begin Path := AddBackslash(P) + 'python.exe'; Result := True; end;
end;

function FindPython(): String;
var Vers: TArrayOfString; i: Integer; P: String;
begin
  if PythonChecked then begin Result := FoundPython; exit; end;
  PythonChecked := True; FoundPython := '';
  SetArrayLength(Vers, 4); Vers[0] := '3.12'; Vers[1] := '3.13'; Vers[2] := '3.11'; Vers[3] := '3.10';
  for i := 0 to GetArrayLength(Vers) - 1 do begin
    if TryPyKey(HKEY_CURRENT_USER, Vers[i], P) or TryPyKey(HKLM64, Vers[i], P) or TryPyKey(HKLM32, Vers[i], P) then begin
      FoundPython := P; break;
    end;
  end;
  Result := FoundPython;
end;

function NeedPython(): Boolean;
begin
  Result := FindPython() = '';
end;

{ the Python that runs postinstall.py: yours, or the one this setup just installed }
function BasePython(Param: String): String;
begin
  Result := FindPython();
  if Result = '' then Result := ExpandConstant('{localappdata}\Programs\Python\Python312\python.exe');
end;

function OllamaExe(): String;
begin
  Result := ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe');
  if FileExists(Result) then exit;
  Result := ExpandConstant('{commonpf64}\Ollama\ollama.exe');
  if FileExists(Result) then exit;
  Result := FileSearch('ollama.exe', GetEnv('PATH'));
end;

function NeedOllama(): Boolean;
begin
  Result := WizardIsComponentSelected('brain') and (OllamaExe() = '');
end;

{ ---------------------------------------------------------------- the AI model that speaks your language best }
function BrainModel(Lang: String): String;
begin
  if (Lang = 'en') or (Lang = 'fr') or (Lang = 'de') or (Lang = 'es') or (Lang = 'it') or (Lang = 'pt') then
    Result := 'llama3.2:3b'
  else
    Result := 'qwen2.5:3b';     { Japanese, Chinese, Korean, Arabic, Hindi, Russian, Ukrainian, Turkish, Polish, Dutch }
end;

{ ---------------------------------------------------------------- writing the language + plan for postinstall.py }
function J(S: String): String;
begin
  StringChangeEx(S, '\', '\\', True);
  StringChangeEx(S, '"', '\"', True);
  StringChangeEx(S, #13, ' ', True);
  StringChangeEx(S, #10, ' ', True);
  Result := '"' + S + '"';
end;

function B(V: Boolean): String;
begin
  if V then Result := 'true' else Result := 'false';
end;

procedure WritePlan();
var L: TArrayOfString; Lang, Url: String;
begin
  Lang := ActiveLanguage();
  Url := '';
#ifdef AppZipUrl
  Url := '{#AppZipUrl}';
#endif
  { 1) the language Capri speaks: read (and removed) by modes.py on her next start }
  SetArrayLength(L, 1);
  L[0] := '{"language": ' + J(Lang) + '}';
  SaveStringsToUTF8File(ExpandConstant('{app}\install_language.json'), L, False);

  { 2) the plan for postinstall.py (it re-runs fine from the Start Menu "Repair" shortcut) }
  SetArrayLength(L, 1);
  L[0] := '{' +
    '"language": ' + J(Lang) + ', ' +
    '"app_dir": ' + J(ExpandConstant('{app}')) + ', ' +
    '"app_zip_url": ' + J(Url) + ', ' +
    '"brain": ' + B(WizardIsComponentSelected('brain')) + ', ' +
    '"ears": ' + B(WizardIsComponentSelected('ears')) + ', ' +
    '"voice": ' + B(WizardIsComponentSelected('voice')) + ', ' +
    '"model": ' + J(BrainModel(Lang)) + ', ' +
    '"ollama": ' + J(OllamaExe()) + ', ' +
    '"strings": {' +
      '"title": ' + J(CustomMessage('PiTitle')) + ', ' +
      '"app": ' + J(CustomMessage('PiApp')) + ', ' +
      '"packages": ' + J(CustomMessage('PiPackages')) + ', ' +
      '"brain": ' + J(CustomMessage('PiBrain')) + ', ' +
      '"ears": ' + J(CustomMessage('PiEars')) + ', ' +
      '"voice": ' + J(CustomMessage('PiVoice')) + ', ' +
      '"ok": ' + J(CustomMessage('PiOk')) + ', ' +
      '"failed": ' + J(CustomMessage('PiFailed')) + ', ' +
      '"done": ' + J(CustomMessage('PiDone')) + ', ' +
      '"close": ' + J(CustomMessage('PiClose')) +
    '}}';
  SaveStringsToUTF8File(ExpandConstant('{app}\install_plan.json'), L, False);
end;

{ ---------------------------------------------------------------- wizard }
function OnDownloadProgress(const Url, FileName: String; const Progress, ProgressMax: Int64): Boolean;
begin
  if Progress = ProgressMax then Log(Format('Downloaded %s', [FileName]));
  Result := True;
end;

procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption := WizardForm.WelcomeLabel2.Caption + #13#10#13#10 + CustomMessage('WelcomeLang');
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing), CustomMessage('DownloadDesc'), @OnDownloadProgress);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID <> wpReady then exit;
  DownloadPage.Clear;
  if NeedPython() then DownloadPage.Add('{#PyUrl}', 'python-setup.exe', '');
  if NeedOllama() then DownloadPage.Add('{#OllamaUrl}', 'OllamaSetup.exe', '');
  if NeedPython() or NeedOllama() then begin
    DownloadPage.Show;
    try
      try
        DownloadPage.Download;
      except
        if DownloadPage.AbortedByUser then Log('Download aborted by user.')
        else SuppressibleMsgBox(AddPeriod(GetExceptionMessage) + #13#10#13#10 + CustomMessage('DownloadFailed'), mbCriticalError, MB_OK, IDOK);
        Result := False;
      end;
    finally
      DownloadPage.Hide;
    end;
  end;
end;

