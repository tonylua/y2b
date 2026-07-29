import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
from yt_dlp import YoutubeDL
from common import setup_path, get_project_root, cli_progress, cli_progress_done, default_save_dir

setup_path()

from utils.account import get_youtube_info, base_ydl_opts
from utils.stringUtil import sanitize_title, sanitize_filename, clean_reship_url
from utils.db import VideoDB
from utils.constants import VideoStatus


def main():
    parser = argparse.ArgumentParser(description='下载 YouTube 视频')
    parser.add_argument('url', help='YouTube 视频 URL')
    args = parser.parse_args()

    # 与 src/index.py 一致：追新 yt-dlp 以躲避 YouTube bot 检测。
    # upgrade_yt_dlp 自带每日节流（.yt-dlp-last-check），不会每次都跑网络。
    try:
        from upgrade_yt_dlp import main as upgrade_yt_dlp_main
        print("正在检查 yt-dlp 版本...")
        upgrade_yt_dlp_main()
    except Exception as e:
        print(f"yt-dlp 升级检查失败: {e}")

    url = clean_reship_url(args.url)
    resolution = '1080'
    user = 'cli'

    print(f"正在获取视频信息: {url}")
    info = get_youtube_info(url)
    orig_id = info['id']
    title = sanitize_title(info.get('title', ''))
    file_size = info.get('file_size', 0)
    print(f"视频: {title} ({orig_id})")
    if file_size:
        print(f"预估大小: {file_size / 1024 / 1024:.1f} MB")

    save_dir = default_save_dir()
    # 以正式标题命名，视频 id 作为方括号后缀附加（保留 id 便于封面匹配与查重）。
    # 仅当「标题 + id 后缀」总长仍在 max_len 内时才附加 id，否则只用标题。
    max_len = 80
    safe_title = sanitize_filename(info.get('title', ''), max_len=max_len)
    suffix = f" [{orig_id}]"
    if len(safe_title) + len(suffix) <= max_len:
        base_name = f"{safe_title}{suffix}"
    else:
        base_name = safe_title
    final_save_path = os.path.join(save_dir, f"{base_name}.{resolution}.mp4")
    temp_save_path = os.path.join(save_dir, f"{base_name}.{resolution}.tmp.mp4")

    if os.path.exists(final_save_path):
        print(f"文件已存在，跳过下载: {final_save_path}")
    else:
        def progress_hook(d):
            status = d.get('status')
            if status == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                percent = int(downloaded * 100 / total) if total else 0
                cli_progress(percent, f"下载中... {downloaded // 1024 // 1024}MB")
            elif status == 'finished':
                cli_progress(100, '下载完成')
                cli_progress_done()

        opts = {
            **base_ydl_opts(),
            'outtmpl': temp_save_path,
            'format': f"bv*[height<={resolution}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            'continuedl': True,
            'retries': 10,
            'fragment_retries': 10,
            'writethumbnail': True,
            'progress_hooks': [progress_hook],
        }

        print("开始下载...")
        with YoutubeDL(opts) as ydl:
            ydl.download([url])

        if os.path.exists(temp_save_path):
            os.rename(temp_save_path, final_save_path)
        else:
            print(f"错误: 临时文件不存在 {temp_save_path}")
            return

    db = VideoDB()
    existing = db.query_video_by_origin_id(user, orig_id)
    if existing:
        video_id = existing['id']
        db.update_video(video_id, save_path=final_save_path, status=VideoStatus.DOWNLOADED)
    else:
        video_id = db.create_video(
            user=user,
            origin_id=orig_id,
            origin_url=url,
            save_path=final_save_path,
            save_srt='',
            title=title,
            subtitle_lang=''
        )
        db.update_video(video_id, status=VideoStatus.DOWNLOADED)

    print(f"\n完成! video_id={video_id}")
    print(f"文件: {final_save_path}")


if __name__ == '__main__':
    main()
