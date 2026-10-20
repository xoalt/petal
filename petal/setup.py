"""First-launch setup and reusable preference pages. Drafts save on Finish only."""
from copy import deepcopy
from gi.repository import GObject
from .legacy import Gtk,Gdk,Gio,GLib,box,label,button,fit_size
from .preferences import DEFAULTS,PRESETS,APP_ROLES,COLOR_KEYS,normalize
from . import integrations

SETUP_CSS='''
.setup-root {padding:24px;background:#fafafa;color:#202124;}
.setup-heading {font-size:25px;font-weight:600;}
.setup-steps {font-size:12px;color:#7c8189;}
.setup-card {padding:15px;border:1px solid #dfe2e6;border-radius:12px;background:rgba(255,255,255,.6);}
.preference-row {padding:4px 0;}
.preference-row dropdown,.setup-root dropdown {padding:0;background:transparent;border:0;}
.preference-row dropdown button,.setup-root dropdown button {padding:6px 10px;min-height:24px;}
.theme-preview {padding:18px;border:1px solid #dfe2e6;border-radius:12px;}
.theme-preview .sample-petal {padding:12px 22px;border-radius:12px;}
'''

class ColorPicker(Gtk.MenuButton):
 __gsignals__={'color-set':(GObject.SignalFlags.RUN_FIRST,None,())}
 def __init__(self,rgba):
  super().__init__();self.rgba=rgba;self.swatch=Gtk.DrawingArea();self.swatch.set_content_width(38);self.swatch.set_content_height(24);self.swatch.set_draw_func(self.draw);self.set_child(self.swatch)
  popup=Gtk.Popover();panel=box(spacing=8);panel.set_margin_top(10);panel.set_margin_bottom(10);panel.set_margin_start(10);panel.set_margin_end(10);self.chooser=Gtk.ColorChooserWidget();self.chooser.set_use_alpha(False);panel.append(self.chooser)
  row=box(Gtk.Orientation.HORIZONTAL,8);row.append(button('Cancel',popup.popdown))
  def apply():self.set_rgba(self.chooser.get_rgba());self.emit('color-set');popup.popdown()
  self.apply_button=button('Use color',apply,'primary');row.append(self.apply_button);panel.append(row);popup.set_child(panel);self.set_popover(popup);popup.connect('show',lambda *_:self.chooser.set_rgba(self.rgba))
 def set_rgba(self,rgba):self.rgba=rgba;self.swatch.queue_draw()
 def get_rgba(self):return self.rgba
 def draw(self,area,c,w,h):
  from .wheel import rounded
  rounded(c,1,1,w-2,h-2,5);c.set_source_rgba(self.rgba.red,self.rgba.green,self.rgba.blue,1);c.fill_preserve();c.set_source_rgba(.4,.4,.4,.4);c.set_line_width(1);c.stroke()

class AppPicker(Gtk.Box):
 def __init__(self,parent,role,value,changed):
  super().__init__(orientation=Gtk.Orientation.HORIZONTAL,spacing=8);self.parent_window=parent;self.role=role;self.changed=changed;self.items=integrations.choices(role);self.updating=False
  self.dropdown=Gtk.DropDown();self.dropdown.set_enable_search(True);self.dropdown.set_hexpand(True);self.append(self.dropdown)
  if role!='terminal_app':self.append(button('Other…',self.choose_other))
  self.rebuild(value);self.dropdown.connect('notify::selected',self.selected)
 def rebuild(self,value):
  if not any(item.id==value for item in self.items):
   try:name=integrations.app_info(value).get_display_name()
   except Exception:name='Unavailable application'
   self.items.append(integrations.AppChoice(value,name))
  self.updating=True;self.dropdown.set_model(Gtk.StringList.new([x.name for x in self.items]));self.dropdown.set_selected(next(i for i,x in enumerate(self.items) if x.id==value));self.updating=False
 def refresh_apps(self):
  i=self.dropdown.get_selected();value=self.items[i].id if i<len(self.items) else '';self.items=integrations.choices(self.role);self.rebuild(value)
 def selected(self,*_):
  if not self.updating:
   i=self.dropdown.get_selected()
   if i<len(self.items):self.changed(self.items[i].id)
 def choose_other(self):
  chooser=Gtk.AppChooserDialog.new_for_content_type(self.parent_window,Gtk.DialogFlags.MODAL,integrations.MIMES[self.role]);chooser.set_heading('Choose an application for Petal');chooser.get_widget().set_show_all(True);chooser.set_destroy_with_parent(True);self.chooser=chooser
  from .legacy import Layer
  restore=bool(Layer and Layer.is_layer_window(self.parent_window) and self.parent_window.get_visible())
  if restore:self.parent_window.set_visible(False)
  def response(dialog,result):
   if result==Gtk.ResponseType.OK:
    app=dialog.get_app_info()
    if app and app.get_id():self.rebuild(app.get_id());self.changed(app.get_id())
   dialog.destroy();self.chooser=None
   if restore:self.parent_window.present()
  chooser.connect('response',response);chooser.present()

class PreferencePages:
 def __init__(self,app,window,values,on_change):self.app=app;self.window=window;self.values=values;self.on_change=on_change;self.color_buttons={};self.mode_picker=None;self.refreshing=False;self.toggles={}
 def change(self,key,value):
  self.values[key]=value
  if not self.refreshing:self.on_change(key,value)
 def applications(self):
  page=box(spacing=6);page.append(label('Your applications','title'));page.append(label('Choose the apps Petal opens. Your system defaults stay as they are.','muted',True));self.pickers={}
  for role,title,description in APP_ROLES:
   row=box(Gtk.Orientation.HORIZONTAL,14);row.add_css_class('preference-row');words=box(spacing=3);words.set_size_request(195 if self.window.get_title()=='Welcome to Petal' else 150,-1);words.append(label(title));detail=label(description,'muted',True);detail.set_max_width_chars(30 if self.window.get_title()=='Welcome to Petal' else 22);words.append(detail);row.append(words);picker=AppPicker(self.window,role,self.values[role],lambda value,r=role:self.change(r,value));picker.set_hexpand(True);row.append(picker);page.append(row);self.pickers[role]=picker
  return page
 def color_button(self,key,title,parent):
  row=box(Gtk.Orientation.HORIZONTAL,12);name=label(title);name.set_hexpand(True);row.append(name);rgba=Gdk.RGBA();rgba.parse(self.values[key]);picker=ColorPicker(rgba);picker.set_tooltip_text(title)
  def selected(b):
   rgba=b.get_rgba();value='#'+''.join(f'{round(v*255):02x}' for v in (rgba.red,rgba.green,rgba.blue));self.change(key,value);self.preview_colors()
  picker.connect('color-set',selected);row.append(picker);parent.append(row);self.color_buttons[key]=picker
 def appearance(self):
  page=box(spacing=9);page.append(label('Make it yours','title'));page.append(label('Choose a preset, or set your own colors.','muted',True));presets=Gtk.FlowBox();presets.set_selection_mode(Gtk.SelectionMode.NONE);presets.set_min_children_per_line(1);presets.set_max_children_per_line(6);presets.set_column_spacing(4);presets.set_row_spacing(4)
  for name in PRESETS:presets.insert(button(name,lambda n=name:self.preset(n)),-1)
  page.append(presets)
  row=box(Gtk.Orientation.HORIZONTAL,12);text=label('Settings appearance');text.set_hexpand(True);row.append(text);self.mode_picker=Gtk.DropDown.new_from_strings(['Light','Dark','Follow system']);self.mode_picker.set_selected(['light','dark','system'].index(self.values['appearance_mode']));self.mode_picker.connect('notify::selected',lambda d,*_:self.change('appearance_mode',['light','dark','system'][d.get_selected()]) if not self.refreshing else None);row.append(self.mode_picker);page.append(row)
  for key,title in [('accent_color','Highlight color'),('petal_color','Leaf color'),('text_color','Wheel text')]:self.color_button(key,title,page)
  row=box(Gtk.Orientation.HORIZONTAL,12);row.append(label('Leaf opacity'));scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,35,100,1);scale.set_hexpand(True);scale.set_draw_value(False);scale.set_value(self.values['petal_opacity']);readout=label(str(self.values['petal_opacity'])+'%');self.opacity_scale=scale
  def opacity(s):self.change('petal_opacity',s.get_value_as_int() if hasattr(s,'get_value_as_int') else round(s.get_value()));readout.set_text(str(round(s.get_value()))+'%');self.preview_colors()
  scale.connect('value-changed',opacity);row.append(scale);row.append(readout);page.append(row)
  self.switch(page,'Animate leaves on hover','Expand the highlighted leaf smoothly.','animations')
  self.preview=box(Gtk.Orientation.HORIZONTAL,12);self.preview.add_css_class('theme-preview');self.preview.append(label('Preview'));sample=label('Leaf');sample.add_css_class('sample-petal');self.preview.append(sample);self.sample=sample;highlight=label('Highlight');highlight.add_css_class('sample-highlight');self.preview.append(highlight);self.highlight=highlight;page.append(self.preview);self.preview_colors();return page
 def preview_colors(self):
  if not hasattr(self,'preview'):return
  from .preferences import rgb,readable_ink
  p=normalize(self.values);r,g,b=(round(c*255) for c in rgb(p['petal_color']));ink='#'+''.join(f'{round(v*255):02x}' for v in readable_ink(p['accent_color']))
  css=Gtk.CssProvider();css.load_from_string('.sample-petal {background:rgba('+f'{r},{g},{b},{p["petal_opacity"]/100}'+');color:'+p['text_color']+';} .sample-highlight {padding:12px 22px;border-radius:12px;background:'+p['accent_color']+';color:'+ink+';}')
  for widget in (self.sample,self.highlight):
   old=getattr(widget,'preview_css',None)
   if old:widget.get_style_context().remove_provider(old)
   widget.get_style_context().add_provider(css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1);widget.preview_css=css
 def preset(self,name):
  for key,value in zip(COLOR_KEYS,PRESETS[name]):
   self.change(key,value);rgba=Gdk.RGBA();rgba.parse(value);self.color_buttons[key].set_rgba(rgba)
  self.preview_colors()
 def switch(self,page,title,description,key):
  row=box(Gtk.Orientation.HORIZONTAL,12);words=box(spacing=4);words.set_hexpand(True);words.append(label(title));words.append(label(description,'muted',True));row.append(words);toggle=Gtk.Switch(active=bool(self.values.get(key)));toggle.set_valign(Gtk.Align.CENTER);toggle.connect('notify::active',lambda s,*_:self.change(key,s.get_active()));row.append(toggle);page.append(row);self.toggles[key]=toggle
 def workflow(self):
  page=box(spacing=17);page.append(label('How you work','title'))
  for key,title,description in [('tray_enabled','Show in Noctalia tray','Open the wheel or Settings from the tray icon.'),('drop_target','Floating drop target','Drag files here to reveal the wheel.'),('notify','Completion notifications','Know when a converted copy is ready.')]:self.switch(page,title,description,key)
  page.append(label('Save converted copies'));self.output_label=label(self.values.get('output_dir') or 'Beside the original files','muted',True);page.append(self.output_label);row=box(Gtk.Orientation.HORIZONTAL,8)
  def picked(paths):self.change('output_dir',str(paths[0]));self.output_label.set_text(str(paths[0]))
  def reset():self.change('output_dir','');self.output_label.set_text('Beside the original files')
  row.append(button('Choose folder…',lambda:self.folder_dialog(picked)));row.append(button('Beside originals',reset));page.append(row)
  for key,title,low,high in [('quality','Image quality',1,100),('dpi','PDF image DPI',36,600)]:
   row=box(Gtk.Orientation.HORIZONTAL,12);name=label(title);name.set_hexpand(True);row.append(name);spin=Gtk.SpinButton.new_with_range(low,high,1);spin.set_value(self.values[key]);spin.connect('value-changed',lambda s,k=key:self.change(k,s.get_value_as_int()));row.append(spin);page.append(row)
  page.append(label('Optional: configure a MangoWM shortcut using the included example.','muted',True));return page
 def folder_dialog(self,callback):
  dialog=Gtk.FileChooserNative.new('Choose output folder',self.window,Gtk.FileChooserAction.SELECT_FOLDER,'Choose','Cancel')
  def response(d,result):
   if result==Gtk.ResponseType.ACCEPT:
    f=d.get_file()
    if f and f.get_path():callback([f.get_path()])
   d.destroy()
  dialog.connect('response',response);self.folder_chooser=dialog;dialog.show()

class SetupWizard:
 def __init__(self,app):
  self.app=app;self.draft=deepcopy(app.settings);self.closed=False;self.index=0;self.return_to_settings=bool(app.controls and app.controls.get_visible());
  if app.controls:app.controls.set_visible(False)
  if app.main:app.main.set_visible(False)
  self.window=Gtk.ApplicationWindow(application=app,title='Welcome to Petal');self.window.set_default_size(*fit_size(800,760));self.window.set_resizable(False)
  self.window.connect('close-request',self.cancel);root=box(spacing=17);root.add_css_class('setup-root');self.window.set_child(root);root.append(label('Welcome to Petal','setup-heading'));root.append(label('Choose your apps, colors, and preferences. You can change them later in Settings.','muted',True));self.steps=label('','setup-steps');root.append(self.steps)
  self.stack=Gtk.Stack();self.stack.set_vexpand(True);self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT);root.append(self.stack);self.pages=PreferencePages(app,self.window,self.draft,self.changed)
  from .software import SoftwarePage
  self.software=SoftwarePage(app,self.window,self.draft,self.change_software)
  for name,page in [('software',self.software),('apps',self.pages.applications()),('appearance',self.pages.appearance()),('workflow',self.pages.workflow())]:
   scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);scroll.set_child(page);self.stack.add_named(scroll,name)
  self.error=label('','error',True);root.append(self.error);row=box(Gtk.Orientation.HORIZONTAL,10);root.append(row);row.append(button('Keep current choices' if app.settings['setup_completed'] else 'Use defaults',self.use_defaults));space=Gtk.Box();space.set_hexpand(True);row.append(space);self.back_button=button('Back',lambda:self.navigate(-1));row.append(self.back_button);self.next_button=button('Next',lambda:self.navigate(1),'primary');row.append(self.next_button);self.refresh();self.window.present()
 def changed(self,key,value):
  if key in COLOR_KEYS or key in ('appearance_mode','petal_opacity','animations'):self.app.apply_appearance(self.draft)
 def change_software(self,key,value):self.draft[key]=value
 def navigate(self,delta):
  if delta>0 and self.index==3:self.finish();return
  self.index=max(0,min(3,self.index+delta));self.refresh()
 def refresh(self):
  if self.index==1:
   for picker in self.pages.pickers.values():picker.refresh_apps()
  names=['software','apps','appearance','workflow'];self.stack.set_visible_child_name(names[self.index]);self.steps.set_text(f'{self.index+1} of 4  ·  '+['Software','Applications','Appearance','Preferences'][self.index]);self.back_button.set_sensitive(self.index>0);self.next_button.set_label('Finish setup' if self.index==3 else 'Next')
 def use_defaults(self):
  self.draft=deepcopy(self.app.settings);self.finish()
 def finish(self):
  if self.closed:return
  settings=normalize(self.draft);settings['setup_completed']=True;settings['setup_version']=2
  try:self.app.complete_setup(settings)
  except OSError as e:self.error.set_text('Could not save your preferences: '+str(e));return
  self.closed=True;self.software.dispose_page();self.window.destroy()
 def cancel(self,*_):
  if not self.closed:
   self.closed=True;self.software.dispose_page();self.app.apply_appearance(self.app.settings);self.app.setup_wizard=None;self.app.setup_requests=[];self.window.destroy()
   if self.return_to_settings and self.app.controls:self.app.controls.present()
  return True
