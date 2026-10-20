"""First-launch setup, persistence, cancellation, and live Settings integration."""
import argparse,json,os,sys,tempfile,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
parser=argparse.ArgumentParser();parser.add_argument('--output-dir');args=parser.parse_args()
scratch=tempfile.TemporaryDirectory(prefix='petal-setup-check-');state=Path(scratch.name)/'state';state.mkdir();output=Path(args.output_dir).resolve() if args.output_dir else Path(scratch.name)/'report';output.mkdir(parents=True,exist_ok=True)
initial={'quality':91,'dpi':200,'output_dir':'','notify':False,'drop_target':False};(state/'settings.json').write_text(json.dumps(initial))
os.environ['GSETTINGS_BACKEND']='memory'
os.environ['PETAL_STATE_DIR']=str(state);os.environ['PETAL_APP_ID']='io.github.petal.SetupCheck';os.environ['PETAL_DISABLE_TRAY']='1'
from petal.app import Petal
from petal.legacy import Gtk,Gdk,GLib
from petal.preferences import PRESETS,rgb
from petal import wheel

class Check(Petal):
 def __init__(self):super().__init__();self.checks={};self.failed=False;self.step=0;self.ticks=0;self.total=0
 def check(self,key,value):
  self.checks[key]=bool(value)
  if not value:raise AssertionError(key)
 def do_command_line(self,cmd):
  result=super().do_command_line(cmd);self.paint=Gtk.WidgetPaintable.new(self.setup_wizard.window.get_child());GLib.timeout_add(100,self.advance);return result
 def capture(self,name):
  wizard=self.setup_wizard;widget=wizard.window.get_child();snapshot=Gtk.Snapshot();self.paint.snapshot(snapshot,wizard.window.get_width(),wizard.window.get_height());node=snapshot.to_node()
  self.check('render_'+name,node is not None);texture=wizard.window.get_renderer().render_texture(node,None);texture.save_to_png(str(output/(name+'.png')))
 def advance(self):
  self.ticks+=1;self.total+=1
  if self.ticks<5:return True
  self.ticks=0
  try:
   if self.total>200:raise TimeoutError('Onboarding check timed out')
   if self.step==0:
    w=self.setup_wizard;self.check('first_launch_shows_setup',w.window.get_visible());self.check('first_launch_defers_wheel',self.main is None);self.check('previous_preferences_preserved',self.settings['quality']==91 and not self.settings['drop_target']);self.check('software_is_first_step',w.stack.get_visible_child_name()=='software');w.navigate(1);self.capture('setup-applications')
    picker=w.pages.pickers['file_manager'];i=1 if len(picker.items)>1 else 0;picker.dropdown.set_selected(i);self.chosen_manager=picker.items[i].id
    self.check('application_choice_is_draft',self.settings['file_manager']=='' and w.draft['file_manager']==self.chosen_manager)
    w.navigate(1);w.pages.preset('Ocean');w.pages.mode_picker.set_selected(1);w.pages.opacity_scale.set_value(78)
    rgba=Gdk.RGBA();rgba.parse('#16334e');picker=w.pages.color_buttons['text_color'];picker.popup();self.check('custom_color_popover_opens',picker.get_popover().get_visible());picker.chooser.set_rgba(rgba);picker.apply_button.emit('clicked')
    self.check('color_preview_updates_wheel',wheel.ORANGE==rgb(PRESETS['Ocean'][0]));self.check('draft_is_not_saved_early','setup_completed' not in json.loads((state/'settings.json').read_text()));self.step=1
   elif self.step==1:
    self.capture('setup-appearance');w=self.setup_wizard;w.navigate(1);w.pages.toggles['drop_target'].set_active(True);w.draft['output_dir']=str(state/'results');self.step=2
   elif self.step==2:
    self.capture('setup-preferences');self.setup_wizard.finish();saved=json.loads((state/'settings.json').read_text());self.check('finish_persists_setup_marker',saved['setup_completed'] and saved['setup_version']==2);self.check('selected_app_saved',saved['file_manager']==self.chosen_manager);self.check('appearance_saved',saved['accent_color']==PRESETS['Ocean'][0] and saved['text_color']=='#16334e' and saved['petal_opacity']==78 and saved['appearance_mode']=='dark');self.check('workflow_saved',saved['drop_target'] and saved['quality']==91 and saved['output_dir']==str(state/'results'));self.check('pending_launch_resumes',self.started and self.drop_window is not None);self.step=3
   elif self.step==3:
    other=Petal();self.check('next_launch_loads_completed_setup',other.settings['setup_completed']);self.show_settings();self.check('settings_has_app_and_appearance_pages',self.section_stack.get_child_by_name('Applications') is not None and self.section_stack.get_child_by_name('Appearance') is not None);self.preference_pages.preset('Forest');picker=self.preference_pages.pickers['file_manager'];picker.choose_other();self.check('other_app_chooser_opens',picker.chooser.get_visible());picker.chooser.response(Gtk.ResponseType.CANCEL);self.check('other_app_cancel_restores_settings',self.controls.get_visible());self.check('settings_changes_persist',json.loads((state/'settings.json').read_text())['accent_color']==PRESETS['Forest'][0]);self.show_setup(['--settings']);self.setup_wizard.pages.preset('Rose');self.check('setup_hides_layer_settings',not self.controls.get_visible());self.setup_wizard.cancel();self.check('cancel_restores_saved_theme',wheel.ORANGE==rgb(PRESETS['Forest'][0]) and self.settings['accent_color']==PRESETS['Forest'][0]);self.check('cancel_returns_to_settings',self.controls.get_visible());self.step=4
   elif self.step==4:
    self.show_setup(['--settings']);wizard=self.setup_wizard;wizard.pages.preset('Ocean')
    with patch.object(self,'save_settings',side_effect=OSError('simulated read-only folder')):wizard.finish()
    self.check('failed_save_keeps_setup_open',not wizard.closed and wizard.window.get_visible());self.check('failed_save_keeps_preferences',self.settings['accent_color']==PRESETS['Forest'][0]);self.check('failed_save_is_visible','Could not save' in wizard.error.get_text());wizard.cancel();self.show_setup(['--settings']);self.setup_wizard.pages.preset('Rose');self.setup_wizard.use_defaults();self.check('keep_current_ignores_draft',self.settings['accent_color']==PRESETS['Forest'][0]);
    if self.desktop_appearance:
     self.setting('appearance_mode','system');self.desktop_appearance.set_string('color-scheme','prefer-dark');self.system_appearance_changed();self.check('system_dark_follows_preference',self.system_dark);self.desktop_appearance.set_string('color-scheme','prefer-light');self.system_appearance_changed();self.check('system_light_follows_preference',not self.system_dark)
    self.check('activity_feedback_reparented',self.status_box.get_parent() is not None);self.complete();return False
  except Exception:self.failed=True;traceback.print_exc();self.complete();return False
  return True
 def complete(self):
  (output/'checks.json').write_text(json.dumps({'passed':not self.failed,'checks':self.checks},indent=2)+'\n');print(json.dumps(self.checks),flush=True);self.request_quit()

if not Gtk.init_check():raise SystemExit('Wayland desktop is unavailable')
app=Check();status=app.run(['setup-check','--tray']);raise SystemExit(status or int(app.failed))
