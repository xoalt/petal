"""Native release checks for empty states, keyboard access, and compact layouts."""
import argparse,json,os,sys,tempfile,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);args=p.parse_args();out=Path(args.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
scratch=tempfile.TemporaryDirectory(prefix='petal-release-ui-');base=Path(scratch.name)
os.environ.update(PETAL_STATE_DIR=str(base/'state'),PETAL_APP_ID='io.github.xoalt.Petal.ReleaseCheck',PETAL_DISABLE_TRAY='1',GSETTINGS_BACKEND='memory')
from PIL import Image
from pypdf import PdfWriter
from petal.app import Petal
from petal.legacy import Gtk,Gdk,Gio,GLib,Layer,fit_size
from petal import wheel
image=base/'photo with spaces.png';Image.new('RGB',(160,120),'#f66c29').save(image)
pdf=base/'document.pdf';writer=PdfWriter();writer.add_blank_page(width=72,height=72)
with pdf.open('wb') as f:writer.write(f)
class Check(Petal):
 def __init__(self):super().__init__();self.checks={};self.failed=False;self.stage=0;self.ticks=0
 def check(self,key,value):
  self.checks[key]=bool(value)
  if not value:raise AssertionError(key)
 def accept(self,path):
  model=Gio.ListStore.new(Gio.File);model.append(Gio.File.new_for_path(str(path)));dialog=self.choosers[0];dialog.get_files=lambda:model;dialog.emit('response',Gtk.ResponseType.ACCEPT)
 def capture(self,window,name):
  paint=Gtk.WidgetPaintable.new(window.get_child());snap=Gtk.Snapshot();paint.snapshot(snap,window.get_width(),window.get_height());node=snap.to_node();self.check('render_'+name,node is not None);window.get_renderer().render_texture(node,None).save_to_png(str(out/(name+'.png')))
 def do_command_line(self,cmd):
  self._skip_onboarding=True;self.settings['drop_target']=False;self.settings['setup_completed']=True;self.activate_request([]);GLib.timeout_add(300,self.advance);return 0
 def advance(self):
  self.ticks+=1
  if self.ticks%2:return True
  try:
   if self.stage==0:
    controllers=self.drawing.observe_controllers()
    for i in range(controllers.get_n_items()-1,-1,-1):
     controller=controllers.get_item(i)
     if isinstance(controller,Gtk.EventControllerMotion):self.drawing.remove_controller(controller)
    self.check('key_events_captured_before_mnemonics',self.wheel_keys.get_propagation_phase()==Gtk.PropagationPhase.CAPTURE)
    for key,mode in [(Gdk.KEY_Alt_L,'tools'),(Gdk.KEY_Shift_L,'convert'),(Gdk.KEY_Control_L,'actions'),(Gdk.KEY_Alt_R,'tools'),(Gdk.KEY_Control_R,'actions'),(Gdk.KEY_Shift_R,'convert')]:
     self.wheel_keys.emit('key-pressed',key,0,Gdk.ModifierType(0));self.check('modifier_'+Gdk.keyval_name(key),self.mode==mode)
    self.observe_modifiers(Gdk.ModifierType.ALT_MASK);self.check('already_held_modifier_detected',self.mode=='tools');self.observe_modifiers(Gdk.ModifierType(0));self.check('mode_latches_after_key_release',self.mode=='tools')
    target=type('DragState',(),{'get_current_event_state':lambda _:Gdk.ModifierType.CONTROL_MASK})();self.drag_motion(target,180,90);self.check('drag_modifier_switches_without_key_event',self.mode=='actions');self.observe_modifiers(Gdk.ModifierType(0));self.switch_mode('convert')
    if Layer and Layer.is_layer_window(self.main):
     self.check('explicit_wheel_takes_keyboard_focus',Layer.get_keyboard_mode(self.main)==Layer.KeyboardMode.EXCLUSIVE);self.main.set_visible(False);self.check('hidden_wheel_releases_keyboard',Layer.get_keyboard_mode(self.main)==Layer.KeyboardMode.NONE);self.show_main(focus=False);self.check('passive_drag_preview_does_not_grab_keyboard',Layer.get_keyboard_mode(self.main)==Layer.KeyboardMode.ON_DEMAND);self.show_main()
    self.click_wheel(180,90);self.check('empty_leaf_opens_picker',len(self.choosers)==1 and self.choosers[0].get_visible());self.check('wheel_hidden_below_picker',not self.main.get_visible());self.choosers[0].emit('response',Gtk.ResponseType.CANCEL);self.check('cancel_returns_to_empty_wheel',self.main.get_visible() and not self.paths);self.key_pressed(None,Gdk.KEY_Return,0,Gdk.ModifierType(0));self.check('enter_empty_opens_picker',len(self.choosers)==1);self.choosers[0].emit('response',Gtk.ResponseType.CANCEL);self.click_wheel(180,90);self.accept(image)
   elif self.stage==1:
    self.check('leaf_choice_remembered',self.paths==[image] and self.page_items()[self.selected].id=='to:jpg');self.check('selection_does_not_start_surprise_conversion',not self.busy and not self.jobs);self.check('selected_file_has_thumbnail',self.thumbnail is not None);self.capture(self.main,'wheel');self.set_files([]);self.click_wheel(270,180);self.accept(pdf)
   elif self.stage==2:
    self.check('incompatible_pending_action_cleared',self.paths==[pdf] and self.selected==-1 and not self.busy);self.key_pressed(None,Gdk.KEY_F10,0,Gdk.ModifierType.SHIFT_MASK);self.check('keyboard_context_menu_opens',self.wheel_menu.get_visible());panel=self.wheel_menu.get_child();buttons=[];child=panel.get_first_child()
    while child:
     if isinstance(child,Gtk.Button):buttons.append(child)
     child=child.get_next_sibling()
    self.check('context_actions_are_accessible_native_buttons',len(buttons)>=8 and all(b.get_label() and b.get_accessible_role()==Gtk.AccessibleRole.BUTTON for b in buttons));self.key_pressed(None,Gdk.KEY_Escape,0,Gdk.ModifierType(0));self.check('escape_closes_menu_before_wheel',not self.wheel_menu.get_visible() and self.main.get_visible());self.key_pressed(None,Gdk.KEY_o,0,Gdk.ModifierType.CONTROL_MASK);self.check('ctrl_o_opens_file_picker',len(self.choosers)==1);self.choosers[0].emit('response',Gtk.ResponseType.CANCEL)
    values=dict(self.settings,animations=False);self.apply_appearance(values);self.set_petal_hover(0);self.check('reduced_motion_disables_hover_animation',self.petal_values=={0:1.0});self.show_settings();self.select_section('About');self.check('settings_is_separate_layer',self.controls is not self.main and self.section_stack.get_visible_child_name()=='About')
   elif self.stage==3:
    self.capture(self.controls,'about');Gtk.Settings.get_default().set_property('gtk-font-name','Sans 14');self.show_setup(['--settings']);self.setup_wizard.window.set_default_size(760,520);self.setup_wizard.index=3;self.setup_wizard.refresh()
   elif self.stage==4:
    wizard=self.setup_wizard;ok,rect=wizard.next_button.compute_bounds(wizard.window);self.check('large_text_footer_stays_in_window',ok and rect.get_y()+rect.get_height()<=wizard.window.get_height()+1);self.check('setup_pages_scroll_on_small_screens',wizard.stack.get_visible_child().get_property('vscrollbar-policy')==Gtk.PolicyType.AUTOMATIC);self.capture(wizard.window,'setup-large-text');self.complete();return False
   self.stage+=1
  except Exception:self.failed=True;traceback.print_exc();self.complete();return False
  return True
 def complete(self):
  (out/'checks.json').write_text(json.dumps({'passed':not self.failed,'checks':self.checks,'picker_selection':'Real native opening/cancellation; selected-file model supplied for acceptance callbacks.','accessibility_limit':'Native keyboard controls and accessible button roles tested; no full screen-reader certification.'},indent=2)+'\n');print(json.dumps(self.checks),flush=True);self.request_quit()
if not Gtk.init_check():raise SystemExit('Wayland display is unavailable')
app=Check();code=app.run(['petal-release-check']);raise SystemExit(code or int(app.failed))
