import os
from src.utils import subtitle


def test_download_fallback_with_yt_dlp(tmp_path, monkeypatch):
    video_id = 'FAKEID'
    save_path = str(tmp_path / f"{video_id}.en.srt")

    # Simulate YouTubeTranscriptApi failing (e.g. SSL error)
    class DummyAPI:
        def list(self, vid):
            raise RuntimeError('SSL failure')

    monkeypatch.setattr(subtitle, 'YouTubeTranscriptApi', DummyAPI)

    # Simulate the yt-dlp fallback writing the srt file
    srt_path = tmp_path / f"{video_id}.en.srt"
    def fake_yt_dlp_download(vid, sp, langs):
        srt_path.write_text('''1\n00:00:00,000 --> 00:00:01,000\nHello\n''', encoding='utf-8')
        return str(srt_path)

    monkeypatch.setattr(subtitle, '_yt_dlp_download_subtitles', fake_yt_dlp_download)

    result = subtitle.download_subtitles(video_id, save_path, 'en')
    assert result and 'path' in result
    assert os.path.exists(result['path'])
    assert result['lang'] in ('en', 'cn', 'bilingual')
