import importlib.util,copy,json,os,stat,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('settings_core',ROOT/'backend/helper.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
class Fake:
 caller=1000
 def __init__(self):
  self.a={'name':'tester','fullname':'Test User','gecos':'Test User,Room 4,123','uid':1000,'gid':1000,'home':'/home/tester','groups':['audio','wheel'],'primary':'tester'};self.calls=[];self.allow=True;self.known={'tester','audio','wheel','docker','root'};self.admin_list=['tester','other']
 def get(self,name):return copy.deepcopy(self.a)
 def groups(self):return self.known
 def policy(self):return self.allow
 def admins(self):return self.admin_list
 def run(self,args,secret=None):self.calls.append((args,secret))
 def exists(self,name):return name=='tester'
 def change_password(self,name,value):self.run(['/usr/sbin/chpasswd'],name+':'+value+'\n')
class Helper(unittest.TestCase):
 def setUp(self):self.s=Fake()
 def req(self,op,**fields):return dict(op=op,name='tester',expected=core.digest(self.s.a),**fields)
 def test_name_preserves_other_gecos_fields(self):
  core.handle(self.req('profile',fullname='New Name'),self.s);self.assertEqual(self.s.calls[0][0],['/usr/sbin/usermod','-c','New Name,Room 4,123','--','tester'])
 def test_reject_stale_without_commands(self):
  r=self.req('profile',fullname='New');r['expected']='stale'
  with self.assertRaises(ValueError):core.handle(r,self.s)
  self.assertFalse(self.s.calls)
 def test_reject_unknown_operation_or_extra_fields(self):
  for r in [{'op':'exec','command':'id'},{'op':'unlock','path':'/etc/shadow'}]:
   with self.assertRaises(ValueError):core.handle(r,self.s)
 def test_reject_control_characters_in_fullname(self):
  for value in ['Bad:Name','Bad\nName','x'*101]:
   with self.assertRaises(ValueError):core.handle(self.req('profile',fullname=value),self.s)
  self.assertFalse(self.s.calls)
 def test_password_only_in_stdin(self):
  value='correct horse sample';core.handle(self.req('password',password=value),self.s)
  self.assertNotIn(value,str(self.s.calls[0][0]));self.assertEqual(self.s.calls[0][1],'tester:'+value+'\n')
 def test_reject_short_and_delimited_passwords(self):
  for value in ['tiny','a'*8+'\n','a'*8+'\x00','a'*1025]:
   with self.assertRaises(ValueError):core.handle(self.req('password',password=value),self.s)
  self.assertFalse(self.s.calls)
 def test_cannot_remove_own_admin(self):
  with self.assertRaises(ValueError):core.handle(self.req('groups',groups=['audio']),self.s)
 def test_cannot_remove_last_admin(self):
  self.s.a['uid']=1001;self.s.admin_list=['tester']
  with self.assertRaises(ValueError):core.handle(self.req('groups',groups=['audio']),self.s)
 def test_group_change_preserves_selected_groups(self):
  core.handle(self.req('groups',groups=['audio','wheel','docker','tester']),self.s);self.assertEqual(self.s.calls[0][0][2],'audio,docker,wheel')
 def test_no_unverified_wheel_promotion(self):
  self.s.a['groups']=['audio'];self.s.allow=False
  with self.assertRaises(ValueError):core.handle(self.req('groups',groups=['audio','wheel']),self.s)
 def test_reject_root_and_unknown_groups(self):
  for groups in [['root'],['does-not-exist']]:
   with self.assertRaises(ValueError):core.handle(self.req('groups',groups=groups),self.s)
 def test_existing_user_creation_rejected(self):
  with self.assertRaises(ValueError):core.handle(dict(op='create',name='tester',fullname='A',password='long enough',admin=False),self.s)
  self.assertFalse(self.s.calls)
 def test_user_creation_and_role_are_fixed_commands(self):
  core.handle(dict(op='create',name='sampletester',fullname='A User',password='long enough',admin=True),self.s)
  self.assertEqual(self.s.calls[0][0][:4],['/usr/sbin/useradd','-m','-U','-s']);self.assertEqual(self.s.calls[-1][0],['/usr/sbin/usermod','-a','-G','wheel','--','sampletester'])
 def test_partial_creation_does_not_delete_home(self):
  self.s.change_password=lambda *args:(_ for _ in ()).throw(RuntimeError('secret backend text'))
  with self.assertRaisesRegex(RuntimeError,'account was created'):core.handle(dict(op='create',name='sampletester',fullname='A',password='long enough',admin=False),self.s)
  self.assertFalse(any('userdel' in str(c) for c in self.s.calls))
 def test_port_bounds_protocol_and_deduplication(self):
  self.assertEqual(core.ports('8080/tcp, 1194/udp,8080/tcp'),[('8080','tcp'),('1194','udp')])
  for text in ['0/tcp','65536/tcp','80/anything','22/tcp;rm']:
   with self.assertRaises(ValueError):core.ports(text)
 def test_zone_has_no_assignment_or_activation(self):
  with patch.object(Path,'is_file',return_value=True):data=core.zone_xml(['ssh'],'8080/tcp')
  self.assertIn(b'<service name="ssh"',data);self.assertNotIn(b'<interface',data);self.assertNotIn(b'<source',data)
 def test_vpn_inline_profile(self):
  text='client\ndev tun\nremote vpn.example.invalid 1194\n<ca>\nDATA\n</ca>\n';self.assertEqual(core.vpn_profile(text),text.encode())
 def test_vpn_dangerous_or_external_directives_rejected(self):
  for line in ['up /tmp/script','plugin /tmp/plugin','config /tmp/other','auth-user-pass /tmp/password','ca /tmp/ca','log /etc/test','script-security 2','management 127.0.0.1 1234']:
   with self.assertRaises(ValueError):core.vpn_profile('remote vpn.example.invalid 1194\n'+line+'\n')
 def test_vpn_requires_remote_and_complete_blocks(self):
  for text in ['client\n','remote vpn.example.invalid\n<key>\nDATA']:
   with self.assertRaises(ValueError):core.vpn_profile(text)
 def test_no_service_commands_in_account_operations(self):
  core.handle(self.req('profile',fullname='A'),self.s);self.assertFalse(any('rc-service' in str(c) or 'rc-update' in str(c) for c in self.s.calls))
 def test_atomic_rejects_user_owned_directory(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ValueError):core.atomic(Path(d)/'test',b'x',0o600)
if __name__=='__main__':unittest.main()
