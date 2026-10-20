"""Real capability scan and native installer review; package execution is mocked."""
import argparse,json,os,sys,tempfile,traceback
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True);args=parser.parse_args();output=Path(args.output_dir).resolve();output.mkdir(parents=True,exist_ok=True)
scratch=tempfile.TemporaryDirectory(prefix='petal-software-check-')
os.environ['PETAL_STATE_DIR']=str(Path(scratch.name)/'state');os.environ['GSETTINGS_BACKEND']='memory';os.environ['PETAL_APP_ID']='io.github.petal.SoftwareCheck';os.environ['PETAL_DISABLE_TRAY']='1'
from petal.app import Petal
from petal.legacy import Gtk,GLib
from petal import readiness,integrations

class Check(Petal):
 def __init__(self):super().__init__();self.checks={};self.failed=False;self.stage=0;self.ticks=0;self.launch_patch=patch.object(integrations,'launch_terminal');self.launch=self.launch_patch.start()
 def check(self,key,value):
  self.checks[key]=bool(value)
  if not value:raise AssertionError(key)
 def do_command_line(self,cmd):
  self.show_software();GLib.timeout_add(200,self.advance);return 0
 def capture(self,window,name):
  widget=window.get_child();paint=Gtk.WidgetPaintable.new(widget);snapshot=Gtk.Snapshot();paint.snapshot(snapshot,window.get_width(),window.get_height());node=snapshot.to_node();self.check('render_'+name,node is not None);window.get_renderer().render_texture(node,None).save_to_png(str(output/(name+'.png')))
 def advance(self):
  self.ticks+=1
  try:
   if self.ticks>600:raise TimeoutError('Software verification timed out')
   page=self.software_window.page
   if page.checking:return True
   if self.stage==0:
    self.check('real_scan_completed',len(page.results)==8);self.check('missing_office_detected',any(r.key=='office' and r.status=='missing' for r in page.results));self.check('sample_image_and_media_exports_passed',all(r.status=='ready' for r in page.results if r.key in ('images','media')));self.check('no_automatic_install',not self.launch.called);self.check('all_downloads_opt_in',not any(b.get_active() for b in page.choices.values()));self.check('install_disabled_without_selection',not page.install_button.get_sensitive());self.capture(self.software_window.window,'software-check');self.real_results=page.results
    (output/'capabilities.json').write_text(json.dumps([r.data() for r in page.results],indent=2)+'\n');self.check('no_program_preselected',all(d.get_selected()==0 for d in page.program_pickers.values()));page.program_pickers['office'].set_selected(1);page.review();self.stage=1
   elif self.stage==1:
    self.check('native_review_opens',page.review_window.get_visible());self.check('review_does_not_install',not self.launch.called);self.capture(page.review_window,'installation-review');page.review_window.close();self.check('cancel_does_not_install',not self.launch.called and page.review_window is None);page.test_office('/usr/bin/true');self.stage=2
   elif self.stage==2:
    self.check('incompatible_program_rejected',not self.settings.get('libreoffice_path'));self.check('neutral_alternative_choice','Choose another program' in page.message.get_text() and 'recommend' not in page.message.get_text().lower());page.review();page.confirm_install_button.emit('clicked');self.check('explicit_confirmation_opens_terminal',self.launch.call_count==1);self.check('only_selected_packages_planned',json.loads((page.install_job/'plan.json').read_text())['packages']==['libreoffice-fresh']);payload=self.launch.call_args.args[2];self.check('installer_receives_literal_argv',payload[1].endswith('install_helper.py') and payload[2].endswith('plan.json'))
    self.scan_patch=patch.object(readiness,'scan',return_value=self.real_results);self.scan_patch.start();(page.install_job/'result.json').write_text(json.dumps({'success':False,'message':'Installation cancelled. Existing features remain available.'}));page.poll_install();self.stage=3
   elif self.stage==3:
    self.check('cancelled_install_is_reported','cancelled' in page.message.get_text());self.check('installation_triggers_rescan',bool(page.results) and page.install_job is None);self.check('no_additional_terminal_launched',self.launch.call_count==1)
    with patch.object(self,'save_settings',side_effect=OSError('simulated read-only settings')):saved=page.save_office('/tmp/check-office')
    self.check('failed_selection_save_preserves_previous_program',not saved and not self.settings.get('libreoffice_path'));self.check('failed_selection_save_explained','could not be saved' in page.message.get_text());self.complete();return False
  except Exception:self.failed=True;traceback.print_exc();self.complete();return False
  return True
 def complete(self):
  if hasattr(self,'scan_patch'):self.scan_patch.stop()
  self.launch_patch.stop();(output/'checks.json').write_text(json.dumps({'passed':not self.failed,'checks':self.checks,'installation_testing':'Terminal launch and package execution mocked; no packages installed.'},indent=2)+'\n');print(json.dumps(self.checks),flush=True);self.request_quit()
if not Gtk.init_check():raise SystemExit('Wayland desktop is unavailable')
app=Check();status=app.run(['software-check']);raise SystemExit(status or int(app.failed))
