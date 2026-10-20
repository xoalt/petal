from dataclasses import dataclass
from pathlib import Path
import os
import json
import shutil

# The reference wheel treats animated GIF as video; SVG is an image input only.
IMAGES = {'jpg','jpeg','png','webp','heic','heif','tif','tiff','avif','bmp','svg'}
AUDIO = {'mp3','m4a','wav','flac','ogg','opus','aiff','aif','wma','aac'}
VIDEO = {'mp4','mov','mkv','webm','avi','wmv','m4v','gif'}
DOCUMENTS = {'doc','docx','odt','rtf','txt','md','markdown','html','htm','epub','pages','rtfd','textclipping'}
SHEETS = {'xlsx','xls','ods','csv','tsv'}
SLIDES = {'ppt','pptx','odp','key'}
ARCHIVES = {'zip','tar','gz','tgz','bz2','xz','7z','rar'}
CONVERSIONS = {
 'image': ['jpg','png','webp','heic','tiff','avif','bmp','pdf','docx'],
 'audio': ['mp3','m4a','wav','flac','ogg','opus','aiff','wma'],
 'video': ['mp4','mov','mkv','webm','avi','wmv','gif','mp3'],
 'pdf': ['docx','epub','png','jpg','txt','md'],
 'document': ['pdf','docx','odt','rtf','txt','md','html','epub','png','jpg'],
 'slides': ['pdf','pptx','odp','png','jpg'],
 'sheet': ['xlsx','ods','csv','tsv','pdf'],
 'subtitle': ['srt','vtt','txt'],
 'archive': ['zip','tar','tar.gz'],
 'folder': ['zip','tar','tar.gz'],
 'other': ['zip','tar','tar.gz'],
}

@dataclass(frozen=True)
class Action:
 id: str
 label: str
 hint: str = ''

# The 26 reference tools, plus the Linux-only extras kept after them.
TOOLS = {
 'image': [
  Action('compress','Compress','Quality-controlled copy'),
  Action('strip','Metadata','Remove file metadata'),
  Action('edit','Edit Photo','Adjust light, color, and detail'),
  Action('annotate','Annotate Photo','Text, rectangle, ellipse, or arrow'),
  Action('background','Add BG','Padding, corners, shadow, ratio'),
  Action('crop','Crop Image','Width × height + x + y'),
  Action('redact','Redact Photo','Cover a rectangle in black'),
  Action('resize','Resize','Set maximum width and height'),
  Action('rotate','Rotate','Clockwise degrees'),
  Action('flip','Flip','Mirror horizontally or vertically'),
  Action('grayscale','Grayscale'),
  Action('blur','Blur','Adjust Gaussian blur with a preview'),
  Action('sharpen','Sharpen','Adjust detail strength'),
  Action('invert','Invert Colors','Create a negative copy'),
  Action('sepia','Sepia','Warm monochrome effect'),
  Action('watermark','Watermark','Text, color, position and opacity'),
  Action('border','Add Border','Width and color'),
 ],
 'audio': [
  Action('compress','Compress','Choose a bitrate'),
  Action('strip','Metadata','Remove file metadata'),
  Action('normalize','Normalize Volume','Loudness normalization'),
  Action('visualizer','Audio Visualizer','Waveform video'),
  Action('trim','Trim Audio','Start time + duration'),
  Action('channels','Convert Audio Channels','Mono or stereo with levels'),
  Action('bleep','Bleep Audio','Mute one or more time ranges'),
  Action('volume','Change Volume'),
  Action('speed','Change Speed'),
  Action('fade','Fade Audio','Fade in and out'),
 ],
 'video': [
  Action('compress','Compress','Choose a CRF'),
  Action('strip','Metadata','Remove file metadata'),
  Action('mute','Remove Audio'),
  Action('trim','Trim Video','Start time + duration'),
  Action('crop','Crop Video','Width × height + x + y'),
  Action('speed','Change Video Speed'),
  Action('snapshots','Video Snapshots','Evenly spaced PNG frames'),
  Action('video_split','Split Video','Segments of a chosen length'),
  Action('redact','Redact Video','Cover a rectangle, optionally timed'),
  Action('resize','Resize'),
  Action('rotate','Rotate'),
  Action('extract_audio','Extract Audio'),
  Action('fade','Fade Video','Fade from and to black'),
 ],
 'pdf': [
  Action('pdf_compress','Compress PDF'),
  Action('strip','Remove Metadata'),
  Action('pdf_split','Split PDF','One file per page'),
  Action('pdf_organize','Organize PDF','Reorder or remove pages'),
  Action('pdf_extract','Extract Pages'),
  Action('pdf_rotate','Rotate Pages'),
  Action('pdf_reverse','Reverse Pages','Reverse the page order'),
  Action('pdf_remove','Remove Pages','Choose pages to leave out'),
  Action('pdf_duplicate','Duplicate Pages','Append copies of selected pages'),
 ],
 'archive': [Action('extract','Extract','Unpack into a new folder')],
 'subtitle': [Action('shift_subtitles','Shift Timing')],
 'document': [Action('metadata','Inspect File')],
 'slides': [Action('metadata','Inspect File')],
 'sheet': [Action('metadata','Inspect File')],
 'folder': [Action('metadata','Inspect Folder')],
 'other': [Action('metadata','Inspect File')],
}
# Tools that stay available when several files are selected, as in the reference.
MULTI_TOOLS = {
 'image': {'compress','strip','crop','image_pdf','collage','blur','sharpen','invert','sepia','watermark','border'},
 'audio': {'compress','strip','normalize','merge_media'},
 'video': {'compress','strip','mute','trim','crop','speed','merge_media'},
 'pdf': {'pdf_compress','strip','pdf_split','pdf_merge'},
 'archive': {'extract'},
}
ACTIONS = [
 Action('open','Open','Open in your chosen application'),
 Action('share','Share','Send with LocalSend, or use the file shelf'),
 Action('shelf','Float','Pin files to the shelf'),
 Action('copy','Copy','File clipboard'),
 Action('move','Move…','Choose a destination'),
 Action('copy_path','Copy Path','One path per line'),
 Action('terminal','Terminal','Open the containing folder'),
]

def kind(path):
 p=Path(path)
 if p.is_dir(): return 'folder'
 e=p.suffix.lower().lstrip('.')
 if e in IMAGES:return 'image'
 if e in AUDIO:return 'audio'
 if e in VIDEO:return 'video'
 if e=='pdf':return 'pdf'
 if e in SHEETS:return 'sheet'
 if e in SLIDES:return 'slides'
 if e in DOCUMENTS:return 'document'
 if e in ('srt','vtt'):return 'subtitle'
 if e in ARCHIVES:return 'archive'
 return 'other'

def choices(paths,mode='convert'):
 if mode=='actions':return ACTIONS
 if not paths:return []
 kinds={kind(p) for p in paths}
 if mode=='tools':
  if len(kinds)!=1:return [Action('metadata','Inspect Files')]
  k=next(iter(kinds))
  tools=list(TOOLS.get(k,[]))
  if len(paths)>1:
   allowed=MULTI_TOOLS.get(k,set())
   tools=[a for a in tools if a.id in allowed]
  if len(paths)>1:
   tools += {
    'image':[Action('image_pdf','Create PDF','One page per image, in selection order'),Action('collage','Collage','Combine selected images')],
    'pdf':[Action('pdf_merge','Merge PDF','Join in selection order')],
    'audio':[Action('merge_media','Merge Audio','Join in selection order')],
    'video':[Action('merge_media','Merge Video','Join in selection order')],
   }.get(k,[])
  return tools
 sets=[set(CONVERSIONS[k]) for k in kinds]
 common=set.intersection(*sets)
 ordered=CONVERSIONS[kind(paths[0])]
 result=[Action('to:'+x,x.upper(),('Text-only export; layout, images, and scanned text are not reconstructed' if kinds=={'pdf'} and x in ('docx','epub','md') else 'Embed image in a Word document; no OCR' if kinds=={'image'} and x=='docx' else 'Convert locally')) for x in ordered if x in common and not all(Path(p).suffix.lower()=='.'+x for p in paths)]
 if len(kinds)>1:return [Action('to:'+x,x.upper(),'Package the selection') for x in ('zip','tar','tar.gz')]
 return result

def configure_engines(settings):
 paths=settings.get('engine_paths',{})
 os.environ['PETAL_ENGINE_PATHS']=json.dumps(paths if isinstance(paths,dict) else {})
 if settings.get('libreoffice_path'):os.environ['PETAL_LIBREOFFICE']=settings['libreoffice_path']

def dependencies():
 result={k: next((shutil.which(n) for n in names if shutil.which(n)),None) for k,names in {
  'FFmpeg':['ffmpeg'],'ImageMagick':['magick'],'LibreOffice':['libreoffice','soffice'],
  'PDF images':['pdftoppm'],'PDF text':['pdftotext'],'7-Zip':['7zz','7z'],
  'LocalSend':['localsend','localsend_app'],'KDE Connect':['kdeconnect-cli'],
  'Pandoc':['pandoc'],'FFprobe':['ffprobe'],'FFplay':['ffplay'],
 }.items()}
 office=os.environ.get('PETAL_LIBREOFFICE')
 if office and Path(office).is_file() and os.access(office,os.X_OK):result['LibreOffice']=office
 try:overrides=json.loads(os.environ.get('PETAL_ENGINE_PATHS','{}'))
 except ValueError:overrides={}
 if isinstance(overrides,dict):
  for key,path in overrides.items():
   if key in result and isinstance(path,str) and Path(path).is_file() and os.access(path,os.X_OK):result[key]=path
 return result
