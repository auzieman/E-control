import importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('displays',ROOT/'tools/display-provider.py');provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)
class Displays(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  subprocess.run([sys.executable,str(ROOT/'tests/create_display_fixture.py'),str(self.root)],check=True)
  self.env=dict(os.environ,PATH=str(self.root/'bin')+os.pathsep+os.environ['PATH'],WORKSTATION_TEST_DISPLAY_STATE=str(self.root/'state.json'),XDG_RUNTIME_DIR=str(self.root),XDG_SESSION_TYPE='x11')
  self.before=json.loads((self.root/'state.json').read_text());self.plan=[dict(o,mode='1280x720',x=n*1280,panning='0x0') for n,o in enumerate(self.before['outputs'])]
 def start(self,seconds=.25,**extra):
  code="import importlib.util,json,sys; s=importlib.util.spec_from_file_location('d',sys.argv[1]); d=importlib.util.module_from_spec(s); s.loader.exec_module(d); d.trial(json.loads(sys.argv[2]),seconds=float(sys.argv[3]))"
  return subprocess.Popen([sys.executable,'-c',code,str(ROOT/'tools/display-provider.py'),json.dumps(self.plan),str(seconds)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(self.env,**extra))
 def state(self):return json.loads((self.root/'state.json').read_text())
 def test_snapshot_reads_without_writes(self):
  with patch.dict(os.environ,self.env,clear=True):s=provider.snapshot()
  self.assertEqual(s['outputs'][1]['x'],1600);self.assertTrue(s['supported']);self.assertFalse((self.root/'state.writes').exists())
 def test_timeout_restores_positions_modes_panning(self):
  p=self.start();self.assertTrue(p.stdout.readline().startswith('pending'))
  p.wait(timeout=5);self.assertEqual(self.state(),self.before);p.communicate()
 def test_keep_retains_new_state(self):
  p=self.start(3);self.assertTrue(p.stdout.readline().startswith('pending'));out,err=p.communicate('keep\n',timeout=5)
  self.assertEqual(p.returncode,0,err);self.assertIn('kept',out);self.assertEqual(self.state()['outputs'][1]['x'],1280)
 def test_ui_close_reverts(self):
  p=self.start(3);p.stdout.readline();out,err=p.communicate('',timeout=5)
  self.assertIn('reverted',out);self.assertEqual(self.state(),self.before)
 def test_partial_apply_failure_restores(self):
  p=self.start(WORKSTATION_TEST_FAIL_APPLY='1');out,err=p.communicate('',timeout=5)
  self.assertIn('reverted',out);self.assertEqual(self.state(),self.before)
 def test_all_off_rejected_before_write(self):
  self.plan=[dict(o,mode=None) for o in self.plan];p=self.start();p.communicate('',timeout=5)
  self.assertNotEqual(p.returncode,0);self.assertFalse((self.root/'state.writes').exists())
 def test_missing_display_rejected_before_write(self):
  self.plan.pop();p=self.start();p.communicate('',timeout=5);self.assertNotEqual(p.returncode,0);self.assertFalse((self.root/'state.writes').exists())
 def test_unavailable_mode_rejected_before_write(self):
  self.plan[0]['mode']='9999x9999';p=self.start();p.communicate('',timeout=5);self.assertNotEqual(p.returncode,0);self.assertFalse((self.root/'state.writes').exists())
 def test_closed_stdout_does_not_prevent_restore(self):
  p=self.start(3);p.stdout.readline();p.stdout.close();p.stdin.close();p.wait(timeout=5);p.stderr.close()
  self.assertEqual(self.state(),self.before)
 def test_second_transaction_cannot_interfere(self):
  first=self.start(3);first.stdout.readline();second=self.start();second.communicate('',timeout=5)
  self.assertNotEqual(second.returncode,0);first.communicate('revert\n',timeout=5);self.assertEqual(self.state(),self.before)
 def test_disabling_main_selects_an_enabled_main(self):
  old=dict(outputs=self.before['outputs'],supported=True)
  self.plan[0]['mode']=None
  provider.validate(old,self.plan)
  self.assertFalse(self.plan[0]['primary']);self.assertTrue(self.plan[1]['primary'])
 def test_unknown_active_mode_is_not_treated_as_off(self):
  text='Screen 0: minimum 320 x 200, current 800 x 600, maximum 16384 x 16384\neDP-1 connected 800x600+0+0 (normal left inverted right x axis y axis)\n   custom-mode 60.00*+\n'
  with patch.object(provider,'run',return_value=text),self.assertRaises(ValueError):provider.snapshot()
 def test_restore_without_a_primary_clears_trial_primary(self):
  for o in self.before['outputs']:o['primary']=False
  (self.root/'state.json').write_text(json.dumps(self.before))
  for o in self.plan:o['primary']=False
  p=self.start();p.stdout.readline();p.wait(timeout=5);p.communicate();self.assertEqual(self.state(),self.before)
 def test_scaled_layout_rejected(self):
  old=dict(outputs=self.before['outputs'],supported=False)
  with self.assertRaises(ValueError):provider.validate(old,self.plan)
if __name__=='__main__':unittest.main()
