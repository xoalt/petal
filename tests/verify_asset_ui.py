"""Exercise and render the native reference-based editors in an isolated instance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
parser=argparse.ArgumentParser();parser.add_argument('--output-dir');args=parser.parse_args()
scratch=tempfile.TemporaryDirectory(prefix='petal-asset-ui-');base=Path(scratch.name);output=Path(args.output_dir).resolve() if args.output_dir else base/'report';output.mkdir(parents=True,exist_ok=True)
os.environ['PETAL_APP_ID']='io.github.petal.AssetVerification';os.environ['PETAL_DISABLE_TRAY']='1';os.environ['PETAL_STATE_DIR']=str(base/'state')
from PIL import Image
import cairo
from petal.app import Petal
from petal.catalog import Action
from petal.legacy import Gtk,GLib
image=base/'photo.png';im=Image.new('RGB',(320,240));pixels=im.load()
for y in range(240):
 for x in range(320):pixels[x,y]=(40+x//2,80+y//2,90+x//3)
im.save(image)
audio=base/'tone.wav';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=3','-af',"volume='0.1+0.9*abs(sin(2*PI*t))':eval=frame",'-ac','2',str(audio)],check=True)
source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (image,audio)}

def duration(path):return float(json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(path)]))['format']['duration'])

class Check(Petal):
 def __init__(self):super().__init__();self.checks={};self.step=0;self.deadline=time.monotonic()+65;self.frames=0;self.failed=False;self.editor=None
 def assert_check(self,name,value):
  self.checks[name]=bool(value)
  if not value:raise AssertionError(name)
 def show_editor(self,id,title,src=image):
  if self.editor:self.editor.close()
  self.set_files([src]);self.tool_options(Action(id,title));self.editor=self.editors[-1];self.paint=Gtk.WidgetPaintable.new(self.editor.shell);self.frames=0
 def capture(self,name,widget=None,paint=None):
  widget=widget or self.editor.shell;paint=paint or self.paint;snapshot=Gtk.Snapshot();paint.snapshot(snapshot,widget.get_width(),widget.get_height());node=snapshot.to_node()
  if node is None:raise AssertionError('No render node for '+name)
  renderer=self.editor.window.get_renderer() if self.editor else self.main.get_renderer();texture=renderer.render_texture(node,None);texture.save_to_png(str(output/(name+'.png')))
 def do_command_line(self,cmd):
  self.settings.update(notify=False,drop_target=False,output_dir=str(base/'results'));self.set_files([image]);self.show_main();self.wheel_paint=Gtk.WidgetPaintable.new(self.drawing)
  GLib.timeout_add(100,self.advance);return 0
 def advance(self):
  self.frames+=1
  try:
   if time.monotonic()>self.deadline:raise TimeoutError('Editor test timed out at step '+str(self.step))
   if self.frames<4:return True
   if self.step==0:
    if not self.thumbnail:return True
    self.assert_check('reference_conversion_wheel_eight',len(self.page_items())==8);self.assert_check('file_thumbnail_loaded',self.thumbnail.get_width()>0);self.capture('wheel',self.drawing,self.wheel_paint);self.switch_mode('tools')
    self.assert_check('reference_image_tools_seven',len(self.page_items())==7);self.frames=0;self.step=1
   elif self.step==1:self.capture('tool-wheel',self.drawing,self.wheel_paint);self.show_editor('edit','Edit Photo');self.step=2
   elif self.step==2:
    e=self.editor
    if not e.picture_widget.get_paintable():return True
    self.assert_check('photo_14_adjustment_sliders',len(e.scales)==14);self.capture('edit-photo');e.scales['exposure'].set_value(1.25);self.assert_check('photo_slider_updates_parameter',e.values['exposure']==1.25);e.reset_photo();self.assert_check('photo_reset_restores_defaults',all(e.values[k]==v for k,v in e.defaults.items()));self.show_editor('background','Add BG');self.step=3
   elif self.step==3:
    e=self.editor
    if not e.picture_widget.get_paintable():return True
    self.capture('add-background');e.scales['padding'].set_value(40);e.scales['corners'].set_value(0);e.scales['shadow'].set_value(0);e.values['ratio']='auto';e.apply();self.editor=None;self.step=4;self.frames=0
   elif self.step==4:
    if self.busy:return True
    self.assert_check('background_creates_copy',bool(self.last_outputs))
    with Image.open(self.last_outputs[0]) as im:self.assert_check('background_sliders_affect_export',im.size==(400,320))
    self.show_editor('trim','Trim Audio',audio);self.step=5
   elif self.step==5:
    e=self.editor
    if not e.wave_images:return True
    self.capture('trim-audio');e.drag_begin(None,0,60);e.drag_update(None,e.wave.get_width()*.2,0);self.assert_check('trim_handle_drags',abs(e.values['start']-.6)<.03);e.start_scale.set_value(.5);e.end_scale.set_value(1.5);e.apply();self.editor=None;self.step=6;self.frames=0
   elif self.step==6:
    if self.busy:return True
    self.assert_check('trim_range_affects_export',bool(self.last_outputs) and abs(duration(self.last_outputs[0])-1)<.05);self.show_editor('channels','Convert Audio Channels',audio);self.step=7
   elif self.step==7:
    e=self.editor
    if not e.wave_images:return True
    self.capture('audio-channels');self.assert_check('channel_previews_loaded',len(e.wave_images)==2);e.values['mode']='mono';e.scales['left'].set_value(.5);e.scales['right'].set_value(.5);e.apply();self.editor=None;self.step=8;self.frames=0
   elif self.step==8:
    if self.busy:return True
    info=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-of','json',str(self.last_outputs[0])]))
    self.assert_check('channel_selection_affects_export',info['streams'][0]['channels']==1);self.show_editor('bleep','Bleep Audio',audio);self.step=9
   elif self.step==9:
    e=self.editor
    if not e.wave_images:return True
    e.drag_begin(None,e.wave.get_width()*.2,50);e.drag_end(None,e.wave.get_width()*.2,0);self.assert_check('bleep_range_created',len(e.ranges)==1 and e.apply_button.get_sensitive());self.frames=0;self.step=10
   elif self.step==10:
    self.capture('bleep-audio');self.editor.remove_range();self.assert_check('bleep_range_removed',not self.editor.ranges and not self.editor.apply_button.get_sensitive());self.editor.close();self.editor=None
    self.assert_check('sources_unchanged',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in source_hashes.items()))
    self.assert_check('native_editors_close_cleanly',not self.editors)
    with Image.open(output/'edit-photo.png') as im:self.assert_check('material_is_translucent',0<im.getpixel((300,30))[3]<255)
    self.complete();return False
  except Exception:
   self.failed=True;traceback.print_exc();self.complete();return False
  return True
 def complete(self):
  (output/'checks.json').write_text(json.dumps({'checks':self.checks,'passed':not self.failed,'rendering':'Actual GTK widgets; transparent surfaces are preserved in PNG alpha.'},indent=2)+'\n');print(json.dumps(self.checks),flush=True);self.request_quit()

if not Gtk.init_check():raise SystemExit('A Wayland desktop is required.')
app=Check();result=app.run(['petal-asset-verification']);raise SystemExit(result or int(app.failed))
