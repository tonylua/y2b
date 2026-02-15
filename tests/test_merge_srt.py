from src.utils.translate_srt import merge_srt_files


def test_merge_srt(tmp_path):
    orig_text = """1
00:00:00,000 --> 00:00:01,000
Hello

2
00:00:01,500 --> 00:00:03,000
Goodbye
"""

    trans_text = """1
00:00:00,000 --> 00:00:01,000
你好

2
00:00:01,500 --> 00:00:03,000
再见
"""

    orig = tmp_path / "sample.en.srt"
    trans = tmp_path / "sample.cn.srt"
    out = tmp_path / "sample.en_cn.srt"

    orig.write_text(orig_text, encoding="utf-8")
    trans.write_text(trans_text, encoding="utf-8")

    merge_srt_files(str(orig), str(trans), str(out))

    merged = out.read_text(encoding="utf-8")
    assert "Hello\n你好" in merged
    assert "Goodbye\n再见" in merged


def test_merge_srt_time_alignment(tmp_path):
    # indexes do not line up, but times overlap and should be paired when align_by='time'
    orig_text = """1
00:00:00,000 --> 00:00:02,000
One two

2
00:00:02,500 --> 00:00:04,000
Second original
"""

    trans_text = """1
00:00:00,500 --> 00:00:01,500
一二

2
00:00:02,600 --> 00:00:03,500
第二个
"""

    orig = tmp_path / "t1.en.srt"
    trans = tmp_path / "t1.cn.srt"
    out = tmp_path / "t1.en_cn.srt"

    orig.write_text(orig_text, encoding="utf-8")
    trans.write_text(trans_text, encoding="utf-8")

    merge_srt_files(str(orig), str(trans), str(out), align_by='time')

    merged = out.read_text(encoding="utf-8")
    assert "One two\n一二" in merged
    assert "Second original\n第二个" in merged
