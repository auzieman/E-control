import importlib.util,json,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('audio_provider',Path(__file__).parents[1]/'tools/audio-provider.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class AudioActions(unittest.TestCase):
 def setUp(self):self.obj={'index':11,'name':'speaker','volume':{'left':{'value':32768},'right':{'value':65536}}}
 def test_builtin_output_name_uses_active_port(self):
  self.assertEqual(a.title('output',{'description':'Built-in Audio Analog Stereo','active_port':'analog-output-speaker'}),'Built-in speakers')
  self.assertEqual(a.title('output',{'description':'Built-in Audio Analog Stereo','active_port':'analog-output-headphones'}),'Headphones')
 def test_microphone_name_keeps_product_but_drops_format(self):
  self.assertEqual(a.title('input',{'description':'Meteorite condenser microphone Analog Stereo'}),'Meteorite condenser microphone')
 def test_volume_preserves_channel_balance(self):
  with patch.object(a,'listing',return_value=[self.obj]),patch.object(a,'call') as call,patch.object(a,'emit'):
   a.apply('volume','output',11,'50');call.assert_called_once_with('set-sink-volume','11','25.00000%','50.00000%')
 def test_invalid_volume_never_writes(self):
  with patch.object(a,'listing',return_value=[self.obj]),patch.object(a,'call') as call:
   for value in ['-1','101','nan','inf']:
    with self.assertRaises(ValueError):a.apply('volume','output',11,value)
   call.assert_not_called()
 def test_disappeared_device_never_writes(self):
  with patch.object(a,'listing',return_value=[]),patch.object(a,'call') as call:
   with self.assertRaises(ValueError):a.apply('mute','input',11,'1')
   call.assert_not_called()
 def test_route_validates_destination(self):
  with patch.object(a,'listing',side_effect=[[{'index':31}],[]]),patch.object(a,'call') as call:
   with self.assertRaises(ValueError):a.apply('route','playback',31,'999')
   call.assert_not_called()
 def test_default_uses_resolved_name_and_no_shell(self):
  with patch.object(a,'listing',return_value=[self.obj]),patch.object(a,'call') as call,patch.object(a,'emit'):
   a.apply('default','output',11,'');call.assert_called_once_with('set-default-sink','speaker')
 def test_invalid_mute_never_writes(self):
  with patch.object(a,'listing',return_value=[self.obj]),patch.object(a,'call') as call:
   with self.assertRaises(ValueError):a.apply('mute','output',11,'toggle')
   call.assert_not_called()
 def test_capture_route_uses_source_output(self):
  with patch.object(a,'listing',side_effect=[[{'index':31}],[{'index':21}]]),patch.object(a,'call') as call,patch.object(a,'emit'):
   a.apply('route','recording',31,'21');call.assert_called_once_with('move-source-output','31','21')
if __name__=='__main__':unittest.main()
