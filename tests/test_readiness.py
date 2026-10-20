"""Capability checks and installation boundaries. Never installs system packages."""
import json,os,sys,tempfile,unittest,zipfile,shutil
from pathlib import Path
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from petal import readiness as r,install_helper

class ReadinessTests(unittest.TestCase):
 def test_missing_office_is_not_ready(self):
  row=r.probe_office(None);self.assertEqual(row.status,'missing');self.assertIn('libreoffice-fresh',row.packages)
 def test_unrelated_program_is_not_accepted_as_office(self):
  runner=Mock();runner.run.return_value='Some PDF Viewer 1.0'
  with tempfile.TemporaryDirectory() as td:
   exe=Path(td)/'viewer';exe.touch();exe.chmod(0o755);row=r.probe_office(str(exe),runner)
  self.assertEqual(row.status,'failed');self.assertEqual(runner.run.call_count,1)
 def test_office_checks_every_configured_family_export(self):
  class FakeRunner:
   def run(self,args,**kwargs):
    if '--version' in args:return 'LibreOffice test'
    fmt=args[args.index('--convert-to')+1].split(':')[0];out=Path(args[args.index('--outdir')+1]);target=out/('sample.'+fmt)
    if fmt in ('docx','odt','epub','pptx','odp','xlsx','ods'):
     with zipfile.ZipFile(target,'w') as z:z.writestr('content.xml','sample')
    else:target.write_bytes(b'%PDF-1.7 sample' if fmt=='pdf' else b'sample')
  with tempfile.TemporaryDirectory() as td:
   exe=Path(td)/'office';exe.touch();exe.chmod(0o755);row=r.probe_office(str(exe),FakeRunner())
  self.assertEqual(row.status,'ready');self.assertEqual(len(row.checks),15)
 def test_version_only_program_does_not_pass_conversion_checks(self):
  runner=Mock();runner.run.return_value='LibreOffice test'
  with tempfile.TemporaryDirectory() as td:
   exe=Path(td)/'office';exe.touch();exe.chmod(0o755);row=r.probe_office(str(exe),runner)
  self.assertEqual(row.status,'failed');self.assertFalse(any(row.checks.values()))
 def test_partial_codec_support_is_reported(self):
  row=r.result('media','/usr/bin/ffmpeg',{'MP4':True,'WEBM':False})
  self.assertEqual(row.status,'partial');self.assertIn('WEBM',row.detail)
 def test_plan_uses_only_known_packages_and_interactive_system_installer(self):
  with patch.object(r.shutil,'which',side_effect=lambda name:'/usr/bin/'+name):plan=r.install_plan(['office','media','office'],'arch',{'office':'libreoffice-fresh','media':'ffmpeg'})
  self.assertEqual(plan['packages'],['ffmpeg','libreoffice-fresh']);self.assertEqual(plan['command'],['/usr/bin/pkexec','/usr/bin/pacman','-S','--needed','ffmpeg','libreoffice-fresh'])
  self.assertNotIn('--noconfirm',plan['command']);self.assertNotIn('-Sy',plan['command']);self.assertNotIn('-Syu',plan['command'])
 def test_unknown_feature_cannot_become_shell_or_package_argument(self):
  with self.assertRaises(ValueError):r.install_plan(['office; echo bad'],'arch')
 def test_unsupported_distro_offers_manual_option(self):
  with self.assertRaisesRegex(ValueError,'official download links'):r.install_plan(['office'],'unknown')
 def test_empty_selection_does_not_install(self):
  with self.assertRaises(ValueError):r.install_plan([],'arch')
 def test_no_default_program_is_selected_for_download(self):
  with self.assertRaisesRegex(ValueError,'Choose a program'):r.install_plan(['office'],'arch')
 def test_user_can_choose_either_office_package(self):
  with patch.object(r.shutil,'which',side_effect=lambda name:'/usr/bin/'+name):plan=r.install_plan(['office'],'arch',{'office':'libreoffice-still'})
  self.assertEqual(plan['packages'],['libreoffice-still'])
 def test_external_program_is_checked_without_changing_active_engine(self):
  with patch.object(r,'probe_images',return_value=r.Result('images',r.TITLES['images'],'ready','passed',(),{'PNG':True})) as probe,patch.object(r.CheckRunner,'run',return_value='ImageMagick test'):
   row,paths=r.check_program('images','/usr/bin/true')
  self.assertEqual(row.status,'ready');self.assertEqual(paths,{'ImageMagick':str(Path('/usr/bin/true').resolve())});probe.assert_called_once()
 @unittest.skipUnless(shutil.which('magick'),'ImageMagick unavailable')
 def test_chosen_external_program_is_used_for_real_conversion(self):
  from petal.catalog import configure_engines
  from petal.engine import execute
  from PIL import Image
  with tempfile.TemporaryDirectory() as td,patch.dict(os.environ):
   folder=Path(td);exe=folder/'external program';magick=shutil.which('magick');exe.write_text('#!/usr/bin/python3\nimport os,sys\nprogram='+repr(magick)+'\nos.execv(program,[program,*sys.argv[1:]])\n');exe.chmod(0o755)
   row,paths=r.check_program('images',str(exe));self.assertEqual(row.status,'ready');configure_engines({'engine_paths':paths})
   self.assertEqual(r.dependencies()['ImageMagick'],str(exe));source=folder/'input file.png';Image.new('RGB',(16,16),'orange').save(source);original=source.read_bytes();out=execute([source],'to:webp',{})
   self.assertTrue(out[0].is_file());self.assertEqual(source.read_bytes(),original)
 def test_rejected_installation_preserves_failure_in_report(self):
  plan={'features':['office'],'packages':['libreoffice-fresh'],'command':['/usr/bin/pkexec','/usr/bin/pacman','-S','--needed','libreoffice-fresh']}
  with tempfile.TemporaryDirectory() as td,patch.object(install_helper,'install_plan',return_value=plan),patch.object(install_helper.subprocess,'run',return_value=Mock(returncode=0)),patch.object(install_helper.subprocess,'call',return_value=1) as call:
   p=Path(td)/'plan.json';p.write_text(json.dumps(plan));self.assertEqual(install_helper.main(p),1);report=json.loads(p.with_name('result.json').read_text());self.assertFalse(report['success']);self.assertIn('cancelled or failed',report['message']);call.assert_called_once_with(plan['command'])
 def test_repository_failure_does_not_attempt_install_or_refresh(self):
  plan={'features':['office'],'packages':['libreoffice-fresh'],'command':['/usr/bin/pkexec','/usr/bin/pacman','-S','--needed','libreoffice-fresh']}
  with tempfile.TemporaryDirectory() as td,patch.object(install_helper,'install_plan',return_value=plan),patch.object(install_helper.subprocess,'run',return_value=Mock(returncode=1)),patch.object(install_helper.subprocess,'call') as call:
   p=Path(td)/'plan.json';p.write_text(json.dumps(plan));self.assertEqual(install_helper.main(p),1);call.assert_not_called()
 def test_tampered_package_plan_is_rejected(self):
  plan={'features':['office'],'packages':['libreoffice-fresh'],'command':['/usr/bin/pkexec','/usr/bin/pacman','-S','--needed','libreoffice-fresh']}
  with tempfile.TemporaryDirectory() as td,patch.object(install_helper,'install_plan',return_value=plan),patch.object(install_helper.subprocess,'run') as run,patch.object(install_helper.subprocess,'call') as call:
   p=Path(td)/'plan.json';p.write_text(json.dumps({'features':['office'],'packages':['unrelated']}));self.assertEqual(install_helper.main(p),1);run.assert_not_called();call.assert_not_called()
if __name__=='__main__':unittest.main(verbosity=2)
