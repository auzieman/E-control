#!/usr/bin/python3
"""Scoped authenticated account/offline-network changes. GPL-3.0-only.
Patterns: Enaptic root-owned helper + installer password-over-stdin transport.
No caller commands, arbitrary paths, service activation, or password output.
"""
import fcntl,grp,hashlib,json,os,pwd,re,stat,subprocess,sys,tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
ENV={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','HOME':'/root'}
NAME=re.compile(r'[a-z_][a-z0-9_-]{0,30}\Z')
ZONE=Path('/etc/firewalld/zones/auzietek-workstation.xml')
MARKER='Managed by AlpinE Workstation Settings'

def valid_name(value):
    if not isinstance(value,str) or not NAME.fullmatch(value):raise ValueError('Use a short lowercase name with letters, numbers, underscores or hyphens.')
    return value

def fullname(value):
    if not isinstance(value,str) or len(value)>100 or any(ord(c)<32 or c in ':\x7f' for c in value):raise ValueError('Name must be at most 100 characters without colons or control characters.')
    return value

def password(value):
    if not isinstance(value,str) or not 8<=len(value)<=1024 or any(c in value for c in '\x00\r\n'):raise ValueError('Use a password of 8–1024 characters without line breaks.')
    return value

def account(name):
    p=pwd.getpwnam(valid_name(name))
    if not 1000<=p.pw_uid<65534 or p.pw_shell.endswith(('nologin','/false')):raise ValueError('Only ordinary local login accounts can be edited.')
    # Do not route writes to NSS/directory users.
    if not any(line.split(':',1)[0]==name for line in Path('/etc/passwd').read_text().splitlines()):raise ValueError('Only local accounts can be edited.')
    groups=sorted(g.gr_name for g in grp.getgrall() if name in g.gr_mem and g.gr_gid!=p.pw_gid)
    return {'name':name,'fullname':p.pw_gecos.split(',')[0],'gecos':p.pw_gecos,'uid':p.pw_uid,'gid':p.pw_gid,'home':p.pw_dir,'groups':groups,'primary':grp.getgrgid(p.pw_gid).gr_name}

def digest(a):return hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest()

def wheel_policy():
    main=Path('/etc/sudoers')
    try:base=main.read_text()
    except OSError:base=''
    included=bool(re.search(r'(?m)^\s*(?:@includedir|#includedir)\s+/etc/sudoers.d\s*(?:#.*)?$',base))
    files=[main]+([p for p in Path('/etc/sudoers.d').glob('*') if '.' not in p.name and not p.name.endswith('~')] if included else [])
    sudo=[]
    for p in files:
        try:
            info=p.lstat()
            if stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022:sudo+=p.read_text().splitlines()
        except (OSError,UnicodeError):pass
    # Recognize the common unrestricted wheel grant; complex policies remain unknown.
    grant=any(re.fullmatch(r'\s*%wheel\s+ALL\s*=\s*\(ALL(?::ALL)?\)\s+(?:(?:NOPASSWD|PASSWD):\s*)?ALL\s*(?:#.*)?',line) for line in sudo)
    overrides=any(line.strip() and not line.lstrip().startswith('#') and '!' in line and ('wheel' in line or 'ALL' in line) for line in sudo)
    return grant and not overrides

def validate_groups(values,old,system):
    if not isinstance(values,list) or len(values)>64 or len(set(values))!=len(values):raise ValueError('Invalid group list.')
    for value in values:
        valid_name(value)
        if value=='root' or value not in system.groups():raise ValueError('Choose existing non-root groups.')
    prior=set(old['groups']);new=set(values)
    old_wheel='wheel' in prior or old['primary']=='wheel';new_wheel='wheel' in new or old['primary']=='wheel'
    if old_wheel!=new_wheel:
        if not system.policy():raise ValueError('An unrestricted wheel policy could not be verified on this host.')
        if old_wheel and not new_wheel:
            if old['uid']==system.caller:raise ValueError('Use another administrator account to remove your own administrator access.')
            if len(system.admins())<=1:raise ValueError('Keep a working administrator account.')
    return sorted(new-{old['primary']})

def ports(text):
    if not isinstance(text,str) or len(text)>1024:raise ValueError('Invalid port list.')
    result=[]
    for token in filter(None,(v.strip() for v in text.split(','))):
        m=re.fullmatch(r'([0-9]{1,5})/(tcp|udp)',token)
        if not m or not 1<=int(m[1])<=65535:raise ValueError('Enter ports like 8080/tcp, 1194/udp (1–65535).')
        pair=(str(int(m[1])),m[2])
        if pair not in result:result.append(pair)
    if len(result)>32:raise ValueError('Use at most 32 port rules.')
    return result

def zone_xml(services,port_text):
    if not isinstance(services,list) or len(services)>64 or len(set(services))!=len(services):raise ValueError('Invalid service list.')
    for name in services:
        valid_name(name)
        if not Path('/usr/lib/firewalld/services',name+'.xml').is_file():raise ValueError('A selected firewall service is unavailable.')
    root=ET.Element('zone');ET.SubElement(root,'short').text='AlpinE Workstation';ET.SubElement(root,'description').text=MARKER
    for name in sorted(services):ET.SubElement(root,'service',name=name)
    for port,protocol in ports(port_text):ET.SubElement(root,'port',port=port,protocol=protocol)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)+b'\n'

VPN_OPTIONS={'client','dev','proto','remote','remote-random','resolv-retry','nobind','persist-key','persist-tun','remote-cert-tls','verify-x509-name','cipher','data-ciphers','data-ciphers-fallback','auth','auth-user-pass','auth-nocache','verb','mute','keepalive','ping','ping-restart','connect-retry','connect-timeout','reneg-sec','key-direction','tls-version-min','tls-cipher','tls-ciphersuites','explicit-exit-notify','sndbuf','rcvbuf','tun-mtu','mssfix','pull','pull-filter','redirect-gateway','route','route-ipv6','dhcp-option','setenv','float','comp-lzo','compress'}
def vpn_profile(text):
    if not isinstance(text,str) or not 1<=len(text.encode())<=256*1024 or '\x00' in text:raise ValueError('Choose a text OpenVPN profile smaller than 256 KiB.')
    block=None;remote=False
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith(('#',';')):continue
        if block:
            if line=='</'+block+'>':block=None
            continue
        if line.startswith('<'):
            if line not in ('<ca>','<cert>','<key>','<tls-auth>','<tls-crypt>','<tls-crypt-v2>'):raise ValueError('Only inline CA/certificate/key blocks are supported.')
            block=line[1:-1];continue
        parts=line.split();option=parts[0].removeprefix('--')
        if option not in VPN_OPTIONS:raise ValueError('This profile contains an unsupported directive. Script/plugin and external-file directives are not imported.')
        if option=='auth-user-pass' and len(parts)!=1:raise ValueError('Credential-file paths are not imported. Use interactive auth-user-pass.')
        if option=='dev' and parts[1:] not in (['tun'],['tap']):raise ValueError('Only tun or tap devices are supported.')
        if option=='remote':
            if not 2<=len(parts)<=4 or parts[1].startswith('-'):raise ValueError('Invalid VPN server line.')
            remote=True
    if block or not remote:raise ValueError('The profile needs a remote server and complete inline blocks.')
    return text.encode()

def atomic(path,data,mode,replace=True):
    for directory in [path.parent,*path.parent.parents]:
        info=directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Unsafe configuration directory.')
    if path.is_symlink():raise ValueError('Refusing a configuration symlink.')
    if path.exists():
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Unsafe existing configuration file.')
    fd,name=tempfile.mkstemp(prefix='.workstation-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fchmod(f.fileno(),mode);os.fsync(f.fileno())
        if replace:os.replace(name,path)
        else:os.link(name,path,follow_symlinks=False);os.unlink(name)
        fd=os.open(path.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
    finally:
        if os.path.exists(name):os.unlink(name)

class System:
    def __init__(self,caller):self.caller=caller
    def get(self,name):return account(name)
    def groups(self):return {g.gr_name for g in grp.getgrall()}
    def policy(self):return wheel_policy()
    def admins(self):return [p.pw_name for p in pwd.getpwall() if 1000<=p.pw_uid<65534 and not p.pw_shell.endswith(('nologin','/false')) and ('wheel' in account(p.pw_name)['groups'] or account(p.pw_name)['primary']=='wheel') and not p.pw_shell.endswith(('nologin','/false'))]
    def run(self,args,secret=None):
        p=subprocess.run(args,input=secret,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=ENV,text=True,timeout=30)
        if p.returncode:raise RuntimeError('The system account command failed. Refresh to check current account state.')
    def exists(self,name):
        try:pwd.getpwnam(name);return True
        except KeyError:return False
    def change_password(self,name,value):self.run(['/usr/sbin/chpasswd'],name+':'+value+'\n')

def handle(r,s):
    if not isinstance(r,dict):raise ValueError('Invalid request.')
    op=r.get('op');schemas={'unlock':{'op'},'profile':{'op','name','fullname','expected'},'groups':{'op','name','groups','expected'},'password':{'op','name','password','expected'},'create':{'op','name','fullname','password','admin'},'firewall':{'op','services','ports','expected'},'vpn':{'op','name','profile'}}
    if op not in schemas or set(r)!=schemas[op]:raise ValueError('Unknown operation or fields.')
    if op=='unlock':return {'message':'Controls unlocked; each save is still authenticated by host policy.','wheel_policy':s.policy()}
    if op in ('profile','groups','password'):
        old=s.get(r['name'])
        if r['expected']!=digest(old):raise ValueError('Account changed. Refresh before saving.')
        if op=='profile':
            full=fullname(r['fullname']);tail=old.get('gecos','').split(',',1)
            if len(tail)==2:full+=','+tail[1]
            s.run(['/usr/sbin/usermod','-c',full,'--',old['name']])
        elif op=='groups':s.run(['/usr/sbin/usermod','-G',','.join(validate_groups(r['groups'],old,s)),'--',old['name']])
        else:s.change_password(old['name'],password(r['password']))
        return {'message':'Account change saved.'}
    if op=='create':
        name=valid_name(r['name']);full=fullname(r['fullname']);pw=password(r['password'])
        if type(r['admin']) is not bool:raise ValueError('Invalid administrator choice.')
        if s.exists(name) or name in s.groups() or os.path.lexists('/home/'+name):raise ValueError('That username or home folder already exists.')
        if r['admin'] and not s.policy():raise ValueError('A wheel administrator policy could not be verified.')
        s.run(['/usr/sbin/useradd','-m','-U','-s','/bin/ash','-c',full,'--',name])
        try:
            s.change_password(name,pw)
            if r['admin']:s.run(['/usr/sbin/usermod','-a','-G','wheel','--',name])
        except Exception:raise RuntimeError('The account was created, but its password or role could not be completed. Refresh; finish that account before creating another.') from None
        return {'message':'Login account created.'}
    if op=='firewall':
        bus=subprocess.run(['/usr/bin/gdbus','call','--system','--dest','org.freedesktop.DBus','--object-path','/org/freedesktop/DBus','--method','org.freedesktop.DBus.NameHasOwner','org.fedoraproject.FirewallD1'],capture_output=True,text=True,timeout=5)
        if bus.returncode or bus.stdout.strip()!='(false,)':raise ValueError('Offline editing requires an available system bus and stopped firewalld; this operation will not stop it.')
        old=ZONE.read_bytes() if ZONE.exists() and not ZONE.is_symlink() else b''
        if old:
            root=ET.fromstring(old)
            if MARKER.encode() not in old:raise ValueError('Existing zone is not owned by this panel.')
            if root.attrib or any(c.tag not in {'short','description','service','port'} or (c.tag=='service' and set(c.attrib)!={'name'}) or (c.tag=='port' and set(c.attrib)!={'port','protocol'}) for c in root):raise ValueError('The zone contains advanced settings. Preserve them with the existing firewall tools.')
        if r['expected']!=hashlib.sha256(old).hexdigest():raise ValueError('The saved zone changed. Refresh first.')
        data=zone_xml(r['services'],r['ports']);atomic(ZONE,data,0o644)
        return {'message':'Custom firewall zone saved. It is not assigned or enabled.'}
    name=valid_name(r['name']);path=Path('/etc/openvpn')/('auzietek-'+name+'.conf');data=vpn_profile(r['profile'])
    if os.path.lexists(path):raise ValueError('That VPN profile already exists. Choose a different profile name.')
    atomic(path,data,0o600,replace=False)
    return {'message':'VPN profile saved with owner-only permissions. No VPN was started.'}

def main():
    if os.geteuid()!=0:raise PermissionError('Administrator authentication required.')
    here=Path(__file__).resolve().parent
    for p in (here,here/'helper.py',here/'settings-helper'):
        st=p.lstat()
        if st.st_uid!=0 or st.st_mode&0o022 or p.is_symlink():raise PermissionError('Unsafe helper installation.')
    caller=int(os.environ.get('PKEXEC_UID','-1'))
    if caller<=0:raise PermissionError('Use the authenticated settings entrypoint.')
    os.environ.clear();os.environ.update(ENV)
    raw=sys.stdin.buffer.read(512*1024+1)
    if len(raw)>512*1024:raise ValueError('Request too large.')
    r=json.loads(raw);directory=Path('/run/workstation-settings');directory.mkdir(mode=0o700,exist_ok=True)
    st=directory.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid or stat.S_IMODE(st.st_mode)!=0o700:raise PermissionError('Unsafe transaction directory.')
    with (directory/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=handle(r,System(caller))
    print(json.dumps({'ok':True,**result}))
if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Never echo requests, command arguments, raw subprocess errors or passwords.
        print(json.dumps({'ok':False,'message':str(exc) if isinstance(exc,(ValueError,RuntimeError,PermissionError)) else 'Operation failed. Refresh and try again.'}));sys.exit(1)
