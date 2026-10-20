"""Content and original-file guarantees for Beta 2 tools and previews."""
import hashlib,io,json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from PIL import Image,ImageStat
from pypdf import PdfReader,PdfWriter
from petal.engine import execute,Runner,ConversionError
from petal.workflows import build_preview

class BetaTwoTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.source=self.base/'pattern.png'
  im=Image.new('RGB',(160,120));pixels=im.load()
  for y in range(im.height):
   for x in range(im.width):pixels[x,y]=((x%8)*30,(y%8)*30,80)
  im.save(self.source);self.digest=hashlib.sha256(self.source.read_bytes()).hexdigest();self.out=self.base/'results'
 def tearDown(self):self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(),self.digest);self.tmp.cleanup()
 def image(self,action,params=None):return execute([self.source],action,params,self.out)[0]
 def test_blur_reduces_local_variation_and_sharpen_changes_pixels(self):
  with Image.open(self.source) as original,Image.open(self.image('blur',{'radius':5})) as blurred:
   self.assertLess(ImageStat.Stat(blurred).var[0],ImageStat.Stat(original).var[0])
  with Image.open(self.image('sharpen',{'amount':3})) as sharpened,Image.open(self.source) as original:self.assertNotEqual(sharpened.convert('RGB').tobytes(),original.tobytes())
 def test_invert_sepia_border_and_watermark_content(self):
  with Image.open(self.image('invert')) as image:self.assertEqual(image.getpixel((1,1))[:3],(225,225,175))
  with Image.open(self.image('sepia')) as image:r,g,b=image.getpixel((1,1))[:3];self.assertGreaterEqual(r,g);self.assertGreaterEqual(g,b)
  with Image.open(self.image('border',{'width':7,'color':'#ff0000'})) as image:self.assertEqual(image.size,(174,134));self.assertEqual(image.getpixel((0,0))[:3],(255,0,0))
  with Image.open(self.image('watermark',{'text':'Hello','font_size':18,'position':'center'})) as image,Image.open(self.source) as original:self.assertNotEqual(image.convert('RGB').tobytes(),original.tobytes())
 def test_invalid_new_parameters_do_not_publish(self):
  for action,params in [('blur',{'radius':-1}),('watermark',{'text':''}),('border',{'color':'not-a-color'})]:
   with self.subTest(action=action),self.assertRaises(ConversionError):self.image(action,params)
  self.assertFalse(any(self.out.iterdir()))
 def test_pdf_page_operations_preserve_order_and_dimensions(self):
  source=self.base/'pages.pdf';writer=PdfWriter()
  for width in (100,200,300):writer.add_blank_page(width=width,height=400)
  with source.open('wb') as f:writer.write(f)
  for action,params,expected in [('pdf_reverse',{},[300,200,100]),('pdf_remove',{'pages':'2'},[100,300]),('pdf_duplicate',{'pages':'2,1'},[100,200,300,200,100])]:
   result=execute([source],action,params,self.out)[0];self.assertEqual([int(p.mediabox.width) for p in PdfReader(result).pages],expected)
  with self.assertRaises(ConversionError):execute([source],'pdf_remove',{'pages':'1-3'},self.out)
  with self.assertRaises(ConversionError):execute([source],'pdf_extract',{'pages':'1-999999999'},self.out)
 def test_preview_matches_crop_output_and_stays_in_temporary_folder(self):
  stage=self.base/'preview';stage.mkdir();params={'x':12,'y':8,'width':71,'height':63}
  preview=build_preview([self.source],'crop',params,stage,Runner())
  with Image.open(io.BytesIO(preview.image)) as shown:self.assertEqual(shown.size,(71,63))
  with Image.open(self.image('crop',params)) as saved:self.assertEqual(saved.size,(71,63))
  self.assertEqual(sorted(p.name for p in self.base.iterdir()),['pattern.png','preview','results'])
 def test_invalid_crop_cannot_generate_misleading_preview(self):
  for params in ({'x':150,'width':30,'height':20},{'x':1.5,'width':20,'height':20}):
   with self.assertRaises(ConversionError):build_preview([self.source],'crop',params,self.base/'preview',Runner())
 def test_archive_preview_does_not_compress_or_extract_files(self):
  preview=build_preview([self.source],'to:zip',{},self.base/'preview',Runner());self.assertIn('Archive plan',preview.text);self.assertFalse((self.base/'preview').exists())
 def test_preview_limits_media_without_shortening_real_export(self):
  source=self.base/'long.wav';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=5',str(source)],check=True)
  preview=execute([source],'to:wav',{},self.base/'sample',preview=True)[0];full=execute([source],'to:wav',{},self.out)[0]
  def duration(p):return float(json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(p)]))['format']['duration'])
  self.assertLessEqual(duration(preview),3.05);self.assertGreaterEqual(duration(full),4.95)
 def test_fade_audio_and_sample_waveform(self):
  source=self.base/'tone.wav';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=duration=2',str(source)],check=True)
  preview=build_preview([source],'fade',{'fade_in':.4,'fade_out':.4},self.base/'preview',Runner())
  self.assertTrue(preview.image);self.assertTrue(preview.media);self.assertEqual(preview.suffix,'.wav')
  with self.assertRaises(ConversionError):execute([source],'fade',{'fade_in':2,'fade_out':2},self.out)
 def test_video_fade_reaches_black_and_keeps_middle_color(self):
  source=self.base/'blue.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=96x64:d=2','-c:v','libx264',str(source)],check=True)
  target=execute([source],'fade',{'fade_in':.4,'fade_out':.4},self.out)[0]
  def blue_at(seconds):
   data=subprocess.check_output(['ffmpeg','-v','error','-ss',str(seconds),'-i',str(target),'-frames:v','1','-f','image2pipe','-vcodec','png','-'])
   with Image.open(io.BytesIO(data)) as frame:return frame.convert('RGB').getpixel((48,32))[2]
  self.assertLess(blue_at(0),10);self.assertGreater(blue_at(1),220)
 def test_media_trim_preview_uses_the_selected_time(self):
  source=self.base/'timeline.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=96x64:d=4','-c:v','libx264',str(source)],check=True)
  target=execute([source],'trim',{'start':3,'duration':.5},self.out,preview=True)[0]
  seconds=float(json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(target)]))['format']['duration'])
  self.assertGreaterEqual(seconds,.45);self.assertLessEqual(seconds,.6)
if __name__=='__main__':unittest.main()
