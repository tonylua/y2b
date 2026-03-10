#!/usr/bin/env python
import os
import re
import sys

# Locate project root and sample .en.srt
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
static_dir = os.path.join(repo_root, 'static')
if not os.path.isdir(static_dir):
    print('ERROR: static directory not found:', static_dir)
    sys.exit(2)

en_files = []
for root, _, files in os.walk(static_dir):
    for fn in files:
        if fn.lower().endswith('.en.srt'):
            en_files.append(os.path.join(root, fn))

if not en_files:
    print(f'ERROR: no .en.srt files found under {static_dir}')
    sys.exit(2)

sample = en_files[0]
print('Using sample SRT:', sample)

def _parse_srt_to_objs(path):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    blocks = [b.strip() for b in re.split(r"\r?\n\r?\n", text) if b.strip()]
    subs = []
    for b in blocks:
        lines = b.splitlines()
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except Exception:
            idx = 0
        times = lines[1].strip()
        start_s, end_s = [t.strip() for t in times.split('-->')]
        content = '\n'.join(lines[2:]).strip()
        class Sub: pass
        s = Sub()
        s.index = idx
        s.start = start_s
        s.end = end_s
        s.content = content
        subs.append(s)
    return subs

subs = _parse_srt_to_objs(sample)
if not subs:
    print('ERROR: no subtitles parsed from', sample)
    sys.exit(2)

# Use a small simplified subset to keep test stable
use_n = min(8, len(subs))
simple_subs = []
for i in range(use_n):
    orig = subs[i]
    class Sub: pass
    s = Sub()
    s.index = orig.index
    s.start = orig.start
    s.end = orig.end
    s.content = orig.content.splitlines()[0].strip()[:200]
    simple_subs.append(s)

# ensure project root on sys.path so `src` package can be imported
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from src.utils.translate_srt import SRTTranslator

# create minimal translator instance without heavy deps
tr = object.__new__(SRTTranslator)
tr.max_chars = 1200
tr.translate_mode = 'full'
tr.domain = 'programming'
tr.glossary = {}

# identity translator
def fake_translate_texts(texts):
    return texts

tr.translate_texts = fake_translate_texts

# inject tiny fake srt module used by _translate_full to construct Subtitle
import types
fake_srt = types.ModuleType('srt')
class Subtitle:
    def __init__(self, index, start, end, content):
        self.index = index
        self.start = start
        self.end = end
        self.content = content
fake_srt.Subtitle = Subtitle
sys.modules['srt'] = fake_srt

print('Running _translate_full on', len(simple_subs), 'items')
res = tr._translate_full(simple_subs)
if res is None:
    print('FAIL: _translate_full returned None')
    sys.exit(1)
if len(res) != len(simple_subs):
    print('FAIL: result length mismatch', len(res), '!=', len(simple_subs))
    sys.exit(1)
for o, n in zip(simple_subs, res):
    if o.index != n.index or o.start != n.start or o.end != n.end or o.content != n.content:
        print('FAIL: mismatch for index', o.index)
        print('orig:', o.index, o.start, o.end, repr(o.content))
        print('new :', getattr(n,'index',None), getattr(n,'start',None), getattr(n,'end',None), repr(getattr(n,'content',None)))
        sys.exit(1)

print('OK: _translate_full preserved alignment and content for', len(simple_subs), 'items')
sys.exit(0)
