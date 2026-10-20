"""Interactive terminal installer; only predefined distro package plans are accepted."""
import json,os,subprocess,sys,signal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from petal.readiness import install_plan

def main(plan_file):
 job=Path(plan_file).resolve();result=job.with_name('result.json');outcome={'success':False,'message':'Installation did not complete.'}
 try:
  job.with_name('started.json').write_text(json.dumps({'pid':os.getpid()}))
  saved=json.loads(job.read_text());plan=install_plan(saved['features'],programs=saved.get('programs'))
  if saved['packages']!=plan['packages']:raise ValueError('The installation plan changed. Review it again in Petal.')
  print('Petal — selected software\n',flush=True)
  print('Packages: '+', '.join(plan['packages']),flush=True)
  print('The system installer will show dependencies and download sizes, ask for confirmation, and request authentication.\n',flush=True)
  metadata=subprocess.run([plan['command'][1],'-Si',*plan['packages']],capture_output=True,text=True,timeout=30)
  if metadata.returncode:raise ValueError('A selected package is unavailable in the current repository database. Use your normal system software manager to update the system, then try again. No repository refresh or system upgrade was attempted.')
  code=subprocess.call(plan['command'])
  outcome={'success':code==0,'message':'Installation finished. Petal will check the features again.' if code==0 else 'Installation was cancelled or failed. Existing features remain available. Review the terminal output, or install with your software manager.'}
 except KeyboardInterrupt:outcome['message']='Installation interrupted. Petal will check which features are available.'
 except Exception as e:outcome['message']=str(e)
 finally:
  temp=result.with_suffix('.tmp');temp.write_text(json.dumps(outcome));temp.replace(result)
  print('\n'+outcome['message'],flush=True)
  if sys.stdin.isatty():
   try:input('\nPress Enter to close this window. ')
   except (EOFError,KeyboardInterrupt):pass
 return 0 if outcome['success'] else 1
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
