#!/usr/bin/env python3
"""Isolated RandR fixture; never talks to the display server."""
import json,os,sys
from pathlib import Path
p=Path(os.environ['WORKSTATION_TEST_DISPLAY_STATE']);s=json.loads(p.read_text());args=sys.argv[1:]
if args==['--listmonitors']:
 print('Monitors: '+str(len(s['outputs'])))
elif args in (['--query'],['--verbose']):
 print('Screen 0: minimum 320 x 200, current 3520 x 1080, maximum 16384 x 16384')
 for o in s['outputs']:
  geometry=f"{o['mode']}+{o['x']}+{o['y']} " if o['mode'] else ''
  print(f"{o['name']} connected {'primary ' if o['primary'] else ''}{geometry}(normal left inverted right x axis y axis)"+(' panning '+o['panning'] if o['mode'] else ''))
  if args==['--verbose']:
   print(' Transform: 1.000000 0.000000 0.000000\n            0.000000 1.000000 0.000000\n            0.000000 0.000000 1.000000')
  for mode in o['modes']:print('   '+mode+'  60.00'+('*+' if mode==o['mode'] else ''))
elif args and args[0] in ('--output','--noprimary'):
 with p.with_suffix('.writes').open('a') as f:f.write(json.dumps(args)+'\n')
 index=0;o=None
 while index<len(args):
  a=args[index]
  if a=='--noprimary':
   for x in s['outputs']:x['primary']=False
   index+=1
  elif a=='--output':o=next(x for x in s['outputs'] if x['name']==args[index+1]);index+=2
  elif a=='--off':o['mode']=None;index+=1
  elif a=='--primary':
   for x in s['outputs']:x['primary']=x is o
   index+=1
  elif a=='--pos':o['x'],o['y']=map(int,args[index+1].split('x'));index+=2
  elif a in ('--mode','--rate','--panning','--rotate'):o[{'--rotate':'rotation'}.get(a,a[2:])]=args[index+1];index+=2
  else:raise ValueError(a)
 q=p.with_suffix('.next');q.write_text(json.dumps(s));q.replace(p)
 if os.environ.get('WORKSTATION_TEST_FAIL_APPLY') and len(p.with_suffix('.writes').read_text().splitlines())==1:sys.exit(1)

else:raise ValueError(args)
