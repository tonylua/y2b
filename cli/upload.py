import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import argparse
import bilibili_api
from bilibili_api import video_uploader, Credential
from bilibili_api.video_uploader import VideoUploaderEvents
from common import setup_path, load_bili_cookies, cli_progress, cli_progress_done

setup_path()

from utils.db import VideoDB
from utils.constants import VideoStatus
from utils.stringUtil import sanitize_title_for_bilibili, cleaned_text
from utils.sys import find_cover_images, extract_cover_from_video


async def do_cli_upload(record, cookies):
    video_id = record['id']
    title = record['title']
    orig_id = record['origin_id']
    video_path = record['save_path']

    title = sanitize_title_for_bilibili(cleaned_text(title), max_len=80)

    save_dir = os.path.dirname(video_path)
    cover = find_cover_images(save_dir, orig_id)
    if not cover:
        cover_path = os.path.join(save_dir, f"{orig_id}.jpg")
        if extract_cover_from_video(video_path, cover_path):
            cover = cover_path
        else:
            print("错误: 找不到封面且无法从视频提取")
            return False

    credential = Credential(
        sessdata=cookies['SESSDATA'],
        bili_jct=cookies['bili_jct'],
        buvid3=cookies['buvid3']
    )

    origin_name = record.get('origin_title') or record.get('title') or ''
    desc = f"via. {record['origin_url']} | {origin_name}"
    tid = record['tid'] if record.get('tid') else 231
    tags = record['tags'].split(',') if record.get('tags') else ['youtube']

    meta = video_uploader.VideoMeta(
        tid=tid,
        original=True,
        source='youtube',
        no_reprint=True,
        title=title,
        tags=tags,
        desc=desc,
        cover=cover
    )
    page = video_uploader.VideoUploaderPage(
        path=video_path,
        title=title,
        description=desc
    )
    uploader = video_uploader.VideoUploader([page], meta, credential)

    db = VideoDB()
    success = False

    @uploader.on("__ALL__")
    async def ev(data):
        nonlocal success
        if data['name'] == VideoUploaderEvents.COMPLETED.value:
            success = True
            cli_progress(100, '上传完成')
            cli_progress_done()
            db.update_video(video_id, status=VideoStatus.UPLOADED, title=title, desc=desc, tid=tid, tags=tags)
        elif data['name'] == VideoUploaderEvents.FAILED.value:
            db.update_video(video_id, status=VideoStatus.ERROR)
            cli_progress_done()
            err_data = data.get('data', ())
            if err_data and len(err_data) > 0:
                print(f"\n上传失败: {err_data[0]}")
            else:
                print("\n上传失败")
        elif data['name'] == 'UPLOAD':
            progress = data.get('data', {}).get('p', 0)
            cli_progress(progress, f'上传中 {progress}%')

    db.update_video(video_id, status=VideoStatus.UPLOADING)
    print("开始上传...")

    try:
        await uploader.start()
    except bilibili_api.exceptions.NetworkException:
        print("\nbilibili_api 403，请更新 cookie 信息")
        db.update_video(video_id, status=VideoStatus.ERROR)
        return False
    except bilibili_api.exceptions.ResponseCodeException:
        print("\n需要输入验证码，请稍后再投稿")
        db.update_video(video_id, status=VideoStatus.ERROR)
        return False

    return success


def main():
    parser = argparse.ArgumentParser(description='上传视频到 Bilibili')
    parser.add_argument('video_id', help='数据库记录 ID')
    args = parser.parse_args()

    video_id = args.video_id

    db = VideoDB()
    record = db.read_video(video_id)
    if not record:
        print(f"错误: 找不到 video_id={video_id} 的记录")
        return

    video_path = record['save_path']
    if not os.path.exists(video_path):
        print(f"错误: 视频文件不存在 {video_path}")
        return

    print(f"视频: {record['title']}")
    print(f"文件: {video_path}")

    print("验证 Bilibili cookie...")
    cookies = load_bili_cookies()
    print(f"登录用户: {cookies.get('user_name', 'unknown')}")

    success = asyncio.run(do_cli_upload(record, cookies))
    if success:
        print("\n上传成功!")


if __name__ == '__main__':
    main()
