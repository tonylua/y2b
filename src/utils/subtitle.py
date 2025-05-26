import os
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from .retry_decorator import retry

@retry(max_retries=3, retry_delay=0.5)
def download_subtitles(video_id: str, save_path: str, need_subtitle: str) -> str | bool:
    """下载字幕并保存为 SRT 文件，返回是否成功"""
    try:
        languages = ['en']
        if need_subtitle == 'cn':
            languages = ['zh-Hans', 'zh-CN', 'en']
        # 方案1：使用 youtube-transcript-api
        transcript = YouTubeTranscriptApi.get_transcript(
            video_id, 
            languages=languages
        )
        srt_content = SRTFormatter().format_transcript(transcript)
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        print("srt downloaded by YouTubeTranscriptApi", save_path)
        return transcript[0]['language_code'] 
        
    except Exception as e:
        print(f"API 方式失败: {e}")
        languages = ['en']
        if need_subtitle == 'cn':
            languages = ['zh', 'en']
        try:
            # 方案2：回退到 yt-dlp
            ydl_opts = {
                'writesubtitles': True,
                'subtitlesformat': 'srt',
                'subtitleslangs': languages,
                'skip_download': True,
                'quiet': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f'https://youtu.be/{video_id}'])
            
            # 尝试找到下载的字幕文件
            for lang in languages:
                srt_file = f"{video_id}.{lang}.srt"
                if os.path.exists(srt_file):
                    os.rename(srt_file, save_path)
                    print("srt downloaded by yt_dlp", save_path)
                    return lang 
                    
            print(f"yt-dlp 方式失败")
            return False
        except Exception as e:
            print(f"yt-dlp 方式失败: {e}")
            return False


