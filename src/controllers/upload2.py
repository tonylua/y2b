import os
import subprocess
from flask import Flask, g, request, redirect, url_for, flash
import bilibili_api
from bilibili_api import video_uploader, Credential
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from utils.string import cleaned_text, truncate_str
from utils.constants import Route, VideoStatus
from utils.sys import run_cli_command, find_cover_images
from utils.dict import pick
from utils.db import VideoDB


def get_path(key):
    return f"{g.session['save_dir']}/{key}"

async def do_upload(video_id):
    db = VideoDB()

    # task = task_status[task_id]
    # title = task['title']
     
    record = db.read_video(video_id)
    title = record['title']
    orig_id = g.session['origin_id']
    
    origin_video_path = get_path(session_item["save_video"])

    need_subtitle = session_item['need_subtitle']
    subtitle_title_map = {
        'en': '英字',
        'cn': '中字'
    }
    if (need_subtitle):
        subtitles_path = get_path(session_item["save_srt_{need_subtitle}"])
        subtitles_exist = os.path.exists(subtitles_path)

        if not subtitles_exist:
            print(f"尝试补充字幕 {orig_id} {title}")
            transcript_list = YouTubeTranscriptApi.list_transcripts(orig_id)
            transcript = transcript_list.find_transcript(['en'])
            if need_subtitle == 'cn':
                transcript = transcript.translate('zh-Hans')
            formatter = SRTFormatter()
            srt_formatted = formatter.format_transcript(transcript.fetch())
            with open(subtitles_path, 'w', encoding='utf-8') as srt_file:
                srt_file.write(srt_formatted)
            print(f"补充了字幕 {subtitles_path}")
            subtitles_exist = os.path.exists(subtitles_path)

        if (subtitles_exist):
            video_path = get_path(f"with_srt_{session['save_video']}")
            title = f"[{subtitle_title_map.get(need_subtitle, '转')}] {title}"
            
            ff_args = [
                "-i", origin_video_path,
                "-vf",
                f"subtitles={subtitles_path}",
                "-c:a",
                "copy",
                video_path
            ]
            if (need_subtitle == 'cn'):
                ff_args = ff_args[:3] + [f"colorspace=bt709,subtitles={subtitles_path}:force_style='FontName=AR PL UKai CN'"] + ff_args[4:]
            print("加字幕...", title, subtitles_path, ff_args)
            try:
                run_cli_command('ffmpeg', ff_args)
            except (Exception, subprocess.CalledProcessError) as e:
                print('ffmpeg 加字幕过程报错', e)
        else:
            print("设置了字幕但没下载到...", title)
            need_subtitle = False
            title = f"[转] {title}"
    title = truncate_str(cleaned_text(title), 77)

    cover = find_cover_images(g.session['save_dir'])
    if not cover:
        raise FileNotFoundError('封面不存在', g.session['origin_id'])

    db_update_args = {
        "title": title,
        "cover": cover,
        "save_srt": subtitles_path if need_subtitle else None
    }

    if not session['auto_upload']:
        # rename_completed_file(origin_video_path, '.unuploaded')
        db_update_args += {
            "status": VideoStatus.DOWNLOADED # 只有非自动上传时才让列表页识别已下载状态
        }
        db.update_video(video_id, **db_update_args)
        return redirect(url_for(Route.LIST))

    args = {
        "sessdata": g.session['SESSDATA'],
        "bili_jct": g.session['bili_jct'],
        "buvid3": g.session['buvid3']
    }
    credential = Credential(**args)
    desc = f"via. {g.session['video_url']}"
    vu_data = {
        'tid': g.session['tid'],
        'original': True,  # TODO 设置转载报错
        'source': 'youtube',
        'no_reprint': True,
        'title': title,
        'tags': g.session['tags'],
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
    async def ev(data):
        print('上传完成', data)
        db_update_args += pick(vu_data, ["desc", "tid", "tags"])
        db_update_args["status"] = VideoStatus.UPLOADED
        db.update_video(video_id, **db_update_args)

    print("开始上传...");
    try:
        db.update_video(video_id, status=VideoStatus.UPLOADING)
        await uploader.start()
    except bilibili_api.exceptions.NetworkException as e:
        flash("bilibili_api 403，请尝试更新cookie信息", "warning")
        return redirect(url_for(Route.LOGIN))
    except bilibili_api.exceptions.ResponseCodeException as e:
        print(e)
        flash("需要输入验证码了，请稍后再投稿", "warning")
        return redirect(url_for(Route.LOGIN))

async def upload_controller(session):
    video_id = request.form.get('video_id')
    await do_upload(video_id)
    return redirect(url_for(Route.LIST))