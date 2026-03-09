import os
import sys
import tempfile

# Ensure project root is on sys.path so `src` package can be imported in tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Ensure tests don't fail if youtube_transcript_api isn't installed in the test env
import types
fake_ytt = types.ModuleType('youtube_transcript_api')

class DummyYT:
    def list(self, vid):
        raise RuntimeError('dummy')

fake_ytt.YouTubeTranscriptApi = DummyYT

formatters = types.ModuleType('youtube_transcript_api.formatters')
class DummyFormatter:
    def format_transcript(self, transcript):
        return ''

formatters.SRTFormatter = lambda: DummyFormatter()
sys.modules['youtube_transcript_api'] = fake_ytt
sys.modules['youtube_transcript_api.formatters'] = formatters

from src.utils.subtitle import _yt_dlp_download_subtitles


def test_yt_dlp_strategy_creates_candidate(monkeypatch):
    video_id = 'TESTVID'
    with tempfile.TemporaryDirectory() as td:
        save_path = os.path.join(td, f"{video_id}.srt")

        calls = []

        def fake_run_cli(cmd, args_list, *a, **k):
            # simulate yt-dlp creating a subtitle file for en
            calls.append((cmd, args_list))
            out = os.path.join(td, f"{video_id}.en.srt")
            with open(out, 'w', encoding='utf-8') as f:
                f.write('1\n00:00:00,000 --> 00:00:01,000\nTest\n')
            return 0

        monkeypatch.setattr('src.utils.subtitle.run_cli_command', fake_run_cli)

        res = _yt_dlp_download_subtitles(video_id, save_path, ['en'])
        assert res is not False
        assert res.endswith('.en.srt')


def test_yt_dlp_no_candidate_returns_false(monkeypatch):
    video_id = 'NOFILE'
    with tempfile.TemporaryDirectory() as td:
        save_path = os.path.join(td, f"{video_id}.srt")

        def fake_run_cli_fail(cmd, args_list, *a, **k):
            # simulate failure/no file created
            return 1

        monkeypatch.setattr('src.utils.subtitle.run_cli_command', fake_run_cli_fail)

        res = _yt_dlp_download_subtitles(video_id, save_path, ['en'])
        assert res is False
