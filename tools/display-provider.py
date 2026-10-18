#!/usr/bin/env python3
"""Unprivileged X11 display transactions; trial watchdog owns the old layout.
SPDX-License-Identifier: GPL-3.0-only
"""
import fcntl
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import sys
import time
from urllib.parse import quote

TIMEOUT = 15

def run(args):
    return subprocess.run(['xrandr', *args], capture_output=True, text=True, timeout=5, check=True).stdout

def snapshot():
    text = run(['--query'])
    outputs = []
    current = None
    for line in text.splitlines():
        match = re.match(r'^(\S+) (connected|disconnected)\b(.*)', line)
        if match:
            current = None
            if match[2] != 'connected':
                continue
            tail = match[3]
            geometry = re.search(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', tail)
            # Rotation before the parenthesized list is the active rotation.
            active_rotation = re.search(r'\d+x\d+\+-?\d+\+-?\d+\s+(left|right|inverted)', tail)
            current = dict(name=match[1], primary=' primary ' in ' '+tail+' ', modes=[],
                           mode=None, rate=None, x=0, y=0, rotation=active_rotation[1] if active_rotation else 'normal', panning='0x0', reflected=bool(re.search(r'(?:x|y) axis', tail.split('(')[0])))
            if geometry:
                current.update(x=int(geometry[3]), y=int(geometry[4]))
            current['active'] = geometry is not None
            pan = re.search(r' panning (\S+)', tail)
            if pan:
                current['panning'] = pan[1]
            outputs.append(current)
        elif current:
            mode = re.match(r'^\s+(\d+x\d+)\s+(.+)', line)
            if mode:
                rates = re.findall(r'([0-9]+\.[0-9]+)([*+]*)', mode[2])
                if rates:
                    current['modes'].append(mode[1])
                for rate, flags in rates:
                    if '*' in flags:
                        current.update(mode=mode[1], rate=rate)
    if not outputs:
        raise ValueError('No connected displays were reported.')
    if any(o['active'] and o['mode'] is None for o in outputs):
        raise ValueError('An active display uses an unsupported mode name. Use the existing display settings for this layout.')
    # Refuse mutations of transformations we cannot faithfully restore.
    verbose = run(['--verbose'])
    transforms = re.findall(r'Transform:\s+([^\n]+)\n\s*([^\n]+)\n\s*([^\n]+)', verbose)
    transformed = any([round(float(v), 5) for row in t for v in row.split()] != [1,0,0,0,1,0,0,0,1] for t in transforms)
    return dict(outputs=outputs, supported=not transformed and all(o['rotation']=='normal' and not o['reflected'] for o in outputs))

def validate(old, plan):
    if not old['supported']:
        raise ValueError('This layout uses rotation or scaling. Use the existing display settings for now.')
    devices = {o['name']: o for o in old['outputs']}
    if not isinstance(plan, list) or len(plan) != len(devices) or {p.get('name') for p in plan} != set(devices):
        raise ValueError('The connected displays changed. Refresh before applying.')
    enabled = 0
    for p in plan:
        device = devices[p['name']]
        if p.get('mode') is None:
            continue
        if p['mode'] not in device['modes']:
            raise ValueError('That resolution is no longer available. Refresh and try again.')
        if any(type(p.get(k)) is not int or not 0 <= p[k] <= 16384 for k in ('x','y')):
            raise ValueError('Display positions must be between 0 and 16384.')
        w,h = map(int,p['mode'].split('x'))
        if p['x']+w>16384 or p['y']+h>16384:
            raise ValueError('The requested desktop is too large.')
        if p['mode'] == device['mode'] and device['rate']:
            p['rate'] = device['rate']
        else:
            p.pop('rate',None)
        enabled += 1
    if not enabled:
        raise ValueError('Keep at least one display enabled.')
    if not any(p['mode'] and p.get('primary') for p in plan):
        first = next(p for p in plan if p['mode'])
        for p in plan:
            p['primary'] = p is first

def arguments(outputs, restore=False):
    args = ['--noprimary'] if restore and not any(o.get('primary') for o in outputs) else []
    for o in outputs:
        args += ['--output',o['name']]
        if o['mode'] is None:
            args += ['--off']
            continue
        args += ['--mode',o['mode'],'--pos',f"{o['x']}x{o['y']}",'--rotate','normal','--panning',o.get('panning','0x0') if restore else '0x0']
        if o.get('rate'):
            args += ['--rate',o['rate']]
        if o.get('primary'):
            args += ['--primary']
    return args

def emit(tag, message):
    try:
        print(tag+'\t'+quote(str(message),safe=''), flush=True)
    except BrokenPipeError:
        sys.stdout = open(os.devnull, 'w')  # A closed UI must not interrupt restoration.

def matches(actual, desired, restored=False):
    a={o['name']:o for o in actual['outputs']}
    if set(a)!={p['name'] for p in desired}:
        return False
    for p in desired:
        o=a[p['name']]
        if o['mode']!=p['mode']:
            return False
        if p['mode'] is None:
            continue
        if any(o[k]!=p[k] for k in ('x','y','primary') if k in p):
            return False
        if p.get('rate') and abs(float(o['rate'] or 0)-float(p['rate']))>.02:
            return False
        if restored and o['panning']!=p['panning']:
            return False
    return True

def trial(plan, control=sys.stdin, seconds=TIMEOUT):
    # Lock is held by the watchdog, not by the UI that may disappear.
    directory=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/('workstation-displays-'+str(os.getuid()))
    directory.mkdir(mode=0o700,exist_ok=True)
    info=directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise ValueError('The display safety directory is unavailable.')
    with (directory/'transaction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=snapshot();validate(old,plan)
        try:
            run(arguments(plan))
            if not matches(snapshot(),plan):
                raise ValueError('The display service did not apply the requested layout.')
            emit('pending',f'Keep these display settings? Reverting in {seconds} seconds.')
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                ready,_,_=select.select([control],[],[],max(0,deadline-time.monotonic()))
                if not ready:
                    break
                command=control.readline().strip()
                if command=='keep':
                    if not matches(snapshot(),plan):
                        raise ValueError('The layout changed before confirmation.')
                    emit('kept','Display settings kept for this session.');return
                break  # Revert, EOF, or malformed input always restores.
        except Exception as exc:
            emit('note','Could not keep the new layout: '+str(exc))
        try:
            run(arguments(old['outputs'],restore=True))
            if not matches(snapshot(),old['outputs'],restored=True):
                raise ValueError('A display may have disconnected.')
            emit('reverted','Previous display settings restored.')
        except Exception as exc:
            emit('error','Could not restore the previous layout: '+str(exc))
            raise

def main():
    if os.environ.get('XDG_SESSION_TYPE')=='wayland':
        raise ValueError('Display controls currently support X11 sessions only.')
    if sys.argv[1:] == ['snapshot']:
        state=snapshot()
        for o in state['outputs']:
            fields=['output',o['name'],o['mode'] or 'off',str(o['x']),str(o['y']),str(int(o['primary'])),','.join(dict.fromkeys(o['modes']))]
            print('\t'.join(quote(f,safe='') for f in fields),flush=True)
        emit('ready','Ready to arrange displays.' if state['supported'] else 'Rotation or scaling is active; changes are unavailable in this first pass.')
        emit('supported',int(state['supported']))
    elif len(sys.argv)==3 and sys.argv[1]=='trial':
        trial(json.loads(sys.argv[2]))
    else:
        raise ValueError('Unknown display operation.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        emit('error',str(exc));sys.exit(1)
