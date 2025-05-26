import os
import sys
import platform
import subprocess
from flask import Flask, request, redirect, url_for, flash
import bilibili_api
import yt_dlp
from bilibili_api import video_uploader, Credential
from bilibili_api.video_uploader import VideoUploaderEvents
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from utils.stringUtil import cleaned_text, truncate_str, add_suffix_to_filename, abs_to_rel
from utils.constants import Route, VideoStatus
from utils.sys import run_cli_command, find_cover_images, join_root_path
from utils.dict import pick
from utils.db import VideoDB
from utils.account import AccountUtil
from utils.subtitle import download_subtitles

def get_path(session, key):
    return f"{session['save_dir']}/{key}"

async def do_upload(session, video_id):
    db = VideoDB()
    record = db.read_video(video_id)
    title = record['title']
    orig_id = record['origin_id']
    origin_video_path = record['save_path'] 
    video_path = origin_video_path

    architecture = platform.machine()
    # runInPI = architecture in ['aarch64', 'arm64']

    print(f"准备上传 {video_id} {title}")

    # TODO srt字幕直接上传 https://github.com/Nemo2011/bilibili-api/issues/748
    need_subtitle = record['subtitle_lang']
    subtitle_title_map = {
        'en': '英字',
        'cn': '中字'
    }
    subtitles_path = '' 
    if (need_subtitle):
        subtitles_path = record['save_srt'] 
        subtitles_exist = subtitles_path and os.path.exists(subtitles_path)
        has_subtitle = False

        if subtitles_path and not subtitles_exist:
            print(f"尝试补充字幕 {orig_id} {title}")
            transcript_list = YouTubeTranscriptApi.list_transcripts(orig_id)

            # TODO 字幕语言识别不准确
            has_subtitle = download_subtitles(orig_id, subtitles_path, need_subtitle)
            if isinstance(has_subtitle, str):
                need_subtitle = 'en' if has_subtitle == 'en' else 'cn'

            subtitles_exist = os.path.exists(subtitles_path)
            print(f"下载了字幕 {subtitles_path}", subtitles_exist)

        if (subtitles_exist):
            try:
                title_prefix = subtitle_title_map.get(need_subtitle, '转') if bool(has_subtitle) else '转'
                title = f"[{title_prefix}] {title.replace(r'^\[.*?]\s*', '')}"
                video_path = add_suffix_to_filename(video_path, 'with_srt') 
                
                if sys.platform == 'win32':
                    input_path = abs_to_rel(origin_video_path, 3)
                    srt_path = abs_to_rel(subtitles_path, 3)
                    ass_path = srt_path[:-4] + '.ass' 
                    output_path = abs_to_rel(video_path, 3)

                    run_cli_command('ffmpeg', ['-i', srt_path, ass_path])
                    print('🐏', origin_video_path, input_path, subtitles_path, ass_path, video_path, output_path)

                    ff_args: List[str] = [
                        "-i", input_path,
                        "-vf", f"ass={ass_path}",
                        output_path
                    ]
                else:
                    ff_args = [
                        "-i", origin_video_path,
                        "-vf",
                        f"subtitles={subtitles_path}",
                        "-c:a",
                        "copy",
                        video_path
                    ]
                    if (need_subtitle == 'cn'):
                        font_args = f"colorspace=bt709,subtitles={subtitles_path}:force_style='FontName=AR PL UKai CN'"
                        font_args = f"colorspace=bt709,subtitles={subtitles_path}{font_name}'"
                        ff_args = ff_args[:3] + [font_args] + ff_args[4:]

                print("加字幕...", title, subtitles_path, ff_args)
                run_cli_command('ffmpeg', ff_args)
            except (Exception, subprocess.CalledProcessError) as e:
                print('ffmpeg 加字幕过程报错', e)
        else:
            print("设置了字幕但没下载到...", title)
            need_subtitle = False
            title = f"[转] {title}"
    title = truncate_str(cleaned_text(title), 77)

    save_dir, _ = os.path.split(video_path)
    cover = find_cover_images(save_dir)
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
