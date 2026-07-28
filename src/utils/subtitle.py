import os
import re
import sys
import glob
import subprocess
from typing import Optional, Dict, List, Callable
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from .retry_decorator import retry
from .db import VideoDB
from .stringUtil import add_suffix_to_filename, abs_to_rel
from .sys import run_cli_command, get_video_duration
from .translate_srt import SRTTranslator, merge_srt_files as _merge_srt_files

EN_LANGS = ['en', 'en-US', 'en-GB']
CN_LANGS = ['zh-Hans', 'zh-CN', 'zh', 'zh-Hant', 'zh-TW']


def _is_probably_translated_srt(path: str, sample_lines: int = 200) -> bool:
    """Rudimentary heuristic: sample the file and decide if it contains
    a meaningful amount of Chinese (CJK) characters, or mixed bilingual lines.
    Returns True if it's likely already translated (bilingual).
    """
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = []
            for _ in range(sample_lines):
                line = f.readline()
                if not line:
                    break
                lines.append(line.strip())
        if not lines:
            return False

        total = 0
        cjk_count = 0
        lines_with_cjk = 0
        for ln in lines:
            if not ln:
                continue
            total += len(ln)
            # count CJK characters
            cjk_matches = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\u3000-\u303f\uff00-\uffef]', ln)
            if cjk_matches:
                cjk_count += len(cjk_matches)
                lines_with_cjk += 1

        # if many lines contain CJK, treat as translated
        if lines_with_cjk >= max(3, int(len(lines) * 0.05)):
            return True

        # if proportion of CJK chars over sampled chars > 2%
        if total and (cjk_count / total) > 0.02:
            return True

    except Exception:
        return False
    return False



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

    # If requested bilingual but the stored path (save_srt) doesn't exist,
    # search for any merged subtitle file by original id (e.g. GQvDNRBe4IU.en_cn.srt)
    # and use it to skip re-downloading/translating.
    if need_subtitle == 'bilingual' and not subtitles_exist:
        # Prefer searching in the video's save directory (where subtitles are usually written).
        # Fallback to directory of `save_srt` if provided, otherwise current dir.
        search_dir = ''
        if origin_video_path:
            search_dir = os.path.dirname(origin_video_path)
        if not search_dir and subtitles_path:
            search_dir = os.path.dirname(subtitles_path)
        if not search_dir:
            search_dir = '.'
        # prefer searching by orig_id if available
        prefix = orig_id if orig_id else (os.path.basename(subtitles_path).split('.')[0] if subtitles_path else '')
        if prefix:
            candidates = glob.glob(os.path.join(search_dir, f"{prefix}*.srt"))
            for c in candidates:
                # look for merged files containing an underscore before the .srt
                if re.search(r"_[^.]+\.srt$", os.path.basename(c)):
                    # verify file likely contains Chinese / bilingual content
                    if _is_probably_translated_srt(c):
                        subtitles_path = c
                        subtitles_exist = True
                        actual_subtitle_type = 'bilingual'
                        print(f"Found existing merged subtitle by orig_id, skipping translate: {c}")
                        # persist this found subtitle path back to DB so future runs see it immediately
                        try:
                            if record and isinstance(record, dict) and record.get('id'):
                                db = VideoDB()
                                db.update_video(record['id'], save_srt=subtitles_path)
                        except Exception:
                            pass
                        break
                    else:
                        print(f"Found candidate merged subtitle but content not bilingual-looking: {c}")

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
            update_progress(26, '正在下载字幕...')
            subtitle_down_result = retryable_download(orig_id, subtitles_path, need_subtitle, update_progress)

            if subtitle_down_result:
                actual_subtitle_type = subtitle_down_result['lang']
                subtitles_path = subtitle_down_result['path']
                subtitles_exist = os.path.exists(subtitles_path)
                print(f"下载字幕 {subtitles_exist}: {subtitles_path}")
            else:
                # 已尝试通过 YouTubeTranscriptApi+yt-dlp(+youtube-dl)等回退下载字幕，未找到
                print('字幕下载失败，已回退多种下载方式仍未获取到字幕')
                # 如果用户明确指定需要字幕，则中断整个流程
                raise RuntimeError(f'缺少字幕: {need_subtitle} 尚未获取到')
        except KeyboardInterrupt:
            print("\n用户中断了字幕下载")
            raise
        except Exception as e:
            print(f"下载字幕失败: {e}")
            raise
    elif subtitles_exist:
        existing_type = check_subtitle_type(subtitles_path)
        print(f"现有字幕类型: {existing_type}, 需要类型: {need_subtitle}")
        
        # If user wants bilingual but saved path is a single-language file,
        # check nearby files (same dir, same orig_id prefix) for an existing merged file
        if need_subtitle == 'bilingual' and existing_type != 'bilingual':
            try:
                search_dir = os.path.dirname(subtitles_path) or '.'
                prefix = orig_id if orig_id else os.path.basename(subtitles_path).split('.')[0]
                if prefix:
                    candidates = glob.glob(os.path.join(search_dir, f"{prefix}*.srt"))
                    for c in candidates:
                        if re.search(r"_[^.]+\.srt$", os.path.basename(c)):
                            if _is_probably_translated_srt(c):
                                subtitles_path = c
                                subtitles_exist = True
                                existing_type = 'bilingual'
                                actual_subtitle_type = 'bilingual'
                                print(f"Found existing merged subtitle near saved SRT, skipping translate: {c}")
                                try:
                                    if record and isinstance(record, dict) and record.get('id'):
                                        db = VideoDB()
                                        db.update_video(record['id'], save_srt=subtitles_path)
                                except Exception:
                                    pass
                                break
                            else:
                                print(f"Found candidate merged subtitle but content not bilingual-looking: {c}")
            except Exception:
                pass

        if need_subtitle == 'bilingual' and existing_type != 'bilingual':
            print("需要双语字幕，但现有字幕不是双语，尝试翻译...")
            try:
                update_progress(26, '正在翻译字幕...')
                translator = SRTTranslator(translate_mode='full', domain='programming', max_chars=4000)
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
            # final path with subtitle suffix
            final_with_srt = add_suffix_to_filename(video_path, 'with_srt')

            # If final file already exists, skip embedding
            if os.path.exists(final_with_srt):
                print("已存在带字幕的视频，跳过嵌入字幕:", final_with_srt)
                return {
                    'title': title,
                    'video_path': final_with_srt,
                    'subtitles_path': subtitles_path
                }

            # write to a temp output first, then atomically rename to final
            temp_output = final_with_srt + '.tmp'
            ff_args = prepare_ffmpeg_args(
                origin_video_path,
                subtitles_path,
                temp_output,
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
            try:
                run_cli_command('ffmpeg', ff_args, ffmpeg_progress_callback, video_duration)
                # move temp to final
                try:
                    os.replace(temp_output, final_with_srt)
                except Exception:
                    # fallback to rename
                    if os.path.exists(temp_output):
                        os.rename(temp_output, final_with_srt)
                video_path = final_with_srt
            finally:
                # cleanup any leftover temp file
                if os.path.exists(temp_output):
                    try:
                        os.remove(temp_output)
                    except Exception:
                        pass

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


def _lang_kind(lang_code: str) -> str:
    """把具体语言代码归类为 'en' / 'cn' / 其它。"""
    lc = (lang_code or '').lower()
    if lc.startswith('en'):
        return 'en'
    if lc.startswith('zh'):
        return 'cn'
    return lang_code


def _srt_base(path: str) -> str:
    """去掉 .srt 以及可能存在的 .<lang> 后缀，得到基础路径。
    例如 a/b/ID.en.srt -> a/b/ID ；a/b/ID.srt -> a/b/ID 。
    """
    base = path[:-4] if path.lower().endswith('.srt') else path
    base = re.sub(r'\.[a-zA-Z\-]+$', '', base)
    return base


def _write_transcript_srt(transcript, out_path: str) -> str:
    fetched = transcript.fetch()
    srt_content = SRTFormatter().format_transcript(fetched)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    return out_path


def _download_track(
    video_id: str,
    save_path: str,
    languages: List[str],
    update_progress: Callable[[int, str], None],
) -> Dict[str, str] | bool:
    """尽力“下载”某一语言的字幕（不翻译）。

    先用 YouTubeTranscriptApi，失败再回退 yt-dlp / youtube-dl。
    返回 {'lang': 'en'|'cn'|<code>, 'path': ...}，全部失败返回 False。
    """
    base = _srt_base(save_path)
    try:
        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.list(video_id).find_transcript(languages)
        code = transcript.language_code
        out_path = f"{base}.{code}.srt"
        _write_transcript_srt(transcript, out_path)
        print(f"字幕下载成功(API) [{code}]: {out_path}")
        return {'lang': _lang_kind(code), 'path': out_path, 'code': code}
    except Exception as e:
        print(f"YouTubeTranscriptApi 获取失败（{languages}），回退 yt-dlp: {e}")

    fallback_path = _yt_dlp_download_subtitles(video_id, save_path, languages)
    if not fallback_path:
        return False
    m = re.search(r"\.(?P<lang>[a-zA-Z\-]+)\.srt$", os.path.basename(fallback_path))
    code = m.group('lang') if m else (languages[0] if languages else '')
    print(f"字幕下载成功(yt-dlp) [{code}]: {fallback_path}")
    return {'lang': _lang_kind(code), 'path': fallback_path, 'code': code}


def translate_and_merge(
    primary: Dict[str, str],
    make_bilingual: bool,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Dict[str, str]:
    """在下载不到目标语言时，用本地模型翻译（并按需合并成双语）。

    primary: {'lang','path','code'} 已下载到的字幕（通常是英文）。
    make_bilingual: True 生成双语（原文+译文合并），False 只输出译文。
    仅在调用方确认允许使用模型后才应调用本函数。
    """
    def update_progress(percent: int, message: str):
        if progress_callback:
            progress_callback(percent, message)

    src_path = primary['path']
    src_kind = primary['lang']
    # 目前本地模型是 en->zh，翻译目标固定为中文
    other = 'cn' if src_kind == 'en' else 'en'
    base = _srt_base(src_path)
    translated_path = f"{base}.{other}.srt"

    update_progress(29, '正在用模型翻译字幕...')
    translator = SRTTranslator(translate_mode='full', domain='programming', max_chars=4000)
    translator.translate_srt_file(src_path, translated_path)

    if not make_bilingual:
        return {'lang': other, 'path': translated_path, 'code': other}

    merged_path = f"{base}.{primary.get('code', src_kind)}_{other}.srt"
    en_path = src_path if src_kind == 'en' else translated_path
    cn_path = translated_path if src_kind == 'en' else src_path
    _merge_srt_files(en_path, cn_path, merged_path)
    print(f"字幕已翻译并合并为双语: {merged_path}")
    return {'lang': 'bilingual', 'path': merged_path, 'code': f"{primary.get('code', src_kind)}_{other}"}


def download_subtitles(
    video_id: str,
    save_path: str,
    need_subtitle: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    allow_translate: bool = True,
) -> Dict[str, str] | bool:
    def update_progress(percent: int, message: str):
        if progress_callback:
            progress_callback(percent, message)

    # ---- 第一步：尽可能“下载”字幕，优先尝试目标语言，失败再多试几个来源 ----
    # 主语言优先级：cn 模式先找中文，其它模式先找英文。
    if need_subtitle == 'cn':
        primary_langs = CN_LANGS + EN_LANGS
    else:
        primary_langs = EN_LANGS + CN_LANGS

    update_progress(29, '正在下载字幕...')
    primary = _download_track(video_id, save_path, primary_langs, update_progress)
    if not primary:
        print('所有下载方式均未获取到字幕')
        return False

    # 只要单语：直接返回，或已是目标语言
    if need_subtitle == 'en':
        if primary['lang'] == 'en':
            return primary
        # 拿到的不是英文，且下载不到英文 —— 需要翻译
        if not allow_translate:
            return {**primary, 'need_translate': True, 'target': 'en', 'make_bilingual': False}
        return translate_and_merge(primary, make_bilingual=False, progress_callback=progress_callback)

    if need_subtitle == 'cn':
        if primary['lang'] == 'cn':
            return primary
        if not allow_translate:
            return {**primary, 'need_translate': True, 'target': 'cn', 'make_bilingual': False}
        return translate_and_merge(primary, make_bilingual=False, progress_callback=progress_callback)

    # ---- 双语：尝试直接下载另一种语言的字幕并合并（不走模型）----
    if need_subtitle in ('bilingual', 'both'):
        other_langs = CN_LANGS if primary['lang'] == 'en' else EN_LANGS
        update_progress(29, '正在下载另一语言字幕...')
        secondary = _download_track(video_id, save_path, other_langs, update_progress)

        if secondary and secondary['lang'] != primary['lang']:
            en_track = primary if primary['lang'] == 'en' else secondary
            cn_track = secondary if primary['lang'] == 'en' else primary
            base = _srt_base(en_track['path'])
            merged_path = f"{base}.{en_track.get('code', 'en')}_{cn_track.get('code', 'cn')}.srt"
            _merge_srt_files(en_track['path'], cn_track['path'], merged_path)
            print('两种语言字幕均下载成功，直接合并为双语:', merged_path)
            return {'lang': 'bilingual', 'path': merged_path,
                    'code': f"{en_track.get('code', 'en')}_{cn_track.get('code', 'cn')}"}

        # 下载不到另一种语言 —— 需要用模型翻译后合并
        if not allow_translate:
            return {**primary, 'need_translate': True, 'target': 'cn', 'make_bilingual': True}
        return translate_and_merge(primary, make_bilingual=True, progress_callback=progress_callback)

    return primary


def _yt_dlp_download_subtitles(video_id: str, save_path: str, languages: List[str]) -> str | bool:
    out_dir = os.path.dirname(save_path) or '.'
    outtmpl = os.path.join(out_dir, f"{video_id}.%(ext)s")
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    # Try multiple strategies to maximize chance of getting English subtitles quickly
    strategies = [
        (['--write-auto-sub'], 'auto-sub only'),
        (['--write-sub'], 'manual-sub only'),
        (['--write-sub', '--write-auto-sub'], 'both subs'),
    ]

    # also try language variants for English
    lang_variants = []
    for lang in languages:
        if lang.lower() == 'en':
            lang_variants.extend(['en', 'en-US', 'en-GB'])
        else:
            lang_variants.append(lang)

    tried = []
    for flags, desc in strategies:
        for lang in lang_variants:
            args = ['--skip-download'] + flags + ['--sub-lang', lang, '--sub-format', 'srt', '-o', outtmpl, video_url]
            tried.append((desc, lang))
            try:
                run_cli_command('yt-dlp', args)
            except Exception as e:
                print(f'yt-dlp {desc}({lang}) 失败:', e)
                continue

            candidates = glob.glob(os.path.join(out_dir, f"{video_id}*.srt"))
            if not candidates:
                continue

            # prefer exact lang match
            for c in candidates:
                if re.search(rf"\.{re.escape(lang)}\.srt$", c, re.IGNORECASE):
                    return c

            # fallback to any candidate
            return candidates[0]

    # try youtube-dl as an extra fallback if installed
    try:
        for flags, desc in strategies:
            for lang in lang_variants:
                args = ['--skip-download'] + flags + ['--sub-lang', lang, '--sub-format', 'srt', '-o', outtmpl, video_url]
                tried.append((f'youtube-dl {desc}', lang))
                try:
                    run_cli_command('youtube-dl', args)
                except Exception as e:
                    print(f'youtube-dl {desc}({lang}) 失败:', e)
                    continue

                candidates = glob.glob(os.path.join(out_dir, f"{video_id}*.srt"))
                if not candidates:
                    continue

                for c in candidates:
                    if re.search(rf"\.{re.escape(lang)}\.srt$", c, re.IGNORECASE):
                        return c
                return candidates[0]
    except Exception:
        pass

    print('尝试的 字幕下载 策略列表:', tried)
    return False


retryable_download = retry(max_retries=3)(download_subtitles)
