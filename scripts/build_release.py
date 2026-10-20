#!/usr/bin/env python3
"""Build reproducible, allowlisted release archives; exclude all user state."""
import ast,gzip,hashlib,io,json,os,tarfile,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def build(destination=None):
 version=next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'petal/__init__.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in n.targets))
 prefix=f'petal-{version}';out=Path(destination or ROOT/'dist');out.mkdir(parents=True,exist_ok=True);epoch=int(os.environ.get('SOURCE_DATE_EPOCH','1792454400'));files={}
 allowed=['petal','vendor','assets','integration','tests','scripts','docs','README.md','LICENSE','CHANGELOG.md','SECURITY.md','CONTRIBUTING.md','requirements-audit.txt','pyproject.toml','petal-run','install.py']
 for item in allowed:
  path=ROOT/item
  if not path.exists():continue
  for p in ([path] if path.is_file() else sorted(path.rglob('*'))):
   if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.suffix=='.pyc':continue
   name=p.relative_to(ROOT).as_posix();files[name]=p.read_bytes()
 hashes={name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())};files['SHA256SUMS']=''.join(f'{h}  {n}\n' for n,h in hashes.items()).encode()
 archives=[out/f'{prefix}-linux.tar.gz',out/f'{prefix}-linux.zip']
 with archives[0].open('wb') as f,gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=epoch) as gz,tarfile.open(fileobj=gz,mode='w') as tar:
  for name,data in sorted(files.items()):
   info=tarfile.TarInfo(prefix+'/'+name);info.size=len(data);info.mtime=epoch;info.mode=0o755 if name=='petal-run' else 0o644;tar.addfile(info,io.BytesIO(data))
 with zipfile.ZipFile(archives[1],'w',zipfile.ZIP_DEFLATED) as z:
  for name,data in sorted(files.items()):
   info=zipfile.ZipInfo(prefix+'/'+name,time.gmtime(max(epoch,315532800))[:6]);info.create_system=3;info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=(0o100755 if name=='petal-run' else 0o100644)<<16;z.writestr(info,data)
 with zipfile.ZipFile(archives[1]) as z:
  assert z.testzip() is None
  for name,h in hashes.items():assert hashlib.sha256(z.read(prefix+'/'+name)).hexdigest()==h,name
 with tarfile.open(archives[0]) as tar:
  for name,h in hashes.items():assert hashlib.sha256(tar.extractfile(prefix+'/'+name).read()).hexdigest()==h,name
 (out/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in archives));print(json.dumps({'version':version,'files':len(files),'archives':[str(p) for p in archives],'hashes_verified':True}));return archives
if __name__=='__main__':build()
