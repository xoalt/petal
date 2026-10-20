"""Launch the user's chosen installed apps through GIO or fixed argument lists."""
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from gi.repository import Gio
from .catalog import kind

MIMES={'file_manager':'inode/directory','image_app':'image/png','media_app':'video/mp4','document_app':'application/pdf','sharing_app':'application/octet-stream'}
TERMINALS=('ghostty','foot','kitty','alacritty','konsole','gnome-terminal','wezterm','x-terminal-emulator')
@dataclass(frozen=True)
class AppChoice:
 id:str
 name:str

class AppUnavailable(Exception):pass

def choices(role):
 result=[AppChoice('','Use system default' if role not in ('terminal_app','sharing_app') else 'Choose automatically')]
 if role=='terminal_app':
  result += [AppChoice('command:'+name,name.replace('-',' ').title()) for name in TERMINALS if shutil.which(name)]
 else:
  result += [AppChoice(a.get_id(),a.get_display_name()) for a in Gio.AppInfo.get_all_for_type(MIMES[role]) if a.get_id() and a.should_show()]
  if role=='sharing_app':
   result=[result[0]]+[AppChoice('command:'+n,'LocalSend') for n in ('localsend','localsend_app') if shutil.which(n)]
  # A terminal file manager is useful even without a desktop entry.
  if role=='file_manager' and shutil.which('yazi') and not any(x.id=='yazi.desktop' for x in result):result.append(AppChoice('command:yazi','Yazi'))
 unique={x.id:x for x in result}
 return [unique.pop('')]+sorted(unique.values(),key=lambda x:x.name.casefold())

def app_info(identifier):
 app=Gio.DesktopAppInfo.new(identifier)
 if not app:raise AppUnavailable('That application is no longer installed. Choose another in Settings → Applications.')
 return app

def terminal_command(identifier,cwd,payload=None):
 name=identifier.removeprefix('command:') if identifier else next((n for n in TERMINALS if shutil.which(n)),None)
 if name not in TERMINALS or not shutil.which(name or ''):raise AppUnavailable('The selected terminal is unavailable. Choose another in Settings → Applications.')
 executable=shutil.which(name);folder=str(Path(cwd));payload=list(payload or [])
 if name=='ghostty':return [executable,'--working-directory='+folder]+(['-e',*payload] if payload else [])
 if name=='foot':return [executable,'--working-directory='+folder,*payload]
 if name=='kitty':return [executable,'--directory',folder,*payload]
 if name=='alacritty':return [executable,'--working-directory',folder]+(['-e',*payload] if payload else [])
 if name=='konsole':return [executable,'--workdir',folder]+(['-e',*payload] if payload else [])
 if name=='gnome-terminal':return [executable,'--working-directory='+folder]+(['--',*payload] if payload else [])
 if name=='wezterm':return [executable,'start','--cwd',folder]+(['--',*payload] if payload else [])
 return [executable]+(['-e',*payload] if payload else [])

def launch_terminal(settings,cwd,payload=None):
 return subprocess.Popen(terminal_command(settings.get('terminal_app',''),cwd,payload),cwd=cwd,start_new_session=True)

def launch(settings,role,paths,context=None):
 paths=[Path(p).resolve() for p in paths];identifier=settings.get(role,'')
 if not paths:return
 if role=='terminal_app':return launch_terminal(settings,paths[0] if paths[0].is_dir() else paths[0].parent)
 if role=='file_manager' and not identifier:
  default=Gio.AppInfo.get_default_for_type('inode/directory',False)
  if default and default.get_id()=='yazi.desktop':identifier='yazi.desktop'
 if role=='file_manager' and identifier in ('command:yazi','yazi.desktop'):
  executable=shutil.which('yazi')
  if not executable:raise AppUnavailable('Yazi is unavailable. Choose another file manager in Settings → Applications.')
  return launch_terminal(settings,paths[0] if paths[0].is_dir() else paths[0].parent,[executable,*map(str,paths)])
 if role=='sharing_app' and (not identifier or identifier.startswith('command:')):
  names=('localsend','localsend_app') if not identifier else (identifier.removeprefix('command:'),)
  executable=next((shutil.which(n) for n in names if n in ('localsend','localsend_app') and shutil.which(n)),None)
  if not executable:raise AppUnavailable('No sharing app is available. Choose one in Settings → Applications, or drag files from the shelf into another app.')
  return subprocess.Popen([executable,*map(str,paths)],start_new_session=True)
 if identifier:
  return app_info(identifier).launch([Gio.File.new_for_path(str(p)) for p in paths],context)
 for p in paths:Gio.AppInfo.launch_default_for_uri(p.as_uri(),context)

def role_for_path(path):
 k=kind(path)
 return 'file_manager' if k=='folder' else 'image_app' if k=='image' else 'media_app' if k in ('audio','video') else 'document_app' if k in ('pdf','document','slides','sheet') else None

def open_files(settings,paths,context=None):
 groups={}
 for path in paths:groups.setdefault(role_for_path(path),[]).append(path)
 for role,files in groups.items():
  if role:launch(settings,role,files,context)
  else:
   for path in files:Gio.AppInfo.launch_default_for_uri(Path(path).resolve().as_uri(),context)
