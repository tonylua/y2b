import os
import re
import sys
import glob
import subprocess
from typing import Optional, Dict, List, Callable
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from .retry_decorator import retry
from .stringUtil import add_suffix_to_filename, abs_to_rel
from .sys import run_cli_command, get_video_duration
from .translate_srt import SRTTranslator


def add_subtitle(
    record: Dict,
    orig_id: str,
    title: str,
    video_path: str,
    origin_video_path: str,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, str]:
    def update_progress(percent: int, message: str):
        if progress_callback:
            progress_callback(percent, message)

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
    actual_subtitle_type = need_subtitle

    def check_subtitle_type(path: str) -> str:
        if not path or not os.path.exists(path):
            return ''
        basename = os.path.basename(path)
        if '_' in basename and '.srt' in basename:
            return 'bilingual'
        elif '.cn.srt' in basename or '.zh-Hans.srt' in basename or '.zh-CN.srt' in basename:
            return 'cn'
        elif '.en.srt' in basename:
            return 'en'
        return ''

    if subtitles_path and not subtitles_exist:
        print(f"尝试补充字幕 {orig_id} {title} {subtitles_path}")
        try:
            update_progress(26, '正在获取字幕列表...')
            transcript_list = YouTubeTranscriptApi().list(orig_id)
            update_progress(28, '正在下载字幕...')
            subtitle_down_result = retryable_download(orig_id, subtitles_path, need_subtitle, update_progress)

            if subtitle_down_result:
                actual_subtitle_type = subtitle_down_result['lang']
                subtitles_path = subtitle_down_result['path']
                subtitles_exist = os.path.exists(subtitles_path)
                print(f"下载字幕 {subtitles_exist}: {subtitles_path}")
        except KeyboardInterrupt:
            print("\n用户中断了字幕下载")
            raise
        except Exception as e:
            print(f"下载字幕失败: {e}")
    elif subtitles_exist:
        existing_type = check_subtitle_type(subtitles_path)
        print(f"现有字幕类型: {existing_type}, 需要类型: {need_subtitle}")
        
        if need_subtitle == 'bilingual' and existing_type != 'bilingual':
            print("需要双语字幕，但现有字幕不是双语，尝试翻译...")
            try:
                update_progress(26, '正在翻译字幕...')
                translator = SRTTranslator()
                base_path = subtitles_path.rsplit('.', 1)[0]
                other_lang = 'cn' if '.en.srt' in subtitles_path else 'en'
                translated_path = f"{base_path.rsplit('.', 1)[0]}.{other_lang}.srt"
                translator.translate_srt_file(subtitles_path, translated_path)
                
                merged_path = subtitles_path.replace('.srt', f'_{other_lang}.srt')
                if '_' not in merged_path:
                    lang_match = re.search(r'\.([a-zA-Z\-]+)\.srt$', subtitles_path)
                    if lang_match:
                        orig_lang = lang_match.group(1)
                        merged_path = subtitles_path.replace(f'.{orig_lang}.srt', f'.{orig_lang}_{other_lang}.srt')
                
                translator.merge_srt_files(subtitles_path, translated_path, merged_path)
                subtitles_path = merged_path
                actual_subtitle_type = 'bilingual'
                print(f"双语字幕已生成: {merged_path}")
            except Exception as e:
                print(f"翻译或合并失败: {e}")
                actual_subtitle_type = existing_type
        else:
            actual_subtitle_type = existing_type if existing_type else need_subtitle

    if subtitles_exist:
        try:
            update_progress(30, '正在处理字幕...')
            title_prefix = subtitle_title_map.get(actual_subtitle_type, '转')
            cleaned_title = re.sub(r'^(\[.*?\]\s*)+', '', title)
            title = f"[{title_prefix}] {cleaned_title}"
            video_path = add_suffix_to_filename(video_path, 'with_srt')
            ff_args = prepare_ffmpeg_args(
                origin_video_path,
                subtitles_path,
                video_path,
                need_subtitle
            )
            print("加字幕...", title, subtitles_path, ff_args)
            video_duration = get_video_duration(origin_video_path)
            
            last_percent = [25]
            def ffmpeg_progress_callback(percent: int, message: str):
                mapped_percent = 25 + int(percent * 0.14)
                if mapped_percent > last_percent[0]:
                    last_percent[0] = mapped_percent
                    update_progress(mapped_percent, '正在嵌入字幕...')
            
            update_progress(25, '正在嵌入字幕...')
            run_cli_command('ffmpeg', ff_args, ffmpeg_progress_callback, video_duration)

        except KeyboardInterrupt:
            print("\n用户中断了字幕处理")
            raise
        except (Exception, subprocess.CalledProcessError) as e:
            print('ffmpeg 加字幕过程报错', e)
            title = f"[转] {title}"
    else:
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
    if sys.platform == 'win32':
        rel_input = abs_to_rel(input_path, 3)
        rel_srt = abs_to_rel(srt_path, 3)
        ass_path = rel_srt[:-4] + '.ass'

        run_cli_command('ffmpeg', ['-y', '-i', rel_srt, ass_path])

        return [
            "-y",
            "-i", rel_input,
            "-vf", f"ass={ass_path}",
            output_path
        ]
    else:
        base_args = [
            "-y",
            "-i", input_path,
            "-vf", f"subtitles={srt_path}",
            "-c:a", "copy",
            output_path
        ]

        if subtitle_lang == 'cn':
            font_style = "force_style='FontName=AR PL UKai CN'"
            return [
                "-y",
                "-i", input_path,
                "-vf", f"subtitles={srt_path}:{font_style}",
                "-c:a", "copy",
                output_path
            ]
        return base_args


def fix_subtitle_path(path: str, lang: str):
    pattern = re.compile(r'(.*)(\.)[a-zA-Z\-]+(\.srt)$', re.IGNORECASE)
    if pattern.match(path):
        return pattern.sub(fr'\1.{lang}\3', path)
    else:
        return path


def download_subtitles(
    video_id: str,
    save_path: str,
    need_subtitle: str,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Dict[str, str] | bool:
    def update_progress(percent: int, message: str):
        if progress_callback:
            progress_callback(percent, message)

    languages = ['en']
    if need_subtitle == 'cn':
        languages = ['zh-Hans', 'zh-CN', 'en']
    elif need_subtitle in ('bilingual', 'both'):
        languages = ['en', 'zh-Hans', 'zh-CN']
    print(need_subtitle, '-->', languages)

    ytt_api = YouTubeTranscriptApi()
    transcript = None
    try:
        update_progress(29, '正在查找字幕...')
        transcript = ytt_api.list(video_id).find_transcript(languages)
        print("find_generated_transcript", transcript.language_code);
    except Exception as e:
        print("YouTubeTranscriptApi 获取失败（可能是网络/SSL问题）:", e)
        update_progress(29, '使用yt-dlp下载字幕...')
        fallback_path = _yt_dlp_download_subtitles(video_id, save_path, languages)
        if not fallback_path:
            print('yt-dlp 回退下载失败')
            return False
        print('yt-dlp 回退下载成功:', fallback_path)
        m = re.search(r"\.(?P<lang>[a-zA-Z\-]+)\.srt$", os.path.basename(fallback_path))
        transcript_lang = m.group('lang') if m else ''
        tmp_path = fallback_path
        lang = 'en' if transcript_lang == 'en' else ('cn' if 'zh' in transcript_lang else transcript_lang)
        fixed_path = tmp_path
        if need_subtitle in ('bilingual', 'both') and lang != 'bilingual':
            other_lang = 'cn' if transcript_lang == 'en' else 'en'
            translated_path = tmp_path.replace(f'.{transcript_lang}.srt', f'.{other_lang}.srt')
            try:
                update_progress(29, '正在翻译字幕...')
                translator = SRTTranslator()
                translator.translate_srt_file(tmp_path, translated_path)
                merged_path = tmp_path.replace(f'.{transcript_lang}.srt', f'.{transcript_lang}_{other_lang}.srt')
                translator.merge_srt_files(tmp_path, translated_path, merged_path)
                fixed_path = merged_path
                lang = 'bilingual'
            except Exception as e2:
                print('回退时翻译或合并失败', e2)
        return {'lang': lang, 'path': fixed_path}

    base_with_lang = fix_subtitle_path(save_path, transcript.language_code)
    if not re.search(rf"\.{transcript.language_code}\.srt$", base_with_lang, re.IGNORECASE):
        base_with_lang = base_with_lang.replace('.srt', f'.{transcript.language_code}.srt')

    tmp_path = base_with_lang
    lang = 'en' if transcript.language_code == 'en' else 'cn'
    print("fix_subtitle_path", tmp_path);
    update_progress(29, '正在下载字幕...')
    fetched_transcript = transcript.fetch()
    srt_content = SRTFormatter().format_transcript(fetched_transcript)
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    print("srt downloaded by YouTubeTranscriptApi", tmp_path)
    fixed_path = tmp_path

    if need_subtitle == 'bilingual' or need_subtitle == 'both':
        other_lang = 'cn' if transcript.language_code == 'en' else 'en'
        translated_path = tmp_path.replace(f'.{transcript.language_code}.srt', f'.{other_lang}.srt')
        update_progress(29, '正在翻译字幕...')
        translator = SRTTranslator()
        translator.translate_srt_file(tmp_path, translated_path)
        merged_path = tmp_path.replace(f'.{transcript.language_code}.srt', f'.{transcript.language_code}_{other_lang}.srt')
        translator.merge_srt_files(tmp_path, translated_path, merged_path)
        print("srt translated and merged for bilingual", merged_path)
        fixed_path = merged_path
        lang = 'bilingual'
    elif need_subtitle != transcript.language_code:
        fixed_path = tmp_path.replace(f'.{transcript.language_code}.srt', f'.{need_subtitle}.srt')
        lang = need_subtitle
        update_progress(29, '正在翻译字幕...')
        translator = SRTTranslator()
        translator.translate_srt_file(tmp_path, fixed_path)
        print("srt translated", fixed_path, transcript.language_code, need_subtitle)
    return {
        'lang': lang,
        'path': fixed_path
    }


def _yt_dlp_download_subtitles(video_id: str, save_path: str, languages: List[str]) -> str | bool:
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

    candidates = glob.glob(os.path.join(out_dir, f"{video_id}*.srt"))
    if not candidates:
        return False

    for lang in languages:
        for c in candidates:
            if re.search(rf"\.{re.escape(lang)}\.srt$", c, re.IGNORECASE):
                return c

    return candidates[0]


retryable_download = retry(max_retries=3)(download_subtitles)
