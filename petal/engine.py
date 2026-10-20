"""Offline transformations. Inputs are never rewritten; results publish without overwrite."""
import bz2
import csv
import gzip
import html
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile
import threading
import time
import uuid
import zipfile

from .catalog import kind, dependencies

class ConversionError(Exception): pass
class Cancelled(ConversionError): pass

class Runner:
 def __init__(self, cancel=None, preview=False): self.cancel=cancel or threading.Event();self.commands=[];self.preview=preview
 def check(self):
  if self.cancel.is_set():raise Cancelled('Cancelled. Originals are unchanged.')
 def run(self,args,timeout=1800,max_output=10000,truncate=True):
  self.check();args=[str(a) for a in args]
  if self.preview:
   timeout=min(timeout,90)
   if args[0]==dependencies().get('FFmpeg') and '-i' in args:
    # Input/output limits apply only to disposable previews, never saved copies.
    cap=min([3.0]+[float(args[i+1]) for i,value in enumerate(args[:-1]) if value=='-t'])
    if '-ss' in args:
     i=args.index('-ss');seek=args[i:i+2];del args[i:i+2];j=args.index('-i');args[j:j]=seek
    for i in reversed([i for i,v in enumerate(args) if v=='-i']):args[i:i]=['-t','3']
    args[-1:-1]=['-t',f'{cap:g}']
  self.commands.append(args)
  with tempfile.TemporaryFile() as log:
   try: p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   except FileNotFoundError as e:raise ConversionError(f'{args[0]} is unavailable. See Settings → Conversions.') from e
   import time
   start=time.monotonic()
   while p.poll() is None:
    if self.cancel.wait(.1) or time.monotonic()-start>timeout:
     os.killpg(p.pid,signal.SIGTERM)
     try:p.wait(timeout=3)
     except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
     self.check();raise ConversionError('The conversion exceeded its time limit.')
   log.seek(0,2);size=log.tell()
   if size>max_output and not truncate:raise ConversionError('Engine listing exceeds the validation limit; extraction refused.')
   log.seek(max(0,size-max_output));text=log.read().decode(errors='replace')
   if p.returncode:raise ConversionError(text.strip()[-3500:] or f'{Path(args[0]).name} exited with code {p.returncode}.')
   return text

def required(name):
 p=dependencies().get(name)
 if not p:raise ConversionError(f'{name} is not installed. Other available tools still work. See Settings → Conversions.')
 return p

def number(p,key,default,low,high):
 try:v=float(p.get(key,default))
 except (TypeError,ValueError):raise ConversionError(f'{key} must be a number.')
 if not math.isfinite(v) or not low<=v<=high:raise ConversionError(f'{key} must be between {low:g} and {high:g}.')
 return v

def safe_name(text):return re.sub(r'[\x00-\x1f/\\]','_',str(text))[:150] or 'result'

def publish(stage,parent):
 """Hard links make publication exclusive, even when another job uses the same name."""
 output=[]
 for item in sorted(stage.iterdir()):
  if item.name.startswith('.'):continue
  stem=item.stem;suffix=item.suffix
  for i in range(10000):
   dest=parent/(item.name if i==0 else f'{stem} ({i}){suffix}')
   try:
    if item.is_dir():
     dest.mkdir();
     try:
      for member in item.iterdir():shutil.move(str(member),dest/member.name)
     except Exception:shutil.rmtree(dest);raise
    else:os.link(item,dest)
    output.append(dest);break
   except FileExistsError:continue
  else:raise ConversionError('Could not choose an unused output filename.')
 return output

def _image(src,out,fmt,params,runner,extra=()):
 args=[required('ImageMagick'),str(src)+'[0]','-auto-orient']
 if fmt in ('jpg','bmp','pdf'):args+=['-background',params.get('background','#ffffff'),'-alpha','remove','-alpha','off']
 args+=list(extra)+['-quality',str(int(number(params,'quality',85,1,100))),str(out)]
 runner.run(args)

def _image_effect(src,out,action,p):
 from PIL import Image,ImageOps,ImageFilter,ImageEnhance,ImageDraw,ImageFont,ImageColor
 with Image.open(src) as source:
  image=ImageOps.exif_transpose(source).convert('RGBA')
 if action=='blur':image=image.filter(ImageFilter.GaussianBlur(number(p,'radius',4,0,100)))
 elif action=='sharpen':image=ImageEnhance.Sharpness(image).enhance(number(p,'amount',1,0,5))
 elif action=='invert':
  alpha=image.getchannel('A');image=ImageOps.invert(image.convert('RGB')).convert('RGBA');image.putalpha(alpha)
 elif action=='sepia':
  alpha=image.getchannel('A');image=ImageOps.colorize(ImageOps.grayscale(image),'#24160f','#ffe4b5').convert('RGBA');image.putalpha(alpha)
 elif action=='border':
  width=int(number(p,'width',16,0,1000))
  try:color=ImageColor.getcolor(str(p.get('color','#ffffff')),'RGBA')
  except ValueError:raise ConversionError('Choose a valid border color.')
  image=ImageOps.expand(image,border=width,fill=color)
 elif action=='watermark':
  text=str(p.get('text','Petal'))[:500]
  if not text.strip():raise ConversionError('Enter watermark text.')
  size=int(number(p,'font_size',32,8,500));opacity=int(number(p,'opacity',60,0,100)*255/100)
  try:color=ImageColor.getrgb(str(p.get('color','#ffffff')))[:3]
  except ValueError:raise ConversionError('Choose a valid text color.')
  try:font=ImageFont.truetype('DejaVuSans.ttf',size)
  except OSError:font=ImageFont.load_default(size=size)
  overlay=Image.new('RGBA',image.size);draw=ImageDraw.Draw(overlay);bounds=draw.textbbox((0,0),text,font=font)
  w,h=bounds[2]-bounds[0],bounds[3]-bounds[1];margin=max(8,round(min(image.size)*.04));position=p.get('position','bottom-right')
  if position not in ('center','top-left','bottom-right'):raise ConversionError('Choose center, top-left, or bottom-right.')
  x,y=(margin,margin) if position=='top-left' else ((image.width-w)/2,(image.height-h)/2) if position=='center' else (image.width-w-margin,image.height-h-margin)
  draw.text((max(0,x)-bounds[0],max(0,y)-bounds[1]),text,font=font,fill=(*color,opacity));image=Image.alpha_composite(image,overlay)
 fmt=out.suffix.lower()
 if fmt in ('.jpg','.jpeg','.bmp'):image=image.convert('RGB')
 if fmt not in ('.png','.jpg','.jpeg','.webp','.tiff','.tif','.bmp'):
  raise ConversionError('Save this image as PNG, JPG, WebP, TIFF or BMP before using this effect.')
 image.save(out,quality=int(number(p,'quality',85,1,100)))
 image.close()

def _edit_image(src,out,fmt,p,runner):
 """Edit Photo: approximate light and color adjustments using ImageMagick."""
 args=[]
 exposure=number(p,'exposure',0,-3,3)
 if exposure:args+=['-evaluate','multiply',f'{2**exposure:.6g}']
 brightness=number(p,'brightness',0,-100,100);contrast=number(p,'contrast',0,-100,100)
 if brightness or contrast:args+=['-brightness-contrast',f'{brightness:g}x{contrast:g}']
 blacks=number(p,'blacks',0,-100,100);whites=number(p,'whites',0,-100,100)
 shadows=number(p,'shadows',0,-100,100);highlights=number(p,'highlights',0,-100,100)
 gamma=number(p,'gamma',1,.2,3)
 lo=min(49,max(0,blacks*.3));hi=max(51,min(100,100-max(0,whites*.3)-max(0,highlights*.25)))
 gamma*=1-shadows/300
 if lo or hi<100 or gamma!=1:args+=['-level',f'{lo:.2f}%,{hi:.2f}%,{gamma:.4f}']
 temperature=number(p,'temperature',0,-100,100)/100
 if temperature:
  args+=['-channel','R','-evaluate','multiply',f'{1+.18*temperature:.4f}','+channel','-channel','B','-evaluate','multiply',f'{1-.18*temperature:.4f}','+channel']
 tint=number(p,'tint',0,-100,100)/100
 if tint:
  args+=['-channel','G','-evaluate','multiply',f'{1-.15*tint:.4f}','+channel','-channel','R','-evaluate','multiply',f'{1+.07*tint:.4f}','+channel','-channel','B','-evaluate','multiply',f'{1+.07*tint:.4f}','+channel']
 saturation=number(p,'saturation',0,-100,100)+number(p,'vibrance',0,-100,100)*.6
 if saturation:args+=['-modulate',f'100,{max(0,100+saturation):.2f},100']
 sharpness=number(p,'sharpness',0,0,200)
 if sharpness:args+=['-unsharp',f'0x{sharpness/100*1.5:.3f}']
 vignette=number(p,'vignette',0,0,100)
 if vignette:args+=['-vignette',f'0x{max(1,vignette*2):.0f}+0+0']
 _image(src,out,fmt,p,runner,args)

def _add_background(src,out,p):
 """Add BG: padding, rounded corners, shadow, aspect ratio, and color/gradient."""
 from PIL import Image,ImageColor,ImageDraw,ImageFilter,ImageOps
 padding=int(number(p,'padding',64,0,2000));corners=int(number(p,'corners',24,0,400));shadow=int(number(p,'shadow',30,0,400))
 ratio=str(p.get('ratio','auto')).strip().lower()
 bg=str(p.get('background','#f5f6f7')).strip() or '#f5f6f7'
 with Image.open(src) as source:image=ImageOps.exif_transpose(source).convert('RGBA')
 w,h=image.size
 base_w,base_h=w+2*padding,h+2*padding
 ratios={'1:1':(1,1),'16:9':(16,9),'4:5':(4,5)}
 if ratio in ratios:
  rw,rh=ratios[ratio];cw=max(base_w,math.ceil(base_h*rw/rh));ch=math.ceil(cw*rh/rw)
  if ch<base_h:ch=base_h;cw=math.ceil(ch*rw/rh)
 else:cw,ch=base_w,base_h
 def color(value,default=(245,246,247,255)):
  try:return ImageColor.getrgb(value)+(255,)
  except ValueError:return default
 if ',' in bg or ' ' in bg:
  parts=[x for x in re.split(r'[,\s]+',bg) if x]
  first=color(parts[0]);second=color(parts[1] if len(parts)>1 else parts[0])
  canvas=Image.new('RGBA',(cw,ch),first);draw=ImageDraw.Draw(canvas)
  for y in range(ch):
   t=y/max(1,ch-1);draw.line([(0,y),(cw,y)],fill=tuple(int(first[i]+(second[i]-first[i])*t) for i in range(4)))
 else:canvas=Image.new('RGBA',(cw,ch),color(bg))
 if shadow:
  layer=Image.new('RGBA',(cw,ch),(0,0,0,0));draw=ImageDraw.Draw(layer);x0=(cw-w)//2;y0=(ch-h)//2+max(1,shadow//3)
  draw.rounded_rectangle([x0,y0,x0+w,y0+h],radius=min(corners,min(w,h)//2),fill=(0,0,0,120))
  canvas.alpha_composite(layer.filter(ImageFilter.GaussianBlur(max(1,shadow/2))))
 mask=Image.new('L',(w,h),0);ImageDraw.Draw(mask).rounded_rectangle([0,0,w-1,h-1],radius=min(corners,min(w,h)//2),fill=255)
 from PIL import ImageChops
 image.putalpha(ImageChops.multiply(image.getchannel('A'),mask))
 canvas.alpha_composite(image,((cw-w)//2,(ch-h)//2))
 if out.suffix.lower() in ('.jpg','.jpeg','.bmp'):
  flat=Image.new('RGB',canvas.size,(255,255,255));flat.paste(canvas,(0,0),canvas);flat.save(out,quality=int(number(p,'quality',85,1,100)))
 else:canvas.save(out)

def _pdf_pages(src,stage,runner):
 textfile=stage/f'.{safe_name(src.stem)}-pdftext.txt'
 runner.run([required('PDF text'),'-layout',src,textfile])
 text=textfile.read_text(encoding='utf-8',errors='replace');textfile.unlink(missing_ok=True)
 pages=text.split('\f')
 if pages and not pages[-1].strip():pages.pop()
 return [page.strip('\n') for page in pages] or ['']

def _write_docx(pages,out,title):
 def xml(value):return html.escape(str(value),quote=False)
 paragraphs=[]
 for number_,page in enumerate(pages):
  if number_:paragraphs.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
  for line in page.replace('\r','').split('\n'):
   paragraphs.append(f'<w:p><w:r><w:t xml:space="preserve">{xml(line)}</w:t></w:r></w:p>')
 document=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
  '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+''.join(paragraphs)
  +'<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>')
 content_types=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
  '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
  '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
  '<Default Extension="xml" ContentType="application/xml"/>'
  '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
  '</Types>')
 relationships=('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
  '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
  '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
  '</Relationships>')
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml',content_types);z.writestr('_rels/.rels',relationships);z.writestr('word/document.xml',document)

def _write_epub(pages,out,title):
 def xml(value):return html.escape(str(value),quote=False)
 identifier=f'urn:uuid:{uuid.uuid4()}'
 modified=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
 body=''.join('<p>'+xml(line)+'</p>' for page in pages for line in page.replace('\r','').split('\n'))
 body=body.replace('</p><p>','</p><p>')
 content=('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="utf-8"/><title>'+xml(title)+'</title></head><body><h1>'+xml(title)+'</h1>'+body+'</body></html>')
 nav=('<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Contents</title></head><body><nav epub:type="toc"><h1>Contents</h1><ol><li><a href="content.xhtml">'+xml(title)+'</a></li></ol></nav></body></html>')
 package=('<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
  f'<dc:identifier id="bookid">{identifier}</dc:identifier><dc:title>{xml(title)}</dc:title><dc:language>en</dc:language><meta property="dcterms:modified">{modified}</meta></metadata>'
  '<manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="content" href="content.xhtml" media-type="application/xhtml+xml"/></manifest>'
  '<spine><itemref idref="content"/></spine></package>')
 container=('<?xml version="1.0" encoding="UTF-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
 with zipfile.ZipFile(out,'w') as z:
  z.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED)
  for name,data in [('META-INF/container.xml',container),('OEBPS/content.opf',package),('OEBPS/nav.xhtml',nav),('OEBPS/content.xhtml',content)]:
   z.writestr(name,data,compress_type=zipfile.ZIP_DEFLATED)

def _image_docx(src,out,params,runner):
 """Embed a rendered image in a Word page. This route does not perform OCR."""
 from PIL import Image
 with tempfile.TemporaryDirectory(prefix='petal-word-image-') as td:
  image=Path(td)/'image.png';_image(src,image,'png',params,runner)
  with Image.open(image) as im:w,h=im.size
  scale=min(9525,5943600/w,8229600/h);cx,cy=int(w*scale),int(h*scale)
  document=('<?xml version="1.0" encoding="UTF-8"?>'
   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body><w:p><w:r><w:drawing><wp:inline>'
   f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="1" name="Picture 1"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="image.png"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rIdImage"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
   '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>')
  with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
   z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
   z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdDocument" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
   z.writestr('word/_rels/document.xml.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdImage" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image.png"/></Relationships>')
   z.writestr('word/document.xml',document);z.write(image,'word/media/image.png')

def _ffmpeg(src,out,fmt,params,runner,extra=(),executable=None):
 audio={'mp3':['-c:a','libmp3lame','-q:a','2'],'m4a':['-c:a','aac','-b:a','192k'],
        'wav':['-c:a','pcm_s16le'],'flac':['-c:a','flac'],'ogg':['-c:a','libvorbis','-q:a','5'],
        'opus':['-c:a','libopus','-b:a','128k'],'aiff':['-c:a','pcm_s16be'],'wma':['-c:a','wmav2','-b:a','192k']}
 codecs={'mp4':['-c:v','libx264','-preset','fast','-crf',str(int(number(params,'crf',23,0,51))),'-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart'],
         'mov':['-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac'],
         'mkv':['-c:v','libx264','-c:a','aac'],'webm':['-c:v','libvpx-vp9','-crf','32','-b:v','0','-c:a','libopus'],
         'avi':['-c:v','mpeg4','-q:v','4','-c:a','libmp3lame'],'wmv':['-c:v','wmv2','-c:a','wmav2'],
         'gif':['-an','-vf','fps=12,scale=640:-1:flags=lanczos']}
 args=[executable or required('FFmpeg'),'-nostdin','-hide_banner','-loglevel','error','-i',src]
 if fmt in audio:
  codec=list(audio[fmt])
  if '-b:a' in extra and '-q:a' in codec:
   i=codec.index('-q:a');del codec[i:i+2]
  if 'bitrate' in params and fmt in ('mp3','m4a','ogg','opus','wma'):
   for flag in ('-q:a','-b:a'):
    if flag in codec:
     i=codec.index(flag);del codec[i:i+2]
   codec+=['-b:a',str(int(number(params,'bitrate',192,32,320)))+'k']
  args+=['-vn']+codec
 else:args+=codecs.get(fmt,['-c:v','libx264','-c:a','aac'])
 extra=list(extra)
 if fmt in ('mp4','mov','mkv'):
  pad='pad=ceil(iw/2)*2:ceil(ih/2)*2'
  if '-vf' in extra:
   i=extra.index('-vf')+1;extra[i]+=','+pad
  else:extra+=['-vf',pad]
 runner.run(args+extra+['-y',out])

OFFICE_FILTERS={'pdf':'pdf','docx':'docx','odt':'odt','rtf':'rtf','txt':'txt:Text','html':'html','epub':'epub','pptx':'pptx','odp':'odp','xlsx':'xlsx','ods':'ods','csv':'csv:Text - txt - csv (StarCalc):44,34,76','tsv':'csv:Text - txt - csv (StarCalc):9,34,76'}

def _office(src,stage,fmt,runner):
 filters=OFFICE_FILTERS
 with tempfile.TemporaryDirectory(prefix='petal-office-') as td:
  profile=Path(td)/'profile';output=Path(td)/'out';output.mkdir()
  runner.run([required('LibreOffice'),f'-env:UserInstallation={profile.as_uri()}','--headless','--convert-to',filters[fmt],'--outdir',output,src])
  files=list(output.iterdir())
  if not files:raise ConversionError('LibreOffice could not convert this file. Try PDF export in the originating application.')
  for f in files:
   name=safe_name(src.stem)+'-converted'+('.tsv' if fmt=='tsv' and f.suffix=='.csv' else f.suffix)
   target=stage/name
   if f.is_dir():shutil.copytree(f,target)
   else:shutil.copy2(f,target)

def _subtitle(src,out,fmt,offset=0):
 text=src.read_text(encoding='utf-8-sig')
 rx=re.compile(r'(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})')
 def stamp(m):
  value=max(0,((int(m[1] or 0)*60+int(m[2]))*60+int(m[3]))*1000+int(m[4])+round(offset*1000))
  h,value=divmod(value,3600000);mi,value=divmod(value,60000);s,ms=divmod(value,1000)
  return f'{h:02}:{mi:02}:{s:02}{"," if fmt=="srt" else "."}{ms:03}'
 text=rx.sub(stamp,text)
 blocks=re.split(r'\n\s*\n',text.replace('\r\n','\n'))
 cues=[]
 for b in blocks:
  lines=b.strip().splitlines()
  for i,line in enumerate(lines):
   if '-->' in line:cues.append((line,lines[i+1:]));break
 if not cues:raise ConversionError('No valid subtitle cues were found.')
 if fmt=='txt':result='\n\n'.join('\n'.join(lines) for _,lines in cues)
 elif fmt=='vtt':result='WEBVTT\n\n'+'\n\n'.join(t+'\n'+'\n'.join(lines) for t,lines in cues)
 else:result='\n\n'.join(f'{i}\n{t}\n'+ '\n'.join(lines) for i,(t,lines) in enumerate(cues,1))
 out.write_text(result+'\n',encoding='utf-8')

def _members_safe(paths):
 for name in paths:
  path=PurePosixPath(name.replace('\\','/'))
  if path.is_absolute() or '..' in path.parts or (path.parts and ':' in path.parts[0]):raise ConversionError('Archive contains an unsafe member path; extraction refused.')

def _extract_7z(src,dest,runner):
 """Extract RAR/7Z with 7-Zip after validating member names and the size budget."""
 tool=required('7-Zip');max_bytes=4*1024**3;max_entries=50000
 listing=runner.run([tool,'l','-slt','-ba','--',src],timeout=180,max_output=16*1024**2,truncate=False)
 entries=[];current={}
 for line in listing.splitlines():
  if not line.strip():
   if current:entries.append(current);current={}
   continue
  if ' = ' in line:
   key,value=line.split(' = ',1);current[key.strip()]=value
 if current:entries.append(current)
 members=[e for e in entries if e.get('Path')]
 _members_safe([e['Path'] for e in members])
 if len(members)>max_entries:raise ConversionError('Archive exceeds the 50,000 entry extraction limit.')
 total=0
 for entry in members:
  try:total+=int(entry.get('Size','0') or 0)
  except ValueError:pass
  if entry.get('Symbolic Link') or entry.get('Hard Link'):raise ConversionError('Archive links are not extracted.')
 if total>max_bytes:raise ConversionError('Archive exceeds the 4 GiB extraction limit.')
 temp=Path(tempfile.mkdtemp(prefix='petal-7z-'))
 try:
  runner.run([tool,'x','-y',f'-o{temp}','--',src],timeout=1800)
  actual_bytes=0;actual_entries=0
  for root,dirs,files in os.walk(temp):
   for name in dirs+files:
    item=Path(root)/name;actual_entries+=1
    if item.is_symlink() or not (item.is_dir() or item.is_file()):raise ConversionError('Archive links and special files are not extracted.')
    if item.is_file():actual_bytes+=item.stat().st_size
    if actual_entries>max_entries or actual_bytes>max_bytes:raise ConversionError('Archive exceeds the extraction limit.')
  dest.mkdir(exist_ok=True)
  for item in temp.iterdir():shutil.move(str(item),dest/item.name)
 finally:shutil.rmtree(temp,ignore_errors=True)

def _extract(src,dest,runner):
 """Reject links/devices and path escapes; extraction has an expanded-size budget."""
 dest.mkdir()
 max_bytes=4*1024**3; max_entries=50000
 if zipfile.is_zipfile(src):
  with zipfile.ZipFile(src) as z:
   members=z.infolist();_members_safe([m.filename for m in members])
   if len(members)>max_entries or sum(m.file_size for m in members)>max_bytes:raise ConversionError('Archive exceeds the 4 GiB / 50,000 entry extraction limit.')
   if any(((m.external_attr>>16)&0o170000)==0o120000 for m in members):raise ConversionError('Archive symlinks are not extracted.')
   for m in members:runner.check();z.extract(m,dest)
 elif tarfile.is_tarfile(src):
  with tarfile.open(src) as t:
   members=t.getmembers();_members_safe([m.name for m in members])
   if len(members)>max_entries or sum(m.size for m in members)>max_bytes:raise ConversionError('Archive exceeds the extraction limit.')
   if any(not(m.isfile() or m.isdir()) for m in members):raise ConversionError('Archive links and special files are not extracted.')
   for m in members:runner.check();t.extract(m,dest,filter='data')
 elif src.suffix in ('.gz','.bz2'):
  total=0;opener=gzip.open if src.suffix=='.gz' else bz2.open
  with opener(src,'rb') as f,open(dest/safe_name(src.stem),'wb') as o:
   while block:=f.read(1024*1024):
    runner.check();total+=len(block)
    if total>max_bytes:raise ConversionError('Expanded file exceeds 4 GiB.')
    o.write(block)
 elif src.suffix.lower() in ('.rar','.7z','.xz'):
  _extract_7z(src,dest,runner)
 else:raise ConversionError('Safe extraction supports ZIP, TAR, GZIP, BZIP2, XZ, RAR, and 7Z.')

def _archive(paths,out,fmt,runner):
 names=set();entries=[]
 for p in paths:
  name=p.name
  if name in names:raise ConversionError('Selected files have duplicate names. Rename one before archiving.')
  names.add(name)
  for item in [p]+(list(p.rglob('*')) if p.is_dir() else []):
   runner.check()
   if item.is_symlink() or not(item.is_file() or item.is_dir()):raise ConversionError('Archive creation skips no data silently: remove links and special files from the selection first.')
   entries.append((item,Path(name)/item.relative_to(p) if item!=p else Path(name)))
 if fmt=='zip':
  with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
   for p,name in entries:runner.check();z.write(p,str(name))
 else:
  with tarfile.open(out,'w:gz' if fmt=='tar.gz' else 'w') as t:
   for p,name in entries:runner.check();t.add(p,arcname=str(name),recursive=False)

def _page_indices(raw,count):
 indices=[]
 try:
  for piece in str(raw).replace(' ','').split(','):
   if not piece:continue
   if '-' in piece:
    a,b=map(int,piece.split('-',1))
    if not 1<=a<=b<=count:raise ConversionError('Choose a page range inside this PDF.')
    indices.extend(range(a-1,b))
   else:indices.append(int(piece)-1)
 except ValueError:raise ConversionError('Use page numbers such as 1,3-5.')
 if not indices or any(i<0 or i>=count for i in indices):raise ConversionError('Use page numbers such as 1,3-5 within this PDF’s page count.')
 return indices

def _pdf(paths,stage,action,params,runner):
 from pypdf import PdfReader,PdfWriter
 reader=PdfReader(paths[0])
 if reader.is_encrypted:raise ConversionError('This PDF is encrypted. Open an unlocked copy to use these tools.')
 prefix=safe_name(paths[0].stem)
 def write(pages,name,rotate=0,compress=False):
  w=PdfWriter()
  for page in pages:
   runner.check();w.add_page(page)
   if rotate:w.pages[-1].rotate(rotate)
   if compress:w.pages[-1].compress_content_streams()
  if action=='strip':w.add_metadata({})
  with open(stage/name,'wb') as f:w.write(f)
 if action=='pdf_reverse':write(reversed(reader.pages),f'{prefix}-reversed.pdf')
 elif action=='pdf_remove':
  excluded=set(_page_indices(params.get('pages','1'),len(reader.pages)))
  pages=[page for i,page in enumerate(reader.pages) if i not in excluded]
  if not pages:raise ConversionError('Keep at least one PDF page.')
  write(pages,f'{prefix}-removed.pdf')
 elif action=='pdf_duplicate':
  selected=_page_indices(params.get('pages','1'),len(reader.pages))
  write([*reader.pages,*[reader.pages[i] for i in selected]],f'{prefix}-duplicated.pdf')
 elif action=='pdf_split':
  for i,page in enumerate(reader.pages,1):write([page],f'{prefix}-page-{i:03}.pdf')
 elif action=='pdf_merge':
  readers=[PdfReader(p) for p in paths]
  if any(r.is_encrypted for r in readers):raise ConversionError('Unlock encrypted PDFs before merging.')
  write([page for r in readers for page in r.pages],f'{prefix}-merged.pdf')
 elif action=='pdf_extract':
  write([reader.pages[i] for i in _page_indices(params.get('pages','1'),len(reader.pages))],f'{prefix}-selection.pdf')
 elif action=='pdf_organize':
  write([reader.pages[i] for i in _page_indices(params.get('pages','1'),len(reader.pages))],f'{prefix}-organized.pdf')
 elif action=='pdf_rotate':
  degrees=int(number(params,'degrees',90,-360,360))
  if degrees%90:raise ConversionError('PDF rotation must be a multiple of 90 degrees.')
  write(reader.pages,f'{prefix}-rotated.pdf',rotate=degrees)
 else:write(reader.pages,f'{prefix}-{action.removeprefix("pdf_")}.pdf',compress=action=='pdf_compress')

def _convert(src,stage,fmt,p,runner):
 k=kind(src);name=safe_name(src.stem);out=stage/f'{name}-converted.{fmt}'
 if k=='image':
  if fmt=='docx':_image_docx(src,out,p,runner)
  else:_image(src,out,fmt,p,runner)
 elif k in ('audio','video'):_ffmpeg(src,out,fmt,p,runner)
 elif k=='pdf':
  if fmt in ('txt','md'):
   runner.run([required('PDF text'),'-layout',src,out])
  elif fmt in ('png','jpg'):
   runner.run([required('PDF images'),*(['-f','1','-l','1'] if runner.preview else []),'-r',str(int(number(p,'dpi',150,36,600))),'-png' if fmt=='png' else '-jpeg',src,stage/f'{name}-page'])
  elif fmt=='docx':_write_docx(_pdf_pages(src,stage,runner),out,name)
  elif fmt=='epub':_write_epub(_pdf_pages(src,stage,runner),out,name)
  else:raise ConversionError('This PDF export needs an offline layout/OCR engine that is not bundled. Text and page-image exports work now.')
 elif k in ('document','sheet','slides'):
  if src.suffix.lower() in ('.pages','.key'):
   raise ConversionError('Apple Pages/Keynote export is not reliably supported on Linux. Export DOCX, PPTX, or PDF from the originating app first.')
  if src.suffix.lower() in ('.rtfd','.textclipping'):
   raise ConversionError('Apple RTFD and text-clipping bundles are not supported on Linux. Export RTF, TXT, or PDF from the originating app first.')
  if fmt in ('png','jpg'):
   with tempfile.TemporaryDirectory() as td:
    d=Path(td);_office(src,d,'pdf',runner)
    pdf=next(d.glob('*.pdf'));_convert(pdf,stage,fmt,p,runner)
  elif fmt=='md':
   if src.suffix.lower() in ('.txt','.md','.markdown'):shutil.copyfile(src,out)
   else:
    with tempfile.TemporaryDirectory() as td:
     text_stage=Path(td);_office(src,text_stage,'txt',runner)
     text=next(text_stage.glob('*.txt'),None)
     if text is None:raise ConversionError('No text could be exported. Try TXT or PDF in the originating app.')
     shutil.copyfile(text,out)
  elif src.suffix.lower() in ('.md','.markdown') and fmt not in ('txt','html'):
   pandoc=dependencies().get('Pandoc')
   if not pandoc:raise ConversionError('Rich Markdown conversion needs Pandoc. You can export TXT or HTML now, or install Pandoc separately.')
   runner.run([pandoc,src,'-o',out])
  elif src.suffix.lower() in ('.md','.markdown') and fmt=='html':
   out.write_text('<!doctype html><meta charset="utf-8"><pre>'+html.escape(src.read_text())+'</pre>')
  elif src.suffix.lower() in ('.md','.markdown') and fmt=='txt':shutil.copyfile(src,out)
  elif src.suffix.lower() in ('.csv','.tsv') and fmt in ('csv','tsv'):
   with src.open(newline='',encoding='utf-8-sig') as f,out.open('w',newline='',encoding='utf-8') as g:
    csv.writer(g,delimiter='\t' if fmt=='tsv' else ',').writerows(csv.reader(f,delimiter='\t' if src.suffix.lower()=='.tsv' else ','))
  else:_office(src,stage,fmt,runner)
 elif k=='subtitle':_subtitle(src,out,fmt)
 else:raise ConversionError('Choose ZIP or TAR to package these files.')

def _probe(src,runner):
 if not dependencies().get('FFprobe'):raise ConversionError('This tool needs ffprobe, normally installed with FFmpeg.')
 return json.loads(runner.run([required('FFprobe'),'-v','quiet','-show_format','-show_streams','-of','json',src]))

def _unique(directory,name):
 dest=directory/name;stem=Path(name).stem;suffix=Path(name).suffix;n=1
 while dest.exists():dest=directory/f'{stem} ({n}){suffix}';n+=1
 return dest

ALIASES={
 'removeMetadata':'strip','editImage':'edit','annotateImage':'annotate','frameImage':'background',
 'cropImage':'crop','redactImage':'redact','createPDF':'image_pdf','mergePDF':'pdf_merge',
 'splitPDF':'pdf_split','organizePDF':'pdf_organize','extractArchive':'extract',
 'normalizeAudio':'normalize','muteVideo':'mute','trimVideo':'trim','cropVideo':'crop',
 'changeVideoSpeed':'speed','joinVideos':'merge_media','videoSnapshots':'snapshots',
 'splitVideo':'video_split','audioToVideo':'visualizer','trimAudio':'trim','audioChannels':'channels',
 'createCollage':'collage','redactVideo':'redact','redactAudio':'bleep',
}

def _rgb(value):
 value=str(value).strip()
 if re.fullmatch(r'#[0-9a-fA-F]{6}',value):return tuple(int(value[i:i+2],16) for i in (1,3,5))
 if re.fullmatch(r'#[0-9a-fA-F]{3}',value):return tuple(int(value[i]*2,16) for i in (1,2,3))
 return {'white':(255,255,255),'black':(0,0,0),'red':(255,0,0),'orange':(255,97,9)}.get(value.lower(),(255,255,255))

def _annotate_args(p):
 args=[];color=str(p.get('color','#ffffff')).strip() or '#ffffff'
 opacity=number(p,'opacity',100,0,100)/100
 text=str(p.get('text',''))[:500]
 x=int(number(p,'x',24,0,32768));y=int(number(p,'y',24,0,32768))
 r,g,b=_rgb(color);paint=f'rgba({r},{g},{b},{opacity:.3f})'
 if text:
  # ImageMagick @file and percent escapes must not interpret user text.
  if text.startswith('@') or '%' in text:raise ConversionError('Text annotations cannot start with @ or contain % escape sequences.')
  args+=['-gravity','northwest','-fill',paint,'-pointsize',str(int(number(p,'font_size',32,8,512))),'-annotate',f'+{x}+{y}',text]
 shape=str(p.get('shape','none')).strip().lower()
 if shape in ('rectangle','ellipse','arrow'):
  w=int(number(p,'width',400,1,32768));h=int(number(p,'height',300,1,32768));lw=int(number(p,'line_width',6,1,200))
  r,g,b=_rgb(color);paint=f'rgba({r},{g},{b},{opacity:.3f})'
  draw={'rectangle':f'rectangle {x},{y} {x+w},{y+h}','ellipse':f'ellipse {x+w//2},{y+h//2} {max(1,w//2)},{max(1,h//2)} 0,360','arrow':f'line {x},{y} {x+w},{y+h}'}[shape]
  if shape=='arrow':
   angle=math.atan2(h,w);length=min(math.hypot(w,h)*.3,max(12,lw*4));ex,ey=x+w,y+h
   points=[(ex-length*math.cos(angle+turn),ey-length*math.sin(angle+turn)) for turn in (-.5,.5)]
   draw+=' polygon '+ ' '.join(f'{px:g},{py:g}' for px,py in [(ex,ey),*points])
  args+=['-fill',paint,'-stroke',paint,'-strokewidth',str(lw),'-draw',draw]
 elif shape not in ('none',''):
  raise ConversionError('Annotation shape must be none, rectangle, ellipse, or arrow.')
 return args

def execute(paths,action,params=None,output_dir=None,cancel=None,*,preview=False):
 """Return created paths. A failed job leaves originals and published results intact."""
 paths=[Path(p).expanduser().resolve(strict=True) for p in paths];p=params or {};runner=Runner(cancel,preview=preview);action=ALIASES.get(action,action)
 if not paths:raise ConversionError('Choose at least one local file.')
 if len(paths)>1000:raise ConversionError('Select up to 1,000 files per job.')
 parent=Path(output_dir).expanduser().resolve() if output_dir else paths[0].parent
 parent.mkdir(parents=True,exist_ok=True)
 # Stage under the destination for exclusive, same-filesystem publication.
 with tempfile.TemporaryDirectory(prefix='.petal-',dir=parent) as temp:
  stage=Path(temp);name=safe_name(paths[0].stem);k=kind(paths[0])
  if action.startswith('to:'):
   fmt=action[3:]
   from .catalog import CONVERSIONS
   if fmt not in ('zip','tar','tar.gz') and any(fmt not in CONVERSIONS[kind(s)] for s in paths):raise ConversionError('This format does not accept every selected file.')
   if fmt in ('zip','tar','tar.gz'):
    if len(paths)==1 and k=='archive':
     with tempfile.TemporaryDirectory() as td:
      extracted=Path(td)/'contents';_extract(paths[0],extracted,runner);_archive(list(extracted.iterdir()),stage/f'{name}-converted.{fmt}',fmt,runner)
    else:
     if any(s.is_dir() and (parent==s or s in parent.parents) for s in paths):raise ConversionError('Choose an output folder outside the folder being archived.')
     _archive(paths,stage/f'{name}-archive.{fmt}',fmt,runner)
   else:
    for index,src in enumerate(paths):
     runner.check()
     # Separate staging prevents duplicate stems from overwriting each other.
     sub=stage/f'.input-{index}';sub.mkdir();_convert(src,sub,fmt,p,runner)
     for item in sub.iterdir():
      dest=stage/item.name
      n=1
      while dest.exists():dest=stage/f'{index+1}-{n}-{item.name}';n+=1
      shutil.move(str(item),dest)
  elif action.startswith('pdf_') or (action=='strip' and k=='pdf'):
   if action=='pdf_merge':_pdf(paths,stage,action,p,runner)
   else:
    for index,src in enumerate(paths):
     sub=stage/f'.pdf-{index}';sub.mkdir();_pdf([src],sub,action,p,runner)
     for item in sub.iterdir():
      dest=stage/item.name;n=1
      while dest.exists():dest=stage/f'{index+1}-{n}-{item.name}';n+=1
      shutil.move(str(item),dest)
  elif action=='snapshots':
   if any(kind(src)!='video' for src in paths):raise ConversionError('Video Snapshots needs video files.')
   count=int(number(p,'count',6,1,200))
   for index,src in enumerate(paths):
    runner.check();info=_probe(src,runner);duration=float(info.get('format',{}).get('duration',0) or 0)
    if duration<=0:raise ConversionError('Cannot establish this video’s duration.')
    sub=stage/f'.snap-{index}';sub.mkdir()
    runner.run([required('FFmpeg'),'-nostdin','-hide_banner','-loglevel','error','-i',str(src),'-vf',f'fps={count/duration:.6f}','-frames:v',str(count),'-q:v','2','-y',str(sub/'frame-%03d.png')])
    for item in sorted(sub.glob('*.png')):
     suffix=item.stem.split('-')[-1];shutil.move(str(item),_unique(stage,f'{safe_name(src.stem)}-snapshot-{suffix}.png'))
  elif action=='video_split':
   if any(kind(src)!='video' for src in paths):raise ConversionError('Split Video needs video files.')
   seconds=number(p,'seconds',30,1,3600)
   for index,src in enumerate(paths):
    runner.check();sub=stage/f'.split-{index}';sub.mkdir()
    runner.run([required('FFmpeg'),'-nostdin','-hide_banner','-loglevel','error','-i',str(src),'-f','segment','-segment_time',f'{seconds:g}','-reset_timestamps','1','-c:v','libx264','-preset','fast','-force_key_frames',f'expr:gte(t,n_forced*{seconds:g})','-segment_time_delta','0.05','-c:a','aac','-pix_fmt','yuv420p','-y',str(sub/'part-%03d.mp4')])
    for item in sorted(sub.glob('*.mp4')):shutil.move(str(item),_unique(stage,f'{safe_name(src.stem)}-{item.name}'))
  elif action in ('collage','image_pdf'):
   if any(kind(src)!='image' for src in paths):raise ConversionError('Choose only images for this tool.')
   if action=='collage':runner.run([required('ImageMagick'),'montage',*[str(x)+'[0]' for x in paths],'-auto-orient','-thumbnail','640x640','-tile','2x','-geometry','+12+12','-background',p.get('background','#ffffff'),stage/f'{name}-collage.png'])
   else:
    from PIL import Image,ImageOps
    images=[]
    for src in paths:
     runner.check()
     with Image.open(src) as im:images.append(ImageOps.exif_transpose(im).convert('RGB'))
    images[0].save(stage/f'{name}-combined.pdf',save_all=True,append_images=images[1:],resolution=150)
    for im in images:im.close()
  elif action=='extract':
   for i,src in enumerate(paths):_extract(src,stage/f'{safe_name(src.stem)}-extracted-{i+1}',runner)
  elif action=='shift_subtitles':
   for src in paths:_subtitle(src,stage/f'{safe_name(src.stem)}-shifted{src.suffix}',src.suffix.lstrip('.'),number(p,'offset',1,-86400,86400))
  elif action=='merge_media':
   if len(paths)<2:raise ConversionError('Select at least two media files in the desired order.')
   # A filter graph avoids concat manifest parsing and safely admits arbitrary filenames.
   args=[required('FFmpeg'),'-nostdin','-hide_banner','-loglevel','error']
   for src in paths:args+=['-i',str(src)]
   if all(kind(s)=='audio' for s in paths):
    streams=''.join(f'[{i}:a:0]' for i in range(len(paths)));expr=f'{streams}concat=n={len(paths)}:v=0:a=1[outa]'
    args+=['-filter_complex',expr,'-map','[outa]','-c:a','flac',str(stage/f'{name}-merged.flac')]
   elif all(kind(s)=='video' for s in paths):
    if not dependencies().get('FFprobe'):raise ConversionError('Video merging needs ffprobe, normally installed with FFmpeg.')
    probes=[json.loads(runner.run([required('FFprobe'),'-v','quiet','-show_format','-show_streams','-of','json',s])) for s in paths]
    first=next((s for s in probes[0]['streams'] if s.get('codec_type')=='video'),None)
    if not first:raise ConversionError('The first file has no video stream.')
    w=int(first['width']);h=int(first['height']);w+=w%2;h+=h%2;filters=[];streams=''
    for i,probe in enumerate(probes):
     filters.append(f'[{i}:v:0]scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,setpts=PTS-STARTPTS[v{i}]')
     if any(s.get('codec_type')=='audio' for s in probe['streams']):filters.append(f'[{i}:a:0]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]')
     else:
      duration=float(probe['format'].get('duration',0))
      if duration<=0:raise ConversionError('Cannot establish duration for a silent video clip.')
      filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={duration},asetpts=PTS-STARTPTS[a{i}]')
     streams+=f'[v{i}][a{i}]'
    filters.append(f'{streams}concat=n={len(paths)}:v=1:a=1[outv][outa]')
    args+=['-filter_complex',';'.join(filters),'-map','[outv]','-map','[outa]','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(stage/f'{name}-merged.mp4')]
   else:raise ConversionError('Choose only audio files or only video files for merging.')
   runner.run(args)
  else:
   for index,src in enumerate(paths):
    runner.check();k=kind(src);stem=safe_name(src.stem);ext=src.suffix.lstrip('.').lower();ext='jpg' if ext=='jpeg' else ext
    out=stage/f'{stem}-{action}{"-"+str(index+1) if index else ""}.{ext if ext not in ("svg","heif") else "png"}'
    if action=='metadata':
     data={'name':src.name,'path':str(src),'bytes':src.stat().st_size,'kind':k}
     if k=='image':
      from PIL import Image
      with Image.open(src) as im:data.update(width=im.width,height=im.height,mode=im.mode,format=im.format)
     if k in ('audio','video') and dependencies().get('FFprobe'):
      result=runner.run([required('FFprobe'),'-v','quiet','-show_format','-show_streams','-of','json',src]);data['media']=json.loads(result)
     out.with_suffix('.json').write_text(json.dumps(data,indent=2)+'\n');continue
    if k=='image':
     if action=='edit':_edit_image(src,out,out.suffix.lstrip('.'),p,runner);continue
     if action=='background':_add_background(src,out,p);continue
     if action in ('blur','sharpen','invert','sepia','watermark','border'):
      _image_effect(src,out.with_suffix('.png'),action,p);continue
     opts=[]
     if action=='compress':opts=['-strip']
     elif action=='resize':opts=['-resize',f'{int(number(p,"width",1920,1,32768))}x{int(number(p,"height",1080,1,32768))}>']
     elif action in ('crop','redact'):
      width=int(number(p,'width',400,1,32768));height=int(number(p,'height',300,1,32768));x=int(number(p,'x',0,0,32768));y=int(number(p,'y',0,0,32768))
      opts=['-crop',f'{width}x{height}+{x}+{y}','+repage'] if action=='crop' else ['-fill','black','-draw',f'rectangle {x},{y} {x+width-1},{y+height-1}','-strip']
     elif action=='rotate':opts=['-rotate',str(number(p,'degrees',90,-360,360))]
     elif action=='flip':opts=['-flip' if p.get('axis')=='vertical' else '-flop']
     elif action=='grayscale':opts=['-colorspace','Gray']
     elif action=='strip':opts=['-strip']
     elif action=='annotate':opts=_annotate_args(p)
     else:raise ConversionError(f'{action} is not an image tool.')
     _image(src,out,out.suffix.lstrip('.'),p,runner,opts)
    elif k in ('audio','video'):
     if action=='strip':
      target=out.with_suffix(src.suffix.lower())
      runner.run([required('FFmpeg'),'-nostdin','-hide_banner','-loglevel','error','-i',str(src),'-map_metadata','-1','-c','copy','-y',str(target)]);continue
     if action=='channels':
      if k!='audio':raise ConversionError('Convert Audio Channels needs an audio file.')
      info=_probe(src,runner);stream=next((s for s in info.get('streams',[]) if s.get('codec_type')=='audio'),None)
      if not stream:raise ConversionError('This file has no audio stream.')
      count=int(stream.get('channels',1) or 1);mode=str(p.get('mode','stereo')).strip().lower()
      left=number(p,'left',1,0,4);right=number(p,'right',1,0,4)
      if mode not in ('mono','stereo'):raise ConversionError('Audio channels must be mono or stereo.')
      if mode=='mono':af=f'pan=mono|c0={left:g}*c0+{right:g}*c1' if count>1 else f'volume={left:g}'
      else:af=f'pan=stereo|c0={left:g}*c0|c1={right:g}*c1' if count>1 else f'pan=stereo|c0={left:g}*c0|c1={right:g}*c0'
      out=out.with_suffix(src.suffix.lower());_ffmpeg(src,out,out.suffix.lstrip('.'),p,runner,['-af',af]);continue
     if action=='visualizer':
      if k!='audio':raise ConversionError('Audio Visualizer needs an audio file.')
      color=str(p.get('color','0xff6109')).strip() or '0xff6109';out=out.with_suffix('.mp4')
      runner.run([required('FFmpeg'),'-nostdin','-hide_banner','-loglevel','error','-i',str(src),'-filter_complex',f'[0:a]showwaves=s=1280x720:mode=cline:colors={color}[v]','-map','[v]','-map','0:a','-c:v','libx264','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-shortest','-y',str(out)]);continue
     if action=='bleep':
      if k!='audio':raise ConversionError('Bleep Audio needs an audio file.')
      ranges=[]
      for piece in str(p.get('ranges','1-2')).replace(' ','').split(','):
       if not piece:continue
       try:
        if '-' in piece:a,b=map(float,piece.split('-',1))
        else:a=float(piece);b=a+1
       except ValueError:raise ConversionError('Bleep ranges look like 3-5, or 8-10,14-16.')
       if not (math.isfinite(a) and math.isfinite(b) and 0<=a<b):raise ConversionError('Mute ranges need finite, nonnegative times with the end after the start.')
       ranges.append((a,b))
      if not ranges:raise ConversionError('Add at least one bleep range.')
      cond='+'.join(f'between(t,{a:g},{b:g})' for a,b in ranges)
      out=out.with_suffix(src.suffix.lower());_ffmpeg(src,out,out.suffix.lstrip('.'),p,runner,['-af',f"aeval=exprs='if(gt({cond},0),0,val(ch))':c=same"]);continue
     extra=[]
     if action=='trim':
      start=number(p,'start',0,0,1e7);duration=number(p,'duration',10,.01,1e7);extra=['-ss',str(start),'-t',str(duration)]
     elif action=='compress':
      if k=='audio':out=out.with_suffix('.mp3');extra=['-b:a',str(int(number(p,'bitrate',128,32,320)))+'k']
      else:out=out.with_suffix('.mp4');extra=['-crf',str(int(number(p,'crf',28,0,51)))]
     elif action=='mute':extra=['-an'];out=out.with_suffix('.mp4')
     elif action=='extract_audio':out=out.with_suffix('.mp3')
     elif action=='crop':
      if k!='video':raise ConversionError('Crop Video needs a video file.')
      w=int(number(p,'width',1280,2,16384));h=int(number(p,'height',720,2,16384));x=int(number(p,'x',0,0,16384));y=int(number(p,'y',0,0,16384));w-=w%2;h-=h%2
      extra=['-vf',f'crop={w}:{h}:{x}:{y}'];out=out.with_suffix('.mp4')
     elif action=='redact':
      if k!='video':raise ConversionError('Redact Video needs a video file.')
      w=int(number(p,'width',300,2,16384));h=int(number(p,'height',120,2,16384));x=int(number(p,'x',40,0,16384));y=int(number(p,'y',40,0,16384))
      start=number(p,'start',0,0,1e7);duration=number(p,'duration',0,0,1e7)
      enable=f'between(t,{start:g},{start+duration:g})' if duration>0 else 'gte(t,0)'
      extra=['-vf',f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black@1:t=fill:enable='{enable}'"];out=out.with_suffix('.mp4')
     elif action=='resize':
      w=int(number(p,'width',1280,16,16384));w-=w%2;extra=['-vf',f'scale={w}:-2'];out=out.with_suffix('.mp4')
     elif action=='rotate':
      degrees=int(number(p,'degrees',90,90,270))
      if degrees not in (90,180,270):raise ConversionError('Video rotation supports 90, 180, or 270 degrees.')
      extra=['-vf',{90:'transpose=1',180:'hflip,vflip',270:'transpose=2'}[degrees]];out=out.with_suffix('.mp4')
     elif action=='fade':
      duration=float(_probe(src,runner).get('format',{}).get('duration',0))
      if not math.isfinite(duration) or duration<=0:raise ConversionError('Cannot establish this media duration.')
      fade_in=number(p,'fade_in',.5,0,duration);fade_out=number(p,'fade_out',.5,0,duration)
      if fade_in+fade_out>duration:raise ConversionError('The fades must fit within the media duration.')
      name='afade' if k=='audio' else 'fade';filters=[]
      if fade_in:filters.append(f'{name}=t=in:st=0:d={fade_in:g}')
      if fade_out:filters.append(f'{name}=t=out:st={duration-fade_out:g}:d={fade_out:g}')
      if filters:extra=['-af' if k=='audio' else '-vf',','.join(filters)]
     elif action=='volume':extra=['-af',f'volume={number(p,"volume",1.5,0,10)}']
     elif action=='normalize':extra=['-af','loudnorm=I=-16:TP=-1.5:LRA=11']
     elif action=='speed':
      speed=number(p,'speed',1.5,.5,2)
      if k=='video':out=out.with_suffix('.mp4');extra=['-vf',f'setpts=PTS/{speed}','-af',f'atempo={speed}']
      else:extra=['-af',f'atempo={speed}']
     else:raise ConversionError(f'{action} is not a media tool.')
     _ffmpeg(src,out,out.suffix.lstrip('.'),p,runner,extra)
    else:raise ConversionError('This tool does not support the selected file.')
  runner.check()
  if not any(not x.name.startswith('.') for x in stage.iterdir()):raise ConversionError('The engine produced no output.')
  return publish(stage,parent)
