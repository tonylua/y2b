import os
from src.utils.subtitle import add_subtitle


def test_add_subtitle_prefix_bilingual(tmp_path, monkeypatch):
    # Prepare dummy files
    video_file = tmp_path / 'video.mp4'
    origin_video_file = tmp_path / 'origin.mp4'
    srt_file = tmp_path / 'video.en_cn.srt'
    video_file.write_text('video', encoding='utf-8')
    origin_video_file.write_text('origin', encoding='utf-8')
    srt_file.write_text('1\n00:00:00,000 --> 00:00:01,000\nHello\n你好\n', encoding='utf-8')

    record = {
        'subtitle_lang': 'bilingual',
        'save_srt': str(srt_file)
    }

    # Stub out external ffmpeg call so we don't execute it during unit tests
    monkeypatch.setattr('src.utils.subtitle.run_cli_command', lambda *a, **kw: None)

    res = add_subtitle(record, orig_id='amyKC9lJe3Q', title='Linus Torvalds', video_path=str(video_file), origin_video_path=str(origin_video_file))

    assert 'title' in res
    assert res['title'].startswith('[双字]')
    # subtitles_path should return the SRT path we provided
    assert 'subtitles_path' in res and res['subtitles_path'] == str(srt_file)
