"""Bounded, offline capability checks and explicit repository installation plans."""
from dataclasses import dataclass,asdict
import importlib.util
import os
from pathlib import Path
import re,shutil,tempfile,zipfile,time
from .engine import Runner,ConversionError,Cancelled,_ffmpeg,OFFICE_FILTERS
from .catalog import dependencies

@dataclass
class Result:
 key:str
 title:str
 status:str
 detail:str
 packages:tuple=()
 checks:dict=None
 executable:str=''
 def data(self):return asdict(self)

PACKAGES={'office':('libreoffice-fresh',),'images':('imagemagick',),'media':('ffmpeg',),'pdf':('poppler',),'archives':('7zip',),'markdown':('pandoc-cli',)}
SOURCES={'office':'https://www.libreoffice.org/download/download-libreoffice/','images':'https://imagemagick.org/script/download.php','media':'https://ffmpeg.org/download.html','pdf':'https://poppler.freedesktop.org/','archives':'https://www.7-zip.org/download.html','markdown':'https://pandoc.org/installing.html','sharing':'https://localsend.org/download'}
TITLES={'office':'Documents, slides & spreadsheets','images':'Images & photo tools','media':'Audio & video','pdf':'PDF text & page images','archives':'RAR & 7Z extraction','markdown':'Rich Markdown exports','sharing':'Sharing','builtin':'Built-in tools'}
PROVIDERS={'office':'LibreOffice','images':'ImageMagick','media':'FFmpeg','pdf':'Poppler','archives':'7-Zip','markdown':'Pandoc'}
PROGRAMS={key:((packages[0],PROVIDERS[key],packages),) for key,packages in PACKAGES.items()}
PROGRAMS['office']=(('libreoffice-fresh','LibreOffice Fresh',('libreoffice-fresh',)),('libreoffice-still','LibreOffice Still',('libreoffice-still',)))

class CheckRunner(Runner):
 def run(self,args,timeout=30,**kwargs):return super().run(args,timeout=min(timeout,30),**kwargs)

def distro():
 try:
  values={k:v.strip('"') for k,v in (line.split('=',1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)}
 except OSError:return 'unknown'
 names=(values.get('ID','')+' '+values.get('ID_LIKE','')).split()
 return 'arch' if any(x in ('arch','cachyos') for x in names) else values.get('ID','unknown')

def install_plan(keys,platform=None,programs=None):
 platform=platform or distro()
 if platform!='arch':raise ValueError('Automatic installation is available for Arch and CachyOS. Use the official download links, then Check again.')
 if not keys:raise ValueError('Select at least one missing feature first.')
 if any(key not in PACKAGES for key in keys):raise ValueError('That program has no supported repository installation plan. Use its official download link.')
 programs=programs or {}
 selected={}
 for key in keys:
  identifier=programs.get(key)
  option=next((item for item in PROGRAMS[key] if item[0]==identifier),None)
  if not option:raise ValueError('Choose a program for every selected feature first.')
  selected[key]=option
 packages=sorted({p for item in selected.values() for p in item[2]})
 if not shutil.which('pacman') or not shutil.which('pkexec'):raise ValueError('The system package installer is unavailable. Install from your software manager, then Check again.')
 return {'platform':platform,'features':sorted(set(keys)),'programs':{k:v[0] for k,v in selected.items()},'packages':packages,'command':[shutil.which('pkexec'),shutil.which('pacman'),'-S','--needed',*packages]}

def run_check(fn,checks,name):
 try:fn();checks[name]=True
 except Cancelled:raise
 except (OSError,ValueError,ConversionError,zipfile.BadZipFile,AssertionError):checks[name]=False

def result(key,executable,checks,missing=''):
 passed=sum(bool(v) for v in checks.values());total=len(checks)
 status='ready' if total and passed==total else 'partial' if passed else 'missing' if not executable else 'failed'
 failed=[k for k,v in checks.items() if not v]
 detail=(f'{passed}/{total} checks passed.' if total else missing or 'Not installed.')
 if failed:detail+=' Needs attention: '+', '.join(failed)+'.'
 return Result(key,TITLES[key],status,detail,PACKAGES.get(key,()),checks,executable or '')

def assert_output(path):
 if not path.is_file() or path.stat().st_size==0:raise ValueError('The program did not produce an output file.')
 if path.suffix in ('.docx','.odt','.ods','.xlsx','.pptx','.odp','.epub'):
  with zipfile.ZipFile(path) as z:
   if z.testzip() is not None:raise ValueError('The program produced a damaged document.')
 if path.suffix=='.pdf' and not path.read_bytes().startswith(b'%PDF-'):raise ValueError('The program did not produce a PDF.')

def office_fixture(folder,family):
 ns='xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"'
 body={'writer':'<office:text><text:p>Petal conversion check</text:p></office:text>','calc':'<office:spreadsheet><table:table table:name="Check"><table:table-row><table:table-cell office:value-type="string"><text:p>Check</text:p></table:table-cell><table:table-cell office:value-type="float" office:value="42"><text:p>42</text:p></table:table-cell></table:table-row></table:table></office:spreadsheet>','impress':'<office:presentation><draw:page draw:name="Check"><draw:frame svg:x="1cm" svg:y="1cm" svg:width="10cm" svg:height="3cm"><draw:text-box><text:p>Petal check</text:p></draw:text-box></draw:frame></draw:page></office:presentation>'}[family]
 suffix,mime={'writer':('fodt','text'),'calc':('fods','spreadsheet'),'impress':('fodp','presentation')}[family]
 path=folder/f'{family}.{suffix}';path.write_text(f'<?xml version="1.0"?><office:document {ns} office:version="1.2" office:mimetype="application/vnd.oasis.opendocument.{mime}"><office:body>{body}</office:body></office:document>');return path

def probe_office(executable,runner=None):
 checks={};runner=runner or CheckRunner()
 try:
  if not executable or not Path(executable).is_file() or not os.access(executable,os.X_OK):return result('office',None,{},'Choose an office export program.')
  version=runner.run([executable,'--version'],timeout=15)
  if 'LibreOffice' not in version:return result('office',executable,{'LibreOffice command-line interface':False})
 except Cancelled:raise
 except (OSError,ConversionError):return result('office',executable,{'Starts successfully':False})
 with tempfile.TemporaryDirectory(prefix='petal-office-check-') as td:
  folder=Path(td);profile=(folder/'profile').as_uri();failures=0;started=time.monotonic()
  for family,formats in [('writer',('pdf','docx','odt','rtf','txt','html','epub')),('calc',('pdf','xlsx','ods','csv','tsv')),('impress',('pdf','pptx','odp'))]:
   src=office_fixture(folder,family)
   for fmt in formats:
    out=folder/(family+'-'+fmt);out.mkdir()
    def check():
     runner.run([executable,f'-env:UserInstallation={profile}','--headless','--convert-to',OFFICE_FILTERS[fmt],'--outdir',out,src],timeout=30)
     files=list(out.iterdir())
     if not files:raise ValueError('The program did not create an export.')
     for p in files:assert_output(p)
    run_check(check,checks,f'{family.title()} → {fmt.upper()}')
    failures=0 if list(checks.values())[-1] else failures+1
    if failures>=2 or time.monotonic()-started>150:
     row=result('office',executable,checks);row.status='partial' if any(checks.values()) else 'failed';row.detail+=' Checks stopped after repeated failures or the time limit. Other exports remain unverified.';return row
 return result('office',executable,checks)

def probe_images(executable,runner,folder):
 checks={}
 if executable:
  for fmt in ('png','jpg','webp','heic','tiff','avif','bmp','pdf'):
   def check():
    target=folder/('image.'+fmt);runner.run([executable,'-size','16x16','xc:#ff6109',target],timeout=15);assert_output(target)
   run_check(check,checks,fmt.upper()+' export')
  def edit():
   out=folder/'edit.png';runner.run([executable,'-size','32x32','xc:red','-resize','16x16','-rotate','90','-strip',out],timeout=15);assert_output(out)
  run_check(edit,checks,'Resize, rotate & metadata')
 return result('images',executable,checks,'Choose an image conversion program.')

def probe_media(executable,runner,folder,companions=None):
 checks={}
 if executable:
  import wave
  src=folder/'sound.wav'
  with wave.open(str(src),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\0\0'*1600)
  for fmt in ('mp3','m4a','wav','flac','ogg','opus','aiff','wma'):
   def check():
    out=folder/('audio.'+fmt);_ffmpeg(src,out,fmt,{},runner,executable=executable);assert_output(out)
   run_check(check,checks,fmt.upper()+' audio')
  for fmt in ('mp4','mov','mkv','webm','avi','wmv','gif'):
   def check():
    sample=folder/'sample.mkv'
    if not sample.exists():runner.run([executable,'-nostdin','-v','error','-f','lavfi','-i','color=c=orange:s=32x32:r=10','-f','lavfi','-i','anullsrc=r=8000:cl=mono','-t','0.2','-c:v','ffv1','-c:a','pcm_s16le',sample],timeout=15)
    out=folder/('video.'+fmt);_ffmpeg(sample,out,fmt,{},runner,executable=executable);assert_output(out)
   run_check(check,checks,fmt.upper()+' video')
  companions=companions or dependencies();probe=companions.get('FFprobe');play=companions.get('FFplay')
  if probe:run_check(lambda:runner.run([probe,'-v','error','-show_format',src],timeout=10),checks,'Media inspection')
  else:checks['Media inspection']=False
  if play:run_check(lambda:runner.run([play,'-version'],timeout=10),checks,'Preview player available')
  else:checks['Preview player available']=False
 return result('media',executable,checks,'Choose an audio/video conversion program.')

def probe_pdf(deps,runner,folder):
 from pypdf import PdfWriter
 src=folder/'check.pdf';writer=PdfWriter();writer.add_blank_page(width=72,height=72)
 with src.open('wb') as f:writer.write(f)
 checks={}
 text=deps.get('PDF text');images=deps.get('PDF images')
 def extract():
  out=folder/'check.txt';runner.run([text,src,out],timeout=15)
  if not out.is_file():raise ValueError('No text output was created.')
 if text:run_check(extract,checks,'Text extraction')
 else:checks['Text extraction']=False
 for fmt in ('png','jpg'):
  def render():
   prefix=folder/('page-'+fmt);runner.run([images,'-r','36','-singlefile','-png' if fmt=='png' else '-jpeg',src,prefix],timeout=15);assert_output(prefix.with_suffix('.'+fmt))
  if images:run_check(render,checks,fmt.upper()+' page export')
  else:checks[fmt.upper()+' page export']=False
 return result('pdf',images or text,checks)

def probe_archives(exe,runner,folder):
 checks={}
 if exe:
  archive=folder/'sample.zip'
  with zipfile.ZipFile(archive,'w') as z:z.writestr('check.txt','Petal')
  run_check(lambda:runner.run([exe,'t',archive],timeout=15),checks,'Archive test')
  def unpack():
   out=folder/'unpacked';runner.run([exe,'x','-y',f'-o{out}',archive],timeout=15)
   if (out/'check.txt').read_text()!='Petal':raise ValueError('Extracted content did not match.')
  run_check(unpack,checks,'Extraction')
 return result('archives',exe,checks,'ZIP/TAR already work. Choose a program for RAR/7Z/XZ extraction.')

def probe_markdown(exe,runner,folder):
 checks={}
 if exe:
  src=folder/'check.md';src.write_text('# Petal\n\n**Conversion check**')
  for fmt in ('docx','odt','rtf','epub','pdf'):
   def convert():
    out=folder/('markdown.'+fmt);runner.run([exe,src,'-o',out],timeout=30);assert_output(out)
   run_check(convert,checks,fmt.upper()+' export')
 row=result('markdown',exe,checks,'Choose a program for formatted Markdown exports. TXT and HTML already work.')
 if checks and not checks.get('PDF export'):row.detail+=' Markdown PDF also needs a compatible PDF engine; this remains unverified until that check passes.'
 return row

def check_program(key,path,settings=None,cancel=None):
 """Check an explicitly selected executable without changing active engines."""
 path=str(Path(path).resolve());runner=CheckRunner(cancel);deps=dependencies()
 if not Path(path).is_file() or not os.access(path,os.X_OK):return Result(key,TITLES[key],'failed','Choose an executable file.',(),{}),{}
 if key=='office':return probe_office(path,runner),{}
 version_args,identity={'images':(['-version'],'imagemagick'),'media':(['-version'],'ffmpeg'),'pdf':(['-v'],'pdftoppm'),'archives':([], '7-zip'),'markdown':(['--version'],'pandoc')}[key]
 try:
  version=runner.run([path,*version_args],timeout=10)
  if identity not in version.lower():return Result(key,TITLES[key],'failed','This program does not expose the command interface used by these conversions.',(),{'Compatible command interface':False}),{}
 except Cancelled:raise
 except (OSError,ConversionError):return Result(key,TITLES[key],'failed','This program could not be started with the required conversion interface.',(),{'Compatible command interface':False}),{}
 slot={'images':'ImageMagick','media':'FFmpeg','pdf':'PDF images','archives':'7-Zip','markdown':'Pandoc'}[key];overrides={slot:path}
 siblings={'media':{'FFprobe':'ffprobe','FFplay':'ffplay'},'pdf':{'PDF text':'pdftotext'}}.get(key,{})
 for name,filename in siblings.items():
  candidate=Path(path).parent/filename
  if candidate.is_file() and os.access(candidate,os.X_OK):overrides[name]=str(candidate)
 deps.update(overrides)
 with tempfile.TemporaryDirectory(prefix='petal-choice-check-') as td:
  folder=Path(td)
  row={'images':lambda:probe_images(path,runner,folder),'media':lambda:probe_media(path,runner,folder,deps),'pdf':lambda:probe_pdf(deps,runner,folder),'archives':lambda:probe_archives(path,runner,folder),'markdown':lambda:probe_markdown(path,runner,folder)}[key]()
 return row,overrides

def scan(settings=None,progress=None,cancel=None):
 settings=settings or {};runner=CheckRunner(cancel);deps=dependencies();results=[]
 paths=settings.get('engine_paths',{})
 if isinstance(paths,dict):
  for key,path in paths.items():
   if key in deps and isinstance(path,str) and Path(path).is_file() and os.access(path,os.X_OK):deps[key]=path
 with tempfile.TemporaryDirectory(prefix='petal-readiness-') as td:
  folder=Path(td)
  jobs=[('office',lambda:probe_office(settings.get('libreoffice_path') or deps.get('LibreOffice'),runner)),('images',lambda:probe_images(deps.get('ImageMagick'),runner,folder)),('media',lambda:probe_media(deps.get('FFmpeg'),runner,folder,deps)),('pdf',lambda:probe_pdf(deps,runner,folder))]
  for key,fn in jobs:
   runner.check()
   if progress:progress(TITLES[key])
   try:results.append(fn())
   except Cancelled:raise
   except Exception as e:results.append(Result(key,TITLES[key],'failed','Could not check: '+str(e)[:240],PACKAGES.get(key,()),{}))
  results.append(probe_archives(deps.get('7-Zip'),runner,folder))
  results.append(probe_markdown(deps.get('Pandoc'),runner,folder))
  exe=deps.get('LocalSend');share=settings.get('sharing_app','')
  if share and not share.startswith('command:'):
   from .integrations import app_info
   try:app_info(share);results.append(Result('sharing',TITLES['sharing'],'available','Your selected sharing application is installed; delivery depends on that app.',(),{'Selected app installed':True}))
   except Exception:results.append(Result('sharing',TITLES['sharing'],'missing','Your selected sharing app is unavailable. Choose another in Applications.',(),{}))
  else:results.append(Result('sharing',TITLES['sharing'],'available' if exe else 'optional','LocalSend is available; delivery depends on the receiving device.' if exe else 'Optional: choose a sharing app in Applications. Files can also be dragged from the shelf.',(),{'LocalSend installed':bool(exe)},exe or ''))
  checks={name:importlib.util.find_spec(module) is not None for name,module in [('Image previews','PIL'),('PDF tools','pypdf'),('Archives','zipfile'),('Subtitles & text','re')]}
  results.append(result('builtin','Python',checks))
 return results
