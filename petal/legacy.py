import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import gi
gi.require_version('Gtk','4.0')
gi.require_version('Gdk','4.0')
from gi.repository import Gtk,Gdk,Gio,GLib
try:
 gi.require_version('Gtk4LayerShell','1.0')
 from gi.repository import Gtk4LayerShell as Layer
except (ImportError,ValueError):Layer=None

from .catalog import choices,dependencies,kind,ACTIONS
from .engine import execute,ConversionError,Cancelled
from . import wheel

CSS='''
window {background: #151a15; color: #f1eee5; font-family: sans-serif;}
window.layer {background: transparent;}
.panel {background: #151a15; border: 1px solid #353d31; border-radius: 24px; padding: 24px;}
.title {font-size: 28px; font-weight: 700; letter-spacing: -1px;}
.muted {color: #9ba291; font-size: 12px;}
.orange {color: #ff8b55;}
button {background: #252d23; color: #e7eadf; border: 1px solid #3a4336; border-radius: 10px; padding: 9px 13px; box-shadow:none;}
button:hover {background:#35402f;}
button:checked,button.primary {background:#ff8a54; color:#192116; border-color:#ff8a54;}
button.flat {background:transparent;border-color:transparent;}
entry, dropdown {background:#20271e; color:#f1eee5; border:1px solid #394333; border-radius:8px; padding:8px;}
.status {background:#20271e;border:1px solid #343f2e;border-radius:12px;padding:12px;}
.error {color:#ffb49c;}
.success {color:#b8d69c;}
.drop {background:#202a1c;border:1px solid #ff9b68;border-radius:18px;padding:12px;}
separator {background:#343c30;min-height:1px;}
'''

FIELDS={
 'blur':[('radius','Blur radius (pixels)','4')],
 'sharpen':[('amount','Sharpness (0–5)','1')],
 'watermark':[('text','Watermark text','Petal'),('font_size','Text size','32'),('color','Text color','#ffffff'),('opacity','Opacity (0–100)','60'),('position','Position: center, top-left, bottom-right','bottom-right')],
 'border':[('width','Border width (pixels)','16'),('color','Border color','#ffffff')],
 'fade':[('fade_in','Fade in (seconds)','0.5'),('fade_out','Fade out (seconds)','0.5')],
 'pdf_remove':[('pages','Pages to remove','1')],
 'pdf_duplicate':[('pages','Pages to append again','1')],
 'compress':[('quality','Image quality (1–100)','82'),('crf','Video quality / CRF (0–51)','28'),('bitrate','Audio bitrate (kbps)','128')],
 'resize':[('width','Maximum width','1920'),('height','Maximum height','1080')],
 'crop':[('width','Width','400'),('height','Height','300'),('x','Left offset','0'),('y','Top offset','0')],
 'redact':[('width','Width','400'),('height','Height','300'),('x','Left offset','0'),('y','Top offset','0'),('start','Start time for video (seconds)','0'),('duration','Video duration (0 = whole clip)','0')],
 'rotate':[('degrees','Clockwise degrees','90')], 'pdf_rotate':[('degrees','Clockwise degrees (90 / 180 / 270)','90')],
 'flip':[('axis','Axis: horizontal or vertical','horizontal')],
 'edit':[('exposure','Exposure (-3 to 3 EV)','0'),('brightness','Brightness (-100 to 100)','0'),('contrast','Contrast (-100 to 100)','0'),('highlights','Highlights (-100 to 100)','0'),('shadows','Shadows (-100 to 100)','0'),('whites','Whites (-100 to 100)','0'),('blacks','Blacks (-100 to 100)','0'),('gamma','Gamma (0.2 to 3)','1'),('temperature','Temperature (-100 to 100)','0'),('tint','Tint (-100 to 100)','0'),('saturation','Saturation (-100 to 100)','0'),('vibrance','Vibrance (-100 to 100)','0'),('sharpness','Sharpness (0 to 200)','0'),('vignette','Vignette (0 to 100)','0')],
 'background':[('background','Background color or gradient (#aabbcc or #aa,#bb)','#f5f6f7'),('padding','Padding in px','64'),('corners','Corner radius in px','24'),('shadow','Shadow blur in px','30'),('ratio','Ratio: auto, 1:1, 16:9, 4:5','auto')],
 'annotate':[('text','Text (optional)',''),('font_size','Text size','32'),('color','Color (#rrggbb)','#ffffff'),('x','X','24'),('y','Y','24'),('shape','Shape: none, rectangle, ellipse, arrow','none'),('width','Shape width','400'),('height','Shape height','300'),('line_width','Line width','6'),('opacity','Opacity 0–100','60')],
 'trim':[('start','Start time (seconds)','0'),('duration','Duration (seconds)','10')],
 'speed':[('speed','Speed (0.5–2.0)','1.5')], 'volume':[('volume','Volume multiplier (0–10)','1.5')],
 'channels':[('mode','Mode: mono or stereo','stereo'),('left','Left level (0–4)','1'),('right','Right level (0–4)','1')],
 'visualizer':[('color','Waveform color (0xRRGGBB)','0xff6109')],
 'bleep':[('ranges','Mute ranges, such as 3-5,10-12','1-2')],
 'snapshots':[('count','Number of frames','6')],
 'video_split':[('seconds','Segment length in seconds','30')],
 'pdf_extract':[('pages','Pages, such as 1,3-5','1')], 'pdf_organize':[('pages','New page order, such as 3,1,2 or 2-4,1','1')],
 'shift_subtitles':[('offset','Shift in seconds (negative is earlier)','1')],
}

def label(s,css=None,wrap=False):
 w=Gtk.Label(label=s,xalign=0);w.set_wrap(wrap)
 if css:w.add_css_class(css)
 return w

def box(orientation=Gtk.Orientation.VERTICAL,spacing=12):return Gtk.Box(orientation=orientation,spacing=spacing)
def button(text,callback,css=None):
 b=Gtk.Button(label=text);b.connect('clicked',lambda *_:callback())
 if css:b.add_css_class(css)
 return b

def fit_size(width,height):
 display=Gdk.Display.get_default();monitors=display.get_monitors() if display else None
 if not monitors or not monitors.get_n_items():return width,height
 sizes=[monitors.get_item(i).get_geometry() for i in range(monitors.get_n_items())]
 return min(width,max(320,min(r.width for r in sizes)-48)),min(height,max(360,min(r.height for r in sizes)-72))

class LegacyApp(Gtk.Application):
 def __init__(self):
  super().__init__(application_id='io.github.petal.Files',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
  self.state=Path(os.environ.get('PETAL_STATE_DIR',str(Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'petal')))
  self.settings={'drop_target':True,'output_dir':'','quality':85,'dpi':150,'notify':True}
  try:
   saved=json.loads((self.state/'settings.json').read_text())
   if isinstance(saved,dict):self.settings.update(saved)
  except (OSError,ValueError):pass
  from .catalog import configure_engines
  configure_engines(self.settings)
  self.paths=[];self.shelf_paths=[];self.mode='convert';self.page=0;self.selected=-1;self.busy=False;self.cancel=threading.Event();self.last_outputs=[]
  self.main=None;self.drop_window=None;self.shelf=None;self.settings_window=None;self.tray=None;self.jobs=[];self.choosers=[];self.started=False

 def do_startup(self):
  Gtk.Application.do_startup(self);self.hold()
  css=Gtk.CssProvider();css.load_from_string(CSS);Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
  from .tray import Tray
  try:self.tray=Tray(self)
  except GLib.Error as e:print('Tray unavailable:',e,flush=True)

 def do_command_line(self,cmd):
  args=cmd.get_arguments()[1:]
  if '--quit' in args:self.request_quit();return 0
  if '--settings' in args:self.show_settings()
  elif '--drop-target' in args:
   self.settings['drop_target']=True;self.save_settings();self.show_drop_target()
  elif '--shelf' in args:self.show_shelf()
  elif '--tray' not in args:
   self.show_main()
   files=[Path(a).resolve() for a in args if not a.startswith('--') and Path(a).exists()]
   if files:self.set_files(files)
  if not self.started:
   self.started=True
   if self.settings['drop_target']:self.show_drop_target()
   print('Petal running. Right-click its system tray icon for Settings.',flush=True)
  if '--smoke-test' in args:
   self.show_main();fixture=os.environ.get('PETAL_TEST_FILE');checks={}
   if fixture:
    self.set_files([Path(fixture)]);checks['format_options']=bool(self.current_items())
    self.switch_mode('tools');checks['tool_options']=bool(self.current_items());self.selected=0;self.refresh()
    self.switch_mode('actions');checks['file_actions']=len(self.current_items())==len(ACTIONS)
    self.switch_mode('convert');self.shelf_paths=[Path(fixture)]
   self.show_shelf();self.show_settings()
   if fixture:
    # Exercise the shelf's content provider without touching the user's clipboard.
    stack=[self.shelf.get_child()];providers=[]
    while stack:
     widget=stack.pop();controllers=widget.observe_controllers()
     for i in range(controllers.get_n_items()):
      controller=controllers.get_item(i)
      if isinstance(controller,Gtk.DragSource):providers.append(controller.emit('prepare',0.,0.))
     child=widget.get_first_child()
     while child:stack.append(child);child=child.get_next_sibling()
    checks['shelf_drag_provider']=bool(providers) and all(p is not None for p in providers)
   def report():
    result={'main_visible':self.main.get_visible(),'main_size':[self.main.get_width(),self.main.get_height()],'settings_visible':self.settings_window.get_visible(),'shelf_visible':self.shelf.get_visible(),
     'wayland':Gdk.Display.get_default().__gtype__.name,'layer_shell':bool(Layer and Layer.is_layer_window(self.main)),
     'drop_target_visible':bool(self.drop_window and self.drop_window.get_visible()),'tray_registered':bool(self.tray and self.tray.registered),'tray_error':self.tray.error if self.tray else 'No tray',**checks}
    self.state.mkdir(parents=True,exist_ok=True);(self.state/'smoke-test.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True);self.request_quit();return False
   GLib.timeout_add(2200,report)
  return 0

 def save_settings(self):
  self.state.mkdir(parents=True,exist_ok=True)
  temp=self.state/'settings.tmp';temp.write_text(json.dumps(self.settings,indent=2)+'\n');temp.replace(self.state/'settings.json')

 def window(self,title,layer=False,width=660,height=740,namespace='petal-dialog'):
  if width>360 or height>360:width,height=fit_size(width,height)
  w=Gtk.ApplicationWindow(application=self,title=title);w.set_default_size(width,height)
  if layer and Layer and Layer.is_supported():
   Layer.init_for_window(w);Layer.set_namespace(w,namespace);Layer.set_layer(w,Layer.Layer.OVERLAY);Layer.set_exclusive_zone(w,-1);Layer.set_keyboard_mode(w,Layer.KeyboardMode.ON_DEMAND)
   w.add_css_class('layer');w.set_decorated(False)
  w.connect('close-request',lambda window:(window.set_visible(False),True)[1])
  return w

 def show_main(self):
  if self.main is None:self.build_main()
  self.main.present()

 def build_main(self):
  self.main=self.window('Petal · local file tools',True,650,760,namespace='petal-wheel')
  panel=box(spacing=13);panel.add_css_class('panel');self.main.set_child(panel)
  header=box(Gtk.Orientation.HORIZONTAL);left=box(spacing=2);left.set_hexpand(True)
  left.append(label('Petal','title'));left.append(label('A little less file busywork.','muted'));header.append(left)
  header.append(button('Settings',self.show_settings,'flat'));header.append(button('×',lambda:self.main.set_visible(False),'flat'));panel.append(header)
  row=box(Gtk.Orientation.HORIZONTAL,6);self.tabs={}
  for id,name in [('convert','⇧  Convert'),('tools','Alt  Tools'),('actions','Ctrl  Actions')]:
   b=Gtk.ToggleButton(label=name);b.set_hexpand(True);b.connect('clicked',lambda _,m=id:self.switch_mode(m));row.append(b);self.tabs[id]=b
  panel.append(row)
  self.file_label=label('Choose files, or drag them onto the wheel.','muted',True);panel.append(self.file_label)
  self.drawing=Gtk.DrawingArea();self.drawing.set_content_width(520);self.drawing.set_content_height(320);self.drawing.set_hexpand(True);self.drawing.set_vexpand(True);self.drawing.set_draw_func(self.draw_wheel);panel.append(self.drawing)
  motion=Gtk.EventControllerMotion();motion.connect('motion',lambda _,x,y:self.hover(x,y));motion.connect('leave',lambda *_:None);self.drawing.add_controller(motion)
  click=Gtk.GestureClick();click.connect('released',lambda _,n,x,y:self.click_wheel(x,y));self.drawing.add_controller(click)
  target=Gtk.DropTarget.new(Gdk.FileList,Gdk.DragAction.COPY);target.set_preload(True)
  target.connect('notify::value',self.preload);target.connect('motion',self.drag_motion);target.connect('enter',self.drag_motion);target.connect('drop',self.on_drop);target.connect('leave',self.drag_leave);self.drawing.add_controller(target)
  self.drop_controller=target;self.before_drag=None
  self.action_label=label('Everything stays on your computer.','orange');self.action_label.set_halign(Gtk.Align.CENTER);panel.append(self.action_label)
  self.pager=box(Gtk.Orientation.HORIZONTAL);self.pager.append(button('←',lambda:self.change_page(-1),'flat'));self.page_label=label('');self.page_label.set_hexpand(True);self.page_label.set_halign(Gtk.Align.CENTER);self.pager.append(self.page_label);self.pager.append(button('→',lambda:self.change_page(1),'flat'));panel.append(self.pager)
  controls=box(Gtk.Orientation.HORIZONTAL);controls.append(button('Choose files…',self.choose_files));controls.append(button('Clear',lambda:self.set_files([]),'flat'));controls.append(button('Shelf',self.show_shelf,'flat'))
  self.run_button=button('Run selected',self.run_selected,'primary');self.run_button.set_hexpand(True);controls.append(self.run_button);panel.append(controls)
  self.accessible=Gtk.DropDown.new_from_strings(['Choose a format']);self.accessible.set_tooltip_text('Accessible action picker; Enter or Run selected applies the choice.');self.accessible.connect('notify::selected',self.dropdown_changed);panel.append(self.accessible)
  self.status_box=box(spacing=7);self.status_box.add_css_class('status');self.status=label('Ready · originals are preserved.','muted',True);self.status.set_selectable(True);self.status_box.append(self.status)
  status_controls=box(Gtk.Orientation.HORIZONTAL);self.cancel_button=button('Cancel job',lambda:self.cancel.set());self.cancel_button.set_visible(False);status_controls.append(self.cancel_button)
  self.open_button=button('Show results',self.open_results);self.open_button.set_visible(False);status_controls.append(self.open_button);self.status_box.append(status_controls);panel.append(self.status_box)
  footer=label('OFFLINE  /  WAYLAND     ·     Escape hides · tray keeps running','muted');footer.set_halign(Gtk.Align.CENTER);panel.append(footer)
  keys=Gtk.EventControllerKey();keys.connect('key-pressed',self.key_pressed);self.main.add_controller(keys)
  self.refresh()

 def current_items(self):return choices(self.paths,self.mode)
 def page_items(self):return self.current_items()[self.page*8:self.page*8+8]
 def set_files(self,files):
  unique=[]
  for p in files:
   p=Path(p)
   if p.exists() and p not in unique:unique.append(p)
  self.paths=unique;self.page=0;self.selected=-1;self.refresh()
 def refresh(self):
  if not self.main:return
  items=self.current_items();self.page=min(self.page,max(0,(len(items)-1)//8));self.selected=min(self.selected,len(self.page_items())-1)
  for m,b in self.tabs.items():b.set_active(m==self.mode)
  if self.paths:
   text=', '.join(p.name for p in self.paths[:3])+ (f' + {len(self.paths)-3} more' if len(self.paths)>3 else '')
   self.file_label.set_text(text)
  else:self.file_label.set_text('Choose files, or drag them onto the wheel.')
  self.page_label.set_text(f'{self.page+1} / {max(1,(len(items)+7)//8)}');self.pager.set_visible(len(items)>8)
  self.updating_dropdown=True;self.accessible.set_model(Gtk.StringList.new([a.label for a in items] or ['Choose files first']));self.accessible.set_selected(Gtk.INVALID_LIST_POSITION);self.updating_dropdown=False
  self.run_button.set_sensitive(bool(self.paths) and bool(items) and not self.busy);self.drawing.queue_draw();self.update_hint()
 def draw_wheel(self,area,c,w,h):
  title=self.paths[0].name if len(self.paths)==1 else f'{len(self.paths)} files' if self.paths else 'Drop files here'
  subtitle=f'{kind(self.paths[0]).title()} · offline' if self.paths else 'or choose files below'
  wheel.draw(c,w,h,self.page_items(),self.selected,title,subtitle,self.mode)
 def hover(self,x,y):
  value=wheel.hit(x,y,self.drawing.get_width(),self.drawing.get_height(),len(self.page_items()))
  if value!=self.selected:self.selected=value;self.drawing.queue_draw();self.update_hint()
 def update_hint(self):
  items=self.page_items()
  self.action_label.set_text((('Convert to ' if self.mode=='convert' else '')+items[self.selected].label) if 0<=self.selected<len(items) else 'Drop on a segment, or pick an action below.')
 def click_wheel(self,x,y):self.hover(x,y);self.run_selected()
 def switch_mode(self,mode):
  if self.mode!=mode:self.mode=mode;self.page=0;self.selected=-1;self.refresh()
 def change_page(self,delta):
  count=max(1,(len(self.current_items())+7)//8);self.page=(self.page+delta)%count;self.selected=-1;self.refresh()
 def dropdown_changed(self,widget,*_):
  if getattr(self,'updating_dropdown',True):return
  i=widget.get_selected()
  if i<len(self.current_items()):self.page=i//8;self.selected=i%8;self.drawing.queue_draw();self.update_hint();self.page_label.set_text(f'{self.page+1} / {(len(self.current_items())+7)//8}')
 def preload(self,target,*_):
  value=target.get_value()
  if value and not self.busy:
   paths=[Path(f.get_path()) for f in value.get_files() if f.get_path()]
   if self.before_drag is None:self.before_drag=list(self.paths)
   self.set_files(paths)
 def drag_motion(self,target,x,y):
  if self.busy:return Gdk.DragAction(0)
  self.hover(x,y);return Gdk.DragAction.COPY
 def drag_leave(self,*_):
  if self.before_drag is not None:
   previous=self.before_drag;self.before_drag=None;self.set_files(previous)
 def on_drop(self,target,value,x,y):
  if self.busy:return False
  paths=[Path(f.get_path()) for f in value.get_files() if f.get_path()]
  if not paths:return False
  self.before_drag=None
  if paths!=self.paths:self.set_files(paths)
  self.hover(x,y);self.run_selected();return True
 def key_pressed(self,_,key,keycode,state):
  if key==Gdk.KEY_Escape:self.main.set_visible(False);return True
  if key in (Gdk.KEY_Shift_L,Gdk.KEY_Shift_R):self.switch_mode('convert');return True
  if key in (Gdk.KEY_Alt_L,Gdk.KEY_Alt_R):self.switch_mode('tools');return True
  if key in (Gdk.KEY_Control_L,Gdk.KEY_Control_R):self.switch_mode('actions');return True
  if key in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Up,Gdk.KEY_Down):
   n=len(self.page_items())
   if n:self.selected=(self.selected+(-1 if key in (Gdk.KEY_Left,Gdk.KEY_Up) else 1))%n;self.drawing.queue_draw();self.update_hint()
   return True
  if key==Gdk.KEY_Return:self.run_selected();return True
  return False

 def file_dialog(self,callback,folder=False,multiple=True,parent=None):
  parent=parent or self.main
  # Layer surfaces cannot be exported as standard Wayland portal parents.
  native_parent=None if parent and Layer and Layer.is_layer_window(parent) else parent
  dialog=Gtk.FileChooserNative.new('Choose a folder' if folder else 'Choose files',native_parent,Gtk.FileChooserAction.SELECT_FOLDER if folder else Gtk.FileChooserAction.OPEN,'Open' if not folder else 'Choose','Cancel');dialog.set_select_multiple(multiple and not folder);dialog.set_modal(True);self.choosers.append(dialog)
  # Layer-shell overlays otherwise stay above the regular file picker.
  restore=[window for window in dict.fromkeys((self.main,self.settings_window,parent)) if window and window.get_visible() and Layer and Layer.is_layer_window(window)]
  for window in restore:window.set_visible(False)
  def response(d,result):
   paths=[]
   if result==Gtk.ResponseType.ACCEPT:
    model=d.get_files();paths=[Path(model.get_item(i).get_path()) for i in range(model.get_n_items()) if model.get_item(i).get_path()]
   if d in self.choosers:self.choosers.remove(d)
   d.destroy()
   for window in restore:window.present()
   if paths:callback(paths)
  dialog.connect('response',response);dialog.show()
 def choose_files(self):self.file_dialog(self.set_files)
 def run_selected(self):
  if self.busy or not self.paths:return
  items=self.page_items()
  if not 0<=self.selected<len(items):self.status.set_text('Choose a format or tool on the wheel first.');return
  action=items[self.selected]
  if self.mode=='actions':self.file_action(action.id);return
  if action.id in FIELDS:self.tool_options(action)
  else:self.start_job(action.id,{})
 def tool_options(self,action):
  fields=list(FIELDS[action.id])
  if action.id=='compress':
   k=kind(self.paths[0]);fields=[f for f in fields if f[0] in ({'quality'} if k=='image' else {'crf'} if k=='video' else {'bitrate'})]
  height=max(220,min(680,170+len(fields)*42))
  w=self.window(action.label,True,width=470,height=height,namespace='petal-tool-dialog');w.set_modal(True)
  scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
  panel=box();panel.add_css_class('panel');scroll.set_child(panel);w.set_child(scroll);panel.append(label(action.label,'title'))
  if action.hint:panel.append(label(action.hint,'muted',True))
  entries={}
  for id,title,default in fields:
   panel.append(label(title,'muted'));entry=Gtk.Entry(text=default);panel.append(entry);entries[id]=entry
  if action.id in ('edit','background'):panel.append(label('Adjustments are approximations. A new copy is created; the original is preserved.','muted',True))
  if action.id=='redact' and kind(self.paths[0])=='video':panel.append(label('A black box covers the rectangle. Duration 0 covers the whole clip.','muted',True))
  if action.id=='bleep':panel.append(label('Ranges are muted in the new copy, like a broadcast bleep.','muted',True))
  row=box(Gtk.Orientation.HORIZONTAL);row.append(button('Cancel',w.destroy));row.append(button('Create copy',lambda:(self.start_job(action.id,{id:e.get_text() for id,e in entries.items()}),w.destroy()),'primary'));panel.append(row);w.present()

 def start_job(self,action,params):
  if self.busy:return
  paths=list(self.paths);settings=dict(self.settings);self.busy=True;self.cancel=threading.Event();self.cancel_button.set_visible(True);self.open_button.set_visible(False);self.status.remove_css_class('error');self.status.set_text(f'Working on {len(paths)} file(s)…');self.refresh()
  merged={'quality':settings['quality'],'dpi':settings['dpi'],**params};started=time.monotonic()
  def worker():
   try:outputs=execute(paths,action,merged,settings.get('output_dir') or None,self.cancel);error=None
   except Exception as e:outputs=[];error=str(e)
   GLib.idle_add(self.finish_job,action,paths,outputs,error,time.monotonic()-started)
  threading.Thread(target=worker,daemon=True).start()
 def finish_job(self,action,paths,outputs,error,elapsed):
  self.busy=False;self.cancel_button.set_visible(False);self.last_outputs=outputs;self.refresh()
  record={'time':time.strftime('%Y-%m-%d %H:%M:%S'),'action':action,'inputs':[str(p) for p in paths],'outputs':[str(p) for p in outputs],'error':error,'seconds':round(elapsed,2)}
  self.jobs.append(record);self.state.mkdir(parents=True,exist_ok=True)
  with (self.state/'history.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
  if error:self.status.add_css_class('error');self.status.set_text(error)
  else:
   self.status.remove_css_class('error');self.status.set_text(f'Done · {len(outputs)} new file(s) in {elapsed:.1f}s. Originals preserved.');self.open_button.set_visible(True)
   if self.settings.get('notify'):
    notification=Gio.Notification.new('Petal · files ready');notification.set_body(f'{len(outputs)} result(s) saved beside your originals.' if not self.settings.get('output_dir') else f'{len(outputs)} result(s) saved in your output folder.');self.send_notification('job',notification)
  return False
 def open_results(self):
  if self.last_outputs:Gio.AppInfo.launch_default_for_uri(self.last_outputs[0].parent.as_uri(),None)

 def file_action(self,action):
  if action=='shelf':
   for p in self.paths:
    if p not in self.shelf_paths:self.shelf_paths.append(p)
   self.show_shelf()
  elif action=='copy_path':Gdk.Display.get_default().get_clipboard().set('\n'.join(str(p) for p in self.paths));self.status.set_text('Full paths copied.')
  elif action=='copy':
   uris='\r\n'.join(p.as_uri() for p in self.paths)+'\r\n';gnome='copy\n'+'\n'.join(p.as_uri() for p in self.paths)
   providers=[Gdk.ContentProvider.new_for_bytes('text/uri-list',GLib.Bytes.new(uris.encode())),Gdk.ContentProvider.new_for_bytes('x-special/gnome-copied-files',GLib.Bytes.new(gnome.encode()))]
   Gdk.Display.get_default().get_clipboard().set_content(Gdk.ContentProvider.new_union(providers));self.status.set_text('Files copied to the clipboard. Paste in your file manager.')
  elif action=='terminal':
   path=self.paths[0] if self.paths[0].is_dir() else self.paths[0].parent
   terminal=next((shutil.which(n) for n in ['ghostty','foot','kitty','alacritty','x-terminal-emulator'] if shutil.which(n)),None)
   if terminal:subprocess.Popen([terminal],cwd=path,start_new_session=True)
   else:self.status.set_text('No supported terminal found. Copy the folder path and open it in your terminal.')
  elif action=='share':
   tool=dependencies().get('LocalSend')
   if tool:subprocess.Popen([tool,*map(str,self.paths)],start_new_session=True)
   else:self.status.set_text('LocalSend is not installed. Open the File shelf here and drag files into your preferred sharing app, or install LocalSend separately.')
  elif action=='move':
   paths=list(self.paths)
   if len({p.name for p in paths})!=len(paths):
    self.status.set_text('These files have matching names. Move them separately or rename them first.');self.show_activity();return
   def move(chosen):
    dest=chosen[0]
    try:
     for p in paths:
      target=dest/p.name
      if target.exists() or target.is_symlink():raise ConversionError(f'{target.name} already exists. Choose another folder; no file has been moved.')
      if p==dest or p in dest.parents:raise ConversionError('Cannot move a folder into itself.')
     moved=[]
     for p in paths:
      Gio.File.new_for_path(str(p)).move(Gio.File.new_for_path(str(dest/p.name)),Gio.FileCopyFlags.NOFOLLOW_SYMLINKS,None,None,None);moved.append(dest/p.name)
     self.set_files(moved);self.status.set_text(f'Moved {len(moved)} item(s).')
    except Exception as e:self.status.set_text(str(e))
   self.file_dialog(move,folder=True)

 def show_drop_target(self):
  if self.drop_window:self.drop_window.present();return
  w=self.window('Petal drop target',True,175,70,namespace='petal-drop-target');self.drop_window=w
  if Layer and Layer.is_layer_window(w):
   Layer.set_anchor(w,Layer.Edge.RIGHT,True);Layer.set_anchor(w,Layer.Edge.BOTTOM,True);Layer.set_margin(w,Layer.Edge.RIGHT,24);Layer.set_margin(w,Layer.Edge.BOTTOM,90);Layer.set_keyboard_mode(w,Layer.KeyboardMode.NONE)
  row=box(Gtk.Orientation.HORIZONTAL,5);row.add_css_class('drop');row.append(button('◉  Drop files',self.show_main,'flat'));row.append(button('×',self.toggle_drop_target,'flat'));w.set_child(row)
  target=Gtk.DropTarget.new(Gdk.FileList,Gdk.DragAction.COPY);target.set_preload(True)
  def preview_files(controller,*_):
   value=controller.get_value()
   if value and not self.busy:
    files=[Path(f.get_path()) for f in value.get_files() if f.get_path()]
    if files:self.show_main();self.set_files(files)
  target.connect('notify::value',preview_files)
  def drop(_,value,x,y):
   files=[Path(f.get_path()) for f in value.get_files() if f.get_path()]
   if files:self.show_main();self.set_files(files);return True
   return False
  target.connect('drop',drop);row.add_controller(target);w.present()
 def toggle_drop_target(self):
  self.settings['drop_target']=not self.settings['drop_target'];self.save_settings()
  if self.settings['drop_target']:self.show_drop_target()
  elif self.drop_window:self.drop_window.destroy();self.drop_window=None
  if self.tray:self.tray.update()

 def show_shelf(self):
  if self.shelf:self.shelf.destroy()
  w=self.window('Petal file shelf',True,380,300,namespace='petal-shelf');self.shelf=w
  if Layer and Layer.is_layer_window(w):Layer.set_anchor(w,Layer.Edge.RIGHT,True);Layer.set_margin(w,Layer.Edge.RIGHT,24)
  panel=box();panel.add_css_class('panel');w.set_child(panel);panel.append(label('File shelf','title'));panel.append(label('Drag a file into another app. Shelf items remain on disk.','muted',True))
  scroller=Gtk.ScrolledWindow();scroller.set_min_content_height(160);scroller.set_max_content_height(420);scroller.set_propagate_natural_height(True);rows=box();scroller.set_child(rows);panel.append(scroller)
  for p in self.shelf_paths:
   if not p.exists():continue
   row=box(Gtk.Orientation.HORIZONTAL);name=label(p.name);name.set_hexpand(True);name.set_ellipsize(3);row.append(name)
   source=Gtk.DragSource(actions=Gdk.DragAction.COPY)
   source.connect('prepare',lambda _,x,y,path=p:Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list([Gio.File.new_for_path(str(path))])))
   row.add_controller(source);row.append(button('×',lambda path=p:(self.shelf_paths.remove(path),self.show_shelf()),'flat'));rows.append(row)
  if not self.shelf_paths:rows.append(label('Use Actions → Float / shelf to pin files here.','muted',True))
  panel.append(button('Hide shelf',lambda:w.set_visible(False)));w.present()

 def show_settings(self):
  if self.settings_window:self.settings_window.present();return
  w=self.window('Petal settings',True,560,650,namespace='petal-settings');self.settings_window=w
  w.connect('close-request',lambda *_:(setattr(self,'settings_window',None),False)[1])
  scroller=Gtk.ScrolledWindow();panel=box();panel.add_css_class('panel');scroller.set_child(panel);w.set_child(scroller)
  panel.append(label('Settings','title'));panel.append(label('Petal · offline tools for Wayland','muted'))
  target=Gtk.Switch(active=self.settings.get('drop_target',False));row=box(Gtk.Orientation.HORIZONTAL);l=label('Floating drop target');l.set_hexpand(True);row.append(l);row.append(target);panel.append(row)
  target.connect('notify::active',lambda s,*_:self.set_drop_enabled(s.get_active()))
  output=label(self.settings.get('output_dir') or 'Beside the original files','muted',True);panel.append(label('Save converted files'));panel.append(output)
  row=box(Gtk.Orientation.HORIZONTAL)
  def selected(paths):self.settings['output_dir']=str(paths[0]);self.save_settings();output.set_text(str(paths[0]))
  def reset():self.settings['output_dir']='';self.save_settings();output.set_text('Beside the original files')
  row.append(button('Choose output folder…',lambda:self.file_dialog(selected,folder=True)));row.append(button('Reset',reset));panel.append(row)
  for id,title,low,high in [('quality','Default image quality',1,100),('dpi','PDF page image DPI',36,600)]:
   row=box(Gtk.Orientation.HORIZONTAL);l=label(title);l.set_hexpand(True);row.append(l);spin=Gtk.SpinButton.new_with_range(low,high,1);spin.set_value(self.settings[id]);spin.connect('value-changed',lambda s,k=id:self.setting(k,s.get_value_as_int()));row.append(spin);panel.append(row)
  row=box(Gtk.Orientation.HORIZONTAL);l=label('Notify when a job finishes');l.set_hexpand(True);row.append(l);notify=Gtk.Switch(active=self.settings['notify']);notify.connect('notify::active',lambda s,*_:self.setting('notify',s.get_active()));row.append(notify);panel.append(row)
  panel.append(Gtk.Separator());panel.append(label('Engines','orange'))
  for name,path in dependencies().items():panel.append(label(('✓ ' if path else '○ ')+name+(' · available' if path else ' · not installed'),'muted'))
  office_path=label(self.settings.get('libreoffice_path') or 'LibreOffice: use the application search path','muted',True);panel.append(office_path)
  def choose_office(paths):
   if not os.access(paths[0],os.X_OK):office_path.set_text('That file is not executable; the engine setting was not changed.');return
   self.settings['libreoffice_path']=str(paths[0]);os.environ['PETAL_LIBREOFFICE']=str(paths[0]);self.save_settings();office_path.set_text(str(paths[0]))
  panel.append(button('Choose an existing LibreOffice executable…',lambda:self.file_dialog(choose_office,multiple=False)))
  panel.append(label('Unavailable engines affect only their own tools. Nothing is downloaded automatically.','muted',True))
  panel.append(Gtk.Separator());panel.append(label('MangoWM shortcut','orange'));panel.append(label('The included integration/mango.conf.example opens Petal with Super+Shift+C. Add it manually after reviewing the path.','muted',True))
  panel.append(label('Shift / Alt / Control switch wheels while Petal has focus. A global bare-Shift trigger is deliberately not installed.','muted',True))
  panel.append(label('Linux differences','orange'));panel.append(label('Apple Pages/Keynote and AirDrop have no exact built-in equivalent. PDF-to-editable-office reconstruction is not included. Markdown to rich office formats needs optional Pandoc.','muted',True))
  panel.append(button('Close settings',lambda:w.set_visible(False)));w.present()
 def setting(self,key,value):self.settings[key]=value;self.save_settings()
 def set_drop_enabled(self,value):
  if self.settings['drop_target']!=value:self.toggle_drop_target()
 def request_quit(self):
  if self.busy:
   self.show_main();self.status.set_text('A conversion is running. Cancel it first, then choose Quit again.');return
  if self.tray:self.tray.close()
  self.quit()

def main(args):
 app=LegacyApp();return app.run(['petal',*args])
