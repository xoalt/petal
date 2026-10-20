import argparse
import json
import os
import sys
from pathlib import Path

root=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(root/'vendor'))

def cli():
 if '--version' in sys.argv:
  from . import __version__
  print('Petal '+__version__);return 0
 if len(sys.argv)==2 and sys.argv[1] in ('--help','-h'):
  print('''Petal — offline file conversion for Wayland

Usage: petal-run [FILES...] [OPTION]
       petal-run convert FILES... --to FORMAT [--output-dir DIRECTORY]

  --wheel       Open the conversion wheel (default)
  --tray        Run in the system tray
  --settings    Open Settings
  --setup       Run first-launch setup again
  --software    Check conversion programs and manage optional downloads
  --shelf       Open the file shelf
  --drop-target Show the floating drop target
  --check       List detected conversion programs (no display required)
  --doctor      Test sample exports (exit 1 when features are unavailable)
  --quit        Quit the running app
  --version     Show version

Original project: Tangerine for macOS — https://tangerineformac.com/
Petal is an unofficial, independently implemented Linux port.''');return 0
 state=Path(os.environ.get('PETAL_STATE_DIR',str(Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'petal')))
 try:settings=json.loads((state/'settings.json').read_text())
 except (OSError,ValueError):settings={}
 if not isinstance(settings,dict):settings={}
 from .catalog import configure_engines
 configure_engines(settings)
 if len(sys.argv)>1 and sys.argv[1]=='convert':
  p=argparse.ArgumentParser(description='Petal offline conversion')
  p.add_argument('command');p.add_argument('files',nargs='+');p.add_argument('--to',required=True);p.add_argument('--output-dir');p.add_argument('--params',default='{}')
  a=p.parse_args()
  from .engine import execute
  try:print(json.dumps([str(x) for x in execute(a.files,'to:'+a.to,json.loads(a.params),a.output_dir)],indent=2));return 0
  except Exception as e:print(str(e),file=sys.stderr);return 1
 if '--check' in sys.argv:
  from .catalog import dependencies
  print(json.dumps(dependencies(),indent=2));return 0
 if '--doctor' in sys.argv:
  from .readiness import scan
  rows=scan(settings);print(json.dumps([r.data() for r in rows],indent=2));return int(any(r.status in ('missing','partial','failed') for r in rows))
 if '--render-preview' in sys.argv:
  from .wheel import preview
  preview(sys.argv[sys.argv.index('--render-preview')+1]);return 0
 known={'--wheel','--tray','--settings','--app','--setup','--software','--shelf','--drop-target','--quit','--smoke-test'}
 unknown=[x for x in sys.argv[1:] if x.startswith('--') and x not in known]
 if unknown:print('Unknown option: '+unknown[0]+'. See --help.',file=sys.stderr);return 2
 try:
  import gi,cairo
  gi.require_version('Gtk','4.0')
  from PIL import Image
 except (ImportError,ValueError) as e:
  print('Petal needs GTK4, PyGObject, pycairo, and Pillow for the desktop interface.\nInstall the core dependencies listed in README.md using your distribution software manager.\nDetails: '+str(e),file=sys.stderr);return 2
 from .app import main
 return main(sys.argv[1:])

raise SystemExit(cli())
