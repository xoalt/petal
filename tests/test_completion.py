"""Regression checks for the finished tool routes and actual output content."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from petal.catalog import choices,dependencies
from petal.engine import execute,ConversionError,Runner
from petal import wheel
from PIL import Image
from pypdf import PdfReader
import cairo

class CatalogAndWheelTests(unittest.TestCase):
 def test_collective_tools_are_reachable(self):
  expected={'png':{'collage','image_pdf'},'pdf':{'pdf_merge','pdf_compress'},'wav':{'merge_media'},'mp4':{'merge_media'}}
  for ext,tools in expected.items():
   self.assertTrue(tools <= {a.id for a in choices([Path('a.'+ext),Path('b.'+ext)],'tools')},ext)
   self.assertNotIn('merge_media',{a.id for a in choices([Path('a.'+ext)],'tools')})
  for count in (1,2):self.assertIn('extract',{a.id for a in choices([Path('a.7z')]*count,'tools')})
 def test_hover_tracks_expanded_petal_and_rounded_gaps(self):
  cx,cy,r,inner=wheel.geometry(360,360)
  self.assertEqual(wheel.hit(cx,cy-r+10,360,360,7),0)
  self.assertEqual(wheel.hit(cx,cy-r-6,360,360,7),-1)
  self.assertEqual(wheel.hit(cx,cy-r-6,360,360,7,0,{0:1}),0)
  self.assertEqual(wheel.hit(cx,cy-r-22,360,360,7,0,{0:1}),-1)
  self.assertEqual(wheel.hit(cx,cy,360,360,7,0,{0:1}),-1)
  import math
  x,y=wheel.point(cx,cy,(r+inner)/2,-math.pi/2+math.tau/14)
  self.assertEqual(wheel.hit(x,y,360,360,7),-1)
 def test_pdf_exports_explain_text_limit(self):
  exports={a.id:a.hint for a in choices([Path('document.pdf')])}
  for name in ('docx','epub','md'):self.assertIn('Text-only',exports['to:'+name])

class CompletionEngineTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.out=self.base/'out';self.out.mkdir()
 def tearDown(self):self.tmp.cleanup()
 def run_action(self,src,action,p=None):return execute([src],action,p,self.out)
 def test_video_split_creates_timed_segments(self):
  src=self.base/'long.mp4'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=128x96:r=25:d=3.2','-c:v','libx264',str(src)],check=True)
  result=self.run_action(src,'video_split',{'seconds':1});self.assertEqual(len(result),4)
  durations=[float(json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-of','json',str(p)]))['format']['duration']) for p in result]
  for d in durations[:3]:self.assertAlmostEqual(d,1,delta=.15)
  self.assertAlmostEqual(sum(durations),3.2,delta=.3)
 def test_pdf_docx_epub_content_and_page_count(self):
  src=self.base/'text.pdf';surface=cairo.PDFSurface(str(src),300,200);c=cairo.Context(surface)
  for text in ('First test page','Second test page'):
   c.move_to(30,60);c.show_text(text);c.show_page()
  surface.finish()
  output=self.run_action(src,'to:docx')[0]
  with zipfile.ZipFile(output) as z:
   doc=ET.fromstring(z.read('word/document.xml'));ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
   text=' '.join(doc.itertext());self.assertIn('First test page',text);self.assertIn('Second test page',text)
   self.assertEqual(len(doc.findall('.//w:br',ns)),1)
  output=self.run_action(src,'to:epub')[0]
  with zipfile.ZipFile(output) as z:
   self.assertEqual(z.infolist()[0].filename,'mimetype');self.assertEqual(z.read('mimetype'),b'application/epub+zip')
   content=ET.fromstring(z.read('OEBPS/content.xhtml'));self.assertIn('Second test page',' '.join(content.itertext()))
 def test_photo_edit_background_alpha_and_arrow(self):
  src=self.base/'photo.png';Image.new('RGBA',(100,80),(0,0,0,0)).save(src)
  bg=self.run_action(src,'background',{'padding':0,'corners':0,'shadow':0,'background':'#ffffff'})[0]
  with Image.open(bg) as im:self.assertEqual(im.getpixel((50,40)),(255,255,255,255))
  Image.new('RGB',(100,80),'#ffffff').save(src)
  result=self.run_action(src,'annotate',{'shape':'arrow','width':50,'height':30,'x':10,'y':10,'color':'#000000','line_width':2,'opacity':100})[0]
  with Image.open(result) as im:
   # Arrowhead extends off the shaft near its end.
   self.assertNotEqual(im.convert('RGB').getpixel((49,39)),(255,255,255))
  result=self.run_action(src,'edit',{'brightness':-60})[0]
  with Image.open(result) as im:self.assertLess(im.convert('RGB').getpixel((50,40))[0],250)
 def test_image_docx_embeds_image_and_page_relationship(self):
  import io
  src=self.base/'photo.png';Image.new('RGB',(120,80),'orange').save(src)
  output=self.run_action(src,'to:docx')[0]
  with zipfile.ZipFile(output) as z:
   with Image.open(io.BytesIO(z.read('word/media/image.png'))) as im:self.assertEqual(im.size,(120,80))
   ns={'r':'http://schemas.openxmlformats.org/package/2006/relationships'}
   rel=ET.fromstring(z.read('word/_rels/document.xml.rels')).find('r:Relationship',ns);self.assertEqual(rel.get('Target'),'media/image.png')
   doc=ET.fromstring(z.read('word/document.xml'));blip=doc.find('.//{http://schemas.openxmlformats.org/drawingml/2006/main}blip');self.assertEqual(blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'),rel.get('Id'))
  self.assertEqual(len(choices([src])),8)
 def test_document_markdown_route(self):
  src=self.base/'note.txt';src.write_text('A text export\n')
  result=self.run_action(src,'to:md')[0];self.assertEqual(result.read_text(),src.read_text())
 def test_7z_extraction_and_links_refused(self):
  tool=dependencies().get('7-Zip')
  if not tool:self.skipTest('7-Zip unavailable')
  folder=self.base/'files';folder.mkdir();(folder/'hello.txt').write_text('Safe extraction')
  src=self.base/'files.7z';subprocess.run([tool,'a',str(src),'files'],cwd=self.base,stdout=subprocess.DEVNULL,check=True)
  result=self.run_action(src,'extract')[0];self.assertEqual((result/'files/hello.txt').read_text(),'Safe extraction')
  (folder/'escape').symlink_to('/tmp');bad=self.base/'links.7z'
  subprocess.run([tool,'a','-snl',str(bad),'files'],cwd=self.base,stdout=subprocess.DEVNULL,check=True)
  with self.assertRaises(ConversionError):self.run_action(bad,'extract')
 def test_archive_listing_cannot_be_silently_truncated(self):
  with self.assertRaises(ConversionError):Runner().run([sys.executable,'-c','print("x"*200)'],max_output=100,truncate=False)
 def test_new_audio_and_video_tool_content(self):
  audio=self.base/'tone.wav';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=1','-y',str(audio)],check=True)
  mono=self.run_action(audio,'channels',{'mode':'mono'})[0]
  info=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-of','json',str(mono)]));self.assertEqual(info['streams'][0]['channels'],1)
  visual=self.run_action(audio,'visualizer')[0]
  info=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-of','json',str(visual)]));self.assertEqual({s['codec_type'] for s in info['streams']},{'video','audio'})
  muted=self.run_action(audio,'bleep',{'ranges':'.2-.5'})[0]
  import array
  samples=array.array('h',subprocess.check_output(['ffmpeg','-v','error','-i',str(muted),'-f','s16le','-ac','1','-ar','1000','-']))
  self.assertLess(max(abs(x) for x in samples[250:450]),5);self.assertGreater(max(abs(x) for x in samples[:100]),100)
  for value in ('nan-inf','-1-2','2-1'):
   with self.assertRaises(ConversionError):self.run_action(audio,'bleep',{'ranges':value})
  video=self.base/'video.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=128x96:r=25:d=1','-c:v','libx264',str(video)],check=True)
  snaps=self.run_action(video,'snapshots',{'count':3});self.assertEqual(len(snaps),3)
  for snap in snaps:
   with Image.open(snap) as im:self.assertEqual(im.size,(128,96))
  crop=self.run_action(video,'crop',{'width':64,'height':48,'x':0,'y':0})[0]
  info=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_streams','-of','json',str(crop)]));self.assertEqual((info['streams'][0]['width'],info['streams'][0]['height']),(64,48))
  redacted=self.run_action(video,'redact',{'width':32,'height':32,'x':0,'y':0})[0]
  raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(redacted),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
  im=Image.frombytes('RGB',(128,96),raw);self.assertLess(max(im.getpixel((10,10))),15);self.assertGreater(im.getpixel((100,60))[2],150)

if __name__=='__main__':unittest.main(verbosity=2)
