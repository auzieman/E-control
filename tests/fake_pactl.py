#!/usr/bin/env python3
"""Test-only Pulse CLI simulator. Only modifies an explicitly selected fixture."""
import json,os,sys,time
from pathlib import Path
state=Path(os.environ['WORKSTATION_TEST_AUDIO_STATE']);args=sys.argv[1:]
def read():return json.loads(state.read_text())
def save(s):
 p=state.with_suffix('.next');p.write_text(json.dumps(s));p.replace(state)
def write_log():
 with state.with_suffix('.writes').open('a') as f:f.write(json.dumps(args)+'\n')
if args==['subscribe']:
 stamp=state.stat().st_mtime_ns
 while True:
  time.sleep(.05);new=state.stat().st_mtime_ns
  if new!=stamp:print("Event 'change' on sink #11",flush=True);stamp=new
elif args==['-f','json','info']:print(json.dumps(read()['info']))
elif args[:3]==['-f','json','list']:print(json.dumps(read()[args[3]]))
elif args and (args[0].startswith('set-') or args[0].startswith('move-')):
 s=read();operation=args[0];write_log()
 if operation.startswith('set-default-'):
  key='default_sink_name' if operation.endswith('sink') else 'default_source_name';s['info'][key]=args[1]
 else:
  prefixes={'sink-input':'sink-inputs','source-output':'source-outputs','sink':'sinks','source':'sources'}
  noun=next(n for n in prefixes if operation.startswith('set-'+n+'-') or operation=='move-'+n);obj=next(x for x in s[prefixes[noun]] if x['index']==int(args[1]))
  if operation.startswith('move-'):obj['sink' if noun=='sink-input' else 'source']=int(args[2])
  elif operation.endswith('-mute'):obj['mute']=args[2]=='1'
  else:
   for name,value in zip(obj['volume'],args[2:]):obj['volume'][name]={'value':round(float(value.rstrip('%'))/100*65536)}
 save(s)
else:print('Unsupported test request',file=sys.stderr);sys.exit(1)
