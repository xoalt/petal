"""Disposable output previews, using the same transformations as final exports."""
import tarfile,zipfile
from dataclasses import dataclass
from pathlib import Path
from PIL import Image,ImageOps
from .catalog import kind,dependencies
from .engine import execute,ConversionError

@dataclass
class PreviewResult:
 text:str
 image:bytes|None=None
 media:bytes|None=None
 suffix:str=''
 pages:int=1

def png_preview(path,folder,runner,page=1):
 output_kind=kind(path);dest=folder/'display.png'
 if output_kind=='pdf':
  if not dependencies().get('PDF images'):return None
  runner.run([dependencies()['PDF images'],'-f',str(page),'-l',str(page),'-singlefile','-scale-to','900','-png',path,folder/'display'])
 elif output_kind=='video':
  runner.run([dependencies()['FFmpeg'],'-v','error','-i',path,'-frames:v','1','-vf','scale=720:-1','-y',dest])
 elif output_kind=='audio':
  runner.run([dependencies()['FFmpeg'],'-v','error','-i',path,'-filter_complex','showwavespic=s=720x180:colors=0xff6109','-frames:v','1','-y',dest])
 elif output_kind=='image':
  try:
   with Image.open(path) as source:
    image=ImageOps.exif_transpose(source).convert('RGBA');image.thumbnail((1000,800));image.save(dest)
  except (OSError,ValueError):
   if not dependencies().get('ImageMagick'):return None
   runner.run([dependencies()['ImageMagick'],str(path)+'[0]','-thumbnail','1000x800',dest])
 else:return None
 return dest.read_bytes()

def archive_listing(path):
 if zipfile.is_zipfile(path):
  with zipfile.ZipFile(path) as archive:
   entries=archive.infolist();names=[f'{e.filename} · {e.file_size:,} bytes' for e in entries[:200]];total=len(entries)
 elif tarfile.is_tarfile(path):
  # Stream only the displayed subset; don't unpack data to build a preview.
  with tarfile.open(path) as archive:
   names=[];total=0
   for member in archive:
    total+=1
    if total<=200:names.append(f'{member.name} · {member.size:,} bytes')
    if total>=50000:break
 else:return 'Archive contents cannot be previewed for this format. Extraction still uses the validated archive engine.'
 return f'Archive entries: {total:,}\n'+ '\n'.join(names)+ ('\nShowing the first 200 entries.' if total>200 else '')

def build_preview(paths,action,params,folder,runner,page=1):
 paths=[Path(p) for p in paths];source=paths[0];source_kind=kind(source)
 if action in ('to:zip','to:tar','to:tar.gz'):
  return PreviewResult('Archive plan — no archive is created until you apply.\n'+ '\n'.join(p.name for p in paths)+f'\n{len(paths)} selected input(s). Final archive size is calculated during export.')
 if action=='extract':return PreviewResult('Preview only; files are not extracted until you apply.\n'+archive_listing(source))
 if action=='crop' and source_kind=='image':
  with Image.open(source) as im:
   width,height=ImageOps.exif_transpose(im).size
  x,y,w,h=(float(params.get(k,d)) for k,d in [('x',0),('y',0),('width',width),('height',height)])
  if not all(v.is_integer() for v in (x,y,w,h)):raise ConversionError('Use whole pixels for the crop values.')
  if x<0 or y<0 or w<1 or h<1 or x+w>width or y+h>height:raise ConversionError('Keep the crop rectangle inside the source image.')
 aggregate=action in ('pdf_merge','collage','image_pdf','merge_media') or action in ('to:zip','to:tar','to:tar.gz')
 sample=paths[:16] if aggregate else paths[:1]
 preview_action='pdf_extract' if action=='pdf_split' else action
 preview_params=dict(params)
 if action=='pdf_split':preview_params['pages']='1'
 outputs=execute(sample,preview_action,preview_params,folder/'outputs',runner.cancel,preview=True)
 target=outputs[0];size=sum(p.stat().st_size for p in outputs if p.is_file());pages=1
 summary=f'{len(outputs)} preview output(s) · {size:,} bytes\n'+ '\n'.join(p.name for p in outputs[:20])
 if aggregate and len(paths)>16:summary+='\nPreview combines the first 16 inputs; Apply processes the full displayed order.'
 if len(paths)>1:summary+=f'\n{len(paths)} files selected. '+('Combined in the displayed order.' if aggregate else 'Preview shows the first file; Apply processes every selected file.')
 if source_kind in ('audio','video'):summary+='\nMedia preview is a sample of up to 3 seconds; Apply processes the full selection.'
 if action=='pdf_split':summary+='\nPreview shows page 1. Apply creates one file for every page.'
 output_kind=kind(target)
 if output_kind=='image':
  try:
   with Image.open(target) as image:summary+=f'\nDimensions: {image.width} × {image.height} pixels · {image.format}'
  except OSError:summary+='\nImage format: '+target.suffix.lstrip('.').upper()
 if output_kind=='pdf':
  from pypdf import PdfReader
  pages=len(PdfReader(target).pages);summary+=f'\nPDF pages: {pages}'
 if output_kind=='archive':summary+='\n'+archive_listing(target)
 if target.suffix.lower() in ('.txt','.md','.srt','.vtt','.csv','.tsv','.json','.html'):
  with target.open('r',errors='replace') as text:summary+='\n\n'+text.read(16000)
 if target.suffix.lower() in ('.docx','.odt','.xlsx','.ods','.pptx','.odp','.epub'):
  summary+='\nDocument output generated successfully.'
  if dependencies().get('LibreOffice'):
   try:
    rendered=execute([target],'to:pdf',{},folder/'document-view',runner.cancel,preview=True)[0]
    image=png_preview(rendered,folder,runner)
    return PreviewResult(summary+'\nRendered from the converted document.',image)
   except ConversionError as e:summary+='\nVisual rendering unavailable: '+str(e)[:180]
  else:summary+='\nA visual document preview needs a compatible office engine; a PDF or image export can be previewed directly.'
 image=png_preview(target,folder,runner,min(max(1,page),pages))
 if output_kind=='pdf' and image is None:summary+='\nPage image preview unavailable; output details are shown instead.'
 if output_kind in ('audio','video') and target.stat().st_size<=32*1024*1024:return PreviewResult(summary,image,target.read_bytes(),target.suffix,pages)
 return PreviewResult(summary,image,pages=pages)
