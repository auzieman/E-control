#!/usr/bin/env python3
"""Native forms over Linux services. JSON requests, escaped TSV view models.
No shell commands or automatic settings writes. SPDX-License-Identifier: GPL-3.0-only
"""
import ipaddress,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
from urllib.parse import quote

def emit(*fields): print('\t'.join(quote(str(x),safe='') for x in fields),flush=True)
def title(s): emit('heading',s)
def text(s): emit('text',s)
def field(key,label,value='',kind='entry'): emit('field',key,label,value,kind)
def action(label,op,target=''): emit('action',label,op,target)
def run(*args,timeout=15):
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,env={**os.environ,'LC_ALL':'C'})
 if p.returncode: raise ValueError(' '.join(p.stderr.split())[:300] or 'The service rejected the operation.')
 return p.stdout.strip()
def bus():
 import dbus
 return dbus.SystemBus()
def iface(service,path,interface):
 import dbus
 return dbus.Interface(bus().get_object(service,path),interface)
def props(service,path,interface): return iface(service,path,'org.freedesktop.DBus.Properties').GetAll(interface)
NM='org.freedesktop.NetworkManager'; ROOT='/org/freedesktop/NetworkManager'; BLUE='org.bluez'
def nm(): return iface(NM,ROOT,NM)
def devices():
 return [(str(p),props(NM,p,NM+'.Device')) for p in nm().GetDevices()]
def device(path,kind=None):
 for p,d in devices():
  if p==path and (kind is None or int(d['DeviceType'])==kind): return d
 raise ValueError('This device is no longer available. Refresh and select it again.')
def connection(path):
 if path not in [str(x) for x in iface(NM,ROOT+'/Settings',NM+'.Settings').ListConnections()]: raise ValueError('Saved connection is no longer available.')
 obj=iface(NM,path,NM+'.Settings.Connection'); return obj,obj.GetSettings()
def profiles():
 return [(str(p),connection(str(p))[1]) for p in iface(NM,ROOT+'/Settings',NM+'.Settings').ListConnections()]
def state(d): return {20:'Unavailable',30:'Disconnected',40:'Preparing',50:'Connecting',60:'Authentication needed',70:'Getting address',100:'Connected',120:'Failed'}.get(int(d['State']),'Not connected')
def addresses(d):
 p=str(d.get('Ip4Config','/'))
 if p=='/':return '', '', ''
 v=props(NM,p,NM+'.IP4Config')
 return ', '.join(str(a['address'])+'/'+str(a['prefix']) for a in v.get('AddressData',[])),str(v.get('Gateway','')),', '.join(str(x['address']) for x in v.get('NameserverData',[]))
def blue():return iface(BLUE,'/','org.freedesktop.DBus.ObjectManager').GetManagedObjects()
def bt_device(path):
 v=blue().get(path,{}).get('org.bluez.Device1')
 if v is None:raise ValueError('That Bluetooth device is no longer available.')
 return v

def view(page):
 if page.startswith('appearance'):appearance_view(page);return
 title({'wired':'Wired connections','wifi':'Wi-Fi networks','bluetooth':'Bluetooth','firewall':'Firewall','vpn':'VPN connections','system':'About this workstation','storage':'Storage usage','software':'Software & updates','services':'System services','printing':'Printers & jobs','appearance':'Desktop appearance','appearance-advanced':'Advanced appearance','appearance-wallpaper':'Wallpaper','appearance-text':'Text and interface size','appearance-layout':'Panels and workspaces'}.get(page,page))
 if page in ('wired','wifi'):
  kind=1 if page=='wired' else 2
  found=False
  for path,d in devices():
   if int(d['DeviceType'])!=kind:continue
   found=True;title(str(d['Interface'])+' · '+state(d))
   addr,gw,dns=addresses(d)
   if addr:text('Address: '+addr+'   Gateway: '+gw+'   DNS: '+dns)
   if kind==1: action('Connection settings…','wired_form',path)
   else:
    action('Scan for networks','wifi_scan',path)
    aps=iface(NM,path,NM+'.Device.Wireless').GetAccessPoints()
    if not aps:text('No networks in the current scan. Choose Scan for networks.')
    seen=set()
    for ap in sorted(aps,key=lambda p:-int(props(NM,p,NM+'.AccessPoint')['Strength'])):
     a=props(NM,ap,NM+'.AccessPoint');ssid=bytes(a['Ssid']).decode('utf-8','replace');security=security_type(a)
     key=(ssid,security)
     if key in seen:continue
     seen.add(key)
     title((ssid or 'Hidden network')+' · '+str(int(a['Strength']))+'% · '+security)
     action('Join…','wifi_form',path+'|'+str(ap))
   if int(d['State'])==100:action('Disconnect…','disconnect_form',path)
  if not found:text('No '+('wired' if kind==1 else 'wireless')+' adapters available.')
  if kind==2:
   action('Turn Wi-Fi off' if props(NM,ROOT,NM)['WirelessEnabled'] else 'Turn Wi-Fi on','wifi_radio')
   title('Saved networks')
   for p,s in profiles():
    if s['connection']['type']=='802-11-wireless':
     text(str(s['connection']['id']));action('Connect saved network','saved_connect',p);action('Forget…','wifi_forget_form',p)
  action('Advanced connection editor','launch','network')
 elif page=='bluetooth':
  objects=blue();adapters=[(p,v['org.bluez.Adapter1']) for p,v in objects.items() if 'org.bluez.Adapter1' in v]
  for p,a in adapters:
   text(str(a.get('Alias','Bluetooth adapter'))+' · '+('On' if a['Powered'] else 'Off'))
   action('Turn off' if a['Powered'] else 'Turn on','bt_power_off' if a['Powered'] else 'bt_power_on',str(p))
   if a['Powered']:action('Scan for devices','bt_scan',str(p))
  if not adapters:text('No Bluetooth adapter is available.')
  for p,v in objects.items():
   if 'org.bluez.Device1' not in v:continue
   d=v['org.bluez.Device1'];title(str(d.get('Alias',d['Address'])))
   text(str(d['Address'])+' · '+('Connected' if d.get('Connected') else 'Disconnected')+' · '+('Paired' if d.get('Paired') else 'Not paired'))
   action('Device settings…','bt_form',str(p))
  action('Advanced Bluetooth manager','launch','bluetooth')
 elif page=='vpn':
  for p,s in profiles():
   if s['connection']['type'] in ('vpn','wireguard'):
    text(str(s['connection']['id']));action('Connect','saved_connect',p)
  text('Import and edit VPN profiles with the installed connection editor.')
  action('VPN editor','launch','network')
 elif page=='firewall':
  try:run('firewall-cmd','--state');active=True
  except (OSError,ValueError):active=False
  text('Firewall service is running.' if active else 'Firewall service is stopped. Rules are not being enforced.')
  if not active:
   action('Edit saved rules…','firewall_offline_form');action('Start firewall…','firewall_start_form');return
  zone=run('firewall-cmd','--get-default-zone');text('Default zone: '+zone)
  action('Edit default-zone rules…','firewall_form',zone);action('Stop firewall…','firewall_stop_form')
  text('Active zones:\n'+run('firewall-cmd','--get-active-zones'))
 elif page=='system':
  osinfo={}
  for line in Path('/etc/os-release').read_text().splitlines():
   if '=' in line:k,v=line.split('=',1);osinfo[k]=v.strip('"')
  text(osinfo.get('PRETTY_NAME','Linux'));text('Kernel: '+os.uname().release+' · '+os.uname().machine)
  cpu=Path('/proc/cpuinfo').read_text();model=re.search(r'model name\s*:\s*(.*)',cpu)
  text('Processor: '+(model[1] if model else os.uname().machine));text('Logical CPUs: '+str(os.cpu_count()))
  mem=dict(re.findall(r'^(MemTotal|MemAvailable):\s+(\d+)',Path('/proc/meminfo').read_text(),re.M))
  text('Memory: %.1f GiB total · %.1f GiB available'%(int(mem['MemTotal'])/1048576,int(mem['MemAvailable'])/1048576))
  text('Host name: '+os.uname().nodename);text('Time: '+time.strftime('%Y-%m-%d %H:%M %Z'))
 elif page=='storage':storage_view()
 elif page=='software':
  text('Package installation, repositories and updates are managed in Enaptic.')
  title('APK updates from cached repository indexes')
  text(run('apk','list','--upgradable') or 'No APK updates in the current indexes.')
  if shutil.which('flatpak'):
   title('Flatpak updates from cached metadata')
   try:text(run('flatpak','remote-ls','--updates','--cached','--columns=name,branch') or 'No Flatpak updates in cached metadata.')
   except ValueError:text('Update metadata unavailable; refresh repositories in Enaptic.')
  action('Open Enaptic','launch','software')
 elif page=='printing':
  try:text(run('lpstat','-d'))
  except ValueError:text('No default printer selected.')
  try:printers=run('lpstat','-p')
  except ValueError:printers='';text('No printers configured.')
  for line in printers.splitlines():
   if not line.startswith('printer '):continue
   name=line.split()[1];title(name);text(line);action('Make default','printer_default',name);action('Options…','printer_form',name);action('Print test page…','printer_test_form',name);action('Remove printer…','printer_remove_form',name)
  title('Print jobs');jobs=run('lpstat','-o');text(jobs or 'No queued print jobs.')
  for line in jobs.splitlines():action('Cancel '+line.split()[0]+'…','job_cancel_form',line.split()[0])
  action('Add printer…','printer_add_form');action('Advanced printer setup','launch','printing')
 elif page=='services':
  text('Manage optional services. Boot and core services are shown separately.')
  field('filter','Find a service',SERVICE_FILTER)
  action('Search','service_search')
  field('advanced','Show core and other services (read-only)',int(SERVICE_ADVANCED),'check')
  for name in sorted(p.name for p in Path('/etc/init.d').iterdir() if p.is_file() and p.name!='functions.sh'):
   if SERVICE_FILTER.lower() not in name.lower():continue
   if name not in OPTIONAL_SERVICES and not SERVICE_ADVANCED:continue
   title(name)
   text(service_state(name)+' · '+('Starts in default runlevel' if (Path('/etc/runlevels/default')/name).exists() else 'Not enabled in default runlevel'))
   if name in OPTIONAL_SERVICES:action('Manage…','service_form',name)
   else:text('Core/advanced service — managed outside this panel.')


def security_type(ap):
 w=int(ap.get('RsnFlags',0))|int(ap.get('WpaFlags',0))
 if w&0x400:return 'WPA3 Personal'
 if w&(0x200|0x2000):return 'Enterprise'
 if w&(0x800|0x1000):return 'Enhanced Open'
 if w&0x100:return 'WPA Personal'
 return 'Legacy encrypted' if int(ap['Flags'])&1 else 'Open'

def form(op,target):
 if op=='wifi_form':
  dev,ap=target.split('|');device(dev,2);a=props(NM,ap,NM+'.AccessPoint');security=security_type(a)
  title('Join '+bytes(a['Ssid']).decode('utf-8','replace'));text(security+' · Signal '+str(int(a['Strength']))+'%')
  text('This secondary connection will not replace the wired default route.')
  if security in ('Enterprise','Legacy encrypted','Enhanced Open'):
   text('Use the advanced editor for this security type.');action('Open connection editor','launch','network')
  else:
   if security!='Open':field('password','Wi-Fi password','','password')
   field('autoconnect','Connect automatically when available',1,'check')
   action('Join network','wifi_join',target)
 elif op=='wired_form':
  d=device(target,1);path=str(d['ActiveConnection'])
  if path=='/':text('Connect an existing wired profile in the advanced editor first.');action('Open connection editor','launch','network');return
  profile=str(props(NM,path,NM+'.Connection.Active')['Connection']);_,s=connection(profile);a,g,dns=addresses(d);v=s.get('ipv4',{})
  title('Edit '+str(d['Interface']));text(str(s['connection']['id']))
  field('automatic','Automatic address (DHCP)',int(v.get('method','auto')=='auto'),'check')
  text('Uncheck Automatic to use the address fields below. Keeping Automatic ignores these fields and renews DHCP.')
  field('addresses','IPv4 addresses (CIDR, comma separated)',a);field('gateway','Gateway',g);field('dns','DNS servers (comma separated)',dns)
  text('Apply tries these values for 45 seconds. Keep them or let NetworkManager restore the previous connection.')
  action('Apply and test','wired_apply',target+'|'+profile)
 elif op=='bt_form':
  d=bt_device(target);title(str(d.get('Alias',d['Address'])));text(str(d['Address']))
  text(('Paired' if d.get('Paired') else 'Not paired')+' · '+('Connected' if d.get('Connected') else 'Disconnected'))
  if d.get('Paired'):action('Disconnect' if d.get('Connected') else 'Connect','bt_disconnect' if d.get('Connected') else 'bt_connect',target)
  else:action('Pair headphones / device','bt_pair',target)
  text('For devices needing a PIN or passkey confirmation, use the Bluetooth manager.')
  action('Pair with PIN / advanced options','launch','bluetooth');action('Forget device…','bt_forget_form',target)
 elif op in ('wifi_forget_form','bt_forget_form','disconnect_form','firewall_start_form','firewall_stop_form','job_cancel_form','printer_remove_form'):
  if op=='wifi_forget_form':_,s=connection(target);name=str(s['connection']['id']);nextop='wifi_forget';msg='Remove saved credentials and connection settings for '
  elif op=='bt_forget_form':d=bt_device(target);name=str(d.get('Alias',d['Address']));nextop='bt_forget';msg='Remove pairing and trust for '
  elif op=='disconnect_form':name=str(device(target)['Interface']);nextop='disconnect';msg='Disconnect '
  elif op=='job_cancel_form':name=target;nextop='job_cancel';msg='Cancel print job '
  elif op=='printer_remove_form':name=target;nextop='printer_remove';msg='Remove printer '
  else:name='the firewall';nextop='firewall_start' if op=='firewall_start_form' else 'firewall_stop';msg='Start ' if op=='firewall_start_form' else 'Stop ';text('This changes packet filtering immediately. Existing connections may be affected.')
  title(msg+name+'?');action('Confirm',''+nextop,target)
 elif op=='service_form':
  if target not in OPTIONAL_SERVICES or not (Path('/etc/init.d')/target).is_file():raise ValueError('Select an installed optional service.')
  title('Manage '+target);text(service_state(target))
  field('running','Run this service now',int((Path('/run/openrc/started')/target).exists()),'check')
  field('enabled','Start in default runlevel',int((Path('/etc/runlevels/default')/target).exists()),'check')
  text('Apply may start or stop this service immediately.');action('Apply','service_apply',target)
 elif op=='printer_add_form':
  title('Add a printer');field('name','Printer name (letters, numbers, underscores)')
  field('uri','Printer address (ipp://, ipps:// or socket://)')
  text('IPP Everywhere uses the printer’s advertised driver. For legacy drivers use Advanced printer setup.')
  action('Add printer','printer_add')
 elif op=='printer_form':
  title('Printer options · '+target)
  for key,(label,options,current) in printer_options(target).items():
   text(label+': '+', '.join(options));field('option_'+key,label,current)
  action('Save printing preferences','printer_options',target)
 elif op=='printer_test_form':
  title('Print a test page on '+target+'?');action('Print test page','printer_test',target)
 elif op=='firewall_offline_form':
  import hashlib,xml.etree.ElementTree as ET
  path=Path('/etc/firewalld/zones/auzietek-workstation.xml');raw=path.read_bytes() if path.exists() else b'';root=ET.fromstring(raw) if raw else ET.Element('zone')
  title('Saved workstation firewall rules');text('These rules are saved in the auzietek-workstation zone. Saving does not start the firewall or assign interfaces.')
  selected={e.attrib['name'] for e in root.findall('service')}
  for service in sorted(selected|{'ssh','http','https','mdns'}):field('service_'+service,service,int(service in selected),'check')
  field('ports','Ports (e.g. 8080/tcp)',', '.join(e.attrib['port']+'/'+e.attrib['protocol'] for e in root.findall('port')))
  action('Save rules','firewall_offline_apply',hashlib.sha256(raw).hexdigest())
 elif op=='firewall_form':
  if not re.fullmatch(r'[A-Za-z0-9_-]+',target):raise ValueError('Invalid zone.')
  title('Firewall rules · '+target);text('Edit the running zone. Persistent rules are saved only if requested.')
  selected=set(run('firewall-cmd','--zone='+target,'--list-services').split())
  for service in sorted(selected|{'ssh','http','https','mdns'}):field('service_'+service,service,int(service in selected),'check')
  field('services','Additional allowed service names (comma separated)','')
  field('ports','Allowed ports (e.g. 8080/tcp)',run('firewall-cmd','--zone='+target,'--list-ports').replace(' ',','))
  field('persistent','Also save these rules for future starts',0,'check');action('Apply rules','firewall_apply',target)
 action('Cancel / Back','view',page_for(op))

def page_for(op):
 if op.startswith('bt_'):return 'bluetooth'
 if op.startswith(('wifi_','saved_')):return 'wifi'
 if op.startswith('firewall'):return 'firewall'
 if op.startswith(('printer_','job_')):return 'printing'
 if op.startswith('service_'):return 'services'
 return 'wired'

def activate_wait(path):
 for _ in range(40):
  s=int(props(NM,path,NM+'.Connection.Active')['State'])
  if s==2:return
  if s==4:raise ValueError('The connection failed. Check the password and network availability.')
  time.sleep(.5)
 raise ValueError('Connection is still pending. Refresh to check its state.')

def apply(op,target,values):
 import dbus
 if op=='wifi_scan':device(target,2);iface(NM,target,NM+'.Device.Wireless').RequestScan(dbus.Dictionary({},signature='sv'));time.sleep(2)
 elif op=='wifi_radio':
  enabled=props(NM,ROOT,NM)['WirelessEnabled'];iface(NM,ROOT,'org.freedesktop.DBus.Properties').Set(NM,'WirelessEnabled',dbus.Boolean(not enabled))
 elif op=='wifi_join':
  dev,ap=target.split('|');device(dev,2)
  if ap not in [str(p) for p in iface(NM,dev,NM+'.Device.Wireless').GetAccessPoints()]:raise ValueError('Network disappeared. Scan again.')
  a=props(NM,ap,NM+'.AccessPoint');security=security_type(a);ssid=bytes(a['Ssid']);password=values.get('password','')
  if security not in ('Open','WPA Personal','WPA3 Personal'):raise ValueError('Use the advanced editor for this security type.')
  if security!='Open' and not (8<=len(password.encode('utf-8'))<=63 or re.fullmatch('[0-9a-fA-F]{64}',password)):raise ValueError('Enter a valid Wi-Fi password (8–63 characters).')
  import getpass,uuid
  s={'connection':{'id':ssid.decode('utf8','replace'),'uuid':str(uuid.uuid4()),'type':'802-11-wireless','autoconnect':values.get('autoconnect')=='1','permissions':dbus.Array(['user:'+getpass.getuser()+':'],signature='s')},'802-11-wireless':{'ssid':dbus.ByteArray(ssid)},'ipv4':{'method':'auto','never-default':True},'ipv6':{'method':'auto','never-default':True}}
  if security!='Open':s['802-11-wireless-security']={'key-mgmt':'sae' if security=='WPA3 Personal' else 'wpa-psk','psk':password}
  settings=dbus.Dictionary({k:dbus.Dictionary(v,signature='sv') for k,v in s.items()},signature='sa{sv}')
  profile,active=nm().AddAndActivateConnection(settings,dbus.ObjectPath(dev),dbus.ObjectPath(ap),timeout=30)
  try:activate_wait(active)
  except Exception:
   iface(NM,profile,NM+'.Settings.Connection').Delete();raise
 elif op=='saved_connect':
  _,s=connection(target)
  # Preserve the user's saved profile rather than silently changing its route policy.
  if s['connection']['type']=='802-11-wireless' and not s.get('ipv4',{}).get('never-default',False):raise ValueError('This saved profile can replace the default route. Set “Use only for resources on this network” in the advanced editor before connecting as secondary Wi-Fi.')
  activate_wait(nm().ActivateConnection(dbus.ObjectPath(target),dbus.ObjectPath('/'),dbus.ObjectPath('/')))
 elif op=='wifi_forget':
  c,s=connection(target)
  if s['connection']['type']!='802-11-wireless':raise ValueError('Select a saved Wi-Fi profile.')
  c.Delete()
 elif op=='disconnect':device(target);iface(NM,target,NM+'.Device').Disconnect()
 elif op=='wired_apply':
  dev,profile=target.split('|');d=device(dev,1);
  active=str(d['ActiveConnection'])
  if active=='/' or str(props(NM,active,NM+'.Connection.Active')['Connection'])!=profile:raise ValueError('The active wired connection changed. Refresh before applying.')
  c,s=connection(profile);v=s.get('ipv4',dbus.Dictionary({},signature='sv'));auto=values.get('automatic')=='1'
  addresses=[x.strip() for x in values.get('addresses','').split(',') if x.strip()];dns=[x.strip() for x in values.get('dns','').split(',') if x.strip()];gateway=values.get('gateway','').strip()
  if not auto:
   if not addresses:raise ValueError('Enter at least one IPv4 address with a prefix, such as 192.168.1.20/24.')
   parsed=[ipaddress.IPv4Interface(x) for x in addresses]
   for d in dns:ipaddress.IPv4Address(d)
   if gateway:ipaddress.IPv4Address(gateway)
  v['method']='auto' if auto else 'manual'
  for key in ('addresses','address-data','dns','dns-data','gateway'):v.pop(key,None)
  v['ignore-auto-dns']=False
  if not auto:
   v['address-data']=dbus.Array([dbus.Dictionary({'address':str(a.ip),'prefix':dbus.UInt32(a.network.prefixlen)},signature='sv') for a in parsed],signature='a{sv}')
   v['gateway']=gateway;v['dns']=dbus.Array([dbus.UInt32(int.from_bytes(ipaddress.IPv4Address(d).packed,sys.byteorder)) for d in dns],signature='u')
  s['ipv4']=v
  checkpoint=str(nm().CheckpointCreate(dbus.Array([dbus.ObjectPath(dev)],signature='o'),dbus.UInt32(45),dbus.UInt32(0)))
  try:c.Update(s);nm().ActivateConnection(dbus.ObjectPath(profile),dbus.ObjectPath(dev),dbus.ObjectPath('/'))
  except Exception:nm().CheckpointRollback(dbus.ObjectPath(checkpoint));raise
  title('Keep these wired settings?');text('NetworkManager will restore the previous connection after 45 seconds unless you choose Keep.')
  action('Keep settings','wired_keep',checkpoint);action('Revert now','wired_revert',checkpoint);return True
 elif op in ('wired_keep','wired_revert'):
  if not re.fullmatch(ROOT+r'/Checkpoint/\d+',target):raise ValueError('Invalid network checkpoint.')
  if op=='wired_keep':nm().CheckpointDestroy(dbus.ObjectPath(target))
  else:nm().CheckpointRollback(dbus.ObjectPath(target))
 elif op=='bt_scan':
  if 'org.bluez.Adapter1' not in blue().get(target,{}):raise ValueError('No adapter available.')
  obj=iface(BLUE,target,'org.bluez.Adapter1');obj.StartDiscovery()
  try:time.sleep(8)
  finally:obj.StopDiscovery()
 elif op in ('bt_power_on','bt_power_off'):
  if 'org.bluez.Adapter1' not in blue().get(target,{}):raise ValueError('Adapter unavailable.')
  iface(BLUE,target,'org.freedesktop.DBus.Properties').Set('org.bluez.Adapter1','Powered',dbus.Boolean(op=='bt_power_on'))
 elif op.startswith('bt_'):
  d=bt_device(target);obj=iface(BLUE,target,'org.bluez.Device1')
  if op=='bt_pair':
   run('bluetoothctl','--agent','NoInputNoOutput','--timeout','40','pair',str(d['Address']),timeout=45)
   if not bt_device(target).get('Paired'):raise ValueError('Pairing did not complete. For PIN or passkey devices use the advanced Bluetooth manager.')
  elif op=='bt_connect':obj.Connect(timeout=30)
  elif op=='bt_disconnect':obj.Disconnect(timeout=15)
  elif op=='bt_forget':iface(BLUE,d['Adapter'],'org.bluez.Adapter1').RemoveDevice(dbus.ObjectPath(target))
  else:raise ValueError('Unknown Bluetooth operation.')
 elif op in ('firewall_start','firewall_stop'):run('pkexec','/sbin/rc-service','firewalld','start' if op=='firewall_start' else 'stop',timeout=90)
 elif op=='firewall_apply':
  if target not in run('firewall-cmd','--get-zones').split():raise ValueError('Zone no longer exists.')
  services={s.strip() for s in values.get('services','').split(',') if s.strip()}|{k[8:] for k,v in values.items() if k.startswith('service_') and v=='1'};ports={s.strip() for s in values.get('ports','').split(',') if s.strip()}
  if not services<=set(run('firewall-cmd','--get-services').split()):raise ValueError('Unknown service name.')
  for port in ports:
   m=re.fullmatch(r'(\d+)(?:-(\d+))?/(tcp|udp)',port)
   if not m or not 1<=int(m[1])<=int(m[2] or m[1])<=65535:raise ValueError('Use ports such as 8080/tcp or 8000-8010/udp.')
  # Read each destination separately; preserve all unrelated zone configuration.
  for permanent in ([False,True] if values.get('persistent')=='1' else [False]):
   flags=['--zone='+target]+(['--permanent'] if permanent else [])
   for noun,wanted in [('service',services),('port',ports)]:
    before=set(run('firewall-cmd',*flags,'--list-'+noun+'s').split())
    for v in sorted(wanted-before):run('pkexec','/usr/bin/firewall-cmd',*flags,'--add-'+noun+'='+v,timeout=90)
    for v in sorted(before-wanted):run('pkexec','/usr/bin/firewall-cmd',*flags,'--remove-'+noun+'='+v,timeout=90)
 elif op=='firewall_offline_apply':
  payload={'op':'firewall','services':[k[8:] for k,v in values.items() if k.startswith('service_') and v=='1'],'ports':values.get('ports',''),'expected':target}
  p=subprocess.run([sys.executable,str(Path(__file__).with_name('settings-provider.py'))],input=json.dumps(payload),capture_output=True,text=True,timeout=180)
  if p.returncode:raise ValueError('Saved rules were not changed. Check authentication, port syntax and refresh to retry.')
 elif op=='service_apply':
  if target not in OPTIONAL_SERVICES or not (Path('/etc/init.d')/target).is_file():raise ValueError('Select an installed optional service.')
  running=(Path('/run/openrc/started')/target).exists();enabled=(Path('/etc/runlevels/default')/target).exists()
  if (values.get('running')=='1')!=running:run('pkexec','/sbin/rc-service',target,'start' if values.get('running')=='1' else 'stop',timeout=90)
  if (values.get('enabled')=='1')!=enabled:run('pkexec','/sbin/rc-update','add' if values.get('enabled')=='1' else 'del',target,'default',timeout=90)
 elif op=='printer_add':
  from urllib.parse import urlsplit
  name=values.get('name','');uri=values.get('uri','');u=urlsplit(uri)
  if not re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]{0,62}',name) or u.scheme not in ('ipp','ipps','socket') or not u.hostname or u.username or u.password:raise ValueError('Enter a printer name and a valid printer URI without credentials.')
  if u.scheme=='socket':raise ValueError('Socket printers need a driver; use Advanced printer setup.')
  run('pkexec','/usr/sbin/lpadmin','-p',name,'-E','-v',uri,'-m','everywhere',timeout=90)
 elif op=='printer_options':
  options=printer_options(target);args=[]
  for key,(label,choices,current) in options.items():
   value=values.get('option_'+key,current)
   if value not in choices:raise ValueError('Choose one of the listed values for '+label)
   args+=['-o',key+'='+value]
  run('lpoptions','-p',target,*args)
 elif op=='printer_test':
  if not re.fullmatch('[A-Za-z0-9_.-]+',target):raise ValueError('Invalid printer.')
  test=Path('/usr/share/cups/data/testprint')
  if not test.is_file():raise ValueError('CUPS test page is unavailable.')
  run('lp','-d',target,str(test))
 elif op=='printer_remove':
  if not re.fullmatch('[A-Za-z0-9_.-]+',target):raise ValueError('Invalid printer.')
  run('pkexec','/usr/sbin/lpadmin','-x',target,timeout=90)
 elif op=='printer_default':
  if not re.fullmatch(r'[A-Za-z0-9_.-]+',target):raise ValueError('Invalid printer name.')
  run('lpoptions','-d',target)
 elif op=='job_cancel':
  if not re.fullmatch(r'[A-Za-z0-9_.-]+-\d+',target):raise ValueError('Invalid job identifier.')
  run('cancel',target)
 else:raise ValueError('Unknown operation.')
 return False

OPTIONAL_SERVICES={'bluetooth','firewalld','cupsd','openvpn','avahi-daemon','crond','docker','containerd','libvirtd','podman','rsyncd','smartd','ntpd'}
SERVICE_FILTER=''
SERVICE_ADVANCED=False
def service_state(name):
 try:return run('rc-service',name,'status')
 except ValueError:return 'Stopped or not ready'

TOOLS={'network':['nm-connection-editor'],'bluetooth':['blueman-manager'],'printing':['system-config-printer'],'disks':['gparted'],'appearance':['enlightenment_remote','-efm-open-dir',str(Path.home()/'.e/e/themes')],'services':['terminology','-e','rc-status','--all']}
def launch(target):
 if target=='software':
  for folder in [Path.home()/'.local/share/applications',Path('/usr/local/share/applications'),Path('/usr/share/applications')]:
   files=list(folder.glob('*enaptic*.desktop'))+list(folder.glob('*Enaptic*.desktop'))
   if files:subprocess.Popen(['gio','launch',str(files[0])],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True);return
  raise ValueError('Enaptic launcher is not installed.')
 args=TOOLS.get(target)
 if not args or not shutil.which(args[0]):raise ValueError('The companion application is not installed.')
 subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

def printer_options(name):
 if not re.fullmatch('[A-Za-z0-9_.-]+',name):raise ValueError('Invalid printer name.')
 out={}
 for line in run('lpoptions','-p',name,'-l').splitlines():
  if ':' not in line or '/' not in line.split(':',1)[0]:continue
  left,right=line.split(':',1);key,label=left.split('/',1);choices=right.split();current=next((x[1:] for x in choices if x.startswith('*')),'')
  out[key]=(label,[x.lstrip('*') for x in choices],current)
 return out

E_GROUPS=[
 ('Desktop style',[
  ('appearance/theme','Theme','Change the desktop and widget theme.'),
  ('appearance/wallpaper','Wallpaper','Choose a background for your desktop or individual workspaces.'),
  ('appearance/colors','Colors','Adjust the desktop palette.'),
  ('appearance/borders','Window style','Choose window frames and title bars.')]),
 ('Text and size',[
  ('appearance/fonts','Fonts','Choose interface and title fonts.'),
  ('appearance/scale','Text and interface size','Adjust scaling for comfortable reading.')]),
 ('Desktop layout',[
  ('extensions/shelves','Panels and shelves','Arrange launchers, indicators and desktop shelves.'),
  ('screen/virtual_desktops','Workspaces','Set up virtual desktops.'),
  ('extensions/notification','Notifications','Configure how notifications appear.')]),
 ('Advanced appearance and behavior',[
  ('appearance/xsettings','Application appearance','Configure compatibility settings for other application toolkits.'),
  ('appearance/transitions','Animations','Choose transition effects.'),
  ('menus/menu_settings','Menus','Adjust E menu behavior.'),
  ('windows/window_focus','Window focus','Choose how windows receive keyboard focus.'),
  ('windows/window_geometry','Window placement','Configure window placement and geometry.'),
  ('windows/window_remembers','Remember window settings','Manage per-window rules.'),
  ('windows/tiling','Tiling','Arrange windows automatically when the tiling module is loaded.')])]
E_ADVANCED=[
 ('Fonts and sizing', E_GROUPS[1][1]),
 ('Colors and effects', [E_GROUPS[0][1][2],E_GROUPS[0][1][3],E_GROUPS[3][1][1],E_GROUPS[3][1][0]]),
 ('Gadgets and modules',[
  ('extensions/gadman','Desktop gadgets','Add small tools to the desktop. Panel gadgets are managed through the selected shelf’s Contents.'),
  ('extensions/shelves','Panel contents','Select a shelf, then Contents to choose its gadgets.'),
  ('extensions/modules','Modules','Enable or disable E components. Disabling a module can remove its controls or gadgets.')]),
 ('Applications',[
  ('applications/ibar_applications','Pinned launcher apps','Edit launcher app lists. A shelf’s launcher instance chooses which list it uses.'),
  ('applications/startup_applications','Startup apps','Choose applications that start when you sign in.'),
  ('applications/favorite_applications','Favorite apps','Choose applications shown in the favorites menu.'),
  ('applications/personal_applications','Application launchers','Edit personal application launchers.'),
  ('applications/default_applications','Default apps','Choose applications for common tasks and file types.')]),
 ('Windows and menus',E_GROUPS[3][1][2:])]
E_PATHS={path for _,items in E_GROUPS for path,_,_ in items}
E_PATHS.update(path for _,items in E_ADVANCED for path,_,_ in items)
E_PATHS.update(['keyboard_and_mouse/key_bindings','keyboard_and_mouse/mouse_settings','keyboard_and_mouse/xkbswitch','language/language_settings','screen/screen_saver','screen/power_management','applications/default_applications','applications/startup_applications'])
def e_bridge():
 import dbus
 obj=dbus.SessionBus().get_object('org.enlightenment.wm.service','/org/enlightenment/wm/RemoteObject')
 return dbus.Interface(obj,'org.auzietek.WorkstationSettings')
def e_entries():
 try:return {str(path):bool(enabled) for path,enabled in e_bridge().List(timeout=3)}
 except Exception:return None
def e_open(path):
 if path not in E_PATHS:raise ValueError('Unsupported E settings entry.')
 available=e_entries()
 if available is None:raise ValueError('Enable Workstation Settings Bridge in E’s Modules settings, then refresh.')
 if not available.get(path):raise ValueError('This E settings module is not loaded.')
 e_bridge().Open(path,timeout=5)

def bridge_methods():
 try:
  import dbus,xml.etree.ElementTree as ET
  obj=dbus.SessionBus().get_object('org.enlightenment.wm.service','/org/enlightenment/wm/RemoteObject')
  root=ET.fromstring(str(dbus.Interface(obj,'org.freedesktop.DBus.Introspectable').Introspect(timeout=3)))
  return {m.get('name') for interface in root.findall('interface') if interface.get('name')=='org.auzietek.WorkstationSettings' for m in interface.findall('method')}
 except Exception:return set()

def service_error(error):
 name=getattr(error,'get_dbus_name',lambda:'' )()
 if name=='org.freedesktop.DBus.Error.UnknownMethod':return 'The running settings bridge is older than this panel. Unload and load Workstation Settings Bridge in E’s Modules settings, then Refresh.'
 if name.startswith('org.auzietek.WorkstationSettings.'):
  return str(getattr(error,'get_dbus_message',lambda:str(error))())[:400]
 return str(error)[:400] if isinstance(error,(ValueError,OSError)) else 'The system service could not complete this operation. Check authentication and availability, then refresh.'

def mount_entries():
 out=[]
 for line in Path('/proc/self/mountinfo').read_text().splitlines():
  parts=line.split();separator=parts.index('-')
  decode=lambda s:re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),s)
  out.append({'mount':decode(parts[4]),'source':decode(parts[separator+2]),'type':parts[separator+1],'readonly':'ro' in parts[5].split(','),'device':parts[2]})
 return out

def storage_usage(path):
 v=os.statvfs(path);total=v.f_blocks*v.f_frsize
 used=(v.f_blocks-v.f_bfree)*v.f_frsize;available=v.f_bavail*v.f_frsize
 return total,used,available

def storage_view():
 mounts=mount_entries();seen=set();title('Space for your files')
 preferred=['/home','/','/usr']+[m['mount'] for m in mounts if m['mount'].startswith(('/mnt/','/media/','/run/media/'))]
 labels={'/home':'Home — your files','/':'System','/usr':'Applications'}
 for path in dict.fromkeys(preferred):
  m=next((m for m in mounts if m['mount']==path),None)
  if not m or m['device'] in seen:continue
  seen.add(m['device'])
  try:total,used,available=storage_usage(path)
  except OSError:text(path+' — usage unavailable');continue
  title(labels.get(path,Path(path).name or path))
  text('%.1f GiB available of %.1f GiB · %s%s'%(available/2**30,total/2**30,m['type'],' · Read-only' if m['readonly'] else ''))
  emit('meter','%.1f GiB used'%(used/2**30),used/total if total else 0)
  text(path+' · '+m['source'])
  if total and available/total<.1:text('Space is running low. Review files before installing or copying more data.')
  action('Browse files','storage_browse',path)
 title('Drives and volumes')
 data=json.loads(run('lsblk','--json','--bytes','-o','NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS,MODEL,RM,RO'))
 def volume(node,depth=0):
  path=str(node.get('path',''));points=[x for x in node.get('mountpoints',[]) if x]
  if node.get('type')=='disk':title((node.get('model') or node['name']).strip()+' · %.1f GiB'%(int(node.get('size') or 0)/2**30))
  else:
   matching=next((m for m in mounts if m['mount'] in points),None)
   fs=node.get('fstype') or (matching['type'] if matching else 'Filesystem not identified')
   text((node.get('label') or node['name'])+' · %.1f GiB · '%(int(node.get('size') or 0)/2**30)+fs+' · '+(', '.join(points) if points else 'Not mounted'))
  for child in node.get('children',[]):volume(child,depth+1)
 for disk in data.get('blockdevices',[]):
  if disk.get('type')!='loop':volume(disk)
 text('Partition changes and formatting open in GParted. This page does not mount, erase or resize disks.')
 action('Open partition editor','launch','disks')

def storage_browse(path):
 if path not in {m['mount'] for m in mount_entries()}:raise ValueError('That location is no longer mounted. Refresh the storage list.')
 if not shutil.which('xdg-open'):raise ValueError('No desktop file opener is installed.')
 subprocess.Popen(['xdg-open',path],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

def appearance_state():
 try:
  theme,wallpaper,overrides,scale=e_bridge().Appearance(timeout=3)
  return {'theme':str(theme),'wallpaper':str(wallpaper),'overrides':int(overrides),'scale':float(scale)}
 except Exception:return None

def wallpaper_catalog():
 result={}
 for root in [Path.home()/'.e/e/backgrounds',Path('/usr/share/enlightenment/data/backgrounds'),Path('/usr/local/share/enlightenment/data/backgrounds')]:
  for path in sorted(root.glob('*.edj')):
   try:
    if path.is_file() and path.stat().st_size<=64*1024*1024:
     result[str(path.resolve())]=path.stem.replace('_',' ')+(' (personal)' if root.is_relative_to(Path.home()) else ' (system)')
   except OSError:continue
 return result

def appearance_control(available,path,label,hint):
 text(hint)
 if available is not None and available.get(path):action(label+'…','e_open',path)
 else:text(label+' — '+('enable the settings bridge to use this control' if available is None else 'reload the updated bridge' if path not in available else 'E settings module not loaded'))

def theme_catalog():
 import ctypes as c,ctypes.util
 class Node(c.Structure):pass
 Node._fields_=[('data',c.c_void_p),('next',c.POINTER(Node)),('prev',c.POINTER(Node)),('accounting',c.c_void_p)]
 lib=c.CDLL(ctypes.util.find_library('edje'));lib.edje_init()
 lib.edje_file_collection_list.argtypes=[c.c_char_p];lib.edje_file_collection_list.restype=c.POINTER(Node)
 lib.edje_file_collection_list_free.argtypes=[c.POINTER(Node)]
 result={}
 try:
  for root in [Path.home()/'.elementary/themes',Path('/usr/share/elementary/themes')]:
   for path in sorted(root.glob('*.edj')):
    if not path.is_file() or path.stat().st_size>64*1024*1024:continue
    head=lib.edje_file_collection_list(os.fsencode(path));node=head;groups=[]
    try:
     while node:
      groups.append(c.string_at(node.contents.data).decode('utf-8','replace'));node=node.contents.next
    finally:lib.edje_file_collection_list_free(head)
    if not any(g.startswith('e/widgets/border/') for g in groups):continue
    result[str(path.resolve())]=path.stem+(' (personal)' if root.is_relative_to(Path.home()) else ' (system)')
 finally:lib.edje_shutdown()
 return result

def appearance_view(page,selected=None):
 available=e_entries();state=appearance_state()
 if available is None:text('Enable Workstation Settings Bridge in E’s Modules settings, then Refresh. You can browse installed wallpapers now.')
 if page in ('appearance','appearance-theme'):
  title('Desktop theme');catalog=theme_catalog()
  chosen=selected if selected is not None else state['theme'] if state else ''
  if selected is not None and selected not in catalog:raise ValueError('Select an installed desktop theme.')
  text('Choose a theme to preview it. Apply changes the desktop and restarts E; your applications stay open.')
  if chosen and Path(chosen).is_file():
   text('Preview: '+Path(chosen).stem);emit('theme_preview',chosen)
  can_apply='SetTheme' in bridge_methods()
  if not can_apply:text('Theme Apply needs the updated bridge: unload/load Workstation Settings Bridge in E’s Modules settings, then Refresh.')
  if state and can_apply and selected is not None and chosen!=state['theme']:
   action('Apply theme and restart E','appearance_theme_apply',json.dumps({'file':chosen,'expected':state['theme']}))
   action('Cancel selection','view','appearance')
  for path,name in sorted(catalog.items(),key=lambda x:x[1].casefold()):emit('selected_choice' if path==chosen else 'choice',name,'appearance_theme_preview',path)
  if not state:text('Reload the settings bridge to enable theme application.')
 elif page=='appearance-wallpaper':
  title('Wallpaper');catalog=wallpaper_catalog()
  if selected is not None and selected and selected not in catalog:raise ValueError('Wallpaper is no longer installed. Refresh the list.')
  current=state['wallpaper'] if state else None
  chosen=selected if selected is not None else current
  if chosen is not None:
   text(('Selected: ' if selected is not None else 'Current default: ')+(Path(chosen).stem if chosen else 'Use the desktop theme'))
   preview=chosen or (state['theme'] if state else '')
   if preview and Path(preview).is_file():emit('preview',preview,'e/desktop/background')
  if state:
   text('Applies to desktops using the default wallpaper. '+str(state['overrides'])+' individual screen/workspace overrides will be kept.')
   if selected is not None and chosen!=current:
    action('Apply wallpaper','appearance_wallpaper_apply',json.dumps({'file':chosen,'expected':current}))
    action('Cancel selection','view','appearance-wallpaper')
  elif available is not None:text('Wallpaper status needs the updated bridge. Disable and re-enable Workstation Settings Bridge in E’s Modules settings.')
  emit('choice','Use the desktop theme','appearance_wallpaper_preview','')
  for path,name in sorted(catalog.items(),key=lambda item:item[1].casefold()):emit('choice',name,'appearance_wallpaper_preview',path)
  if not catalog:text('No installed E wallpapers found. Use Wallpaper options to import a picture.')
  appearance_control(available,'appearance/wallpaper','Wallpaper options / import','Import a picture or choose a background for a particular screen or workspace.')
 elif page=='appearance-text':
  title('Text and interface size')
  if state:text('Current interface scale: '+str(round(state['scale']*100))+'%')
  text('The quick brown fox jumps over the lazy dog. 0123456789')
  appearance_control(available,'appearance/fonts','Fonts','Choose readable desktop and window-title fonts.')
  appearance_control(available,'appearance/scale','Interface size','Make text, buttons and other controls larger or smaller together.')
 elif page=='appearance-layout':
  title('Panels, gadgets and workspaces')
  text('Each shelf belongs to a screen. Select the shelf for that screen before changing its position, size, auto-hide or contents.')
  appearance_control(available,'extensions/shelves','Panels and shelves','Choose where your launcher and status panel sits, its size, and when it hides.')
  appearance_control(available,'extensions/gadman','Desktop gadgets','Add applets directly to the desktop.')
  action('Apps, gadgets and modules…','view','appearance-advanced')
  appearance_control(available,'screen/virtual_desktops','Workspaces','Organize windows across separate desktop spaces.')
  appearance_control(available,'extensions/notification','Notifications','Choose how desktop notifications appear.')
 elif page=='appearance-advanced':
  title('Advanced desktop settings')
  text('These controls open E’s native dialogs. Apply or Cancel in that dialog, then Refresh here.')
  for group,items in E_ADVANCED:
   title(group)
   for path,label,hint in items:appearance_control(available,path,label,hint)
  action('Back to Desktop','view','appearance')
 else:
  title('Desktop setup')
  if state:
   text('Current theme: '+(Path(state['theme']).stem if state['theme'] else 'Unknown'))
   if state['theme'] and Path(state['theme']).is_file():emit('theme_preview',state['theme'])
  action('Browse desktop themes','view','appearance-theme')
  action('Choose wallpaper','view','appearance-wallpaper')
  action('Fonts and interface size','view','appearance-text')
  action('Panels and workspaces','view','appearance-layout')
  action('More appearance settings…','view','appearance-advanced')

def theme_apply(target):
 try:data=json.loads(target);file=data['file'];expected=data['expected']
 except (ValueError,KeyError,TypeError):raise ValueError('Select a theme again.')
 if not isinstance(file,str) or not isinstance(expected,str) or file not in theme_catalog():raise ValueError('Select an installed desktop theme.')
 state=appearance_state()
 if state is None or state['theme']!=expected:raise ValueError('Theme changed elsewhere or the bridge is unavailable. Refresh before applying.')
 if 'SetTheme' not in bridge_methods():raise ValueError('Reload Workstation Settings Bridge in E’s Modules settings, then Refresh to enable Theme Apply.')
 e_bridge().SetTheme(file,expected,timeout=5)
 emit('notice','Theme saved; E is restarting. Refresh after the desktop returns to read its current theme.')

def wallpaper_apply(target):
 try:data=json.loads(target);file=data['file'];expected=data['expected']
 except (ValueError,KeyError,TypeError):raise ValueError('Select a wallpaper again.')
 if not isinstance(file,str) or not isinstance(expected,str) or (file and file not in wallpaper_catalog()):raise ValueError('Select an installed wallpaper.')
 state=appearance_state()
 if state is None:raise ValueError('Enable the updated settings bridge before applying wallpaper.')
 if state['wallpaper']!=expected:raise ValueError('Wallpaper changed elsewhere. Refresh before applying.')
 e_bridge().SetWallpaper(file,expected,timeout=5)
 after=appearance_state()
 if after is None or after['wallpaper']!=file:raise ValueError('Could not verify the wallpaper change. Refresh to check its state.')
 emit('notice','Default wallpaper updated. Individual workspace backgrounds were kept.')
 appearance_view('appearance-wallpaper')

def main(r):
 op=r.get('op','view');target=r.get('target','wired');values=r.get('values',{})
 if not isinstance(target,str) or not isinstance(values,dict):raise ValueError('Invalid request.')
 if op=='storage_browse':storage_browse(target);emit('notice','Opened file manager.');return
 elif op=='appearance_theme_apply':theme_apply(target);return
 elif op=='appearance_theme_preview':appearance_view('appearance-theme',target)
 elif op=='appearance_wallpaper_preview':appearance_view('appearance-wallpaper',target)
 elif op=='appearance_wallpaper_apply':wallpaper_apply(target)
 elif op=='e_open':
  e_open(target);emit('notice','Opened native Enlightenment settings. Use that dialog to apply or cancel.');return
 elif op=='service_search':
  global SERVICE_FILTER,SERVICE_ADVANCED
  SERVICE_FILTER=values.get('filter','');SERVICE_ADVANCED=values.get('advanced')=='1';view('services')
 elif op=='view':view(target)
 elif op.endswith('_form'):form(op,target)
 elif op=='launch':launch(target);emit('notice','Opened companion application.');return
 else:
  if apply(op,target,values):emit('ready');return
  emit('notice','Operation completed.');view(page_for(op))
 emit('ready')
if __name__=='__main__':
 try:
  data=sys.stdin.buffer.read(65537)
  if len(data)>65536:raise ValueError('Request too large.')
  main(json.loads(data))
 except Exception as e:
  # Requests and secret values are never printed. Service errors may include names.
  emit('error',service_error(e));sys.exit(1)
