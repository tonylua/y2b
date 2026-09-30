import os
import re
import sys
import glob
import json
import math
import subprocess
import logging
from typing import Optional, Dict, List, Callable
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from .retry_decorator import retry
from .db import VideoDB
from .stringUtil import add_suffix_to_filename
from .sys import run_cli_command, get_video_duration, get_video_size, join_root_path
from .translate_srt import LLMTranslator, merge_srt_files as _merge_srt_files, translate_video_title
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
        return llm_client.chat_json(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
    except Exception as e:
        # 术语抽取失败不影响主流程，只是少了术语约束
        logging.error(f"LLM term extraction failed: {e}")
        return {}


def _maybe_translate_title(title: str, actual_subtitle_type: str) -> str:
    """中字/双语字幕时把英文标题翻译成中文。

    已经含中文、LLM 未配置、或任何异常，都原样返回（标题翻译失败不影响主流程）。
    """
    cleaned = re.sub(r'^(\[.*?\]\s*)+', '', title)
    if actual_subtitle_type not in ('cn', 'bilingual'):
        return cleaned
    if _CJK_PATTERN.search(cleaned):
        return cleaned  # 已经是中文标题
    try:
        cfg = LLMConfig()
        if not (cfg.enabled and cfg.api_key) or not cfg.feature_enabled('title_translation'):
            return cleaned
        print("正在翻译视频标题...")
        translated = translate_video_title(
            cleaned,
            LLMClient(cfg),
            glossary=_load_glossary(),
        )
        if translated and translated != cleaned:
            print(f"标题已翻译: {cleaned} -> {translated}")
            return translated
    except Exception as e:
        print(f"标题翻译失败，保留原标题: {e}")
    return cleaned


def _llm_enabled() -> bool:
    """config/_llm.json 里是否配好了可用的 LLM。"""
    try:
        cfg = LLMConfig()
        return bool(cfg.enabled and cfg.api_key)
    except Exception:
        return False


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
            cleaned_title = _maybe_translate_title(title, actual_subtitle_type)
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
            # 注意：临时文件必须保留 .mp4 之类可识别的扩展名，否则 ffmpeg 无法推断封装格式
            # （"Unable to choose an output format"）
            stem, ext = os.path.splitext(final_with_srt)
            temp_output = f"{stem}.tmp{ext}"
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
            # ffmpeg 失败，清除字幕类型前缀，回退到 [转]
            cleaned = re.sub(r'^(\[.*?\]\s*)+', '', title)
            title = f"[转] {cleaned}"
    else:
        # 没下载到字幕
        cleaned = re.sub(r'^(\[.*?\]\s*)+', '', title)
        title = f"[转] {cleaned}"
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
    """构造烧录字幕用的 ffmpeg 参数。

    优先自己把 SRT 转成 ASS（中英样式、字号、分辨率都可控），
    失败才回退到 ffmpeg 的 subtitles 滤镜。
    """
    try:
        ass_path = os.path.splitext(srt_path)[0] + '.ass'
        width, height = get_video_size(input_path)
        if not width or not height:
            width, height = 1920, 1080
        build_ass_from_srt(srt_path, ass_path, width, height)
        print(f"已生成 ASS 字幕: {ass_path} ({width}x{height})")
        vf = f"ass={_escape_ffmpeg_filter_path(ass_path)}"
        # 把仓库内置字体目录挂给 libass，避免机器上没装中文字体时渲染成方块
        fonts_dir = _bundled_fonts_dir()
        if fonts_dir:
            vf += f":fontsdir={_escape_ffmpeg_filter_path(fonts_dir)}"
        return [
            "-y",
            "-i", input_path,
            "-vf", vf,
            "-c:a", "copy",
            output_path
        ]
    except Exception as e:
        print(f"生成 ASS 字幕失败，回退 ffmpeg subtitles 滤镜: {e}")
        return [
            "-y",
            "-i", input_path,
            "-vf", f"subtitles={_escape_ffmpeg_filter_path(srt_path)}",
            "-c:a", "copy",
            output_path
        ]


# ---------------------------------------------------------------------------
# SRT -> ASS
#
# 不用 ffmpeg 的 SRT 转 ASS：它生成的样式固定为 PlayRes 384x288 + Arial 16，
# 烧到 1080p 上会被等比放大（字号约 60px），且中英同色同号，实际效果是字幕
# 铺满整屏。这里自己生成 ASS：分辨率取视频真实宽高，中文/英文分样式。
# ---------------------------------------------------------------------------

_CJK_PATTERN = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')

_ASS_HEADER = """[Script Info]
; Generated by y2b
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 0
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: CN,{cn_font},{cn_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,{cn_bold},0,0,0,100,100,0,0,1,{outline},{shadow},2,{margin_lr},{margin_lr},{margin_v},1
Style: EN,{en_font},{en_size},&H00DCDCDC,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{outline},{shadow},2,{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _subtitle_fonts() -> Dict[str, str]:
    """字幕字体：中文固定用仓库内置的 ukai.ttc（Windows/Docker 渲染一致），
    英文用系统无衬线字体。想换中文字体只需改这里的 cn 值。
    """
    return {
        'cn': 'AR PL UKai CN',
        'en': 'Arial' if sys.platform == 'win32' else 'DejaVu Sans',
    }


def _bundled_fonts_dir() -> str:
    """内置字体所在目录：有 static/ukai.ttc 时返回 static，用于 ass 滤镜的 fontsdir。"""
    try:
        static_dir = join_root_path('static')
        if os.path.exists(os.path.join(static_dir, 'ukai.ttc')):
            return static_dir
    except Exception as e:
        print(f"查找内置字体失败: {e}")
    return ''


def _escape_ffmpeg_filter_path(path: str) -> str:
    """转成可以安全放进 ffmpeg 滤镜参数（ass=/subtitles=）的路径。

    ffmpeg 的滤镜串会被解析两层：先用单引号把整段包住避免被当成滤镜分隔，
    再把冒号转义（Windows 盘符 C: 必须写成 'C\\:/...' ，否则会被当作滤镜选项分隔符）。
    """
    p = os.path.abspath(path).replace('\\', '/')
    p = p.replace("'", "\\'").replace(':', '\\:')
    return f"'{p}'"


def _parse_srt_file(srt_path: str) -> List[Dict]:
    """读取 SRT，返回 [{start, end, lines}]，时间单位秒。"""
    raw = None
    for enc in ('utf-8-sig', 'utf-8', 'gbk'):
        try:
            with open(srt_path, 'r', encoding=enc) as f:
                raw = f.read()
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        with open(srt_path, 'r', encoding='utf-8', errors='replace') as f:
            raw = f.read()

    # 去掉 BOM 和 nbsp（YouTube 字幕里常见），统一空白
    raw = raw.replace('\ufeff', '').replace('\u00a0', ' ')
    raw = re.sub(r'[ \t]+', ' ', raw)

    import srt as _srt
    cues = []
    for sub in _srt.parse(raw):
        lines = [ln.strip() for ln in sub.content.splitlines()]
        lines = [ln for ln in lines if ln]
        if not lines:
            continue
        cues.append({
            'start': sub.start.total_seconds(),
            'end': sub.end.total_seconds(),
            'lines': lines,
        })
    return cues


def _split_bilingual_lines(lines: List[str]) -> tuple:
    """把一条字幕的行拆成 (英文, 中文)。

    双语 SRT 的格式是「英文整句 + 中文整段」，这里按第一处 CJK 字符分界。
    """
    first_cjk = len(lines)
    for i, line in enumerate(lines):
        if _CJK_PATTERN.search(line):
            first_cjk = i
            break
    en_lines = [ln for ln in lines[:first_cjk] if not _CJK_PATTERN.search(ln)]
    cn_lines = [ln for ln in lines[first_cjk:] if _CJK_PATTERN.search(ln)]
    # 中段里夹带的纯英文行也并回中文侧（如 "KDE 桌面环境" 被断行）
    cn_lines += [ln for ln in lines[first_cjk:] if not _CJK_PATTERN.search(ln)]
    return ' '.join(en_lines).strip(), ' '.join(cn_lines).strip()


def _find_boundary(text: str, target: int, window: int = 16) -> int:
    """在 target 附近找最近的断句点（标点或空格），返回切分位置。"""
    if target <= 0:
        return 1
    if target >= len(text):
        return len(text)
    marks = '，。！？；：、,.!?;:'
    for offset in range(window + 1):
        for pos in (target + offset, target - offset):
            if 0 < pos < len(text):
                if text[pos] in marks:
                    return pos + 1
                if text[pos] == ' ':
                    return pos + 1
    return target


def _split_proportional(text: str, parts: int) -> List[str]:
    """把文本按长度近似均分成 parts 段，尽量在标点/空格处断开。"""
    text = (text or '').strip()
    if parts <= 1 or not text:
        return [text] if text else []
    pieces = []
    rest = text
    for i in range(parts - 1):
        target = int(round(len(rest) / (parts - i)))
        cut = _find_boundary(rest, target)
        piece = rest[:cut].strip()
        rest = rest[cut:].strip()
        if piece:
            pieces.append(piece)
        if not rest:
            break
    if rest:
        pieces.append(rest)
    return pieces


def _chunk_cue(en_text: str, cn_text: str, max_en: int, max_cn: int) -> List[tuple]:
    """把一条（可能很长的）字幕切成若干块，返回 [(英文, 中文, 权重)]。

    权重用于按长度比例重新分配时间轴，避免一条字幕挂 40 秒铺满整屏。
    max_en/max_cn 现在是单行字符限制，每块最多 2 行。
    """
    # 每块可以容纳约 2 行（中英各一行，或单语言 2 行）
    chars_per_chunk_en = max_en * 2
    chars_per_chunk_cn = max_cn * 2

    need = 1
    if en_text:
        need = max(need, math.ceil(len(en_text) / chars_per_chunk_en))
    if cn_text:
        need = max(need, math.ceil(len(cn_text) / chars_per_chunk_cn))

    en_parts = _split_proportional(en_text, need)
    cn_parts = _split_proportional(cn_text, need)

    chunks = []
    for i in range(max(len(en_parts), len(cn_parts))):
        e = en_parts[i] if i < len(en_parts) else ''
        c = cn_parts[i] if i < len(cn_parts) else ''
        if not e and not c:
            continue
        # 中文字符信息密度更高，权重按 1.6 折算
        chunks.append((e, c, max(1.0, len(e) + len(c) * 1.6)))
    return chunks


def _distribute_times(start: float, end: float, chunks: List[tuple]) -> List[tuple]:
    total = sum(w for _, _, w in chunks) or 1.0
    duration = max(0.2, end - start)
    t = start
    result = []
    for en, cn, weight in chunks:
        seg = duration * weight / total
        result.append((t, min(end, t + seg), en, cn))
        t += seg
    return result


def _ass_time(seconds: float) -> str:
    total_cs = max(0, int(round(seconds * 100)))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace('\\', '\\\\').replace('{', '\\{').replace('}', '\\}')


def _max_chars_per_chunk(width: int, font_size: int, cjk: bool) -> int:
    """按视频宽度估算单行字幕能放多少字符（保守估算，避免超屏）。"""
    usable = width * 0.85  # 更保守的可用宽度
    per_char = font_size if cjk else font_size * 0.55
    chars_per_line = int(usable / per_char)
    # 返回单行限制，chunk 函数内部会处理多行
    return max(6, chars_per_line)


def build_ass_from_srt(srt_path: str, ass_path: str, width: int, height: int) -> str:
    """把 SRT 转成带样式的 ASS，返回 ASS 路径。"""
    width = width or 1920
    height = height or 1080

    cn_size = max(18, int(round(height * 0.042)))
    en_size = max(14, int(round(height * 0.030)))
    margin_v = max(10, int(round(height * 0.045)))
    margin_lr = max(10, int(round(width * 0.05)))
    # ukai 是楷体、笔画偏细，描边略加粗保证在亮背景上也清晰
    outline = round(height * 0.0028, 1)
    shadow = round(height * 0.0009, 1)

    fonts = _subtitle_fonts()
    header = _ASS_HEADER.format(
        width=width, height=height,
        cn_font=fonts['cn'], cn_size=cn_size, cn_bold=-1,
        en_font=fonts['en'], en_size=en_size,
        outline=outline, shadow=shadow,
        margin_v=margin_v, margin_lr=margin_lr,
    )

    max_cn = _max_chars_per_chunk(width, cn_size, True)
    max_en = _max_chars_per_chunk(width, en_size, False)

    dialogue_lines = []
    cue_count = 0
    for cue in _parse_srt_file(srt_path):
        cue_count += 1
        en_text, cn_text = _split_bilingual_lines(cue['lines'])
        chunks = _chunk_cue(en_text, cn_text, max_en, max_cn)
        for start, end, en, cn in _distribute_times(cue['start'], cue['end'], chunks):
            parts = []
            if en:
                parts.append('{\\rEN}' + _ass_escape(en))
            if cn:
                parts.append('{\\rCN\\q2}' + _ass_escape(cn))  # \q2 强制智能折行
            if not parts:
                continue
            style = 'CN' if cn else 'EN'
            text = '\\N'.join(parts)
            dialogue_lines.append(
                f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},{style},,0,0,0,,{text}"
            )

    if not dialogue_lines:
        raise ValueError(f'字幕文件没有可用内容: {srt_path}')

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(header + "\n".join(dialogue_lines) + "\n")

    print(f"ASS 字幕生成完成: {cue_count} 条字幕 -> {len(dialogue_lines)} 条显示块")
    return ass_path


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

    # ---- 双语：优先用 LLM 翻译另一种语言（YouTube 自动翻译的中文质量很差）----
    if need_subtitle in ('bilingual', 'both'):
        if allow_translate and _llm_enabled():
            print('检测到 LLM 可用，双语字幕走模型翻译（跳过 YouTube 自动翻译的字幕）')
            try:
                return translate_and_merge(primary, make_bilingual=True, progress_callback=progress_callback)
            except Exception as e:
                print(f'LLM 翻译失败，回退下载另一语言字幕: {e}')

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
