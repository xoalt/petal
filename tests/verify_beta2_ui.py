"""Native Beta 2 checks: real widgets, gesture signals and two-way crop fields."""
import argparse,hashlib,json,os,subprocess,sys,tempfile,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);args=p.parse_args();out=Path(args.output_dir).resolve();out.mkdir(parents=True,exist_ok=True)
scratch=tempfile.TemporaryDirectory(prefix='petal-beta2-');base=Path(scratch.name)
os.environ.update(PETAL_STATE_DIR=str(base/'state'),PETAL_APP_ID='io.github.xoalt.Petal.BetaTwoCheck',PETAL_DISABLE_TRAY='1',GSETTINGS_BACKEND='memory')
from PIL import Image
from pypdf import PdfReader,PdfWriter
from petal.app import Petal
from petal.catalog import Action
from petal.legacy import Gtk,GLib
from petal.engine import execute
image=base/'landscape.png';im=Image.new('RGB',(320,240));pixels=im.load()
for y in range(240):
 for x in range(320):pixels[x,y]=(30+x//2,50+y//2,180-x//3)
im.save(image);second=base/'second.png';Image.new('RGB',(200,100),'#47a788').save(second)
video=base/'clip.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=160x120:d=4','-c:v','libx264',str(video)],check=True)
pdf=base/'pages.pdf';w=PdfWriter();w.add_blank_page(width=160,height=240);w.add_blank_page(width=240,height=160)
with pdf.open('wb') as f:w.write(f)
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (image,second,video,pdf)}
class Check(Petal):
 def __init__(self):super().__init__();self.checks={};self.failed=False;self.stage=0;self.deadline=time.monotonic()+120;self.editor=None
 def check(self,key,value):
  self.checks[key]=bool(value)
  if not value:raise AssertionError(key)
 def open_editor(self,action,paths):
  if self.editor:self.editor.close()
  self.set_files(paths);self.tool_options(Action(action,action.replace('_',' ').title()));self.editor=self.editors[-1]
 def ready(self):return self.editor and self.editor.preview_ready
 def capture(self,name):
  widget=self.editor.shell;paint=Gtk.WidgetPaintable.new(widget);snap=Gtk.Snapshot();paint.snapshot(snap,widget.get_width(),widget.get_height());node=snap.to_node();self.check('render_'+name,node is not None);self.editor.window.get_renderer().render_texture(node,None).save_to_png(str(out/(name+'.png')))
 def point(self,x,y):
  scale,ox,oy=self.editor.crop_canvas.transform();return ox+x*scale,oy+y*scale
 def drag(self,x,y,dx,dy):
  canvas=self.editor.crop_canvas;scale,_,_=canvas.transform();model=canvas.observe_controllers();gesture=next(model.get_item(i) for i in range(model.get_n_items()) if isinstance(model.get_item(i),Gtk.GestureDrag));px,py=self.point(x,y)
  gesture.emit('drag-begin',px,py);gesture.emit('drag-update',dx*scale,dy*scale);gesture.emit('drag-end',dx*scale,dy*scale)
 def rect_values(self):return tuple(int(float(self.editor.values[k])) for k in ('x','y','width','height'))
 def do_command_line(self,cmd):
  self._skip_onboarding=True;self.settings.update(setup_completed=True,drop_target=False,notify=False,output_dir=str(base/'exports'));self.set_files([image]);self.show_main()
  self.mode='convert';items=self.current_items();index=next(i for i,a in enumerate(items) if a.id=='to:webp');self.page=index//self.page_capacity();self.selected=index%self.page_capacity();self.run_selected();self.editor=self.editors[-1]
  self.check('format_leaf_opens_editor_before_export',not self.busy and not self.jobs and self.editor.workflow);GLib.timeout_add(120,self.advance);return 0
 def advance(self):
  try:
   if time.monotonic()>self.deadline:raise AssertionError('Timed out at stage '+str(self.stage)+' · '+(self.editor.notice.get_text() if self.editor else ''))
   if self.stage==0:
    if not self.ready():return True
    self.check('conversion_has_actual_image_preview',self.editor.picture_widget.get_paintable() is not None);self.check('apply_enabled_after_preview',self.editor.apply_button.get_sensitive());self.capture('conversion');self.editor.apply();self.stage=1
   elif self.stage==1:
    if self.busy:return True
    self.check('apply_writes_a_copy',bool(self.last_outputs) and self.last_outputs[0].suffix=='.webp');self.check('continue_action_available',self.continue_button.get_visible());outputs=list(self.last_outputs);self.continue_results();self.check('results_can_feed_next_action',self.paths==outputs and self.mode=='tools');self.open_editor('crop',[image]);self.stage=2
   elif self.stage==2:
    if not self.ready():return True
    self.drag(50,40,150,120);self.check('drag_updates_crop_fields',self.rect_values()==(50,40,150,120));self.check('drag_invalidates_old_preview',not self.editor.preview_ready);self.stage=3
   elif self.stage==3:
    if not self.ready():return True
    paint=self.editor.picture_widget.get_paintable();self.check('crop_preview_matches_drag',paint.get_width()==150 and paint.get_height()==120);self.editor.entries['width'].set_text('96');self.check('field_updates_crop_handles',self.editor.crop_canvas.rect==(50,40,96,120));self.stage=4
   elif self.stage==4:
    if not self.ready():return True
    self.drag(80,80,20,10);self.check('crop_selection_can_move',self.rect_values()==(70,50,96,120));self.drag(166,170,30,-20);self.check('corner_handle_resizes_fields',self.rect_values()==(70,50,126,100));self.stage=5
   elif self.stage==5:
    if not self.ready():return True
    saved=execute([image],'crop',dict(self.editor.values),base/'crop-export')[0]
    with Image.open(saved) as exported:self.check('saved_crop_matches_selection',exported.size==(126,100))
    self.capture('drag-crop');self.editor.entries['width'].set_text('9999');self.stage=6
   elif self.stage==6:
    if 'needs attention' not in self.editor.notice.get_text():return True
    self.check('invalid_crop_blocks_apply',not self.editor.apply_button.get_sensitive());self.open_editor('watermark',[image]);self.stage=7
   elif self.stage==7:
    if not self.ready():return True
    self.previous=self.editor.preview_result.image;self.editor.entries['text'].set_text('Beta 2');self.editor.scales['opacity'].set_value(90);self.stage=8
   elif self.stage==8:
    if not self.ready():return True
    self.check('watermark_details_update_preview',self.editor.preview_result.image!=self.previous);self.capture('watermark');self.open_editor('crop',[video]);self.stage=9
   elif self.stage==9:
    if not self.ready() or not getattr(self.editor,'crop_canvas',None):return True
    self.editor.entries['width'].set_text('64');self.editor.entries['height'].set_text('48');self.editor.entries['x'].set_text('16');self.editor.entries['y'].set_text('8');self.check('video_crop_fields_drive_handles',self.editor.crop_canvas.rect==(16,8,64,48));self.stage=10
   elif self.stage==10:
    if not self.ready():return True
    self.check('video_crop_has_frame_and_playable_sample',bool(self.editor.preview_result.image) and bool(self.editor.preview_result.media));self.capture('video-crop');self.open_editor('pdf_organize',[pdf]);self.stage=11
   elif self.stage==11:
    if not self.ready():return True
    self.check('pdf_has_rendered_pages',self.editor.preview_result.pages==2 and bool(self.editor.preview_result.image));self.editor.pdf_order_list.select_row(self.editor.pdf_order_list.get_row_at_index(1));self.editor.move_pdf_page(-1);self.check('pdf_buttons_update_page_order_field',self.editor.entries['pages'].get_text()=='2,1');self.editor.entries['pages'].set_text('1,2');self.check('pdf_page_order_field_updates_list',self.editor.pdf_page_order==[1,2]);self.editor.preview_page.set_value(2);self.stage=12
   elif self.stage==12:
    if not self.ready():return True
    self.check('pdf_preview_can_change_pages',int(self.editor.preview_page.get_value())==2);self.capture('pdf-pages');self.open_editor('image_pdf',[image,second]);self.stage=13
   elif self.stage==13:
    if not self.ready():return True
    self.editor.order_list.select_row(self.editor.order_list.get_row_at_index(1));self.editor.move_file(-1);self.check('batch_order_can_be_changed',self.editor.paths==[second,image]);self.stage=14
   elif self.stage==14:
    if not self.ready():return True
    saved=execute(self.editor.paths,'image_pdf',{},base/'ordered')[0];self.check('batch_export_uses_reviewed_order',int(PdfReader(saved).pages[0].mediabox.width)<int(PdfReader(saved).pages[1].mediabox.width));self.capture('batch-order');self.complete();return False
   return True
  except Exception:self.failed=True;traceback.print_exc();self.complete();return False
 def complete(self):
  for path,digest in hashes.items():self.checks['original_preserved_'+Path(path).name]=hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
  if not all(self.checks.values()):self.failed=True
  (out/'checks.json').write_text(json.dumps({'passed':not self.failed,'checks':self.checks},indent=2)+'\n');print(json.dumps(self.checks),flush=True);self.request_quit()
app=Check();result=app.run(['petal-beta2-check']);raise SystemExit(result or int(app.failed))
