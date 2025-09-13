import os
import re
import sys 
import yt_dlp
import subprocess
from typing import Optional, Dict, List
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from .retry_decorator import retry
from .stringUtil import add_suffix_to_filename, abs_to_rel
from .sys import run_cli_command 
from .translate_srt import SRTTranslator

def add_subtitle(
    record: Dict,
    orig_id: str,
    title: str,
    video_path: str,
    origin_video_path: str
) -> Dict[str, str]:
    """
    为视频添加字幕并返回处理后的视频信息
    
    Args:
        record: 包含字幕信息的字典
        orig_id: 原始视频ID
        title: 视频标题
        video_path: 视频文件路径
        origin_video_path: 原始视频路径
        
    Returns:
        Dict[str, str]: 包含处理后的标题和视频路径
    """
    # 初始化字幕相关变量
    need_subtitle = record.get('subtitle_lang')
    subtitle_title_map = {'en': '英字', 'cn': '中字'}
    subtitles_path = ''
    
    if not need_subtitle:
        return {
            'title': f"[转] {title}",
            'video_path': video_path
        }

    subtitles_path = record.get('save_srt', '')
    subtitles_exist = subtitles_path and os.path.exists(subtitles_path)
    subtitle_down_result = False

    # 尝试下载字幕
    if subtitles_path and not subtitles_exist:
        print(f"尝试补充字幕 {orig_id} {title} {subtitles_path}")
        try:
            transcript_list = YouTubeTranscriptApi().list(orig_id)
            subtitle_down_result = retryable_download(orig_id, subtitles_path, need_subtitle)

            if (subtitle_down_result):
                need_subtitle = subtitle_down_result['lang']
                subtitles_path = subtitle_down_result['path']
                    
                subtitles_exist = os.path.exists(subtitles_path)
                print(f"下载字幕 {subtitles_exist}: {subtitles_path}")
        except Exception as e:
            print(f"下载字幕失败: {e}")

    # 处理字幕添加
    if subtitles_exist:
        try:
            # 更新标题前缀
            title_prefix = subtitle_title_map.get(need_subtitle, '转') if subtitle_down_result else '转'
            cleaned_title = title.replace(r'^\[.*?]\s*', '')
            title = f"[{title_prefix}] {cleaned_title}"
            # 更新视频路径
            video_path = add_suffix_to_filename(video_path, 'with_srt')
            # 准备FFmpeg参数
            ff_args = prepare_ffmpeg_args(
                origin_video_path,
                subtitles_path,
                video_path,
                need_subtitle
            )
            print("加字幕...", title, subtitles_path, ff_args)
            run_cli_command('ffmpeg', ff_args)
            
        except (Exception, subprocess.CalledProcessError) as e:
            print('ffmpeg 加字幕过程报错', e)
            title = f"[转] {title}"
    else:
        title = f"[转] {title}"
        raise FileNotFoundError('设置了字幕但没下载到', subtitles_path)
    
    return {
        'title': title,
        'video_path': video_path,
        'subtitles_path': subtitles_path
    }

def prepare_ffmpeg_args(
    input_path: str,
    srt_path: str,
    output_path: str,
    subtitle_lang: Optional[str] = None
) -> List[str]:
    """准备FFmpeg命令行参数"""
    if sys.platform == 'win32':
        rel_input = abs_to_rel(input_path, 3)
        rel_srt = abs_to_rel(srt_path, 3)
        ass_path = rel_srt[:-4] + '.ass'
        
        # 先转换SRT到ASS
        run_cli_command('ffmpeg', ['-i', rel_srt, ass_path])
        
        return [
            "-i", rel_input,
            "-vf", f"ass={ass_path}",
            output_path
        ]
    else:
        base_args = [
            "-i", input_path,
            "-vf", f"subtitles={srt_path}",
            "-c:a", "copy",
            output_path
        ]
        
        if subtitle_lang == 'cn':
            font_style = "force_style='FontName=AR PL UKai CN'"
            return [
                "-i", input_path,
                "-vf", f"subtitles={srt_path}:{font_style}",
                "-c:a", "copy",
                output_path
            ]
        return base_args

def fix_subtitle_path(path: str, lang: str):
    # 修正路径中的语言部分（假设路径格式为 /path/to/subtitle.{old_lang}.srt）
    pattern = re.compile(r'(.*)(\.)[a-zA-Z\-]+(\.srt)$', re.IGNORECASE)
    if pattern.match(path):
        return pattern.sub(fr'\1.{lang}\3', path)
    else:
        return path 

def download_subtitles(video_id: str, save_path: str, need_subtitle: str) -> Dict[str, str] | bool:
    languages = ['en']
    if need_subtitle == 'cn':
        # https://www.searchapi.io/docs/parameters/youtube-transcripts/lang
        languages = ['zh-Hans', 'zh-CN', 'en']
    print(need_subtitle, '-->', languages)
    # step1：使用 youtube-transcript-api
    ytt_api = YouTubeTranscriptApi()
    transcript = ytt_api.list(video_id).find_transcript(languages)
    print("find_generated_transcript", transcript.language_code);
    tmp_path = fix_subtitle_path(save_path, transcript.language_code)
    lang = 'en' if transcript.language_code == 'en' else 'cn'
    print("fix_subtitle_path", tmp_path);
    fetched_transcript = transcript.fetch() 
    srt_content = SRTFormatter().format_transcript(fetched_transcript)
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    print("srt downloaded by YouTubeTranscriptApi", tmp_path)
    fixed_path = tmp_path
    # step2：使用本地模型加工en字幕
    if need_subtitle != transcript.language_code:
        fixed_path = tmp_path.replace(f'.{transcript.language_code}.srt$', f'.{need_subtitle}.srt')
        lang = need_subtitle
        translator = SRTTranslator()
        translator.translate_srt_file(tmp_path, fixed_path)
        print("srt translated", fixed_path, transcript.language_code, need_subtitle)
    return {
        'lang': lang,
        'path': fixed_path
    }

retryable_download = retry(max_retries=3)(download_subtitles)
