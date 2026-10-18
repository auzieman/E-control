#!/usr/bin/env python3
"""Explicit isolated UI fixture. Never calls pkexec or writes system files."""
import json,os,sys,hashlib
from pathlib import Path
from urllib.parse import quote
p=Path(os.environ['WORKSTATION_FORMS_FIXTURE_STATE'])
s=json.loads(p.read_text());r=json.loads(sys.stdin.buffer.read(512*1024))
def emit(*fields):print('\t'.join(quote(str(v),safe='') for v in fields),flush=True)
def fingerprint(a):return hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest()
op=r['op'];name=r.get('name');error=None
if op=='unlock':emit('unlocked',1);emit('result','Simulation: controls unlocked, no system operations.')
elif op!='snapshot':
 if op=='profile':s['users'][name]['fullname']=r['fullname']
 elif op=='groups':s['users'][name]['groups']=r['groups']
 elif op=='password':s['password_changes']=s.get('password_changes',0)+1
 elif op=='create':s['users'][name]=dict(name=name,fullname=r['fullname'],home='/home/'+name,uid=1001,groups=['wheel'] if r['admin'] else [],primary=name)
 elif op=='firewall':s['services']=r['services'];s['ports']=r['ports']
 elif op=='vpn':s['vpns'].append(name)
 else:error='Unsupported fixture action.'
 s.setdefault('operations',[]).append({k:v for k,v in r.items() if k not in ('password','profile')})
 p.write_text(json.dumps(s));emit('error' if error else 'result',error or 'Simulation: form saved, no system operation.')
emit('helper',1)
for a in s['users'].values():emit('user',a['name'],a['fullname'],a['home'],','.join(a['groups']),a['uid'],a['primary'],fingerprint(a))
for g in ['audio','docker','tester','wheel']:emit('group',g)
emit('zone',','.join(s.get('services',[])),s.get('ports',''),hashlib.sha256(b'').hexdigest())
for name in s.get('vpns',[]):emit('vpn',name)
emit('ready')
