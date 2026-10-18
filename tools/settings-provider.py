#!/usr/bin/env python3
"""Unprivileged bounded JSON-in / escaped TSV-out bridge. GPL-3.0-only."""
import grp,hashlib,json,os,pwd,stat,subprocess,sys
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET
import settings_core as core
HELPER=Path('/usr/libexec/workstation-settings/settings-helper')
def emit(*fields):print('\t'.join(quote(str(f),safe='') for f in fields),flush=True)
def snapshot():
    emit('helper',int(HELPER.is_file() and HELPER.stat().st_uid==0 and not HELPER.stat().st_mode&0o022))
    for p in pwd.getpwall():
        if not 1000<=p.pw_uid<65534 or p.pw_shell.endswith(('nologin','/false')):continue
        try:a=core.account(p.pw_name)
        except (KeyError,ValueError):continue
        emit('user',a['name'],a['fullname'],a['home'],','.join(a['groups']),a['uid'],a['primary'],core.digest(a))
    for g in grp.getgrall():
        if g.gr_name!='root' and core.NAME.fullmatch(g.gr_name):emit('group',g.gr_name)
    try:
        if core.ZONE.is_symlink():raise ValueError('Unsafe saved zone.')
        data=core.ZONE.read_bytes() if core.ZONE.exists() else b''
        services=[];portlist=[]
        if data:
            root=ET.fromstring(data);services=[e.attrib['name'] for e in root.findall('service')];portlist=[e.attrib['port']+'/'+e.attrib['protocol'] for e in root.findall('port')]
        emit('zone',','.join(services),', '.join(portlist),hashlib.sha256(data).hexdigest())
    except (OSError,ValueError,KeyError,ET.ParseError):emit('zone','', '', 'unavailable')
    for p in sorted(Path('/etc/openvpn').glob('auzietek-*.conf')):emit('vpn',p.stem.removeprefix('auzietek-'))
    try:
        for line in subprocess.check_output(['/usr/bin/nmcli','-t','-f','DEVICE,TYPE,STATE,CONNECTION','device'],text=True,stderr=subprocess.DEVNULL,timeout=5).splitlines():
            if line:emit('iface',line.replace(':',' · '))
        for line in subprocess.check_output(['/usr/bin/nmcli','-t','-f','DEVICE,IP4.ADDRESS,IP4.GATEWAY','device','show'],text=True,stderr=subprocess.DEVNULL,timeout=5).splitlines():
            if line and ('IP4' in line or line.count(':')>=1):emit('iface','IP · '+line.replace(':',' · '))
    except (OSError,subprocess.SubprocessError):emit('iface','unavailable')
    try:
        for line in subprocess.check_output(['/usr/bin/nmcli','-t','-f','IN-USE,SSID,SIGNAL,SECURITY','dev','wifi','list'],text=True,stderr=subprocess.DEVNULL,timeout=8).splitlines()[:32]:
            if line:emit('wifi',line.replace(':',' · '))
    except (OSError,subprocess.SubprocessError):emit('wifi','unavailable')
    try:
        devices=subprocess.check_output(['/usr/bin/bluetoothctl','devices'],text=True,stderr=subprocess.DEVNULL,timeout=5).splitlines()[:32]
        seen=set()
        for line in devices:
            parts=line.split(None,2)
            if len(parts)<3: continue
            address,name=parts[1],parts[2]
            if address.lower() in seen: continue
            seen.add(address.lower())
            paired=connected='no'
            try:
                info=subprocess.check_output(['/usr/bin/bluetoothctl','info',address],text=True,stderr=subprocess.DEVNULL,timeout=5)
                paired='yes' if any(x.strip() in ('Paired: yes','Bonded: yes') for x in info.splitlines()) else 'no'
                connected='yes' if any(x.strip()=='Connected: yes' for x in info.splitlines()) else 'no'
            except (OSError,subprocess.SubprocessError): pass
            emit('bt',address,name,paired,connected)
    except (OSError,subprocess.SubprocessError):emit('bt','unavailable')
    emit('ready')
def main():
    raw=sys.stdin.buffer.read(512*1024+1)
    if len(raw)>512*1024:raise ValueError('Request too large.')
    r=json.loads(raw)
    if r=={'op':'snapshot'}:snapshot();return
    if not HELPER.is_file():raise ValueError('The authenticated settings helper is not installed.')
    st=HELPER.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid or st.st_mode&0o022:raise ValueError('The settings helper has unsafe ownership or permissions.')
    p=subprocess.run(['/usr/bin/pkexec',str(HELPER)],input=raw,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=180)
    try:result=json.loads(p.stdout)
    except (ValueError,UnicodeError):raise ValueError('Authentication was cancelled or the operation could not start.')
    if not result.get('ok'):raise ValueError(result.get('message','The operation failed.'))
    if r['op']=='unlock':emit('unlocked',int(result.get('wheel_policy',False)))
    emit('result',result['message']);snapshot()
if __name__=='__main__':
    try:main()
    except Exception as exc:
        emit('error',str(exc) if isinstance(exc,ValueError) else 'The settings operation could not complete. Refresh and try again.')
        try:snapshot()
        except Exception:pass
        sys.exit(1)
