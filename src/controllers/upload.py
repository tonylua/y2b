import os
import sys
import platform
import subprocess
from flask import Flask, request, redirect, url_for, flash
import yt_dlp
import bilibili_api
from bilibili_api import video_uploader, Credential, request_settings
from bilibili_api.video_uploader import VideoUploaderEvents
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from utils.stringUtil import cleaned_text, truncate_str, add_suffix_to_filename, abs_to_rel
from utils.constants import Route, VideoStatus
from utils.sys import run_cli_command, find_cover_images, join_root_path
from utils.dict import pick
from utils.db import VideoDB
from utils.account import AccountUtil
from utils.subtitle import add_subtitle

def get_path(session, key):
    return f"{session['save_dir']}/{key}"

async def do_upload(session, video_id):
    db = VideoDB()
    record = db.read_video(video_id)
    title = record['title']
    orig_id = record['origin_id']
    origin_video_path = record['save_path'] 
    video_path = origin_video_path
    subtitles_path = ''
    architecture = platform.machine()
    # runInPI = architecture in ['aarch64', 'arm64']

    print(f"准备上传 {video_id} {title}")

    if session['need_subtitle']:
        subtitle_result = add_subtitle(
            record=record,
            orig_id=orig_id,
            title=title,
            video_path=video_path,
            origin_video_path=origin_video_path
        ) 
        title = subtitle_result['title']
        video_path = subtitle_result['video_path']
        subtitles_path = subtitle_result['subtitles_path']

    title = truncate_str(cleaned_text(title), 77)

    save_dir, _ = os.path.split(video_path)
    cover = find_cover_images(save_dir, orig_id)
    if not cover:
        raise FileNotFoundError('封面不存在', record['origin_id'])

    db_update_args = {
        "title": title,
        "save_cover": cover,
        "save_srt": subtitles_path
    }

    if not session['auto_upload']:
        db_update_args.update({
            "status": VideoStatus.DOWNLOADED # 只有非自动上传时才让列表页识别已下载状态
        })
        print("not need auto_upload", db_update_args)
        db.update_video(video_id, **db_update_args)
        return True, None

    args = {
        "sessdata": session['SESSDATA'],
        "bili_jct": session['bili_jct'],
        "buvid3": session['buvid3']
    }
    credential = Credential(**args)

    desc = f"via. {record['origin_url']}"
    # TODO 默认值前置到存储阶段
    tid = record['tid'] if record['tid'] else 231
    # TODO 默认值前置到存储阶段
    tags = record['tags'].split(',') if record['tags'] and len(record['tags']) else ['youtube']
    vu_data = {
        'tid': tid,
        'original': True,  # TODO 设置转载报错
        'source': 'youtube',
        'no_reprint': True,
        'title': title,
        'tags': tags,
        'desc': desc,
        'cover': cover
    }
    vu_meta = video_uploader.VideoMeta(**vu_data)
    page = video_uploader.VideoUploaderPage(
        path = video_path,
        title = title,
        description = desc
    )
    uploader = video_uploader.VideoUploader([page], vu_meta, credential)
    # request_settings.set_proxy("http://127.0.0.1:10808")

    @uploader.on("__ALL__")
    async def ev(data, args = db_update_args):
        if data['name'] == VideoUploaderEvents.COMPLETED.value:
            args.update(pick(vu_data, ["desc", "tid", "tags"]))
            args["status"] = VideoStatus.UPLOADED
            db.update_video(video_id, **args)
            print('上传完成', data)
        if data['name'] == VideoUploaderEvents.FAILED.value:
            args["status"] = VideoStatus.ERROR
            db.update_video(video_id, **args)
            print('上传失败', data)
        else:
            print('上传中', data)

    print("开始上传...");
    try:
        db.update_video(video_id, status=VideoStatus.UPLOADING)
        await uploader.start()
    except bilibili_api.exceptions.NetworkException as e:
        msg = "bilibili_api 403，请尝试更新cookie信息"
        return False, msg
    except bilibili_api.exceptions.ResponseCodeException as e:
        msg = "需要输入验证码了，请稍后再投稿"
        return False, msg
    return True, None

async def upload_controller(session):
    session['auto_upload'] = '1' 
    try:
        bili = AccountUtil(config_path=join_root_path("config/bili_cookie.json"))
        bili_cookies = bili.verify_cookie()
        session.update(pick(bili_cookies, ["SESSDATA", "bili_jct", "buvid3"]))
    except Exception as e:
        raise(e)
    video_id = request.form.get('video_id')
    is_succ, msg = await do_upload(session, video_id)
    if not is_succ:
        flash(msg, 'warning')
        return redirect(url_for(Route.LOGIN))
    return redirect(url_for(Route.LIST))
