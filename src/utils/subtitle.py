import os
import re
import sys
import glob
import json
import subprocess
import logging
from typing import Optional, Dict, List, Callable
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from .retry_decorator import retry
from .db import VideoDB
from .stringUtil import add_suffix_to_filename, abs_to_rel
from .sys import run_cli_command, get_video_duration
from .translate_srt import LLMTranslator, merge_srt_files as _merge_srt_files
from .llm_client import LLMConfig, LLMClient

EN_LANGS = ['en', 'en-US', 'en-GB']
CN_LANGS = ['zh-Hans', 'zh-CN', 'zh', 'zh-Hant', 'zh-TW']


def _load_glossary() -> Dict[str, str]:
    """从 config/glossary.json 加载术语表（忽略以 _ 开头的元数据键）。"""
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'glossary.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith('_') and isinstance(v, str)}
    except Exception:
        return {}


def _save_glossary(glossary: Dict[str, str]):
    """保存术语表到 config/glossary.json，保留注释"""
    path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'glossary.json')
    try:
        # 读取现有文件保留注释
        existing_comments = {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            existing_comments = {k: v for k, v in data.items() if k.startswith('_')}
        except Exception:
            pass

        # 合并术语表和注释
        output = {**existing_comments, **glossary}

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to save glossary: {e}")


def _extract_terms_llm(subtitle_text: str, existing_glossary: Dict[str, str], llm_client: LLMClient) -> Dict[str, str]:
    """
    用 LLM 从英文字幕中识别专业术语，返回建议的译法。

    返回格式: {"array": "数组", "React": "React", "callback": "回调"}
    """
    # 只取前 3000 字符，避免超 token
    sample = subtitle_text[:3000]

    prompt = f"""你是专业的技术翻译术语顾问。分析以下英文字幕，识别其中的专业术语（编程语言、框架、库、算法、技术概念、品牌名等）。

对每个术语，判断应该：
1. 翻译成中文（如 "array" → "数组"）
2. 保留英文原文（如 "React" → "React", "GitHub" → "GitHub"）

**已有术语表**（这些术语无需重复返回）：
{json.dumps(existing_glossary, ensure_ascii=False)}

**字幕文本**：
{sample}

**要求**：
- 只返回**新发现的**术语（不在已有术语表中的）
- 输出严格的 JSON 格式：{{"term1": "译文1", "term2": "译文2"}}
- 如果没有新术语，返回空对象：{{}}
- 保留原文时，值也写英文原词（如 {{"React": "React"}}）
"""

    try:
        response = llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        return json.loads(response)
    except Exception as e:
        logging.error(f"LLM term extraction failed: {e}")
        return {}


def _is_interactive() -> bool:
    """判断当前是否为可交互的终端环境（CLI 前台）。

    Web 后台线程 / 非 TTY 环境返回 False，此时术语自动全部接受，不阻塞。
    """
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _confirm_new_terms(new_terms: Dict[str, str]) -> Dict[str, str]:
    """
    确认新术语，返回接受的术语。

    - 交互式终端（CLI）：让用户选择 全部接受 / 逐个确认 / 跳过
    - 非交互环境（Web 后台）：自动全部接受，不阻塞流程
    """
    if not new_terms:
        return {}

    # 非交互环境：自动接受，避免在 Web 后台线程阻塞等待 stdin
    if not _is_interactive():
        print(f"自动接受 {len(new_terms)} 个新术语（非交互环境）: {list(new_terms.keys())}")
        return new_terms

    # 交互时临时压制 werkzeug 访问日志，避免刷屏盖住提示
    werkzeug_logger = logging.getLogger('werkzeug')
    original_level = werkzeug_logger.level
    werkzeug_logger.setLevel(logging.ERROR)
    try:
        print(f"\n检测到 {len(new_terms)} 个新术语：")
        for i, (en, zh) in enumerate(new_terms.items(), 1):
            print(f"  {i}. {en} → {zh}")

        try:
            choice = input("\n[1] 全部接受  [2] 逐个确认  [3] 跳过\n选择: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n跳过术语确认")
            return {}

        if choice == '1':
            return new_terms
        elif choice == '2':
            accepted = {}
            for en, zh in new_terms.items():
                try:
                    ans = input(f"  {en} → {zh}  [Y/n/e(编辑)]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n中断确认")
                    break

                if ans in ('', 'y', 'yes'):
                    accepted[en] = zh
                elif ans.startswith('e'):
                    try:
                        custom = input(f"    输入 {en} 的译法: ").strip()
                        if custom:
                            accepted[en] = custom
                    except (EOFError, KeyboardInterrupt):
                        continue
            return accepted
        else:
            print("跳过术语更新")
            return {}
    finally:
        werkzeug_logger.setLevel(original_level)


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

                # Load LLM config and client
                llm_config = LLMConfig()
                if not llm_config.enabled:
                    raise RuntimeError("LLM 翻译未启用，无法生成双语字幕")

                llm_client = LLMClient(llm_config)
                glossary = _load_glossary()
                translator = LLMTranslator(llm_client=llm_client, glossary=glossary)

                base_path = subtitles_path.rsplit('.', 1)[0]
                other_lang = 'cn' if '.en.srt' in subtitles_path else 'en'

                merged_path = subtitles_path.replace('.srt', f'_{other_lang}.srt')
                if '_' not in merged_path:
                    lang_match = re.search(r'\.([a-zA-Z\-]+)\.srt$', subtitles_path)
                    if lang_match:
                        orig_lang = lang_match.group(1)
                        merged_path = subtitles_path.replace(f'.{orig_lang}.srt', f'.{orig_lang}_{other_lang}.srt')

                # 直接输出双语（sentence 模式内部对齐）
                translator.translate_srt_file(subtitles_path, merged_path, bilingual=True)
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
    """用 LLM 翻译字幕（并按需合并成双语）。

    primary: {'lang','path','code'} 已下载到的字幕（通常是英文）。
    make_bilingual: True 生成双语（原文+译文合并），False 只输出译文。
    """
    def update_progress(percent: int, message: str):
        if progress_callback:
            progress_callback(percent, message)

    src_path = primary['path']
    src_kind = primary['lang']
    other = 'cn' if src_kind == 'en' else 'en'
    base = _srt_base(src_path)

    # 加载 LLM 配置
    llm_config = LLMConfig()
    if not llm_config.enabled:
        raise RuntimeError(
            "LLM 翻译未启用。请编辑 config/_llm.json，设置 enabled=true 并填写 api_key。\n"
            "参考文档：LLM_INTEGRATION.md"
        )

    # 加载术语表
    glossary = _load_glossary()

    # 初始化 LLM 客户端
    llm_client = LLMClient(llm_config)

    # 可选：术语自动识别
    if llm_config.feature_enabled('term_extraction'):
        try:
            print("\n正在识别字幕中的专业术语...")
            with open(src_path, 'r', encoding='utf-8') as f:
                subtitle_text = f.read()

            new_terms = _extract_terms_llm(subtitle_text, glossary, llm_client)

            if new_terms:
                accepted = _confirm_new_terms(new_terms)
                if accepted:
                    glossary.update(accepted)
                    _save_glossary(glossary)
                    print(f"已添加 {len(accepted)} 个术语到 glossary.json")
        except Exception as e:
            logging.warning(f"术语识别失败，继续翻译: {e}")

    update_progress(29, '正在用 LLM 翻译字幕...')
    print("使用 LLM 翻译（带上下文和术语表）...")

    translator = LLMTranslator(
        llm_client=llm_client,
        glossary=glossary
    )

    if not make_bilingual:
        # 纯译文：按中文重新断句
        translated_path = f"{base}.{other}.srt"
        translator.translate_srt_file(src_path, translated_path)
        return {'lang': other, 'path': translated_path, 'code': other}

    # 双语：直接输出中英双语
    merged_path = f"{base}.{primary.get('code', src_kind)}_{other}.srt"
    translator.translate_srt_file(src_path, merged_path, bilingual=True)
    print(f"字幕已翻译为双语: {merged_path}")
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
