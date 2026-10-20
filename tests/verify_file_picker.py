"""Exercise the empty wheel's real native picker on an isolated desktop instance."""
import json,os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
scratch=tempfile.TemporaryDirectory(prefix='petal-picker-')
os.environ['PETAL_STATE_DIR']=str(Path(scratch.name)/'state')
os.environ['PETAL_APP_ID']='io.github.petal.PickerCheck'
os.environ['PETAL_DISABLE_TRAY']='1'
os.environ['GSETTINGS_BACKEND']='memory'
from PIL import Image
from petal.app import Petal
from petal.legacy import Gtk,GLib,Gio
fixture=Path(os.environ.get('PETAL_PICKER_FIXTURE_DIR',scratch.name))/'selected image.png';Image.new('RGB',(64,48),'orange').save(fixture)
class Check(Petal):
 def __init__(self):super().__init__();self.checks={};self.failed=False
 def step(self,fn):
  try:fn()
  except Exception:
   self.failed=True;traceback.print_exc();self.quit()
  return False
 def do_command_line(self,cmd):
  self._skip_onboarding=True;self.activate_request([])
  def open_empty():
   self.checks['starts_empty']=not self.paths
   self.click_wheel(180,180)
   self.checks['center_opens_native_picker']=len(self.choosers)==1 and self.choosers[0].get_visible()
   self.checks['overlay_hidden_for_picker']=not self.main.get_visible()
   self.choose_files();self.checks['duplicate_picker_prevented']=len(self.choosers)==1
  def cancel():
   self.choosers[0].emit('response',Gtk.ResponseType.CANCEL)
   self.checks['cancel_restores_empty_wheel']=self.main.get_visible() and not self.paths and not self.choosers
   self.click_wheel(180,180)
  def select():
   # Native/portal backends populate the file model only on their own response.
   # Supply that return model here; opening and cancellation above use the real picker.
   model=Gio.ListStore.new(Gio.File);model.append(Gio.File.new_for_path(str(fixture)))
   self.choosers[0].get_files=lambda:model
   self.choosers[0].emit('response',Gtk.ResponseType.ACCEPT)
   self.checks['selection_loads_file']=self.paths==[fixture]
   self.checks['selection_restores_wheel']=self.main.get_visible() and not self.choosers
  def finish():
   self.checks['selected_image_has_preview']=self.thumbnail is not None
   print(json.dumps(self.checks,indent=2),flush=True)
   if os.environ.get('PETAL_PICKER_REPORT'):Path(os.environ['PETAL_PICKER_REPORT']).write_text(json.dumps(self.checks,indent=2)+'\n')
   self.failed=self.failed or not all(self.checks.values());self.request_quit()
  for delay,fn in [(250,open_empty),(900,cancel),(1700,select),(2400,finish)]:GLib.timeout_add(delay,lambda f=fn:self.step(f))
  return 0
if not Gtk.init_check():raise SystemExit('A Wayland desktop is required')
app=Check();code=app.run(['petal-picker-check']);raise SystemExit(code or int(app.failed))
