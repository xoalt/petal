#!/usr/bin/env python3
"""Create/remove user-local launchers; never installs system packages or moves data."""
import argparse,os,shlex,tempfile
from pathlib import Path
MARKER='Petal managed launcher'
ID='io.github.xoalt.Petal'
def atomic_write(path,text,mode):
 path.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix='.petal-',dir=path.parent)
 try:
  with os.fdopen(fd,'w') as f:f.write(text)
  os.chmod(name,mode);os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prefix',type=Path,default=Path.home()/'.local');parser.add_argument('--remove',action='store_true');args=parser.parse_args();root=Path(__file__).resolve().parent;prefix=args.prefix.expanduser().resolve()
 launcher=root/'petal-run';icon=root/'assets/petal.png';desktop=prefix/'share/applications'/f'{ID}.desktop';command=prefix/'bin/petal';paths=(command,desktop)
 for path in paths:
  if path.is_symlink() or (path.exists() and (not path.is_file() or MARKER not in path.read_text())):parser.error(f'Refusing to replace an unrelated file: {path}')
 if args.remove:
  for path in paths:
   if path.exists():path.unlink()
  print('Petal launchers removed. App files, settings, and history were kept.');return 0
 if not launcher.is_file() or not icon.is_file():parser.error('Run this installer from the complete extracted Petal folder.')
 if any(c in str(root) for c in ('\n','\r')):parser.error('The app folder path cannot contain a newline.')
 # Desktop Entry Exec uses double quoting, not shell quoting.
 escaped=str(launcher).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$')
 text=f'''[Desktop Entry]
# {MARKER}
Type=Application
Name=Petal
Comment=Offline file conversion wheel for Wayland
Exec="{escaped}" %F
Icon={icon}
Terminal=false
Categories=Utility;
Keywords=convert;wheel;image;audio;video;pdf;
StartupNotify=false
StartupWMClass={ID}
'''
 atomic_write(command,'#!/bin/sh\n# '+MARKER+'\nexec '+shlex.quote(str(launcher))+' "$@"\n',0o755);atomic_write(desktop,text,0o644)
 print(f'Installed launchers in {prefix}. Keep the app folder at {root}.\nSettings stay in $XDG_STATE_HOME/petal (normally ~/.local/state/petal).\nNo autostart or compositor rules were changed.');return 0
if __name__=='__main__':raise SystemExit(main())
