from pathlib import Path
import json,sys,shutil
p=Path(sys.argv[1]);(p/'bin').mkdir(parents=True,exist_ok=True)
shutil.copyfile(Path(__file__).with_name('fake_xrandr.py'),p/'bin/xrandr');(p/'bin/xrandr').chmod(0o755)
def output(name,mode,x,primary):return dict(name=name,mode=mode,x=x,y=0,primary=primary,rate='60.00',rotation='normal',panning=mode+'+'+str(x)+'+0',modes=['1920x1080','1600x900','1280x720'])
(p/'state.json').write_text(json.dumps({'outputs':[output('eDP-1','1600x900',0,True),output('HDMI-1','1920x1080',1600,False)]}))
