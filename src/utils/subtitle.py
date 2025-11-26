import os
import re
import sys 
import yt_dlp
import glob
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
    subtitle_title_map = {'en': '英字', 'cn': '中字', 'bilingual': '双字'}
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
            # Use mapping based on requested subtitle setting (e.g. bilingual -> 双字).
            # If subtitles were successfully downloaded/processed subtitle_down_result will be truthy;
            # but we want the correct title prefix even when subtitles already existed, so prefer explicit mapping.
            title_prefix = subtitle_title_map.get(need_subtitle, '转')
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
        # 未能获取到字幕，记录日志并继续，不抛出异常以免中断整个流程
        title = f"[转] {title}"
        print('设置了字幕但没下载到，跳过字幕嵌入:', subtitles_path)
        subtitles_path = ''
    
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
    # 支持三种模式：'en' / 'cn' / 'bilingual'（双语，原文+译文）
    if need_subtitle == 'cn':
        # https://www.searchapi.io/docs/parameters/youtube-transcripts/lang
        languages = ['zh-Hans', 'zh-CN', 'en']
    elif need_subtitle in ('bilingual', 'both'):
        # 下载任意可用字幕（优先英文），然后产生译文并合并为双语文件
        languages = ['en', 'zh-Hans', 'zh-CN']
    print(need_subtitle, '-->', languages)
    # step1：优先尝试使用 youtube-transcript-api
    ytt_api = YouTubeTranscriptApi()
    transcript = None
    try:
        transcript = ytt_api.list(video_id).find_transcript(languages)
        print("find_generated_transcript", transcript.language_code);
    except Exception as e:
        print("YouTubeTranscriptApi 获取失败（可能是网络/SSL问题）:", e)
        # 回退到 yt-dlp 去下载字幕文件（外部程序）
        fallback_path = _yt_dlp_download_subtitles(video_id, save_path, languages)
        if not fallback_path:
            # 无法通过 yt-dlp 获取字幕，直接返回 False
            print('yt-dlp 回退下载失败')
            return False
        # 找到文件后，将其视为下载到的字幕文件
        print('yt-dlp 回退下载成功:', fallback_path)
        # 推断语言后缀
        m = re.search(r"\.(?P<lang>[a-zA-Z\-]+)\.srt$", os.path.basename(fallback_path))
        transcript_lang = m.group('lang') if m else ''
        tmp_path = fallback_path
        lang = 'en' if transcript_lang == 'en' else ('cn' if 'zh' in transcript_lang else transcript_lang)
        fixed_path = tmp_path
        # 根据请求的 need_subtitle 决定是否翻译或合并
        if need_subtitle in ('bilingual', 'both') and lang != 'bilingual':
            other_lang = 'cn' if transcript_lang == 'en' else 'en'
            translated_path = tmp_path.replace(f'.{transcript_lang}.srt', f'.{other_lang}.srt')
            try:
                translator = SRTTranslator()
                translator.translate_srt_file(tmp_path, translated_path)
                merged_path = tmp_path.replace(f'.{transcript_lang}.srt', f'.{transcript_lang}_{other_lang}.srt')
                translator.merge_srt_files(tmp_path, translated_path, merged_path)
                fixed_path = merged_path
                lang = 'bilingual'
            except Exception as e2:
                print('回退时翻译或合并失败', e2)
        return {'lang': lang, 'path': fixed_path}
    # 确保保存路径包含语言后缀，如 mysub.en.srt
    base_with_lang = fix_subtitle_path(save_path, transcript.language_code)
    if not re.search(rf"\.{transcript.language_code}\.srt$", base_with_lang, re.IGNORECASE):
        base_with_lang = base_with_lang.replace('.srt', f'.{transcript.language_code}.srt')

    tmp_path = base_with_lang
    lang = 'en' if transcript.language_code == 'en' else 'cn'
    print("fix_subtitle_path", tmp_path);
    fetched_transcript = transcript.fetch() 
    srt_content = SRTFormatter().format_transcript(fetched_transcript)
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    print("srt downloaded by YouTubeTranscriptApi", tmp_path)
    fixed_path = tmp_path
    # step2：需要翻译或双语时使用本地模型
    if need_subtitle == 'bilingual' or need_subtitle == 'both':
        # 翻译生成另一个文件，再合并
        other_lang = 'cn' if transcript.language_code == 'en' else 'en'
        translated_path = tmp_path.replace(f'.{transcript.language_code}.srt', f'.{other_lang}.srt')
        translator = SRTTranslator()
        translator.translate_srt_file(tmp_path, translated_path)
        # 合并为双语文件：使用 en_cn 或 cn_en 命名
        merged_path = tmp_path.replace(f'.{transcript.language_code}.srt', f'.{transcript.language_code}_{other_lang}.srt')
        translator.merge_srt_files(tmp_path, translated_path, merged_path)
        print("srt translated and merged for bilingual", merged_path)
        fixed_path = merged_path
        lang = 'bilingual'
    elif need_subtitle != transcript.language_code:
        fixed_path = tmp_path.replace(f'.{transcript.language_code}.srt', f'.{need_subtitle}.srt')
        lang = need_subtitle
        translator = SRTTranslator()
        translator.translate_srt_file(tmp_path, fixed_path)
        print("srt translated", fixed_path, transcript.language_code, need_subtitle)
    return {
        'lang': lang,
        'path': fixed_path
    }


def _yt_dlp_download_subtitles(video_id: str, save_path: str, languages: List[str]) -> str | bool:
    """使用 yt-dlp 回退下载字幕（不下载视频），返回实际保存的 srt 路径或 False。"""
    out_dir = os.path.dirname(save_path) or '.'
    outtmpl = os.path.join(out_dir, f"{video_id}.%(ext)s")
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    args = [
        '--skip-download',
        '--write-sub',
        '--write-auto-sub',
        '--sub-lang', ','.join(languages),
        '--sub-format', 'srt',
        '-o', outtmpl,
        video_url
    ]

    try:
        run_cli_command('yt-dlp', args)
    except Exception as e:
        print('yt-dlp 缺省命令执行失败:', e)
        return False

    # 查找以video_id开头的 srt 文件
    candidates = glob.glob(os.path.join(out_dir, f"{video_id}*.srt"))
    if not candidates:
        return False

    # 根据 languages 优先顺序选取匹配文件
    for lang in languages:
        for c in candidates:
            if re.search(rf"\.{re.escape(lang)}\.srt$", c, re.IGNORECASE):
                return c

    # 没有找到指定语言，返回第一个 srt
    return candidates[0]

retryable_download = retry(max_retries=3)(download_subtitles)
