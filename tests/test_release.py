"""Release boundaries: safe launchers, configuration, optimized validation, archives."""
import tomllib,re,hashlib,importlib.util,os,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from petal import __version__
from petal.preferences import normalize,PRESETS,rgb,readable_ink
class ReleaseTests(unittest.TestCase):
 def test_release_version_matches_metadata_changelog_and_archive(self):
  expected=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
  self.assertEqual(__version__,expected)
  self.assertEqual(re.search(r'^## ([^ ]+)',(ROOT/'CHANGELOG.md').read_text(),re.M).group(1),expected)
  spec=importlib.util.spec_from_file_location('petal_version_builder',ROOT/'scripts/build_release.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
  with tempfile.TemporaryDirectory() as td:
   archives=builder.build(Path(td))
   self.assertEqual(archives[1].name,'petal-'+expected+'-linux.zip')
   with zipfile.ZipFile(archives[1]) as z:
    metadata=tomllib.loads(z.read('petal-'+expected+'/pyproject.toml').decode());self.assertEqual(metadata['project']['version'],expected)
 def test_hidden_wheel_does_not_hit_test_zero_geometry(self):
  from petal import wheel
  self.assertEqual(wheel.hit(180,60,0,0,8),-1)
 def test_headless_cli_help_and_version_do_not_write_state(self):
  with tempfile.TemporaryDirectory() as td:
   env=dict(os.environ,PETAL_STATE_DIR=str(Path(td)/'state'),WAYLAND_DISPLAY='',DISPLAY='')
   for flag,expected in [('--version','Petal '+__version__),('--help','Tangerine for macOS')]:
    result=subprocess.run([str(ROOT/'petal-run'),flag],env=env,text=True,capture_output=True);self.assertEqual(result.returncode,0,result.stderr);self.assertIn(expected,result.stdout)
   self.assertFalse((Path(td)/'state').exists())
 def test_unknown_option_fails_without_opening_ui(self):
  result=subprocess.run([str(ROOT/'petal-run'),'--no-such-option'],capture_output=True,text=True);self.assertEqual(result.returncode,2);self.assertIn('Unknown option',result.stderr)
 def test_invalid_workflow_preferences_are_normalized(self):
  result=normalize({'quality':9999,'dpi':-40,'notify':'yes','tray_enabled':None,'output_dir':[],'engine_paths':['bad']});self.assertEqual((result['quality'],result['dpi']),(100,36));self.assertTrue(result['notify']);self.assertTrue(result['tray_enabled']);self.assertEqual(result['output_dir'],'');self.assertEqual(result['engine_paths'],{})
 def test_primary_button_text_contrast_is_at_least_aa_for_palette(self):
  def lum(rgb):return sum((v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)*w for v,w in zip(rgb,(.2126,.7152,.0722)))
  for color in [p[0] for p in PRESETS.values()]+['#ffffff','#000000','#808080']:
   levels=sorted([lum(rgb(color)),lum(readable_ink(color,reference=False))]);self.assertGreaterEqual((levels[1]+.05)/(levels[0]+.05),4.5,color)
 def test_output_validation_still_runs_with_python_optimized(self):
  code='from petal.readiness import assert_output\nfrom pathlib import Path\ntry: assert_output(Path("/definitely-missing-petal-output.pdf"))\nexcept ValueError: raise SystemExit(0)\nraise SystemExit(1)'
  env=dict(os.environ,PYTHONPATH=str(ROOT)+os.pathsep+str(ROOT/'vendor'));result=subprocess.run([sys.executable,'-O','-c',code],env=env,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr)
 def test_desktop_install_and_remove_keep_source_and_settings(self):
  with tempfile.TemporaryDirectory(prefix='petal install ') as td:
   prefix=Path(td)/'local path';args=[sys.executable,str(ROOT/'install.py'),'--prefix',str(prefix)]
   result=subprocess.run(args,capture_output=True,text=True);self.assertEqual(result.returncode,0,result.stderr);entry=prefix/'share/applications/io.github.xoalt.Petal.desktop';self.assertIn('Petal managed launcher',entry.read_text());check=subprocess.run([str(prefix/'bin/petal'),'--version'],capture_output=True,text=True);self.assertEqual(check.returncode,0,check.stderr)
   if __import__('shutil').which('desktop-file-validate'):subprocess.run(['desktop-file-validate',str(entry)],check=True)
   subprocess.run([*args,'--remove'],check=True,capture_output=True);self.assertFalse(entry.exists());self.assertTrue((ROOT/'petal-run').exists())
 def test_installer_refuses_an_unrelated_existing_launcher(self):
  with tempfile.TemporaryDirectory() as td:
   prefix=Path(td);(prefix/'bin').mkdir();existing=prefix/'bin/petal';existing.write_text('my existing program')
   result=subprocess.run([sys.executable,str(ROOT/'install.py'),'--prefix',td],capture_output=True,text=True);self.assertNotEqual(result.returncode,0);self.assertEqual(existing.read_text(),'my existing program');self.assertFalse((prefix/'share').exists())
 def test_archives_are_reproducible_and_exclude_user_data(self):
  spec=importlib.util.spec_from_file_location('petal_release_builder',ROOT/'scripts/build_release.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  with tempfile.TemporaryDirectory() as td:
   base=Path(td);(base/'petal').mkdir();(base/'petal/__init__.py').write_text('');(base/'pyproject.toml').write_text('[project]\nversion="9.8.7-beta.1"\n');(base/'petal-run').write_text('#!/bin/sh\n');(base/'state').mkdir();(base/'state/settings.json').write_text('PRIVATE');(base/'.git').mkdir();(base/'.git/config').write_text('PRIVATE')
   with patch.object(module,'ROOT',base):a=module.build(base/'a');b=module.build(base/'b')
   for one,two in zip(a,b):self.assertEqual(hashlib.sha256(one.read_bytes()).digest(),hashlib.sha256(two.read_bytes()).digest())
   with zipfile.ZipFile(a[1]) as z:self.assertFalse(any('state/' in name or '.git/' in name for name in z.namelist()))
if __name__=='__main__':unittest.main(verbosity=2)
