#!/usr/bin/env python3
"""Unprivileged Pulse-compatible audio adapter. Fixed operations, argv execution."""
import argparse,json,re,subprocess,sys,urllib.parse
NORMAL=65536
KINDS={'output':('sinks','sink'),'input':('sources','source'),'playback':('sink-inputs','sink-input'),'recording':('source-outputs','source-output')}
def call(*args):
 p=subprocess.run(['pactl',*args],capture_output=True,text=True,timeout=6)
 if p.returncode:raise RuntimeError(' '.join(p.stderr.split())[:300] or 'The sound service did not accept the request.')
 return p.stdout.strip()
def listing(kind):
 result=json.loads(call('-f','json','list',KINDS[kind][0]))
 if not isinstance(result,list):raise RuntimeError('Unexpected sound-service reply.')
 return result
def volume(obj):
 return max((float(v.get('value',0))/NORMAL*100 for v in obj.get('volume',{}).values()),default=0)
def bluetooth_names():
 out={}
 try:
  for line in subprocess.check_output(['/usr/bin/bluetoothctl','devices'],text=True,stderr=subprocess.DEVNULL,timeout=3).splitlines():
   m=re.match(r'Device\s+([0-9A-Fa-f:]{17})\s+(.+)$',line.strip())
   if m: out[m.group(1).lower().replace(':','_')]=m.group(2).strip()
 except (OSError,subprocess.SubprocessError): pass
 return out

def title(kind,obj):
 props=obj.get('properties',{})
 if kind in ('output','input'):
  text=obj.get('description') or props.get('device.description') or ''
  if not text or text == '(null)':
   text=props.get('device.alias') or props.get('device.product.name') or ''
  if not text or text == '(null)':
   name=obj.get('name','')
   m=re.search(r'bluez_(?:output|input)\.([0-9A-Fa-f_]{17})',name)
   text=bluetooth_names().get(m.group(1).lower()) if m else ''
  if not text or text == '(null)': text=obj.get('name','Audio device')
  port=obj.get('active_port','');port=port.get('name','') if isinstance(port,dict) else str(port or '')
  if text.startswith('Built-in Audio'):
   if kind=='input':return 'Built-in microphone' if 'mic' in port else 'Built-in audio input'
   if 'headphone' in port:return 'Headphones'
   if 'speaker' in port:return 'Built-in speakers'
   return 'Built-in audio'
  return re.sub(r'\s+(?:Analog Stereo|Digital Stereo(?: \(HDMI\))?)$','',text)[:200]
 return props.get('application.name') or props.get('media.name') or 'Audio application'
def emit(*fields):print('\t'.join(urllib.parse.quote(str(x),safe='') for x in fields))
def snapshot():
 info=json.loads(call('-f','json','info'))
 for kind in KINDS:
  objects=listing(kind)
  if len(objects)>128:emit('note','Only the first 128 '+kind+' entries are shown.')
  for obj in objects[:128]:
   default=kind in ('output','input') and obj.get('name')==info.get('default_sink_name' if kind=='output' else 'default_source_name')
   monitor=kind=='input' and (obj.get('name','').endswith('.monitor') or obj.get('monitor_of_sink') not in (None,4294967295,'4294967295'))
   route=obj.get('sink' if kind=='playback' else 'source',-1) if kind in ('playback','recording') else -1
   emit('item',kind,obj['index'],title(kind,obj),f'{volume(obj):.3f}',int(bool(obj.get('mute'))),int(default),int(monitor),route,obj.get('name',''))
 emit('ready','Connected to your sound service')
def apply(action,kind,index,value):
 if index<0:raise ValueError('Invalid audio device.')
 obj=next((x for x in listing(kind) if x.get('index')==index),None)
 if obj is None:raise ValueError('That device or application is no longer available. Please choose again.')
 noun=KINDS[kind][1]
 if action=='volume':
  target=float(value)
  if not 0<=target<=100:raise ValueError('Choose a volume from 0 to 100 percent.')
  channels=list(obj.get('volume',{}).values())
  if not channels:raise ValueError('This stream does not offer volume controls.')
  peak=max(float(v.get('value',0)) for v in channels)
  values=[f'{target*(float(v.get("value",0))/peak if peak else 1):.5f}%' for v in channels]
  call('set-'+noun+'-volume',str(index),*values)
 elif action=='mute':
  if value not in ('0','1'):raise ValueError('Invalid mute setting.')
  call('set-'+noun+'-mute',str(index),value)
 elif action=='default':
  if kind not in ('output','input'):raise ValueError('Select an output or microphone.')
  call('set-default-'+noun,obj['name'])
 elif action=='route':
  if kind not in ('playback','recording'):raise ValueError('Select an application stream.')
  dest=int(value);device_kind='output' if kind=='playback' else 'input'
  if not any(x.get('index')==dest for x in listing(device_kind)):raise ValueError('The selected audio device is no longer available.')
  call('move-'+noun,str(index),str(dest))
 else:raise ValueError('Unknown audio action.')
 emit('ok','Sound setting updated')
def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['snapshot','volume','mute','default','route']);p.add_argument('kind',nargs='?',choices=list(KINDS));p.add_argument('index',nargs='?',type=int);p.add_argument('value',nargs='?',default='');a=p.parse_args()
 try:
  if a.action=='snapshot':snapshot()
  elif a.kind is None or a.index is None:raise ValueError('Choose an audio device or application.')
  else:apply(a.action,a.kind,a.index,a.value)
 except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:emit('error',str(e));return 1
 return 0
if __name__=='__main__':sys.exit(main())
