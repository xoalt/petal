"""Isolated GTK/Wayland integration check. Does not contact the production app."""
import json
import os
from pathlib import Path
import sys
import traceback
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
scratch=tempfile.TemporaryDirectory(prefix='petal-desktop-check-')
os.environ.setdefault('PETAL_STATE_DIR',str(Path(scratch.name)/'state'))
from PIL import Image
fixture=Path(scratch.name)/'test.png';Image.new('RGB',(160,120),'#ed9955').save(fixture)
os.environ.setdefault('PETAL_TEST_FILE',str(fixture))
os.environ['PETAL_APP_ID']='io.github.petal.DesktopCheck'
os.environ['PETAL_DISABLE_TRAY']='1'
from petal.app import Petal
from petal.legacy import Gtk,Gdk,GLib
from petal import wheel

class DesktopCheck(Petal):
 def __init__(self):super().__init__();self.checks={};self.failed=False
 def checked(self,fn):
  try:fn()
  except Exception:
   self.failed=True;traceback.print_exc()
  return False
 def do_command_line(self,cmd):
  super().do_command_line(cmd)
  # Settings now correctly hides the wheel and releases its keyboard focus.
  # Remap it before exercising pointer geometry and animation.
  self.show_main()
  def begin():
   # Real pointer enter/leave events must not race these scripted callback checks.
   controllers=self.drawing.observe_controllers()
   for i in range(controllers.get_n_items()-1,-1,-1):
    controller=controllers.get_item(i)
    if isinstance(controller,Gtk.EventControllerMotion):self.drawing.remove_controller(controller)
   self.switch_mode('tools');self.set_files([Path(os.environ['PETAL_TEST_FILE'])])
   self.checks['tool_paging']=len(self.page_items())==self.page_capacity()
   self.change_page(1);self.checks['remaining_tools_reachable']=bool(self.page_items()) and self.page==1
   self.change_page(-1);self.hover(180,60)
   self.checks['hover_selected']=self.selected==0
  def during():
   value=self.petal_values.get(0,0)
   animations=Gtk.Settings.get_default().get_property('gtk-enable-animations')
   self.checks['animation_intermediate_value']=0<value<1 if animations else value==1
  def expanded():
   self.checks['animation_completes']=self.petal_values.get(0,0)>.99
   self.hover(180,42);self.checks['expanded_petal_stays_selected']=self.selected==0
   self.leave_wheel()
  def reset():
   self.checks['animation_returns_to_rest']=not self.petal_values
   self.show_activity();self.checks['activity_opens_separately']=self.section_stack.get_visible_child_name()=='Activity'
   self.controls.close();self.show_settings();self.checks['settings_reopens']=self.controls.get_visible()
   self.settings['notify']=False;self.start_job('to:webp',{})
  def complete():
   self.checks['background_job_completed']=not self.busy and bool(self.last_outputs) and self.last_outputs[0].is_file()
   self.checks['wheel_hides_after_job']=not self.main.get_visible()
   self.checks['activity_has_result']='Done' in self.status.get_text()
   self.state.mkdir(parents=True,exist_ok=True);(self.state/'interaction-checks.json').write_text(json.dumps(self.checks,indent=2)+'\n')
   print(json.dumps(self.checks),flush=True)
   self.failed=self.failed or not all(self.checks.values())
  for delay,fn in [(300,begin),(380,during),(650,expanded),(1000,reset),(1800,complete)]:GLib.timeout_add(delay,lambda f=fn:self.checked(f))
  return 0

if not Gtk.init_check():raise SystemExit('A Wayland desktop is required')
app=DesktopCheck();code=app.run(['petal-check','--smoke-test']);raise SystemExit(code or int(app.failed))
