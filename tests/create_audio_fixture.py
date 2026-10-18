from pathlib import Path
import json,sys,shutil
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True);bin=root/'bin';bin.mkdir(exist_ok=True)
shutil.copyfile(Path(__file__).with_name('fake_pactl.py'),bin/'pactl');(bin/'pactl').chmod(0o755)
def item(index,name,title,pct=50,mute=False,**extra):return dict(index=index,name=name,description=title,mute=mute,volume={'left':{'value':round(pct/100*65536)},'right':{'value':round(pct/100*65536)}},**extra)
s={'info':{'default_sink_name':'laptop','default_source_name':'mic'},'sinks':[item(11,'laptop','Laptop speakers',107,True),item(12,'headphones','USB headphones',35)],'sources':[item(21,'mic','USB microphone',55,True),item(22,'internal','Laptop microphone',25),item(23,'laptop.monitor','System audio monitor',100)],'sink-inputs':[item(31,'','Music player',64,properties={'application.name':'Music player'},sink=11)],'source-outputs':[item(41,'','Voice chat',75,properties={'application.name':'Voice chat'},source=21)]}
(root/'state.json').write_text(json.dumps(s));print(root/'state.json')
