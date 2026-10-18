"""Behavior tests use mocked services; never mutate the workstation."""
import contextlib,importlib.util,io,sys,types,unittest,json
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.parse import unquote
spec=importlib.util.spec_from_file_location('workstation',Path(__file__).resolve().parents[1]/'tools/workstation-provider.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def view(op,target,values=None):
 o=io.StringIO()
 with contextlib.redirect_stdout(o):p.main({'op':op,'target':target,'values':values or {}})
 return [[unquote(x) for x in line.split('\t')] for line in o.getvalue().splitlines()]
class FakeDbus:
 @staticmethod
 def Dictionary(v,**kw):return dict(v)
 @staticmethod
 def Array(v,**kw):return list(v)
 ByteArray=bytes;ObjectPath=str;UInt32=int
class WorkstationTests(unittest.TestCase):
 def setUp(self):
  self.dbus=patch.dict(sys.modules,{'dbus':FakeDbus});self.dbus.start();self.addCleanup(self.dbus.stop)
  self.appearance=patch.object(p,'appearance_state',return_value=None);self.appearance.start();self.addCleanup(self.appearance.stop)
  self.catalog=patch.object(p,'theme_catalog',return_value={});self.catalog.start();self.addCleanup(self.catalog.stop)
  self.methods=patch.object(p,'bridge_methods',return_value={'SetTheme','SetWallpaper'});self.methods.start();self.addCleanup(self.methods.stop)
 def test_nm_security_flag_values(self):
  for flag,label in [(256,'WPA Personal'),(512,'Enterprise'),(1024,'WPA3 Personal'),(2048,'Enhanced Open'),(8192,'Enterprise')]:
   self.assertEqual(p.security_type({'RsnFlags':flag,'Flags':1}),label)
 def test_wifi_identity_and_password_are_separate(self):
  with patch.object(p,'device'),patch.object(p,'props',return_value={'Ssid':'A:B\\ Café'.encode(),'Strength':76,'RsnFlags':256,'Flags':1}):
   rows=view('wifi_form','/device|/ap')
  self.assertIn(['heading','Join A:B\\ Café'],rows)
  self.assertIn(['field','password','Wi-Fi password','','password'],rows)
  self.assertIn(['action','Join network','wifi_join','/device|/ap'],rows)
 def test_bluetooth_forget_has_no_password_form(self):
  with patch.object(p,'bt_device',return_value={'Alias':'Headphones','Address':'00:11:22:33:44:55'}):rows=view('bt_forget_form','/bluez/device')
  self.assertFalse(any(x[0]=='field' for x in rows));self.assertIn(['action','Confirm','bt_forget','/bluez/device'],rows)
 def test_connected_bluetooth_offers_disconnect(self):
  with patch.object(p,'bt_device',return_value={'Alias':'Headphones','Address':'00:11:22:33:44:55','Connected':True,'Paired':True}):rows=view('bt_form','/bluez/device')
  self.assertIn(['action','Disconnect','bt_disconnect','/bluez/device'],rows)
  self.assertNotIn(['action','Connect','bt_connect','/bluez/device'],rows)
 def test_wired_lease_defaults(self):
  with patch.object(p,'device',return_value={'Interface':'eth0','ActiveConnection':'/active'}),patch.object(p,'props',return_value={'Connection':'/profile'}),patch.object(p,'connection',return_value=(Mock(),{'connection':{'id':'LAN'},'ipv4':{'method':'auto'}})),patch.object(p,'addresses',return_value=('192.0.2.2/24','192.0.2.1','192.0.2.53')):
   rows=view('wired_form','/device')
  self.assertIn(['field','addresses','IPv4 addresses (CIDR, comma separated)','192.0.2.2/24','entry'],rows)
  self.assertIn(['action','Apply and test','wired_apply','/device|/profile'],rows)
 def test_invalid_static_does_not_create_checkpoint(self):
  n=Mock()
  with patch.object(p,'device',return_value={'ActiveConnection':'/a'}),patch.object(p,'props',return_value={'Connection':'/p'}),patch.object(p,'connection',return_value=(Mock(),{'ipv4':{}})),patch.object(p,'nm',return_value=n):
   with self.assertRaises(ValueError):p.apply('wired_apply','/d|/p',{'automatic':'0','addresses':'bad'})
  n.CheckpointCreate.assert_not_called()
 def test_failed_wired_update_rolls_back(self):
  n=Mock();n.CheckpointCreate.return_value=p.ROOT+'/Checkpoint/1';c=Mock();c.Update.side_effect=RuntimeError('failed')
  with patch.object(p,'device',return_value={'ActiveConnection':'/a'}),patch.object(p,'props',return_value={'Connection':'/p'}),patch.object(p,'connection',return_value=(c,{'ipv4':{}})),patch.object(p,'nm',return_value=n):
   with self.assertRaises(RuntimeError):p.apply('wired_apply','/d|/p',{'automatic':'1'})
  n.CheckpointRollback.assert_called_once_with(p.ROOT+'/Checkpoint/1')
 def test_wifi_secondary_route_and_no_secret_argv(self):
  n=Mock();n.AddAndActivateConnection.return_value=('/profile','/active');ap=Mock();ap.GetAccessPoints.return_value=['/ap']
  with patch.object(p,'device'),patch.object(p,'iface',return_value=ap),patch.object(p,'props',return_value={'Ssid':b'Test','RsnFlags':256,'Flags':1}),patch.object(p,'nm',return_value=n),patch.object(p,'activate_wait'),patch.object(p,'run') as run:
   p.apply('wifi_join','/device|/ap',{'password':'not-a-real-secret'})
  settings=n.AddAndActivateConnection.call_args.args[0]
  self.assertTrue(settings['ipv4']['never-default']);self.assertTrue(settings['ipv6']['never-default']);run.assert_not_called()
 def test_scan_stops_even_on_failure(self):
  a=Mock()
  with patch.object(p,'blue',return_value={'/adapter':{'org.bluez.Adapter1':{}}}),patch.object(p,'iface',return_value=a),patch.object(p.time,'sleep',side_effect=RuntimeError('interrupted')):
   with self.assertRaises(RuntimeError):p.apply('bt_scan','/adapter',{})
  a.StartDiscovery.assert_called_once();a.StopDiscovery.assert_called_once()
 def test_wifi_scan_calls_service(self):
  a=Mock()
  with patch.object(p,'device'),patch.object(p,'iface',return_value=a),patch.object(p.time,'sleep'):p.apply('wifi_scan','/wifi',{})
  a.RequestScan.assert_called_once()
 def test_forget_only_removes_wifi_profile(self):
  c=Mock()
  with patch.object(p,'connection',return_value=(c,{'connection':{'type':'802-3-ethernet'}})):
   with self.assertRaises(ValueError):p.apply('wifi_forget','/profile',{})
  c.Delete.assert_not_called()
 def test_core_service_cannot_be_changed(self):
  with patch.object(p,'run') as run:
   with self.assertRaises(ValueError):p.apply('service_apply','networkmanager',{'running':'0'})
  run.assert_not_called()
 def test_bad_firewall_ports_never_mutate(self):
  with patch.object(p,'run',side_effect=['public','ssh']) as run:
   with self.assertRaises(ValueError):p.apply('firewall_apply','public',{'ports':'99999/tcp'})
  self.assertFalse(any(c.args[0]=='pkexec' for c in run.call_args_list))
 def test_appearance_uses_registry_identity(self):
  with patch.object(p,'e_entries',return_value={'appearance/fonts':True}):rows=view('view','appearance-text')
  self.assertIn(['action','Fonts…','e_open','appearance/fonts'],rows)
  self.assertFalse(any(len(x)>2 and x[2]=='launch' for x in rows))
 def test_appearance_unknown_and_unavailable_do_not_dispatch(self):
  bridge=Mock()
  with patch.object(p,'e_entries',return_value={'appearance/theme':False}),patch.object(p,'e_bridge',return_value=bridge):
   for path in ['appearance/theme','system/restart']:
    with self.assertRaises(ValueError):p.e_open(path)
  bridge.Open.assert_not_called()
 def test_appearance_does_not_apply_on_read(self):
  with patch.object(p,'e_entries',return_value={}),patch.object(p,'e_open') as opened:view('view','appearance')
  opened.assert_not_called()
 def test_wallpaper_preview_never_applies(self):
  bridge=Mock()
  with patch.object(p,'e_entries',return_value={}),patch.object(p,'e_bridge',return_value=bridge),patch.object(p,'wallpaper_catalog',return_value={'/wall.edj':'Wall'}),patch.object(p,'appearance_state',return_value={'theme':'','wallpaper':'','overrides':2,'scale':1.0}):
   rows=view('appearance_wallpaper_preview','/wall.edj')
  bridge.SetWallpaper.assert_not_called()
  apply=next(x for x in rows if x[0]=='action' and x[2]=='appearance_wallpaper_apply')
  self.assertEqual(json.loads(apply[3]),{'file':'/wall.edj','expected':''})
 def test_wallpaper_stale_and_missing_never_write(self):
  bridge=Mock()
  with patch.object(p,'e_bridge',return_value=bridge),patch.object(p,'wallpaper_catalog',return_value={'/wall.edj':'Wall'}),patch.object(p,'appearance_state',return_value={'wallpaper':'/new.edj'}):
   for file in ['/missing.edj','/wall.edj']:
    with self.assertRaises(ValueError):view('appearance_wallpaper_apply',json.dumps({'file':file,'expected':''}))
  bridge.SetWallpaper.assert_not_called()
 def test_wallpaper_apply_verifies_state(self):
  bridge=Mock()
  with patch.object(p,'e_bridge',return_value=bridge),patch.object(p,'appearance_view'),patch.object(p,'wallpaper_catalog',return_value={'/wall.edj':'Wall'}),patch.object(p,'appearance_state',side_effect=[{'wallpaper':''},{'wallpaper':'/wall.edj'}]):
   rows=view('appearance_wallpaper_apply',json.dumps({'file':'/wall.edj','expected':''}))
  bridge.SetWallpaper.assert_called_once_with('/wall.edj','',timeout=5)
  self.assertTrue(any(x[0]=='notice' for x in rows))
 def test_wallpaper_unverified_is_error(self):
  with patch.object(p,'e_bridge'),patch.object(p,'wallpaper_catalog',return_value={'/wall.edj':'Wall'}),patch.object(p,'appearance_state',return_value={'wallpaper':''}):
   with self.assertRaises(ValueError):view('appearance_wallpaper_apply',json.dumps({'file':'/wall.edj','expected':''}))
 def test_appearance_core_pages_have_specific_controls(self):
  with patch.object(p,'e_entries',return_value={x:True for x in p.E_PATHS}):
   textrows=view('view','appearance-text');layoutrows=view('view','appearance-layout')
  self.assertIn(['action','Fonts…','e_open','appearance/fonts'],textrows)
  self.assertIn(['action','Panels and shelves…','e_open','extensions/shelves'],layoutrows)
  self.assertFalse(any(x[0]=='action' and x[-1]=='windows/tiling' for x in textrows+layoutrows))
 def test_advanced_exposes_apps_gadgets_modules_and_effects(self):
  with patch.object(p,'e_entries',return_value={x:True for x in p.E_PATHS}):rows=view('view','appearance-advanced')
  paths={r[3] for r in rows if r[0]=='action' and r[2]=='e_open'}
  self.assertTrue({'extensions/modules','extensions/gadman','applications/ibar_applications','applications/startup_applications','appearance/transitions','appearance/fonts'}<=paths)
 def test_theme_preview_keeps_selected_identity_without_apply(self):
  bridge=Mock()
  with patch.object(p,'e_entries',return_value={}),patch.object(p,'e_bridge',return_value=bridge),patch.object(p,'theme_catalog',return_value={'/a.edj':'Theme A'}):rows=view('appearance_theme_preview','/a.edj')
  self.assertIn(['selected_choice','Theme A','appearance_theme_preview','/a.edj'],rows)
  bridge.Open.assert_not_called()
 def test_theme_missing_selection_rejected(self):
  with patch.object(p,'e_entries',return_value={}),patch.object(p,'theme_catalog',return_value={}):
   with self.assertRaises(ValueError):view('appearance_theme_preview','/missing.edj')
 def test_theme_apply_preserves_exact_file_identity(self):
  bridge=Mock()
  with patch.object(p,'theme_catalog',return_value={'/personal/a.edj':'A'}),patch.object(p,'appearance_state',return_value={'theme':'/system/a.edj'}),patch.object(p,'e_bridge',return_value=bridge):
   rows=view('appearance_theme_apply',json.dumps({'file':'/personal/a.edj','expected':'/system/a.edj'}))
  bridge.SetTheme.assert_called_once_with('/personal/a.edj','/system/a.edj',timeout=5)
  self.assertTrue(any(r[0]=='notice' for r in rows))
 def test_theme_apply_stale_selection_never_dispatches(self):
  bridge=Mock()
  with patch.object(p,'theme_catalog',return_value={'/new.edj':'New'}),patch.object(p,'appearance_state',return_value={'theme':'/changed.edj'}),patch.object(p,'e_bridge',return_value=bridge):
   with self.assertRaises(ValueError):view('appearance_theme_apply',json.dumps({'file':'/new.edj','expected':'/old.edj'}))
  bridge.SetTheme.assert_not_called()
 def test_old_bridge_blocks_theme_apply(self):
  bridge=Mock()
  with patch.object(p,'bridge_methods',return_value={'SetWallpaper'}),patch.object(p,'theme_catalog',return_value={'/new.edj':'New'}),patch.object(p,'appearance_state',return_value={'theme':'/old.edj'}),patch.object(p,'e_bridge',return_value=bridge):
   with self.assertRaisesRegex(ValueError,'Reload'):view('appearance_theme_apply',json.dumps({'file':'/new.edj','expected':'/old.edj'}))
   rows=view('appearance_theme_preview','/new.edj')
  bridge.SetTheme.assert_not_called()
  self.assertFalse(any(r[0]=='action' and r[2]=='appearance_theme_apply' for r in rows))
 def test_bridge_errors_are_actionable(self):
  class Error(Exception):
   def get_dbus_name(self):return 'org.freedesktop.DBus.Error.UnknownMethod'
  self.assertIn('Unload and load',p.service_error(Error()))
 def test_storage_usage_excludes_reserved_free_space(self):
  with patch.object(p.os,'statvfs',return_value=types.SimpleNamespace(f_blocks=100,f_bfree=30,f_bavail=20,f_frsize=1024)):
   self.assertEqual(p.storage_usage('/'),(102400,71680,20480))
 def test_storage_deduplicates_shared_filesystems(self):
  mounts=[{'mount':'/home','device':'8:1','type':'ext4','source':'/dev/a','readonly':False},{'mount':'/','device':'8:1','type':'ext4','source':'/dev/a','readonly':False}]
  with patch.object(p,'mount_entries',return_value=mounts),patch.object(p,'storage_usage',return_value=(100,60,30)),patch.object(p,'run',return_value='{"blockdevices":[]}'):
   rows=view('view','storage')
  self.assertEqual(len([r for r in rows if r[0]=='meter']),1)
  self.assertIn(['action','Browse files','storage_browse','/home'],rows)
 def test_storage_browse_rejects_unmounted_path(self):
  with patch.object(p,'mount_entries',return_value=[]),patch.object(p.subprocess,'Popen') as launch:
   with self.assertRaises(ValueError):p.storage_browse('/missing')
  launch.assert_not_called()
 def test_unknown_operation_rejected(self):
  with self.assertRaises(ValueError):p.apply('shell','rm',{})
if __name__=='__main__':unittest.main()
