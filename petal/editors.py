"""Native preview editors, arranged from the supplied Petal visual references."""
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import uuid
import cairo
from .legacy import Gtk,Gdk,Gio,GLib,box,label,button,FIELDS
from .catalog import kind,dependencies,choices
from .engine import execute,Runner,Cancelled,_edit_image,_add_background
from . import wheel

EDITOR_CSS='''
window.tool-window {background:transparent;font-family:Arial,sans-serif;color:#202020;}
.material-shell {background:rgba(255,255,255,.68);border:1px solid rgba(45,35,25,.24);border-radius:23px;box-shadow:0 8px 26px rgba(0,0,0,.15);}
.tool-header {padding:12px 16px;border-bottom:1px solid rgba(0,0,0,.12);min-height:30px;}
.tool-title {font-size:20px;font-weight:600;}
.tool-body {padding:17px;}
.tool-footer {border-top:1px solid rgba(0,0,0,.13);padding:16px 20px;}
.tool-window button {background:rgba(50,25,10,.10);border:0;border-radius:7px;padding:5px 12px;min-height:20px;box-shadow:none;}
.tool-window button:hover {background:rgba(50,25,10,.17);}
.tool-window button:checked {background:rgba(50,25,10,.23);}
.tool-window button.primary {background:#ff5300;color:white;}
.tool-window button.close-circle {border-radius:50%;padding:0;min-width:29px;min-height:29px;font-size:22px;font-weight:400;}
.tool-window button.reset-control {background:transparent;padding:0;min-width:24px;min-height:24px;color:rgba(0,0,0,.5);font-size:18px;}
.tool-window .group-title {font-weight:600;font-size:13px;margin-top:10px;}
.tool-window .field-name {font-size:13px;}
.tool-window .readout {font-size:12px;font-family:Arial,sans-serif;}
.tool-window .preview-stage {background:rgba(50,30,10,.045);border-radius:12px;padding:14px;}
.tool-window .photo-stage {background:#13110e;}
.tool-window .photo-stage button {background:rgba(255,255,255,.12);color:#eee;min-height:18px;font-size:11px;}
.tool-window scale {padding:4px 0;min-height:14px;}
.tool-window scale trough,.tool-window scale highlight {border:0;box-shadow:none;min-width:1px;min-height:4px;padding:0;margin:0;}
.tool-window progressbar trough {background:rgba(40,15,5,.18);border:0;min-height:5px;border-radius:4px;}
.tool-window progressbar progress {background:#ff5300;min-height:5px;min-width:1px;border:0;border-radius:4px;padding:0;margin:0;}
.tool-window scale trough {min-height:4px;border-radius:3px;background:rgba(40,15,5,.22);}
.tool-window scale highlight {background:#ff5300;border-radius:3px;}
.tool-window scale slider {background:white;border:0;border-radius:50%;min-width:20px;min-height:20px;box-shadow:0 1px 2px rgba(0,0,0,.1);margin:-8px;}
.tool-window entry,.tool-window spinbutton {background:rgba(255,255,255,.32);border:1px solid rgba(0,0,0,.12);border-radius:6px;min-height:24px;padding:3px 6px;}
.tool-window .segment {background:rgba(40,20,10,.10);border-radius:7px;}
.tool-window .segment button {background:transparent;border-radius:7px;padding:4px 12px;}
.tool-window .segment button:checked {background:rgba(50,25,10,.20);}
.tool-window .hint {font-size:11px;color:rgba(0,0,0,.62);}
.tool-window .time {font-size:12px;font-family:monospace;}
.tool-window .swatch {min-width:30px;min-height:30px;padding:0;border:2px solid transparent;border-radius:8px;}
.tool-window .swatch:checked {border-color:#ff5300;}
'''

PHOTO_GROUPS=[('Light',[('exposure','Exposure',-3,3,.01,0,' EV'),('brightness','Brightness',-100,100,1,0,''),('contrast','Contrast',-100,100,1,0,''),('highlights','Highlights',-100,100,1,0,''),('shadows','Shadows',-100,100,1,0,''),('whites','Whites',-100,100,1,0,''),('blacks','Blacks',-100,100,1,0,''),('gamma','Gamma',.2,3,.01,1,'')]),('Color',[('temperature','Temperature',-100,100,1,0,''),('tint','Tint',-100,100,1,0,''),('saturation','Saturation',-100,100,1,0,''),('vibrance','Vibrance',-100,100,1,0,'')]),('Detail',[('sharpness','Sharpness',0,200,1,0,''),('vignette','Vignette',0,100,1,0,'')])]
PALETTE=['#43c6ef,#bcefff','#50e2da,#07a7c1','#c3c7ff,#fff6fa','#ffb5e0,#c9ffff','#f8fbff,#55d3f4','#003c37,#00b49b','#ffba64,#ff4590','#26b7ef,#616dff','#006e96,#09b9c2','#7547c8','#9a7add','#df4b93','#f11732','#ff5e50','#ff8700','#75482e','#126cda']

class AsyncPreview:
 """Cancel stale renders; publish only the newest preview on the GTK thread."""
 def __init__(self):self.generation=0;self.cancel=None;self.closed=False
 def stop(self):
  self.closed=True;self.generation+=1
  if self.cancel:self.cancel.set()
 def submit(self,worker,done):
  self.generation+=1;generation=self.generation
  if self.cancel:self.cancel.set()
  cancel=threading.Event();self.cancel=cancel
  def run():
   try:
    with tempfile.TemporaryDirectory(prefix='petal-preview-') as td:result=worker(Path(td),Runner(cancel))
    error=None
   except Cancelled:return
   except Exception as e:result=None;error=str(e)
   def publish():
    if not self.closed and generation==self.generation:done(result,error)
    return False
   GLib.idle_add(publish)
  threading.Thread(target=run,daemon=True).start()

def time_label(value):
 minutes=int(value)//60;seconds=value%60
 return f'{minutes}:{seconds:05.2f}'

def scaled_source(src,dest,max_side=1000):
 from PIL import Image,ImageOps
 with Image.open(src) as im:
  im=ImageOps.exif_transpose(im).convert('RGBA');im.thumbnail((max_side,max_side));im.save(dest)
 return dest

class Editor:
 def __init__(self,app,action):
  self.app=app;self.action=action;self.paths=list(app.paths);self.values={};self.defaults={};self.scales={};self.closed=False;self.debounce=None;self.preview=AsyncPreview();self.media_preview=AsyncPreview();self.wave_preview=AsyncPreview();self.player=None;self.audio_dir=None;self.source_duration=0;self.ranges=[];self.range_index=-1;self.stop_buttons=[];self.wave_images=[];self.wave_levels=[];self.error=None;self.preview_ready=False;self.pending_apply=False;self.workflow=False;self.entries={};self._syncing_crop=False;self.preview_result=None;self.canvas_preview=AsyncPreview();self._syncing_pdf=False
  self.window=app.window(action.label,False,680,880 if action.id=='edit' else 840 if action.id=='background' else 820);self.window.add_css_class('tool-window');self.window.set_decorated(False);self.window.set_resizable(False)
  self.window.connect('notify::visible',lambda w,*_:self.close() if getattr(self,'presented',False) and not w.get_visible() else None)
  key=Gtk.EventControllerKey();key.connect('key-pressed',self.key_pressed);self.window.add_controller(key)
  self.shell=box(spacing=0);self.shell.add_css_class('material-shell');self.window.set_child(self.shell)
  header=box(Gtk.Orientation.HORIZONTAL,10);header.add_css_class('tool-header');self.shell.append(header)
  header.append(button('×',self.close,'close-circle'));title=label(action.label,'tool-title');title.set_xalign(.5);title.set_hexpand(True);header.append(title);spacer=Gtk.Box();spacer.set_size_request(29,-1);header.append(spacer)
  scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);scroll.set_vexpand(True);self.shell.append(scroll);self.body=box(spacing=8);self.body.add_css_class('tool-body');scroll.set_child(self.body)
  footer=box(Gtk.Orientation.HORIZONTAL,12);footer.add_css_class('tool-footer');self.shell.append(footer)
  self.notice=label('Original files are preserved.','hint',True);self.notice.set_hexpand(True);footer.append(self.notice);self.apply_button=button('Apply',self.apply,'primary');footer.append(self.apply_button)
  if action.id=='edit':self.photo()
  elif action.id=='background':self.background()
  elif kind(self.paths[0])=='audio' and action.id in ('trim','channels','bleep'):self.audio()
  else:self.generic()
  self.presented=True;self.window.present()
 def key_pressed(self,_,key,*args):
  if key==Gdk.KEY_Escape:self.close();return True
  if key in (Gdk.KEY_Delete,Gdk.KEY_BackSpace) and self.action.id=='bleep':self.remove_range();return True
  return False
 def close(self):
  if self.closed:return
  self.closed=True
  if self.debounce:GLib.source_remove(self.debounce);self.debounce=None
  self.preview.stop();self.media_preview.stop();self.wave_preview.stop();self.canvas_preview.stop();self.stop_audio()
  if self.audio_dir:self.audio_dir.cleanup();self.audio_dir=None
  if getattr(self,'action_popup',None):self.action_popup.unparent()
  self.window.destroy()
  if self in self.app.editors:self.app.editors.remove(self)
 def apply(self):
  if self.closed or self.app.busy:return
  if self.workflow and not self.preview_ready:return
  if self.action.id=='bleep':
   if not self.ranges:return
   self.values['ranges']=','.join(f'{a:.4f}-{b:.4f}' for a,b in self.ranges)
  if self.action.id=='trim' and 'end' in self.values:self.values['duration']=max(.01,self.values['end']-self.values['start'])
  self.app.set_files(self.paths);self.app.start_job(self.action.id,{k:v for k,v in self.values.items() if not k.startswith('_')});self.close()
 def group(self,name):self.body.append(label(name,'group-title'))
 def slider(self,key,title,low,high,step,default,suffix='',changed=None,formatter=None):
  self.values[key]=default;self.defaults[key]=default
  row=box(Gtk.Orientation.HORIZONTAL,14);name=label(title,'field-name');name.set_size_request(125,-1);row.append(name)
  scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,low,high,step);scale.set_draw_value(False);scale.set_hexpand(True);scale.set_value(default);row.append(scale);self.scales[key]=scale
  value=label('','readout');value.set_xalign(1);value.set_size_request(62,-1);row.append(value)
  def update(s):
   v=s.get_value();self.values[key]=v;value.set_text(formatter(v) if formatter else (f'{v:.2f}' if step<1 else f'{v:.0f}')+suffix)
   (changed or self.queue_preview)()
  scale.connect('value-changed',update);update(scale)
  row.append(button('↺',lambda:scale.set_value(default),'reset-control'));self.body.append(row);return scale
 def entry(self,key,title,default):
  self.values[key]=default;row=box(Gtk.Orientation.HORIZONTAL,12);name=label(title,'field-name',True);name.set_hexpand(True);row.append(name);entry=Gtk.Entry(text=str(default));entry.set_width_chars(18)
  def changed(e):
   self.values[key]=e.get_text()
   if self._syncing_crop:return
   if getattr(self,'crop_canvas',None) and key in ('x','y','width','height'):
    try:
     self.crop_canvas.set_rect(*[float(self.values[k]) for k in ('x','y','width','height')]);self.crop_changed(*self.crop_canvas.rect);return
    except (ValueError,TypeError):pass
   if key=='pages' and hasattr(self,'pdf_order_list') and not self._syncing_pdf:
    try:
     from .engine import _page_indices
     self.pdf_page_order=[i+1 for i in _page_indices(e.get_text(),self.pdf_source_count)];self.refresh_pdf_order()
    except ValueError:pass
    except Exception as error:self.notice.set_text(str(error)[:180])
   self.queue_preview()
  entry.connect('changed',changed);row.append(entry);self.body.append(row);self.entries[key]=entry;return entry
 def segments(self,key,title,options,default,changed=None):
  self.values[key]=default;row=box(Gtk.Orientation.HORIZONTAL,12);name=label(title,'field-name');name.set_hexpand(True);row.append(name);segment=box(Gtk.Orientation.HORIZONTAL,0);segment.add_css_class('segment');row.append(segment);buttons=[]
  for text,value in options:
   b=Gtk.ToggleButton(label=text);b.set_active(value==default)
   if buttons:b.set_group(buttons[0])
   def toggled(w,v=value):
    if w.get_active():self.values[key]=v;(changed or self.queue_preview)()
   b.connect('toggled',toggled);buttons.append(b);segment.append(b)
  self.body.append(row);return buttons
 def picture(self,photo=False):
  stage=box(spacing=8);stage.add_css_class('preview-stage')
  if photo:stage.add_css_class('photo-stage')
  pic=Gtk.Picture();pic.set_can_shrink(True);pic.set_content_fit(Gtk.ContentFit.CONTAIN);pic.set_size_request(-1,330 if photo else 350);stage.append(pic);self.body.append(stage);self.picture_widget=pic;self.preview_stage=stage;return pic
 def photo(self):
  self.picture(True);tools=box(Gtk.Orientation.HORIZONTAL);self.preview_stage.prepend(tools);original=Gtk.ToggleButton(label='Original');original.connect('toggled',lambda b:self.show_original(b.get_active()));tools.append(original);self.original_button=original
  spacer=Gtk.Box();spacer.set_hexpand(True);tools.prepend(spacer);tools.insert_child_after(button('Reset',self.reset_photo),spacer)
  for name,fields in PHOTO_GROUPS:
   self.group(name)
   for field in fields:self.slider(*field)
  self.queue_preview()
 def reset_photo(self):
  for key,scale in self.scales.items():scale.set_value(self.defaults[key])
 def show_original(self,active):
  if active:
   self.preview.stop();self.preview=AsyncPreview();self.load_picture(self.paths[0])
  else:self.queue_preview()
 def load_picture(self,src):
  try:self.picture_widget.set_filename(str(src))
  except Exception as e:self.notice.set_text(str(e))
 def background(self):
  self.picture();palette_row=box(Gtk.Orientation.HORIZONTAL,14);palette_name=label('Background','field-name');palette_name.set_size_request(125,-1);palette_name.set_valign(Gtk.Align.START);palette_row.append(palette_name);self.body.append(palette_row)
  grid=Gtk.FlowBox();grid.set_selection_mode(Gtk.SelectionMode.NONE);grid.set_min_children_per_line(9);grid.set_max_children_per_line(9);grid.set_row_spacing(4);grid.set_column_spacing(4);grid.set_hexpand(True);palette_row.append(grid);self.values['background']='#f8fbff,#55d3f4';first=None
  for color in PALETTE:
   b=Gtk.ToggleButton();b.add_css_class('swatch');b.set_tooltip_text(color);b.set_halign(Gtk.Align.CENTER)
   if first:b.set_group(first)
   else:first=b
   swatch=Gtk.DrawingArea();swatch.set_content_width(31);swatch.set_content_height(31)
   def draw(area,c,w,h,color=color):
    from PIL import ImageColor
    colors=color.split(',');g=cairo.LinearGradient(0,0,w,h)
    for t,part in [(0,colors[0]),(1,colors[-1])]:g.add_color_stop_rgb(t,*[v/255 for v in ImageColor.getrgb(part)])
    wheel.rounded(c,0,0,w,h,6);c.set_source(g);c.fill()
   swatch.set_draw_func(draw);b.set_child(swatch);b.set_active(color==self.values['background'])
   def selected(w,col=color):
    if w.get_active():
     self.values['background']=col
     self.queue_preview()
   b.connect('toggled',selected);grid.insert(b,-1)
  custom=Gtk.ColorButton();custom.set_use_alpha(False);custom.set_title('Background color');custom.set_tooltip_text('Choose a custom color');custom.set_halign(Gtk.Align.CENTER);custom.add_css_class('swatch')
  def custom_color(b):
   rgba=b.get_rgba();self.values['background']='#'+''.join(f'{round(v*255):02x}' for v in (rgba.red,rgba.green,rgba.blue));self.queue_preview()
  custom.connect('color-set',custom_color);grid.insert(custom,-1)
  for args in [('padding','Padding',0,600,1,64,' px'),('corners','Corners',0,200,1,24,' px'),('shadow','Shadow',0,200,1,30,' px')]:self.slider(*args)
  self.segments('ratio','Ratio',[('Auto','auto'),('1:1','1:1'),('16:9','16:9'),('4:5','4:5')],'auto');self.queue_preview()
 def generic(self):
  self.workflow=True;self.apply_button.set_label('Create copy');self.apply_button.set_sensitive(False)
  self.body.append(label(self.paths[0].name+(f' + {len(self.paths)-1} more' if len(self.paths)>1 else ''),'field-name',True))
  if len(self.paths)>1:self.file_order()
  crop=self.action.id in ('crop','redact','annotate') and kind(self.paths[0])=='image'
  video_rect=self.action.id in ('crop','redact') and kind(self.paths[0])=='video'
  if crop:
   from .crop import CropCanvas
   try:
    self.crop_canvas=CropCanvas(self.paths[0],self.crop_changed)
    if self.action.id!='crop':self.crop_canvas.set_rect(self.crop_canvas.image_width//4,self.crop_canvas.image_height//4,max(1,self.crop_canvas.image_width//2),max(1,self.crop_canvas.image_height//2))
    self.body.append(label('Drag to select, move or resize the rectangle. Values and handles stay in sync.','hint',True));self.body.append(self.crop_canvas)
   except (OSError,ValueError) as e:self.body.append(label('Visual crop unavailable for this input. Convert it to PNG first. '+str(e),'hint',True))
  if video_rect:
   self.rectangle_stage=box();self.body.append(self.rectangle_stage);self.load_video_rectangle()
  if crop or video_rect:
   self.geometry_grid=Gtk.Grid(column_spacing=18,row_spacing=6);self.geometry_grid.set_column_homogeneous(True);self.body.append(self.geometry_grid)
  self.body.append(label('Result preview','group-title'))
  self.picture();self.picture_widget.set_size_request(-1,150 if crop or video_rect else 290)
  fields=list(FIELDS.get(self.action.id,[]));k=kind(self.paths[0])
  if self.action.id.startswith('to:'):
   target=self.action.id[3:]
   if k=='image' and target not in ('zip','tar','tar.gz'):fields=[('quality','Image quality','85')]
   elif k=='audio':fields=[('bitrate','Audio bitrate (kbps)','192')]
   elif k=='video' and target not in ('zip','tar','tar.gz'):fields=[('crf','Video quality / CRF','23')]
   elif k=='pdf' and target in ('png','jpg'):fields=[('dpi','Resolution (DPI)','150')]
  if self.action.id=='compress':fields=[f for f in fields if f[0] in ({'quality'} if k=='image' else {'crf'} if k=='video' else {'bitrate'})]
  if crop and getattr(self,'crop_canvas',None):
   defaults=dict(zip(('x','y','width','height'),self.crop_canvas.rect))
   fields=[(key,title,str(defaults[key])) if key in defaults else (key,title,default) for key,title,default in fields]
  if self.action.id=='pdf_organize':
   try:
    from pypdf import PdfReader
    self.pdf_source_count=len(PdfReader(self.paths[0]).pages)
   except Exception:self.pdf_source_count=0
   if self.pdf_source_count:fields=[('pages','Page order',f'1-{self.pdf_source_count}')]
  ranges={'quality':(1,100,1),'crf':(0,51,1),'bitrate':(32,320,1),'dpi':(36,600,1),'font_size':(8,160,1),'opacity':(0,100,1),'volume':(0,4,.01),'speed':(.5,2,.01),'seconds':(1,120,1),'count':(1,60,1),'radius':(0,100,.1),'amount':(0,5,.1),'fade_in':(0,10,.1),'fade_out':(0,10,.1)}
  for key,title,default in fields:
   if key in ranges:self.slider(key,title,*ranges[key],float(default))
   elif key=='degrees':self.segments(key,title,[('90°',90),('180°',180),('270°',270)],90)
   elif key=='color':self.color_field(key,title,default)
   elif key=='shape':self.segments(key,'Shape',[('Text only','none'),('Rectangle','rectangle'),('Ellipse','ellipse'),('Arrow','arrow')],'rectangle')
   elif key=='axis':self.segments(key,'Direction',[('Horizontal','horizontal'),('Vertical','vertical')],'horizontal')
   elif key=='position':self.segments(key,title,[('Top left','top-left'),('Center','center'),('Bottom right','bottom-right')],'bottom-right')
   elif key in ('x','y','width','height') and hasattr(self,'geometry_grid'):
    entry=self.entry(key,title,default);entry.set_width_chars(8);row=entry.get_parent();self.body.remove(row);index=('x','y','width','height').index(key);self.geometry_grid.attach(row,index%2,index//2,1,1)
   else:self.entry(key,title,default)
  if self.action.id=='pdf_organize' and 0<getattr(self,'pdf_source_count',0)<=1000:self.pdf_order_controls()
  if k=='pdf' or self.action.id in ('image_pdf','pdf_merge'):
   self.preview_page=Gtk.SpinButton.new_with_range(1,1,1);row=box(Gtk.Orientation.HORIZONTAL);row.append(label('Preview page','field-name'));row.append(self.preview_page);self.body.append(row);self.preview_page.connect('value-changed',lambda *_:self.queue_preview())
  self.preview_details=Gtk.TextView();self.preview_details.set_editable(False);self.preview_details.set_cursor_visible(False);self.preview_details.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
  details=Gtk.ScrolledWindow();details.set_min_content_height(100);details.set_max_content_height(180);details.set_propagate_natural_height(True);details.set_child(self.preview_details);self.body.append(details)
  self.play_row([('Play result sample',self.play_workflow_preview)]) if k in ('audio','video') else None
  row=box(Gtk.Orientation.HORIZONTAL);row.append(button('Refresh preview',self.queue_preview));row.append(button('Choose another action',self.choose_action));self.body.append(row)
  self.body.append(label(self.action.hint or 'Adjust the details, review the result, then create a new copy.','hint',True))
  if not video_rect:self.queue_preview()
 def color_field(self,key,title,default):
  self.values[key]=default;row=box(Gtk.Orientation.HORIZONTAL);name=label(title,'field-name');name.set_hexpand(True);row.append(name);color=Gtk.ColorButton();color.set_use_alpha(False);rgba=Gdk.RGBA();rgba.parse(default.replace('0x','#'));color.set_rgba(rgba)
  def changed(widget):
   rgba=widget.get_rgba();self.values[key]=('0x' if default.startswith('0x') else '#')+''.join(f'{round(v*255):02x}' for v in (rgba.red,rgba.green,rgba.blue));self.queue_preview()
  color.connect('color-set',changed);row.append(color);self.body.append(row)
 def pdf_order_controls(self):
  self.pdf_page_order=list(range(1,self.pdf_source_count+1));self.pdf_order_list=Gtk.ListBox();self.pdf_order_list.set_selection_mode(Gtk.SelectionMode.SINGLE);self.refresh_pdf_order()
  scroll=Gtk.ScrolledWindow();scroll.set_min_content_height(100);scroll.set_max_content_height(160);scroll.set_propagate_natural_height(True);scroll.set_child(self.pdf_order_list);self.body.append(scroll)
  row=box(Gtk.Orientation.HORIZONTAL);row.append(button('Page up',lambda:self.move_pdf_page(-1)));row.append(button('Page down',lambda:self.move_pdf_page(1)));row.append(button('Remove page',self.remove_pdf_page));self.body.append(row)
 def refresh_pdf_order(self):
  child=self.pdf_order_list.get_first_child()
  while child:
   nxt=child.get_next_sibling();self.pdf_order_list.remove(child);child=nxt
  for page in self.pdf_page_order:self.pdf_order_list.append(label('Source page '+str(page),'hint'))
 def sync_pdf_order(self,index):
  self._syncing_pdf=True
  try:self.entries['pages'].set_text(','.join(map(str,self.pdf_page_order)))
  finally:self._syncing_pdf=False
  self.refresh_pdf_order();self.pdf_order_list.select_row(self.pdf_order_list.get_row_at_index(max(0,index)));self.queue_preview()
 def move_pdf_page(self,delta):
  row=self.pdf_order_list.get_selected_row()
  if row is None:return
  index=row.get_index();other=index+delta
  if not 0<=other<len(self.pdf_page_order):return
  self.pdf_page_order[index],self.pdf_page_order[other]=self.pdf_page_order[other],self.pdf_page_order[index];self.sync_pdf_order(other)
 def remove_pdf_page(self):
  row=self.pdf_order_list.get_selected_row()
  if row is None:return
  if len(self.pdf_page_order)<=1:self.notice.set_text('Keep at least one PDF page.');return
  index=row.get_index();del self.pdf_page_order[index];self.sync_pdf_order(min(index,len(self.pdf_page_order)-1))
 def load_video_rectangle(self):
  from .crop import CropCanvas
  source=self.paths[0]
  def worker(stage,runner):
   ffmpeg=dependencies().get('FFmpeg')
   if not ffmpeg:raise ValueError('Video selection needs FFmpeg.')
   path=stage/'frame.png';runner.run([ffmpeg,'-v','error','-i',source,'-frames:v','1','-y',path]);return path.read_bytes()
  def done(data,error):
   if error:self.notice.set_text(error[:180]);return
   self.crop_canvas=CropCanvas(io.BytesIO(data),self.crop_changed,pixel_step=2);self.rectangle_stage.append(self.crop_canvas)
   if self.action.id=='redact':self.crop_canvas.set_rect(self.crop_canvas.image_width//4,self.crop_canvas.image_height//4,max(2,self.crop_canvas.image_width//2),max(2,self.crop_canvas.image_height//2))
   self.rectangle_stage.prepend(label('Drag the rectangle; video coordinates snap to even pixels.','hint',True));self.crop_changed(*self.crop_canvas.rect)
  self.canvas_preview.submit(worker,done)
 def crop_changed(self,x,y,width,height):
  self._syncing_crop=True
  try:
   for key,value in zip(('x','y','width','height'),(x,y,width,height)):
    self.values[key]=value
    if key in self.entries:self.entries[key].set_text(str(value))
  finally:self._syncing_crop=False
  self.queue_preview()
 def file_order(self):
  self.order_list=Gtk.ListBox();self.order_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
  for path in self.paths:self.order_list.append(label(path.name,'hint'))
  self.body.append(label('Files are processed in this order. Select one to move it.','hint',True));order_scroll=Gtk.ScrolledWindow();order_scroll.set_min_content_height(90);order_scroll.set_max_content_height(160);order_scroll.set_propagate_natural_height(True);order_scroll.set_child(self.order_list);self.body.append(order_scroll)
  row=box(Gtk.Orientation.HORIZONTAL);row.append(button('Move up',lambda:self.move_file(-1)));row.append(button('Move down',lambda:self.move_file(1)));self.body.append(row)
 def move_file(self,delta):
  selected=self.order_list.get_selected_row()
  if selected is None:return
  index=selected.get_index();other=index+delta
  if not 0<=other<len(self.paths):return
  self.paths[index],self.paths[other]=self.paths[other],self.paths[index]
  child=self.order_list.get_first_child()
  while child:
   nxt=child.get_next_sibling();self.order_list.remove(child);child=nxt
  for path in self.paths:self.order_list.append(label(path.name,'hint'))
  self.order_list.select_row(self.order_list.get_row_at_index(other));self.queue_preview()
 def choose_action(self):
  if getattr(self,'action_popup',None):self.action_popup.unparent()
  popup=Gtk.Popover();anchor=self.body.get_last_child();popup.set_parent(anchor);panel=box(spacing=4)
  for action in choices(self.paths,'tools')+choices(self.paths,'convert'):
   def select(a=action):
    popup.popdown();self.app.set_files(self.paths);self.app.tool_options(a);self.close()
   panel.append(button(action.label,select))
  scroll=Gtk.ScrolledWindow();scroll.set_max_content_height(360);scroll.set_propagate_natural_height(True);scroll.set_child(panel);popup.set_child(scroll);popup.popup();self.action_popup=popup
 def play_workflow_preview(self):
  result=self.preview_result
  if not self.preview_ready or not result or not result.media:self.notice.set_text('Generate a playable preview first.');return
  player=dependencies().get('FFplay')
  if not player:self.notice.set_text('Playback needs ffplay. The waveform/frame preview is still available.');return
  self.stop_audio()
  if not self.audio_dir:self.audio_dir=tempfile.TemporaryDirectory(prefix='petal-listen-')
  path=Path(self.audio_dir.name)/('sample'+result.suffix);path.write_bytes(result.media)
  args=[player,'-v','error','-autoexit']+(['-nodisp'] if kind(path)=='audio' else [])
  self.player=subprocess.Popen(args+[str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
  for stop in self.stop_buttons:stop.set_visible(True)
 def queue_preview(self):
  if self.closed:return
  if self.debounce:GLib.source_remove(self.debounce)
  if self.workflow:
   self.preview_ready=False;self.apply_button.set_sensitive(False);self.notice.set_text('Updating preview…')
   if hasattr(self,'picture_widget'):self.picture_widget.set_opacity(.35)
   self.preview.stop();self.preview=AsyncPreview()
  self.debounce=GLib.timeout_add(180,self.render_preview)
 def render_preview(self):
  self.debounce=None
  if self.workflow:return self.render_workflow_preview()
  return self.render_photo_preview()
 def render_workflow_preview(self):
  from .workflows import build_preview
  paths=list(self.paths);params=dict(self.values);action=self.action.id;page=int(self.preview_page.get_value()) if hasattr(self,'preview_page') else 1
  def worker(stage,runner):return build_preview(paths,action,params,stage,runner,page)
  def done(result,error):
   if error:
    self.preview_ready=False;self.apply_button.set_sensitive(False);self.notice.set_text('Preview needs attention: '+error[:180]);self.preview_details.get_buffer().set_text(error);return
   self.preview_result=result;self.picture_widget.set_opacity(1);self.preview_details.get_buffer().set_text(result.text);self.picture_widget.set_visible(result.image is not None)
   if result.image:
    try:self.picture_widget.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(result.image)))
    except GLib.Error as e:self.notice.set_text('Unable to display preview: '+str(e));return
   if hasattr(self,'preview_page'):
    adjustment=self.preview_page.get_adjustment()
    if int(adjustment.get_upper())!=result.pages:self.preview_page.set_range(1,result.pages)
   self.preview_ready=True;self.apply_button.set_sensitive(True);self.notice.set_text('Preview ready. Apply creates a new copy; originals stay unchanged.')
  self.preview.submit(worker,done);return False
 def render_photo_preview(self):
  self.debounce=None
  if not hasattr(self,'picture_widget') or self.action.id not in ('edit','background','annotate','crop','redact','resize','rotate','flip','grayscale','compress'):return False
  if getattr(self,'original_button',None) and self.original_button.get_active():return False
  source=self.paths[0];params=dict(self.values);action=self.action.id
  def worker(stage,runner):
   # Coordinates and padding keep the same meaning as the exported result.
   if action=='edit':
    src=scaled_source(source,stage/'source.png');out=stage/'preview.png';_edit_image(src,out,'png',params,runner)
   elif action=='background':
    src=stage/'source.png'
    from PIL import Image
    with Image.open(source) as im:ratio=min(1,1000/max(im.size))
    scaled_source(source,src)
    preview_params=dict(params)
    for key in ('padding','corners','shadow'):preview_params[key]=float(params.get(key,0))*ratio
    out=stage/'preview.png';_add_background(src,out,preview_params)
   else:out=execute([source],action,params,stage,cancel=runner.cancel)[0]
   return out.read_bytes()
  def done(data,error):
   if error:self.notice.set_text('Preview: '+error[:150]);return
   try:self.picture_widget.set_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)));self.notice.set_text('Original files are preserved.')
   except GLib.Error as e:self.notice.set_text(str(e))
  self.preview.submit(worker,done);return False
 def audio(self):
  self.window.set_default_size(600,530);self.values.update(start=0,end=1,mode='stereo',left=1,right=1);self.apply_button.set_sensitive(False)
  self.audio_description=label('Loading audio…','field-name');self.body.append(self.audio_description)
  self.wave=Gtk.DrawingArea();self.wave.set_content_width(540);self.wave.set_content_height(150);self.wave.set_draw_func(self.draw_wave);self.body.append(self.wave)
  self.wave_images=[];self.time_readout=label('','time');self.body.append(self.time_readout)
  if self.action.id in ('trim','bleep'):
   drag=Gtk.GestureDrag();drag.connect('drag-begin',self.drag_begin);drag.connect('drag-update',self.drag_update);drag.connect('drag-end',self.drag_end);self.wave.add_controller(drag)
  if self.action.id=='trim':
   self.start_scale=self.slider('start','Start',0,1,.01,0,' s',self.trim_changed);self.end_scale=self.slider('end','End',0,1,.01,1,' s',self.trim_changed)
   self.start_scale.get_parent().set_visible(False);self.end_scale.get_parent().set_visible(False)
   self.play_row([('▶  Play Selected Range',lambda:self.play_audio(selected=True))])
  elif self.action.id=='bleep':
   self.audio_description.set_text('Drag across the waveform to add a muted range.')
   self.wave.set_content_height(190)
   self.body.append(label('Drag across the Bleep lane to add a range. Drag an edge to adjust it. Delete removes the selected range.','hint',True))
   self.play_row([('▶  Original',self.play_audio),('▶  With Bleeps',lambda:self.play_audio(processed=True))],'Preview');self.apply_button.set_label('Save Bleeped Copy')
  else:
   self.segments('mode','Mode',[('Mono','mono'),('Stereo','stereo')],'stereo',self.channel_changed)
   self.slider('left','Left level',0,4,.01,1,'',self.channel_changed,lambda x:f'{x*100:.0f}%');self.slider('right','Right level',0,4,.01,1,'',self.channel_changed,lambda x:f'{x*100:.0f}%')
   self.play_row([('▶  Play Output',lambda:self.play_audio(processed=True))])
  source=self.paths[0]
  def worker(stage,runner):
   info=json.loads(runner.run([dependencies()['FFprobe'],'-v','quiet','-show_format','-show_streams','-of','json',source],max_output=1024*1024,truncate=False))
   duration=float(info.get('format',{}).get('duration',0));channels=int(next(s for s in info['streams'] if s.get('codec_type')=='audio').get('channels',1));images=[];levels=[]
   for channel in range(min(channels,2) if self.action.id=='channels' else 1):
    image=stage/f'wave-{channel}.png';filt=(f'pan=mono|c0=c{channel},' if self.action.id=='channels' else '')+'showwavespic=s=192x240:colors=0xff5300:draw=full:filter=peak:scale=sqrt'
    runner.run([dependencies()['FFmpeg'],'-v','error','-i',source,'-filter_complex',filt,'-frames:v','1','-y',image]);images.append(image.read_bytes())
    from PIL import Image
    with Image.open(image) as im:
     alpha=im.convert('RGBA').getchannel('A');amps=[]
     for x in range(im.width):
      column=alpha.crop((x,0,x+1,im.height));bounds=column.getbbox();amps.append(max(abs(bounds[1]-im.height/2),abs(bounds[3]-im.height/2)) if bounds else 0)
     maximum=max(amps) or 1;levels.append([value/maximum for value in amps])
   if duration<=0:raise ValueError('Cannot determine the audio duration.')
   return duration,images,levels
  def done(result,error):
   if error:self.notice.set_text(error[:180]);self.audio_description.set_text('Audio preview unavailable.');return
   self.source_duration,images,self.wave_levels=result;self.wave_images=[cairo.ImageSurface.create_from_png(io.BytesIO(data)) for data in images];self.values['end']=self.source_duration
   if self.action.id=='trim':
    self.start_scale.set_range(0,self.source_duration);self.end_scale.set_range(0,self.source_duration);self.end_scale.set_value(self.source_duration);self.audio_description.set_text('Drag the ends to trim')
   elif self.action.id=='channels':self.audio_description.set_text('Output channel preview')
   self.audio_readout();self.apply_button.set_sensitive(self.action.id!='bleep');self.wave.queue_draw()
  self.wave_preview.submit(worker,done)
 def play_row(self,items,title=''):
  row=box(Gtk.Orientation.HORIZONTAL,10);spacer=label(title,'field-name');spacer.set_hexpand(True);row.append(spacer)
  stop=button('■',self.stop_audio);stop.set_tooltip_text('Stop playback');stop.set_visible(False);row.append(stop);self.stop_buttons.append(stop)
  for text,callback in items:row.append(button(text,callback))
  self.body.append(row)
 def audio_readout(self):
  if self.action.id=='trim':self.time_readout.set_text('Start '+time_label(self.values['start'])+'                         End '+time_label(self.values['end']))
  elif self.action.id=='bleep':self.time_readout.set_text(f'Bleeps  {len(self.ranges)}                         '+time_label(self.source_duration));self.apply_button.set_sensitive(bool(self.ranges));self.notice.set_text('Original files are preserved.' if self.ranges else 'Add at least one bleep range.')
  else:self.time_readout.set_text(time_label(self.source_duration))
 def trim_changed(self):
  if not hasattr(self,'wave'):return
  if self.values['start']>=self.values['end']:self.apply_button.set_sensitive(False)
  else:self.apply_button.set_sensitive(self.source_duration>0)
  self.audio_readout();self.wave.queue_draw()
 def channel_changed(self):
  if hasattr(self,'wave'):self.wave.queue_draw()
 def wave_time(self,x):
  offset=58 if self.action.id=='bleep' else 0
  return max(0,min(self.source_duration,(x-offset)/max(1,self.wave.get_width()-offset)*self.source_duration))
 def draw_wave(self,area,c,w,h):
  bleep=self.action.id=='bleep';offset=58 if bleep else 0;track_w=w-offset
  wheel.rounded(c,offset,0,track_w,h,9);c.set_source_rgba(.2,.1,0,.045);c.fill()
  count=2 if self.action.id=='channels' and self.values.get('mode')=='stereo' else 1
  for i in range(count):
   top=68 if bleep else i*h/count;hh=h-74 if bleep else h/count
   if self.wave_levels:
    levels=self.wave_levels[min(i,len(self.wave_levels)-1)];volume=self.values.get('left' if i==0 else 'right',1) if self.action.id=='channels' else 1
    spacing=track_w/len(levels);c.save();c.rectangle(offset,top,track_w,hh);c.clip();c.set_source_rgb(*wheel.ORANGE);c.set_line_width(max(1,spacing*.47));c.set_line_cap(cairo.LINE_CAP_ROUND)
    for j,value in enumerate(levels):
     amplitude=max(.5,min(hh/2-6,value*volume*(hh/2-8)));x=offset+(j+.5)*spacing;c.move_to(x,top+hh/2-amplitude);c.line_to(x,top+hh/2+amplitude)
    c.stroke();c.restore()
  if self.source_duration<=0:return
  if self.action.id=='trim':
   a=self.values['start']/self.source_duration*w;b=self.values['end']/self.source_duration*w
   c.set_source_rgba(.4,.4,.4,.23);c.rectangle(0,0,a,h);c.rectangle(b,0,w-b,h);c.fill()
   c.set_source_rgb(*wheel.ORANGE);c.set_line_width(2);wheel.rounded(c,a+1,1,max(1,b-a-2),h-2,6);c.stroke()
   for x in (a,b):
    left=max(0,min(w-12,x-6));c.set_source_rgb(*wheel.ORANGE);c.rectangle(left,0,12,h);c.fill();c.set_source_rgb(1,1,1);c.rectangle(left+5,h*.35,2,h*.3);c.fill()
  elif bleep:
   wheel.text(c,'Bleep',0,29,12,wheel.INK,False,False);wheel.text(c,'Audio',0,130,12,wheel.INK,False,False)
   c.set_source_rgba(0,0,0,.15);c.set_line_width(1);c.move_to(offset,54);c.line_to(w,54);c.stroke()
   for i,(start,end) in enumerate(self.ranges):
    a=offset+start/self.source_duration*track_w;b=offset+end/self.source_duration*track_w;c.set_source_rgba(1,.28,0,.3 if i==self.range_index else .16);wheel.rounded(c,a,4,max(1,b-a),45,4);c.fill_preserve();c.set_source_rgb(*wheel.ORANGE);c.set_line_width(1.5);c.stroke()
 def drag_begin(self,gesture,x,y):
  if self.source_duration<=0:return
  self.drag_x=x;self.drag_original=list(self.ranges);t=max(0,min(self.source_duration,self.wave_time(x)));self.drag_time=t
  if self.action.id=='trim':self.drag_kind='start' if abs(t-self.values['start'])<=abs(t-self.values['end']) else 'end'
  else:
   self.drag_kind='new';self.range_index=-1
   for i,(a,b) in enumerate(self.ranges):
    if min(abs(t-a),abs(t-b))/self.source_duration*self.wave.get_width()<9:self.range_index=i;self.drag_kind='start' if abs(t-a)<abs(t-b) else 'end';break
   if self.drag_kind=='new':self.ranges.append((t,t));self.range_index=len(self.ranges)-1
 def drag_update(self,gesture,dx,dy):
  if self.source_duration<=0:return
  t=max(0,min(self.source_duration,self.wave_time(self.drag_x+dx)))
  if self.action.id=='trim':
   if self.drag_kind=='start':self.start_scale.set_value(min(t,self.values['end']-.01))
   else:self.end_scale.set_value(max(t,self.values['start']+.01))
  else:
   if self.drag_kind=='new':self.ranges[self.range_index]=tuple(sorted((self.drag_time,t)))
   else:
    a,b=self.drag_original[self.range_index];self.ranges[self.range_index]=(min(t,b-.01),b) if self.drag_kind=='start' else (a,max(t,a+.01))
   self.audio_readout();self.wave.queue_draw()
 def drag_end(self,gesture,dx,dy):
  self.drag_update(gesture,dx,dy)
  if self.action.id=='bleep':self.ranges=[(a,b) for a,b in self.ranges if b-a>=.01];self.range_index=min(self.range_index,len(self.ranges)-1);self.audio_readout();self.wave.queue_draw()
 def remove_range(self):
  if 0<=self.range_index<len(self.ranges):self.ranges.pop(self.range_index);self.range_index=-1;self.audio_readout();self.wave.queue_draw()
 def stop_audio(self):
  self.media_preview.stop();self.media_preview=AsyncPreview()
  for b in self.stop_buttons:b.set_visible(False)
  if self.player and self.player.poll() is None:
   self.player.terminate()
   try:self.player.wait(timeout=.5)
   except subprocess.TimeoutExpired:self.player.kill();self.player.wait()
  self.player=None
 def play_audio(self,selected=False,processed=False):
  self.stop_audio();player=dependencies().get('FFplay')
  if not player:self.notice.set_text('Audio playback needs ffplay, included with many FFmpeg packages.');return
  if not self.source_duration:return
  params=dict(self.values);params['ranges']=','.join(f'{a:.4f}-{b:.4f}' for a,b in self.ranges)
  if processed and self.action.id=='bleep' and not self.ranges:self.notice.set_text('Add a range first.');return
  def start(path):
   if self.closed:return
   args=[player,'-v','error','-nodisp','-autoexit']
   if selected:args+=['-ss',str(self.values['start']),'-t',str(max(.01,self.values['end']-self.values['start']))]
   for b in self.stop_buttons:b.set_visible(True)
   self.player=subprocess.Popen(args+[str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
  if not processed:start(self.paths[0]);return
  if not self.audio_dir:self.audio_dir=tempfile.TemporaryDirectory(prefix='petal-listen-')
  target=Path(self.audio_dir.name)/f'output-{uuid.uuid4().hex}.wav'
  def worker(stage,runner):
   output=execute(self.paths,self.action.id,params,stage,cancel=runner.cancel)[0];runner.check();shutil.copyfile(output,target);return target
  def done(path,error):
   if error:self.notice.set_text(error[:150])
   else:start(path)
  self.media_preview.submit(worker,done)
