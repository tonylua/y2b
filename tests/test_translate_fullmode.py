import os
import re
import sys

# ensure project root is on sys.path so `src` package can be imported in tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.translate_srt import SRTTranslator


def _parse_srt_to_objs(path):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    blocks = [b.strip() for b in re.split(r"\r?\n\r?\n", text) if b.strip()]
    subs = []
    for b in blocks:
        lines = b.splitlines()
        if len(lines) < 3:
            continue
        # simple parse: index, time, content...
        try:
            idx = int(lines[0].strip())
        except Exception:
            idx = 0
        times = lines[1].strip()
        start_s, end_s = [t.strip() for t in times.split('-->')]
        content = '\n'.join(lines[2:]).strip()

        class Sub:
            pass

        s = Sub()
        s.index = idx
        s.start = start_s
        s.end = end_s
        s.content = content
        subs.append(s)
    return subs


def test_translate_full_preserves_alignment(tmp_path):
    # locate the first '*.en.srt' under the repo's static directory
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    static_dir = os.path.join(repo_root, 'static')
    candidates = []
    for root, _, files in os.walk(static_dir):
        for fn in files:
            if fn.lower().endswith('.en.srt'):
                candidates.append(os.path.join(root, fn))
    assert candidates, f"no .en.srt files found under {static_dir}"
    sample = candidates[0]

    subs = _parse_srt_to_objs(sample)
    assert len(subs) > 0

    # use a small simplified subset of subtitles to avoid edge cases in source formatting
    use_n = min(8, len(subs))
    simple_subs = []
    for i in range(use_n):
        orig = subs[i]
        class Sub:
            pass
        s = Sub()
        s.index = orig.index
        s.start = orig.start
        s.end = orig.end
        # take only first line and truncate to keep chunking predictable
        s.content = orig.content.splitlines()[0].strip()[:200]
        simple_subs.append(s)

    # create instance without running __init__ to avoid heavy deps
    tr = object.__new__(SRTTranslator)
    tr.max_chars = 1200
    tr.translate_mode = 'full'
    tr.domain = 'programming'
    tr.glossary = {}

    # fake translate_texts that returns the input unchanged (identity)
    def fake_translate_texts(texts):
        return texts

    tr.translate_texts = fake_translate_texts

    # provide a lightweight fake `srt` module so _translate_full can construct Subtitle objects
    import types
    fake_srt = types.ModuleType('srt')
    class Subtitle:
        def __init__(self, index, start, end, content):
            self.index = index
            self.start = start
            self.end = end
            self.content = content
    fake_srt.Subtitle = Subtitle
    import sys as _sys
    _sys.modules['srt'] = fake_srt

    translated = tr._translate_full(simple_subs)
    assert translated is not None
    assert len(translated) == len(simple_subs)
    # translated subtitles should preserve original timing and content when translate_texts is identity
    for orig, new in zip(simple_subs, translated):
        assert new.index == orig.index
        assert new.start == orig.start
        assert new.end == orig.end
        assert new.content == orig.content
