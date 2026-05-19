import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
from common import setup_path, cli_progress, cli_progress_done

setup_path()

from utils.subtitle import add_subtitle, download_subtitles
from utils.db import VideoDB
from utils.constants import VideoStatus


def main():
    parser = argparse.ArgumentParser(description='为视频添加字幕（下载+翻译+嵌入）')
    parser.add_argument('video_id', help='数据库记录 ID（由 download.py 输出）')
    args = parser.parse_args()

    video_id = args.video_id
    lang = 'bilingual'

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
