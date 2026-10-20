"""Preference migration and real launch routing, without starting external apps."""
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
from petal.preferences import normalize,DEFAULTS,readable_ink
from petal import integrations

class PreferenceTests(unittest.TestCase):
 def test_existing_settings_survive_first_run_migration(self):
  old={'output_dir':'/tmp/my exports','drop_target':False,'quality':91,'dpi':200,'notify':False}
  updated=normalize(old)
  for k,v in old.items():self.assertEqual(updated[k],v)
  self.assertFalse(updated['setup_completed']);self.assertEqual(old,{'output_dir':'/tmp/my exports','drop_target':False,'quality':91,'dpi':200,'notify':False})
 def test_invalid_appearance_is_normalized(self):
  p=normalize({'accent_color':'red;}window{color:red','petal_color':None,'text_color':'#ABCDEF','petal_opacity':500,'appearance_mode':'unknown','animations':'false','setup_completed':'yes'})
  self.assertEqual(p['accent_color'],DEFAULTS['accent_color']);self.assertEqual(p['petal_color'],'#ffffff');self.assertEqual(p['text_color'],'#abcdef');self.assertEqual(p['petal_opacity'],100);self.assertTrue(p['animations']);self.assertFalse(p['setup_completed'])
 def test_light_and_dark_accents_have_legible_ink(self):
  self.assertEqual(readable_ink('#ffffff'),(.10,.11,.12));self.assertEqual(readable_ink('#000000'),(1,1,1))
 def test_terminal_paths_are_literal_arguments(self):
  with patch.object(integrations.shutil,'which',side_effect=lambda n:'/usr/bin/'+n):
   cmd=integrations.terminal_command('command:ghostty','/tmp/a folder; $(test)',payload=['/usr/bin/yazi','/tmp/one file'])
  self.assertEqual(cmd,['/usr/bin/ghostty','--working-directory=/tmp/a folder; $(test)','-e','/usr/bin/yazi','/tmp/one file'])
 def test_chosen_terminal_is_used_for_yazi(self):
  with tempfile.TemporaryDirectory() as td,patch.object(integrations.shutil,'which',side_effect=lambda n:'/usr/bin/'+n),patch.object(integrations.subprocess,'Popen') as spawn:
   integrations.launch({'file_manager':'yazi.desktop','terminal_app':'command:kitty'},'file_manager',[Path(td)])
   argv=spawn.call_args.args[0];self.assertEqual(argv[0],'/usr/bin/kitty');self.assertIn('/usr/bin/yazi',argv);self.assertEqual(argv[-1],td);self.assertNotIn('shell',spawn.call_args.kwargs)
 def test_selected_file_manager_uses_gio_and_preserves_spaces(self):
  app=Mock()
  with patch.object(integrations,'app_info',return_value=app):integrations.launch({'file_manager':'custom.desktop'},'file_manager',[Path('/tmp/a folder')])
  files=app.launch.call_args.args[0];self.assertEqual(files[0].get_path(),'/tmp/a folder')
 def test_missing_selected_app_does_not_launch_another(self):
  with patch.object(integrations,'app_info',side_effect=integrations.AppUnavailable('missing')),patch.object(integrations.Gio.AppInfo,'launch_default_for_uri') as fallback:
   with self.assertRaises(integrations.AppUnavailable):integrations.launch({'image_app':'missing.desktop'},'image_app',[Path('/tmp/a.png')])
   fallback.assert_not_called()
 def test_open_uses_preferences_for_each_file_family(self):
  paths=[Path('/tmp/a.png'),Path('/tmp/b.mp4'),Path('/tmp/c.pdf')]
  with patch.object(integrations,'launch') as launch:integrations.open_files({},paths)
  self.assertEqual([c.args[1] for c in launch.call_args_list],['image_app','media_app','document_app'])
 def test_sharing_choice_is_used_without_a_shell(self):
  with patch.object(integrations.shutil,'which',return_value='/usr/bin/localsend'),patch.object(integrations.subprocess,'Popen') as spawn:
   integrations.launch({'sharing_app':'command:localsend'},'sharing_app',[Path('/tmp/a file.txt')])
   self.assertEqual(spawn.call_args.args[0],['/usr/bin/localsend','/tmp/a file.txt']);self.assertNotIn('shell',spawn.call_args.kwargs)

if __name__=='__main__':unittest.main(verbosity=2)
