import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
from urllib.parse import urlparse, parse_qs
from common import setup_path, cli_progress, cli_progress_done, default_save_dir

setup_path()

from utils.subtitle import add_subtitle, retryable_download, translate_and_merge
from utils.db import VideoDB
from utils.constants import VideoStatus


def extract_youtube_id(url_or_id: str) -> str:
    """从 YouTube URL 或裸 ID 中解析出 11 位视频 ID。"""
    # 已经是裸 ID
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', url_or_id):
        return url_or_id
    parsed = urlparse(url_or_id)
    # https://www.youtube.com/watch?v=ID
    qs = parse_qs(parsed.query)
    if 'v' in qs and qs['v']:
        return qs['v'][0]
    # https://youtu.be/ID 或 /shorts/ID 或 /embed/ID
    m = re.search(r'/(?:shorts|embed)/([A-Za-z0-9_-]{11})', parsed.path)
    if m:
        return m.group(1)
    m = re.search(r'/([A-Za-z0-9_-]{11})$', parsed.path)
    if m:
        return m.group(1)
    raise ValueError(f"无法从输入解析出 YouTube 视频 ID: {url_or_id}")


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"{prompt} [已通过 --yes 自动确认]")
        return True
    try:
        ans = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        # 非交互环境（无法询问）默认不翻译
        return False
    return ans in ('y', 'yes')


def download_only(orig_id: str, lang: str, save_dir: str, assume_yes: bool = False):
    """仅下载字幕：优先走下载方式，多试几个来源；下载不到目标语言时
    先提示用户，用户允许后才用本地模型翻译。不嵌入视频。
    """
    subtitle_map = {'en': 'en', 'cn': 'zh-Hans', 'bilingual': 'en'}
    subtitle_locale = subtitle_map.get(lang, 'en')
    os.makedirs(save_dir, exist_ok=True)
    save_srt = os.path.join(save_dir, f"{orig_id}.{subtitle_locale}.srt")

    print(f"视频 ID: {orig_id}")
    print(f"字幕类型: {lang}")
    print(f"保存目录: {save_dir}")

    # allow_translate=False：只“下载”，需要翻译时返回 need_translate 让 CLI 决定
    result = retryable_download(orig_id, save_srt, lang, cli_progress, allow_translate=False)
    cli_progress_done()

    if not result:
        print("\n字幕下载失败：已尝试 YouTubeTranscriptApi、yt-dlp、youtube-dl 等多种方式仍未获取到字幕。")
        return

    # 需要翻译才能满足目标语言 —— 询问用户是否允许用模型翻译
    if result.get('need_translate'):
        got = result.get('code') or result.get('lang')
        target = result.get('target')
        make_bilingual = result.get('make_bilingual', False)
        print(f"\n已下载到字幕：{result['path']}（语言: {got}）")
        if make_bilingual:
            print(f"未能直接下载到中文字幕，无法凑成双语。")
            question = "是否使用本地模型翻译出中文并合并为双语字幕？"
        else:
            print(f"未能直接下载到目标语言({target})的字幕。")
            question = f"是否使用本地模型翻译为 {target}？"

        if not _confirm(question, assume_yes):
            print("已跳过翻译，仅保留已下载的字幕。")
            print(f"\n完成!")
            print(f"字幕语言: {result['lang']}")
            print(f"字幕文件: {result['path']}")
            return

        result = translate_and_merge(result, make_bilingual=make_bilingual, progress_callback=cli_progress)
        cli_progress_done()

    print(f"\n完成!")
    print(f"字幕语言: {result['lang']}")
    print(f"字幕文件: {result['path']}")


def main():
    parser = argparse.ArgumentParser(description='为视频添加字幕（下载+翻译+嵌入），或仅下载字幕')
    parser.add_argument('video_id', nargs='?', help='数据库记录 ID（由 download.py 输出）')
    parser.add_argument('--url', help='YouTube 视频 URL 或视频 ID，直接下载字幕（无需数据库记录）')
    parser.add_argument('-d', '--download-only', action='store_true', help='仅下载字幕，不嵌入视频')
    parser.add_argument('--lang', choices=['en', 'cn', 'bilingual'], default='bilingual', help='字幕类型（默认 bilingual）')
    parser.add_argument('--output', help='字幕保存目录（仅 --url 模式，默认使用日期目录）')
    parser.add_argument('-y', '--yes', action='store_true', help='下载不到目标语言时，自动允许使用模型翻译（不再询问）')
    args = parser.parse_args()

    lang = args.lang

    # --url 模式：不需要数据库记录，直接下载字幕
    if args.url:
        orig_id = extract_youtube_id(args.url)
        save_dir = args.output or default_save_dir()
        download_only(orig_id, lang, save_dir, assume_yes=args.yes)
        return

    if not args.video_id:
        parser.error('需要提供 video_id，或使用 --url 指定 YouTube 链接')

    video_id = args.video_id

    db = VideoDB()
    record = db.read_video(video_id)
    if not record:
        print(f"错误: 找不到 video_id={video_id} 的记录")
        return

    orig_id = record['origin_id']
    title = record['title']
    video_path = record['save_path']

    if not os.path.exists(video_path):
        print(f"错误: 视频文件不存在 {video_path}")
        return

    save_dir = os.path.dirname(video_path)

    # 仅下载字幕：直接调用下载逻辑，不嵌入视频
    if args.download_only:
        download_only(orig_id, lang, save_dir, assume_yes=args.yes)
        return

    subtitle_map = {'en': 'en', 'cn': 'zh-Hans', 'bilingual': 'en'}
    subtitle_locale = subtitle_map.get(lang, 'en')
    save_srt = os.path.join(save_dir, f"{orig_id}.{subtitle_locale}.srt")

    db.update_video(video_id, subtitle_lang=lang, save_srt=save_srt)
    record = db.read_video(video_id)

    print(f"视频: {title} ({orig_id})")
    print(f"字幕类型: {lang}")

    def progress_cb(percent, message):
        cli_progress(percent, message)

    result = add_subtitle(
        record=record,
        orig_id=orig_id,
        title=title,
        video_path=video_path,
        origin_video_path=video_path,
        progress_callback=progress_cb
    )
    cli_progress_done()

    new_title = result['title']
    new_video_path = result['video_path']
    subtitles_path = result.get('subtitles_path', '')

    update_args = {'title': new_title, 'save_srt': subtitles_path}
    if new_video_path != video_path:
        update_args['save_path'] = new_video_path
    db.update_video(video_id, **update_args)

    print(f"\n完成!")
    print(f"标题: {new_title}")
    print(f"视频: {new_video_path}")
    if subtitles_path:
        print(f"字幕: {subtitles_path}")


if __name__ == '__main__':
    main()
