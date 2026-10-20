import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from petal.engine import execute,ConversionError,Cancelled,Runner
from petal.catalog import choices,dependencies
from PIL import Image
from pypdf import PdfReader,PdfWriter

class EngineTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.out=self.base/'out';self.out.mkdir()
  self.image=self.base/'a photo; $literal.png';Image.new('RGB',(300,200),'#ef8855').save(self.image)
  self.audio=self.base/'tone.wav';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.5',str(self.audio)],check=True)
  self.video=self.base/'clip.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=128x96:d=0.4','-c:v','libx264','-pix_fmt','yuv420p',str(self.video)],check=True)
  self.pdf=self.base/'pages.pdf';w=PdfWriter();w.add_blank_page(width=300,height=200);w.add_blank_page(width=200,height=300)
  with self.pdf.open('wb') as f:w.write(f)
  self.hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in [self.image,self.audio,self.video,self.pdf]}
 def tearDown(self):
  for p,digest in self.hashes.items():self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),digest)
  self.tmp.cleanup()
 def run_action(self,paths,action,params=None):return execute(paths,action,params,self.out)
 def test_image_formats(self):
  for fmt in ['jpg','webp','avif','tiff','bmp','pdf']:
   with self.subTest(fmt=fmt):
    result=self.run_action([self.image],'to:'+fmt);self.assertGreater(result[0].stat().st_size,0)
 def test_image_tools(self):
  for action,p in [('resize',{'width':100,'height':100}),('crop',{'width':50,'height':60}),('rotate',{'degrees':90}),('flip',{}),('strip',{}),('background',{}),('grayscale',{}),('compress',{}),('redact',{'width':30,'height':40}),('annotate',{'text':'Petal test'})]:
   with self.subTest(action=action):
    output=self.run_action([self.image],action,p)[0]
    with Image.open(output) as im:
     self.assertGreater(im.width,0)
     if action=='resize':self.assertEqual(im.size,(100,67))
     if action=='crop':self.assertEqual(im.size,(50,60))
     if action=='rotate':self.assertEqual(im.size,(200,300))
 def test_audio_formats(self):
  for fmt in ['mp3','m4a','flac','ogg','opus','aiff','wma']:
   with self.subTest(fmt=fmt):
    result=self.run_action([self.audio],'to:'+fmt);self.assertGreater(result[0].stat().st_size,0)
 def test_video_formats(self):
  for fmt in ['mov','mkv','webm','avi','wmv','gif']:
   with self.subTest(fmt=fmt):
    result=self.run_action([self.video],'to:'+fmt);self.assertGreater(result[0].stat().st_size,0)
 def test_media_tools(self):
  for action,p in [('trim',{'duration':.1}),('speed',{'speed':1.5}),('compress',{}),('rotate',{'degrees':90}),('resize',{'width':64}),('mute',{})]:
   with self.subTest(action=action):self.assertTrue(self.run_action([self.video],action,p)[0].exists())
  for action in ['volume','normalize','speed','trim','compress']:
   with self.subTest(audio=action):self.assertTrue(self.run_action([self.audio],action)[0].exists())
 def test_merge_media(self):
  for p in [self.audio,self.video]:self.assertTrue(self.run_action([p,p],'merge_media')[0].exists())
 def test_pdf_tools(self):
  output=self.run_action([self.pdf],'pdf_split');self.assertEqual(len(output),2)
  output=self.run_action([self.pdf,self.pdf],'pdf_merge');self.assertEqual(len(PdfReader(output[0]).pages),4)
  output=self.run_action([self.pdf],'pdf_extract',{'pages':'2'});self.assertEqual(len(PdfReader(output[0]).pages),1)
  for action in ['pdf_rotate','pdf_compress','strip']:self.assertTrue(self.run_action([self.pdf],action)[0].exists())
 def test_pdf_page_images(self):self.assertEqual(len(self.run_action([self.pdf],'to:png',{'dpi':40})),2)
 def test_collage_and_image_pdf(self):
  self.assertTrue(self.run_action([self.image,self.image],'collage')[0].exists())
  result=self.run_action([self.image,self.image],'image_pdf');self.assertEqual(len(PdfReader(result[0]).pages),2)
 def test_subtitles(self):
  src=self.base/'captions.srt';src.write_text('1\n00:00:01,000 --> 00:00:02,500\nhello\n')
  result=self.run_action([src],'to:vtt');self.assertIn('WEBVTT',result[0].read_text());self.assertIn('00:00:01.000',result[0].read_text())
  shifted=self.run_action([src],'shift_subtitles',{'offset':-2});self.assertIn('00:00:00,000',shifted[0].read_text())
  result=self.run_action([src],'to:txt');self.assertEqual(result[0].read_text().strip(),'hello')
 def test_spreadsheet_delimiters(self):
  src=self.base/'table.csv';src.write_text('name,value\n"a,b",42\n')
  output=self.run_action([src],'to:tsv')[0];self.assertIn('a,b\t42',output.read_text())
 def test_office_document(self):
  if not dependencies().get('LibreOffice'):self.skipTest('LibreOffice is not installed')
  src=self.base/'note.txt';src.write_text('A local document conversion test.\n')
  output=self.run_action([src],'to:pdf')[0];self.assertEqual(len(PdfReader(output).pages),1)
  output=self.run_action([src],'to:docx')[0];self.assertTrue(zipfile.is_zipfile(output))
 def test_archive_roundtrip(self):
  folder=self.base/'folder';folder.mkdir();(folder/'hello.txt').write_text('hello')
  for fmt in ['zip','tar','tar.gz']:
   archive=self.run_action([folder],'to:'+fmt)[0];extracted=self.run_action([archive],'extract')[0]
   self.assertEqual((extracted/'folder/hello.txt').read_text(),'hello')
 def test_archive_traversal_refused(self):
  archive=self.base/'bad.zip'
  with zipfile.ZipFile(archive,'w') as z:z.writestr('../outside.txt','bad')
  with self.assertRaises(ConversionError):self.run_action([archive],'extract')
  self.assertFalse((self.base/'outside.txt').exists())
 def test_output_collision(self):
  first=self.run_action([self.image],'to:jpg')[0];digest=first.read_bytes();second=self.run_action([self.image],'to:jpg')[0]
  self.assertNotEqual(first,second);self.assertEqual(first.read_bytes(),digest)
 def test_cancel_has_no_output(self):
  event=threading.Event();event.set()
  with self.assertRaises(Cancelled):execute([self.image],'to:jpg',output_dir=self.out,cancel=event)
  self.assertEqual(list(self.out.iterdir()),[])
 def test_failure_publishes_nothing(self):
  broken=self.base/'broken.png';broken.write_text('not an image')
  with self.assertRaises(ConversionError):self.run_action([self.image,broken],'to:jpg')
  self.assertEqual(list(self.out.iterdir()),[])
 def test_mixed_selection_archive_options(self):self.assertEqual([a.id for a in choices([self.image,self.audio])],['to:zip','to:tar','to:tar.gz'])
 def test_mixed_selection_archive_creation(self):
  out=self.run_action([self.image,self.audio],'to:zip')[0]
  with zipfile.ZipFile(out) as z:self.assertEqual(set(z.namelist()),{self.image.name,self.audio.name})
 def test_same_named_inputs(self):
  other=self.base/'another';other.mkdir();copy=other/self.image.name;Image.new('RGB',(20,30),'red').save(copy)
  result=self.run_action([self.image,copy],'to:jpg');self.assertEqual(len(result),2)
  sizes=set()
  for p in result:
   with Image.open(p) as im:sizes.add(im.size)
  self.assertEqual(sizes,{(300,200),(20,30)})
 def test_multiple_pdf_inputs_split(self):self.assertEqual(len(self.run_action([self.pdf,self.pdf],'pdf_split')),4)
 def test_archive_output_inside_source_refused(self):
  folder=self.base/'folder';folder.mkdir()
  with self.assertRaises(ConversionError):execute([folder],'to:zip',output_dir=folder)
 def test_cancel_running_child(self):
  event=threading.Event();timer=threading.Timer(.2,event.set);timer.start()
  try:
   with self.assertRaises(Cancelled):Runner(event).run([sys.executable,'-c','import time;time.sleep(30)'])
  finally:timer.cancel()
 def test_parallel_output_collision(self):
  from concurrent.futures import ThreadPoolExecutor
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.run_action([self.image],'to:jpg')[0],range(2)))
  self.assertNotEqual(*results)

if __name__=='__main__':unittest.main(verbosity=2)
