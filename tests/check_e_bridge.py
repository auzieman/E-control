"""Run under dbus-run-session against the isolated native harness."""
import subprocess,sys,dbus,os
p=subprocess.Popen(sys.argv[1:],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
try:
 line=p.stdout.readline().strip()
 assert line.startswith('READY '),line
 obj=dbus.SessionBus().get_object(line.split()[1],'/org/enlightenment/wm/RemoteObject')
 bridge=dbus.Interface(obj,'org.auzietek.WorkstationSettings')
 entries=dict(bridge.List());assert entries['appearance/theme'];assert not entries['appearance/fonts']
 for invalid in ['system/restart','../../etc/passwd','appearance/fonts']:
  try:bridge.Open(invalid)
  except dbus.DBusException:pass
  else:raise AssertionError('Invalid/unavailable entry accepted: '+invalid)
 bridge.Open('appearance/theme');assert p.stdout.readline().strip()=='OPEN appearance/theme'
 bridge.Open('appearance/wallpaper');assert p.stdout.readline().strip()=='OPEN appearance/wallpaper'
 theme,wallpaper,overrides,scale=bridge.Appearance()
 assert str(theme)=='/fixture/theme.edj' and not wallpaper and overrides==1 and scale==1.25
 for file,expected in [('relative.edj',''),('/etc/passwd',''),('', '/stale.edj')]:
  try:bridge.SetWallpaper(file,expected)
  except dbus.DBusException:pass
  else:raise AssertionError('Invalid or stale wallpaper accepted')
 fixture=os.environ['E_TEST_WALLPAPER']
 bridge.SetWallpaper(fixture,'')
 assert str(bridge.Appearance()[1])==fixture and bridge.Appearance()[2]==1
 bridge.SetWallpaper('',fixture)
 assert not bridge.Appearance()[1] and bridge.Appearance()[2]==1
 for file,expected in [(fixture,'/fixture/theme.edj'),(os.environ['E_TEST_THEME'],'/stale.edj'),(os.environ['E_TEST_THEME']+'.fail.edj','/fixture/theme.edj')]:
  try:bridge.SetTheme(file,expected)
  except dbus.DBusException:pass
  else:raise AssertionError('Invalid, stale or unsaved theme accepted')
 assert str(bridge.Appearance()[0])=='/fixture/theme.edj'
 bridge.SetTheme(os.environ['E_TEST_THEME'],'/fixture/theme.edj')
 assert str(bridge.Appearance()[0])==os.environ['E_TEST_THEME']
 assert p.stdout.readline().strip()=='RESTART'
 assert p.wait(timeout=15)==0
 print('PASS: native module load, fixture registry availability, restricted dispatch, dialog dispatch, wallpaper validation/apply with preserved fixture overrides, theme validation/save rollback/exact-file apply/deferred restart, module shutdown')
finally:
 if p.poll() is None:p.terminate();p.wait(timeout=5)
