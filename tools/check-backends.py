#!/usr/bin/env python3
"""Read-only backend connectivity audit; never apply settings."""
import subprocess,json,sys
from pathlib import Path
from urllib.parse import unquote
root=Path(__file__).resolve().parents[1]/'build/out'
failed=False
checks=[('audio',['audio-provider.py','snapshot'],None),('displays',['display-provider.py','snapshot'],None),('accounts',['settings-provider.py'],{'op':'snapshot'})]
checks += [(p,['workstation-provider.py'],{'op':'view','target':p}) for p in ['wired','wifi','bluetooth','firewall','vpn','system','storage','software','printing','services','appearance-theme','appearance-wallpaper','appearance-text','appearance-layout','appearance-advanced']]
for name,args,request in checks:
 try:
  p=subprocess.run([sys.executable,str(root/args[0]),*args[1:]],input=json.dumps(request) if request else None,capture_output=True,text=True,timeout=40)
  rows=[[unquote(x) for x in line.split('\t')] for line in p.stdout.splitlines()]
  errors=[r[1:] for r in rows if r[0]=='error']
  failed = failed or p.returncode!=0 or bool(errors)
  print(name, 'PASS' if p.returncode==0 and not errors else 'FAIL', 'records='+str(len(rows)),'(provider unavailable; inspect the section in the UI)' if errors else '',flush=True)
 except Exception as e:
  failed=True
  print(name,type(e).__name__,flush=True)
import importlib.util
spec=importlib.util.spec_from_file_location('provider',root/'workstation-provider.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
print('bridge methods',sorted(m.bridge_methods()))

if 'SetTheme' not in m.bridge_methods():print('Theme Apply: enable/reload the current Workstation Settings Bridge module.')
sys.exit(1 if failed else 0)
