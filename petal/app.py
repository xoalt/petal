"""Native UI: a desktop overlay and an independent settings application."""
import json
import math
import os
from pathlib import Path
import subprocess
import cairo
from . import legacy,wheel,appearance,integrations,__version__
from .preferences import DEFAULTS,normalize
from .setup import SetupWizard,PreferencePages,SETUP_CSS
from .catalog import Action,choices,dependencies,kind,configure_engines
from .editors import Editor,EDITOR_CSS,AsyncPreview,scaled_source
from .legacy import Gtk,Gdk,Gio,GLib,Layer,box,label,button

CSS='''
window {background:#fafafa;color:#202124;font-family:sans-serif;}
window.layer,window.wheel-surface {background:transparent;}
.panel {background:#fafafa;border:1px solid #d8dadd;border-radius:14px;padding:24px;}
.title {font-size:23px;font-weight:600;}
.muted {color:#6f7379;font-size:12px;}
.orange {color:#e85b08;}
.sidebar {background:#ebeced;padding:18px 12px;border-radius:14px 0 0 14px;}
.settings-body {padding:26px;background:#fafafa;border-radius:0 14px 14px 0;}
button {background:#f1f2f3;color:#202124;border:1px solid #d8dade;border-radius:7px;padding:8px 12px;box-shadow:none;}
button:hover {background:#e6e8ea;}
button:checked {background:#dfe1e4;border-color:#dfe1e4;}
button.primary {background:#ff6109;color:white;border-color:#ff6109;}
button.flat {background:transparent;border-color:transparent;}
entry,dropdown {background:white;color:#202124;border:1px solid #d8dade;border-radius:7px;padding:8px;}
switch:checked {background:#ff6109;} switch slider {background:white;}
.status {background:#f1f2f3;border:1px solid #e0e2e5;border-radius:8px;padding:12px;}
.error {color:#a72d19;}.success {color:#347047;}
.drop {background:rgba(252,253,254,.92);border:1px solid rgba(120,130,140,.3);border-radius:22px;padding:0;}
separator {background:#e1e3e6;min-height:1px;}
'''
CSS+=EDITOR_CSS+SETUP_CSS
legacy.CSS=CSS

class Petal(legacy.LegacyApp):
 def __init__(self):
  super().__init__();self.set_application_id(os.environ.get('PETAL_APP_ID','io.github.xoalt.Petal'))
  if GLib.get_application_name()!='Petal':GLib.set_application_name('Petal')
  self.settings=normalize(self.settings);self.setup_wizard=None;self.setup_requests=[];self._skip_onboarding=False;self._appearance_provider=None;self.software_window=None
  self.controls=None;self.section_stack=None;self.files_summary=None;self.settings.setdefault('tray_enabled',True)
  self.editors=[];self.thumbnail=None;self.thumbnail_key=None;self.thumbnail_preview=AsyncPreview();self.progress_window=None;self.progress_timer=None
  self.petal_values={};self.petal_from={};self.petal_started={};self.petal_target={};self.petal_anim=None;self.petal_duration=.19
  self._wheel_focus=True;self._mode_modifiers=Gdk.ModifierType(0)
  self.empty_notice_until=0;self.empty_shake_started=0;self.empty_shake_index=-1;self.empty_feedback_timer=None
 def init_feedback(self):
  # Job feedback belongs to Activity; it is never parented into the wheel.
  self.status=label('No conversions yet.','muted',True);self.status.set_selectable(True)
  self.status_box=box();self.status_box.add_css_class('status');self.status_box.append(self.status)
  row=box(Gtk.Orientation.HORIZONTAL);self.cancel_button=button('Cancel job',lambda:self.cancel.set());self.cancel_button.set_visible(False)
  self.continue_button=button('Use results for another action',self.continue_results);self.continue_button.set_visible(False);row.append(self.continue_button)
  self.open_button=button('Show results',self.open_results);self.open_button.set_visible(False);row.append(self.cancel_button);row.append(self.open_button);self.status_box.append(row)
  self.run_button=Gtk.Button();self.action_label=Gtk.Label()
  self.software_help=button('Check features & get missing software…',self.show_software,'primary');self.software_help.set_visible(False);self.status_box.append(self.software_help)

 def do_startup(self):
  Gtk.Application.do_startup(self);self.hold();self.init_feedback()
  gtk_settings=Gtk.Settings.get_default();self.desktop_appearance=None
  schemas=Gio.SettingsSchemaSource.get_default();schema=schemas.lookup('org.gnome.desktop.interface',True) if schemas else None
  if schema and schema.has_key('color-scheme'):
   self.desktop_appearance=Gio.Settings.new_full(schema,None,None);self.desktop_appearance.connect('changed::color-scheme',self.system_appearance_changed)
  gtk_settings.connect('notify::gtk-application-prefer-dark-theme',self.system_appearance_changed);gtk_settings.connect('notify::gtk-theme-name',self.system_appearance_changed)
  self.system_appearance_changed();self.apply_appearance(self.settings)
  if os.environ.get('PETAL_DISABLE_TRAY')!='1' and self.settings['tray_enabled']:
   from .tray import Tray
   try:self.tray=Tray(self)
   except GLib.Error as e:print('Tray:',e,flush=True)

 def do_command_line(self,cmd):
  args=cmd.get_arguments()[1:]
  if '--smoke-test' in args:
   self._skip_onboarding=True
   result=super().do_command_line(cmd)
   def structural_check():
    queue=[self.controls];has_wheel=False
    while queue:
     widget=queue.pop();has_wheel=has_wheel or widget is self.drawing;child=widget.get_first_child()
     while child:queue.append(child);child=child.get_next_sibling()
    result={'standalone_overlay':isinstance(self.main.get_child(),Gtk.DrawingArea),'settings_contains_wheel':has_wheel,'overlay_size':[self.main.get_width(),self.main.get_height()],'tray_disabled_for_isolated_test':os.environ.get('PETAL_DISABLE_TRAY')=='1'}
    self.state.mkdir(parents=True,exist_ok=True);(self.state/'design-checks.json').write_text(json.dumps(result,indent=2)+'\n');return False
   GLib.timeout_add(1500,structural_check);return result
  if '--quit' in args:self.request_quit();return 0
  if '--software' in args:self.show_software();return 0
  if '--setup' in args:self.show_setup(['--settings']);return 0
  if not self.settings['setup_completed'] and not self._skip_onboarding:self.show_setup(args);return 0
  return self.activate_request(args)

 def activate_request(self,args):
  if '--drop-target' in args:self.set_drop_enabled(True);self.show_drop_target()
  elif '--settings' in args or '--app' in args:self.show_settings()
  elif '--shelf' in args:self.show_shelf()
  elif '--tray' not in args:
   files=[Path(a).resolve() for a in args if not a.startswith('--') and Path(a).exists()]
   if files:self.set_files(files)
   self.show_main()
  if not self.started:
   self.started=True
   if self.settings['drop_target']:self.show_drop_target()
  return 0

 def current_items(self):
  if self.paths:return choices(self.paths,self.mode)
  if self.mode=='convert':return [Action('to:'+s,s.upper()) for s in ['jpg','webp','heic','tiff','avif','bmp','pdf','docx']]
  return choices([Path('example.png')],self.mode)
 def page_capacity(self):
  return 7 if self.mode=='tools' and len(self.paths)<=1 and (not self.paths or kind(self.paths[0]) in ('image','audio')) else 8
 def page_items(self):
  capacity=self.page_capacity();return self.current_items()[self.page*capacity:(self.page+1)*capacity]
 def refresh(self):
  self.page=min(self.page,max(0,(len(self.current_items())-1)//self.page_capacity()));self.selected=min(self.selected,len(self.page_items())-1)
  self.petal_values={};self.petal_target={};self.petal_from={};self.petal_started={}
  if self.main:self.drawing.queue_draw()
  self.refresh_thumbnail()
  if self.files_summary:self.files_summary.set_text(', '.join(p.name for p in self.paths[:4]) or 'No files selected.')
 def update_hint(self):
  # Called whenever the highlighted petal changes (hover, keys, dropdown).
  if self.main:
   self.set_petal_hover(self.selected);self.drawing.queue_draw()
   items=self.page_items();hint=items[self.selected].hint if 0<=self.selected<len(items) else 'Choose a file or drop it on a leaf. Right-click for an accessible list of actions.'
   if not self.paths:hint='Select or drag a file. Click the center to browse.'
   elif 0<=self.selected<len(items):hint=items[self.selected].label+'. '+hint
   if len(self.current_items())>self.page_capacity():hint+=' Scroll or Page Up / Down for more choices.'
   self.drawing.set_tooltip_text(hint)
   self.drawing.update_property([Gtk.AccessibleProperty.LABEL,Gtk.AccessibleProperty.DESCRIPTION],['Petal file conversion wheel',hint+' Arrow keys select, Enter applies, Shift+F10 opens the action menu.'])
 def set_petal_hover(self,index):
  if not self.visual_preferences.get('animations',True) or not Gtk.Settings.get_default().get_property('gtk-enable-animations'):
   self.petal_values={index:1.0} if index>=0 else {};self.petal_target={};return
  now=GLib.get_monotonic_time()/1e6
  touched=set(self.petal_target)|set(self.petal_values)
  if index>=0:touched.add(index)
  for i in touched:
   self.petal_from[i]=self.petal_values.get(i,0.0);self.petal_started[i]=now
   self.petal_target[i]=1.0 if i==index else 0.0
  if self.petal_anim is None:self.petal_anim=GLib.timeout_add(16,self.petal_tick)
 def petal_tick(self):
  now=GLib.get_monotonic_time()/1e6;running=False
  for i in list(self.petal_target):
   target=self.petal_target[i];start=self.petal_from.get(i,0.0);t=(now-self.petal_started.get(i,now))/self.petal_duration
   if t>=1:value=target
   else:value=start+(target-start)*(1-(1-t)**3);running=True
   self.petal_values[i]=value
  for i in [k for k,v in self.petal_values.items() if v<.001 and self.petal_target.get(k,0.0)==0]:del self.petal_values[i]
  if self.main:self.drawing.queue_draw()
  self.petal_anim=None if not running else self.petal_anim
  return running
 def leave_wheel(self):
  if self.selected!=-1:self.selected=-1;self.update_hint()
 def hover(self,x,y):
  value=wheel.hit(x,y,self.drawing.get_width(),self.drawing.get_height(),len(self.page_items()),self.selected,self.petal_values)
  if value!=self.selected:self.selected=value;self.update_hint()
 def change_page(self,delta):
  count=max(1,(len(self.current_items())+self.page_capacity()-1)//self.page_capacity())
  self.page=(self.page+delta)%count;self.selected=-1;self.refresh();self.update_hint()
 def key_pressed(self,controller,key,keycode,state):
  if key==Gdk.KEY_Escape and getattr(self,'wheel_menu',None) and self.wheel_menu.get_visible():self.wheel_menu.popdown();return True
  if key==Gdk.KEY_Menu or (key==Gdk.KEY_F10 and state&Gdk.ModifierType.SHIFT_MASK):self.show_wheel_menu();return True
  if key==Gdk.KEY_o and state&Gdk.ModifierType.CONTROL_MASK:self.choose_files();return True
  if key in (Gdk.KEY_Page_Up,Gdk.KEY_Page_Down):self.change_page(-1 if key==Gdk.KEY_Page_Up else 1);return True
  modes={Gdk.KEY_Shift_L:'convert',Gdk.KEY_Shift_R:'convert',Gdk.KEY_Alt_L:'tools',Gdk.KEY_Alt_R:'tools',Gdk.KEY_Control_L:'actions',Gdk.KEY_Control_R:'actions'}
  if key in modes:
   if self.mode!=modes[key]:self.switch_mode(modes[key])
   return True
  return super().key_pressed(controller,key,keycode,state)
 def observe_modifiers(self,state):
  mask=Gdk.ModifierType.SHIFT_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.CONTROL_MASK
  current=state&mask;pressed=current&~self._mode_modifiers;self._mode_modifiers=current
  mode='actions' if pressed&Gdk.ModifierType.CONTROL_MASK else 'tools' if pressed&Gdk.ModifierType.ALT_MASK else 'convert' if pressed&Gdk.ModifierType.SHIFT_MASK else None
  if mode and self.mode!=mode:self.switch_mode(mode)
  return False
 def wheel_motion(self,controller,x,y):
  self.observe_modifiers(controller.get_current_event_state());self.hover(x,y)
 def drag_motion(self,target,x,y):
  if self.busy:return Gdk.DragAction(0)
  self.observe_modifiers(target.get_current_event_state());self.hover(x,y);return Gdk.DragAction.COPY
 def switch_mode(self,mode):self.mode=mode;self.page=0;self.selected=-1;self.petal_values={};self.petal_target={};self.refresh()
 def show_empty_feedback(self):
  now=GLib.get_monotonic_time()/1e6
  self.empty_notice_until=now+2.2;self.empty_shake_started=now;self.empty_shake_index=self.selected
  self.status.set_text('Select or drag a file.');self.update_hint()
  if self.empty_feedback_timer is None:self.empty_feedback_timer=GLib.timeout_add(16,self.empty_feedback_tick)
 def empty_feedback_tick(self):
  running=not self.paths and GLib.get_monotonic_time()/1e6<self.empty_notice_until
  if self.main:self.drawing.queue_draw()
  if not running:self.empty_notice_until=0;self.empty_shake_index=-1;self.empty_feedback_timer=None
  return running
 def empty_shake_offset(self,now):
  elapsed=now-self.empty_shake_started
  animated=self.visual_preferences.get('animations',True) and Gtk.Settings.get_default().get_property('gtk-enable-animations')
  return 5*math.sin(elapsed*math.tau*8)*(1-elapsed/.45) if animated and 0<=elapsed<.45 else 0
 def draw_wheel(self,area,c,w,h):
  size=sum(p.stat().st_size for p in self.paths if p.is_file())
  center=(f'{size/1024**2:.1f} MB' if size>=1024**2 else f'{size/1024:.0f} KB') if self.paths else 'Choose file'
  pages=(len(self.current_items())+self.page_capacity()-1)//self.page_capacity()
  now=GLib.get_monotonic_time()/1e6
  notice='Select or drag a file' if not self.paths and now<self.empty_notice_until else ''
  wheel.draw(c,w,h,self.page_items(),self.selected,center,mode=self.mode,expansions=self.petal_values,page_text=f'{self.page+1} / {pages}' if pages>1 else '',thumbnail=self.thumbnail,subtitle=notice,petal_offsets={self.empty_shake_index:self.empty_shake_offset(now)} if notice else {})
 def build_main(self):
  self.main=self.window('Petal · conversion overlay',True,360,360,namespace='petal-wheel');self.main.add_css_class('wheel-surface');self.main.set_decorated(False);self.main.set_resizable(False)
  self.drawing=Gtk.DrawingArea();self.drawing.set_focusable(True);self.drawing.set_content_width(360);self.drawing.set_content_height(360);self.drawing.set_draw_func(self.draw_wheel);self.main.set_child(self.drawing)
  motion=Gtk.EventControllerMotion();motion.connect('motion',self.wheel_motion);motion.connect('leave',lambda *_:self.leave_wheel());self.drawing.add_controller(motion)
  click=Gtk.GestureClick();click.set_button(Gdk.BUTTON_PRIMARY);click.connect('released',lambda _,n,x,y:self.click_wheel(x,y));self.drawing.add_controller(click)
  context=Gtk.GestureClick();context.set_button(Gdk.BUTTON_SECONDARY);context.connect('released',lambda *_:self.show_wheel_menu());self.drawing.add_controller(context)
  target=Gtk.DropTarget.new(Gdk.FileList,Gdk.DragAction.COPY);target.set_preload(True)
  target.connect('notify::value',self.preload);target.connect('enter',self.drag_motion);target.connect('motion',self.drag_motion);target.connect('leave',self.drag_leave);target.connect('drop',self.on_drop)
  self.drawing.add_controller(target);self.drop_controller=target;self.before_drag=None
  keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE);keys.connect('key-pressed',self.key_pressed);keys.connect('modifiers',lambda _,state:self.observe_modifiers(state));self.main.add_controller(keys);self.wheel_keys=keys
  scroll=Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL|Gtk.EventControllerScrollFlags.DISCRETE)
  scroll.connect('scroll',lambda _,dx,dy:(self.change_page(1 if dy>0 else -1),True)[1]);self.drawing.add_controller(scroll)
  self.main.connect('realize',self.shape_input);self.main.connect('notify::visible',self.wheel_visibility_changed);self.update_hint()
 def shape_input(self,*_):
  # Transparent corners don't intercept a file intended for the desktop below.
  surface=self.main.get_surface()
  if surface:
   region=cairo.Region();cx,cy,r,_=wheel.geometry(360,360);r=min(r*1.14,min(cx,cy))
   for y in range(int(cy-r),int(cy+r)+1):
    half=math.sqrt(max(0,r*r-(y-cy)**2));region.union(cairo.RectangleInt(int(cx-half),y,max(1,int(half*2)),1))
   surface.set_input_region(region)
 def wheel_visibility_changed(self,*_):
  visible=self.main.get_visible()
  if Layer and Layer.is_layer_window(self.main):
   Layer.set_keyboard_mode(self.main,(Layer.KeyboardMode.EXCLUSIVE if self._wheel_focus else Layer.KeyboardMode.ON_DEMAND) if visible else Layer.KeyboardMode.NONE)
  if visible and self._wheel_focus:self.drawing.grab_focus()
  elif not visible:self._mode_modifiers=Gdk.ModifierType(0)
 def show_main(self,focus=True):
  if self.setup_wizard and not self.setup_wizard.closed:self.setup_wizard.window.present();return
  if self.main is None:self.build_main()
  self._wheel_focus=focus;self.position_overlay();self.wheel_visibility_changed();self.main.present();self.wheel_visibility_changed()
 def position_overlay(self):
  if not Layer or not Layer.is_layer_window(self.main):return
  try:
   cursor=json.loads(subprocess.check_output(['mmsg','get','cursorpos'],timeout=.6,text=True))
   monitors=json.loads(subprocess.check_output(['mmsg','get','all-monitors'],timeout=.6,text=True)).get('monitors',[])
   cursor=cursor.get('cursor',cursor)
   monitor=next(m for m in monitors if m['name']==cursor.get('monitor'))
   model=Gdk.Display.get_default().get_monitors()
   for i in range(model.get_n_items()):
    display=model.get_item(i)
    if display.get_connector()==monitor['name']:Layer.set_monitor(self.main,display);break
   x=max(0,min(float(cursor['x'])-monitor['x']-180,monitor['width']-360));y=max(0,min(float(cursor['y'])-monitor['y']-180,monitor['height']-360))
   for edge in [Layer.Edge.RIGHT,Layer.Edge.BOTTOM]:Layer.set_anchor(self.main,edge,False)
   Layer.set_anchor(self.main,Layer.Edge.LEFT,True);Layer.set_anchor(self.main,Layer.Edge.TOP,True)
   Layer.set_margin(self.main,Layer.Edge.LEFT,int(x));Layer.set_margin(self.main,Layer.Edge.TOP,int(y))
  except (OSError,ValueError,KeyError,StopIteration,subprocess.SubprocessError):pass
 def click_wheel(self,x,y):
  self._wheel_focus=True;self.wheel_visibility_changed()
  cx,cy,r,inner=wheel.geometry(360,360)
  if math.hypot(x-cx,y-cy)<inner:self.choose_files();return
  self.hover(x,y);self.run_selected()
 def run_selected(self):
  if self.busy:
   if self.progress_window:self.progress_window.present()
   return
  if not self.paths:
   self.show_empty_feedback();return
  items=self.page_items()
  if not 0<=self.selected<len(items):self.status.set_text('Choose a format or tool first.');return
  action=items[self.selected]
  if self.mode=='actions':self.file_action(action.id)
  else:self.tool_options(action)
 def choose_files(self):
  if self.choosers:return
  def chosen(files):
   self.set_files(files);self.selected=-1;self.empty_notice_until=0;self.show_main();self.update_hint()
  self.file_dialog(chosen)
 def show_wheel_menu(self):
  if getattr(self,'wheel_menu',None):self.wheel_menu.popdown();self.wheel_menu.unparent()
  popup=Gtk.Popover();popup.set_parent(self.drawing);self.wheel_menu=popup;panel=box(spacing=5)
  panel.set_margin_top(10);panel.set_margin_bottom(10);panel.set_margin_start(10);panel.set_margin_end(10)
  def invoke(fn):popup.popdown();fn()
  panel.append(button('Choose files…',lambda:invoke(self.choose_files)))
  for mode,title in [('convert','Formats'),('tools','Tools'),('actions','File actions')]:
   panel.append(button(title,lambda m=mode:invoke(lambda:self.switch_mode(m))))
  panel.append(Gtk.Separator())
  for index,item in enumerate(self.page_items()):
   def activate(i=index):self.selected=i;self.update_hint();self.run_selected()
   panel.append(button(item.label,lambda fn=activate:invoke(fn)))
  popup.set_child(panel);popup.popup()
 def refresh_thumbnail(self):
  source=self.paths[0] if self.paths and kind(self.paths[0])=='image' else None
  try:key=(str(source),source.stat().st_mtime_ns) if source else None
  except OSError:key=None
  if key==self.thumbnail_key:return
  self.thumbnail_key=key;self.thumbnail=None
  if not key:
   self.thumbnail_preview.stop();self.thumbnail_preview=AsyncPreview();return
  def worker(stage,runner):
   out=stage/'thumbnail.png'
   try:scaled_source(source,out,128)
   except Exception:runner.run([dependencies()['ImageMagick'],str(source)+'[0]','-auto-orient','-thumbnail','128x128',out])
   return out.read_bytes()
  def done(data,error):
   if not error and key==self.thumbnail_key:
    import io
    self.thumbnail=cairo.ImageSurface.create_from_png(io.BytesIO(data))
    if self.main:self.drawing.queue_draw()
  self.thumbnail_preview.submit(worker,done)
 def tool_options(self,action):
  if self.busy:return
  editor=Editor(self,action);self.editors.append(editor)
  if self.main:self.main.set_visible(False)
 def start_job(self,action,params):
  if not self.paths or self.busy:return
  super().start_job(action,params)
  if self.main:self.main.set_visible(False)
  self.show_progress(action)
 def continue_results(self):
  if self.busy or not self.last_outputs:return
  if self.progress_window:self.progress_window.set_visible(False)
  self.set_files(self.last_outputs);self.mode='tools';self.page=0;self.selected=-1;self.refresh();self.update_hint();self.show_main()
 def show_progress(self,action):
  if self.progress_window:self.progress_window.destroy()
  self.progress_window=self.window('Petal · conversion',False,420,155);w=self.progress_window;w.add_css_class('tool-window');w.set_decorated(False);w.set_resizable(False)
  panel=box(spacing=12);panel.add_css_class('material-shell');panel.set_margin_top(8);panel.set_margin_bottom(8);panel.set_margin_start(8);panel.set_margin_end(8);w.set_child(panel)
  body=box(spacing=12);body.add_css_class('tool-body');panel.append(body);row=box(Gtk.Orientation.HORIZONTAL,12);body.append(row)
  row.append(button('×',lambda:(self.cancel.set(),w.set_visible(False)),'close-circle'))
  title=('Converting to '+action[3:].upper()) if action.startswith('to:') else next((a.label for a in self.current_items() if a.id==action),'Creating copy')
  self.progress_title=label(title,'tool-title');row.append(self.progress_title);self.progress_file=label(self.paths[0].name+(f' + {len(self.paths)-1} more' if len(self.paths)>1 else ''),'field-name');self.progress_file.set_ellipsize(3);body.append(self.progress_file)
  self.progress_bar=Gtk.ProgressBar();body.append(self.progress_bar)
  self.progress_actions=box(Gtk.Orientation.HORIZONTAL);self.progress_actions.append(button('Open results',self.open_results));self.progress_actions.append(button('Edit result',self.continue_results,'primary'));self.progress_actions.append(button('Done',lambda:w.set_visible(False)));self.progress_actions.set_visible(False);body.append(self.progress_actions)
  def pulse():
   if not self.busy:self.progress_timer=None;return False
   self.progress_bar.pulse();return True
  if self.progress_timer:GLib.source_remove(self.progress_timer)
  self.progress_timer=GLib.timeout_add(100,pulse);w.present()
 def finish_job(self,*args):
  result=super().finish_job(*args)
  self.continue_button.set_visible(not args[3] and bool(self.last_outputs))
  self.software_help.set_visible(bool(args[3]) and any(word in str(args[3]).lower() for word in ('not installed','unavailable','needs','codec','encoder','delegate','convert')))
  if self.progress_window:
   if args[3]:self.progress_window.set_visible(False)
   else:
    self.progress_bar.set_fraction(1);self.progress_title.set_text('Copy saved')
    self.progress_actions.set_visible(True)
  if args[3]:self.show_activity()
  if args[3] and self.settings.get('notify'):
   n=Gio.Notification.new('Petal · conversion needs attention');n.set_body(str(args[3])[:200]);self.send_notification('job',n)
  return result

 def show_drop_target(self):
  if self.drop_window:self.drop_window.present();return
  w=self.window('Petal drop target',True,44,44,namespace='petal-drop-target');self.drop_window=w;w.set_resizable(False)
  if Layer and Layer.is_layer_window(w):
   Layer.set_anchor(w,Layer.Edge.RIGHT,True);Layer.set_anchor(w,Layer.Edge.BOTTOM,True);Layer.set_margin(w,Layer.Edge.RIGHT,22);Layer.set_margin(w,Layer.Edge.BOTTOM,90);Layer.set_keyboard_mode(w,Layer.KeyboardMode.NONE)
  target_button=button('↓',self.show_main,'drop');target_button.set_tooltip_text('Drag files here to reveal the conversion overlay');w.set_child(target_button)
  target=Gtk.DropTarget.new(Gdk.FileList,Gdk.DragAction.COPY);target.set_preload(True)
  def preload(t,*_):
   value=t.get_value()
   if value and not self.busy:
    paths=[Path(f.get_path()) for f in value.get_files() if f.get_path()]
    if paths:self.set_files(paths);self.show_main(focus=False)
  def drop(t,value,x,y):preload(t);return bool(self.paths)
  target.connect('notify::value',preload);target.connect('drop',drop);target_button.add_controller(target);w.present()

 def system_appearance_changed(self,*_):
  gtk=Gtk.Settings.get_default();self.system_dark=bool(gtk.get_property('gtk-application-prefer-dark-theme')) or 'dark' in str(gtk.get_property('gtk-theme-name')).lower()
  if self.desktop_appearance:
   preference=self.desktop_appearance.get_string('color-scheme')
   if preference in ('prefer-dark','prefer-light'):self.system_dark=preference=='prefer-dark'
  if getattr(self,'visual_preferences',{}).get('appearance_mode')=='system':self.apply_appearance(self.visual_preferences)
 def apply_appearance(self,settings):
  self.visual_preferences=normalize(settings);appearance.apply_wheel(self.visual_preferences)
  if self._appearance_provider:Gtk.StyleContext.remove_provider_for_display(Gdk.Display.get_default(),self._appearance_provider)
  provider=Gtk.CssProvider();provider.load_from_string(appearance.stylesheet(CSS,self.visual_preferences,getattr(self,'system_dark',False)))
  Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION);self._appearance_provider=provider
  if self.main:self.drawing.queue_draw()
 def show_setup(self,args=None):
  if args is not None:self.setup_requests.append(list(args))
  if self.setup_wizard and not self.setup_wizard.closed:self.setup_wizard.window.present();return
  self.setup_wizard=SetupWizard(self)
 def complete_setup(self,settings):
  previous=self.settings;self.settings=settings
  try:self.save_settings()
  except OSError:self.settings=previous;raise
  configure_engines(settings)
  self.apply_appearance(settings)
  if self.controls:
   parent=self.status_box.get_parent()
   if parent:parent.remove(self.status_box)
   self.controls.destroy();self.controls=None;self.settings_window=None;self.files_summary=None;self.section_stack=None
  self.sync_surfaces()
  requests=self.setup_requests;self.setup_requests=[];self.setup_wizard=None
  for args in requests:self.activate_request(args)
 def sync_surfaces(self):
  if self.settings.get('drop_target') and self.started:self.show_drop_target()
  elif not self.settings.get('drop_target') and self.drop_window:self.drop_window.destroy();self.drop_window=None
  if os.environ.get('PETAL_DISABLE_TRAY')!='1':
   if self.settings.get('tray_enabled') and self.tray is None:
    from .tray import Tray
    try:self.tray=Tray(self)
    except GLib.Error as e:print('Tray:',e,flush=True)
   elif not self.settings.get('tray_enabled') and self.tray:self.tray.close();self.tray=None
  if self.tray:self.tray.update()
 def show_activity(self):
  self.show_settings()
  if self.section_stack:self.select_section('Activity')
 def show_software(self):
  if self.software_window:self.software_window.window.present();return
  from .software import SoftwareWindow
  self.software_window=SoftwareWindow(self)
 def launch_preferred(self,role,paths):
  try:integrations.launch(self.settings,role,paths,Gdk.Display.get_default().get_app_launch_context());return True
  except Exception as e:self.status.set_text(str(e));self.show_activity();return False
 def open_results(self):
  if self.last_outputs:self.launch_preferred('file_manager',[self.last_outputs[0].parent])
 def open_selected(self):
  if not self.paths:self.choose_files();return
  try:integrations.open_files(self.settings,self.paths,Gdk.Display.get_default().get_app_launch_context())
  except Exception as e:self.status.set_text(str(e));self.show_activity()
 def file_action(self,action):
  if action=='terminal':self.launch_preferred('terminal_app',self.paths);return
  if action=='share':self.launch_preferred('sharing_app',self.paths);return
  if action=='open':self.open_selected();return
  super().file_action(action)
  if action in ('copy','copy_path'):self.show_activity()
 def request_quit(self):
  if self.busy:self.show_activity();self.status.set_text('A conversion is running. Cancel it first, then choose Quit again.');return
  if self.setup_wizard:self.setup_wizard.cancel()
  if self.software_window:self.software_window.close()
  for editor in list(self.editors):editor.close()
  self.thumbnail_preview.stop()
  super().request_quit()
 def show_settings(self):
  if not self.settings['setup_completed'] and not self._skip_onboarding:self.show_setup(['--settings']);return
  if self.controls is None:self.build_controls()
  if self.main:self.main.set_visible(False)
  self.refresh_engine_status()
  self.controls.present()
 def show_shelf(self):
  if self.main:self.main.set_visible(False)
  return super().show_shelf()
 def refresh_engine_status(self):
  if not self.controls or not hasattr(self,'engine_status'):return
  child=self.engine_status.get_first_child()
  while child:next_child=child.get_next_sibling();self.engine_status.remove(child);child=next_child
  for name,path in dependencies().items():self.engine_status.append(label(name+(' · found' if path else ' · not found'),'muted'))
  self.office_path_label.set_text(self.settings.get('libreoffice_path') or 'Office engine: search installed applications')
  for picker in self.preference_pages.pickers.values():picker.refresh_apps()
 def setting(self,key,value):
  super().setting(key,value)
  if key in ('libreoffice_path','engine_paths'):configure_engines(self.settings)
  if key in ('accent_color','petal_color','text_color','petal_opacity','appearance_mode','animations'):self.apply_appearance(self.settings)
  if key in ('tray_enabled','drop_target'):self.sync_surfaces()
 def section(self,title):
  b=box(spacing=18);b.add_css_class('settings-body');b.append(label(title,'title'));return b
 def setting_row(self,parent,title,description,key):
  row=box(Gtk.Orientation.HORIZONTAL,16);words=box(spacing=5);words.set_hexpand(True);words.append(label(title));words.append(label(description,'muted',True));row.append(words)
  toggle=Gtk.Switch(active=bool(self.settings.get(key)));toggle.set_valign(Gtk.Align.START)
  toggle.connect('notify::active',lambda s,*_:self.set_drop_enabled(s.get_active()) if key=='drop_target' else self.setting(key,s.get_active()));row.append(toggle);parent.append(row)
 def build_controls(self):
  self.controls=self.window('Petal · Settings',True,700,510,namespace='petal-settings');self.settings_window=self.controls
  shell=box(Gtk.Orientation.HORIZONTAL,0);self.controls.set_child(shell);sidebar=box(spacing=7);sidebar.add_css_class('sidebar');sidebar.set_size_request(166,-1)
  sidebar.append(label('Petal','title'));sidebar.append(label('for Linux','muted'));sidebar.append(Gtk.Separator());shell.append(sidebar)
  stack=Gtk.Stack();stack.set_hexpand(True);self.section_stack=stack;shell.append(stack)
  general=self.section('General');general.append(label('Keep the app in the tray; convert from the desktop.','muted',True))
  self.setting_row(general,'Show in system tray','Right-click the tray icon to open these settings.','tray_enabled')
  self.setting_row(general,'Floating drop target','Hover files here to reveal the separate overlay.','drop_target')
  self.setting_row(general,'Completion notifications','Notify when converted copies are ready.','notify')
  general.append(label('Save converted files'));output=label(self.settings.get('output_dir') or 'Beside the original file','muted',True);general.append(output)
  def chosen(paths):self.setting('output_dir',str(paths[0]));output.set_text(str(paths[0]))
  output_buttons=box(Gtk.Orientation.HORIZONTAL)
  output_buttons.append(button('Choose output folder…',lambda:self.file_dialog(chosen,folder=True)))
  def reset_output():self.setting('output_dir','');output.set_text('Beside the original file')
  output_buttons.append(button('Reset',reset_output));general.append(output_buttons)
  general.append(button('Run setup again…',lambda:self.show_setup(['--settings'])))
  preferences=PreferencePages(self,self.controls,self.settings,self.setting);self.preference_pages=preferences
  applications=self.section('Applications');applications.append(preferences.applications())
  look=self.section('Appearance');look.append(preferences.appearance())
  shortcuts=self.section('Shortcuts');shortcuts.append(label('Super + Shift + C (optional)','orange'));shortcuts.append(label('Use the included example to add a compositor binding. Petal does not change your shortcuts.','muted',True));shortcuts.append(Gtk.Separator())
  for s in ['Shift — conversions','Alt — file tools','Control — file actions','Escape — dismiss overlay','Arrow keys + Enter — choose and apply','Scroll or Page Up / Down — more petals']:shortcuts.append(label(s))
  shortcuts.append(label('Mode keys apply while the overlay has focus. Global drag-anywhere Shift detection still needs compositor support.','muted',True))
  conversions=self.section('Conversions')
  conversions.append(button('Check features & get missing software…',self.show_software,'primary'))
  for key,title,lo,hi in [('quality','Image quality',1,100),('dpi','PDF image DPI',36,600)]:
   row=box(Gtk.Orientation.HORIZONTAL);l=label(title);l.set_hexpand(True);row.append(l);spin=Gtk.SpinButton.new_with_range(lo,hi,1);spin.set_value(self.settings[key]);spin.connect('value-changed',lambda s,k=key:self.setting(k,s.get_value_as_int()));row.append(spin);conversions.append(row)
  self.engine_status=box(spacing=6);conversions.append(self.engine_status)
  self.office_path_label=label(self.settings.get('libreoffice_path') or 'Office engine: search installed applications','muted',True);conversions.append(self.office_path_label)
  conversions.append(button('Check an existing office program…',self.show_software))
  conversions.append(label('Check features to test exports and choose missing software. Downloads start only after you approve the installation. PDF to DOCX, EPUB, and MD exports text only; scanned pages need OCR.','muted',True))
  activity=self.section('Activity');activity.append(self.status_box);self.files_summary=label('No files selected.','muted',True);activity.append(self.files_summary);activity.append(button('Choose files for the overlay…',self.choose_files));activity.append(button('File shelf',self.show_shelf));activity.append(button('Open selected files',self.open_selected))
  about=self.section('About');about.append(label('Petal '+__version__));about.append(label('An unofficial Linux port/reimplementation of Tangerine for macOS. Independently written for Wayland.','muted',True));about.append(Gtk.LinkButton.new_with_label('https://tangerineformac.com/','Original project: Tangerine'));about.append(label('No uploads. No accounts. Original files are preserved.','muted',True));about.append(label('Borderless petals expand on hover. Settings and activity remain separate from the desktop wheel.','muted',True))
  about.append(label('Apple-only formats and AirDrop need alternatives. Export standard formats from the original app and choose your sharing app in Settings. The app uses the shortcut and floating target on Wayland; it does not modify your compositor configuration.','muted',True))
  buttons=[]
  def select(name):
   stack.set_visible_child_name(name)
   for n,b in buttons:b.set_active(n==name)
  self.select_section=select
  for name,page in [('General',general),('Applications',applications),('Appearance',look),('Shortcuts',shortcuts),('Conversions',conversions),('Activity',activity),('About',about)]:
   scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);scroll.set_child(page);stack.add_named(scroll,name)
   b=Gtk.ToggleButton(label=name);b.connect('clicked',lambda _,n=name:select(n));sidebar.append(b);buttons.append((name,b))
  spacer=Gtk.Box();spacer.set_vexpand(True);sidebar.append(spacer);sidebar.append(button('Close',lambda:self.controls.set_visible(False),'flat'));select('General');self.refresh()

def main(args):
 if not Gtk.init_check() or Gdk.Display.get_default() is None:
  print('Cannot connect to the desktop session. Run this launcher in your Wayland session.',flush=True);return 1
 return Petal().run(['petal',*args])
