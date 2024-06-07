import os
import uuid
import subprocess
from flask import Flask, g, request, redirect, url_for, render_template, jsonify, flash
from threading import Thread
from yt_dlp import YoutubeDL
import bilibili_api
from bilibili_api import sync, video_uploader, Credential
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from forms.download import YouTubeDownloadForm
from utils.string import clean_reship_url,cleaned_text, truncate_str
from utils.account import AccountUtil, get_youtube_info
from utils.constants import Route
from utils.sys import run_cli_command, clear_video_directory, find_cover_images
from utils.dict import pick
from utils.db import VideoDB

task_status = {}

def get_path(key):
    return f"{g.session['save_dir']}/{key}"

async def do_upload(task_id, db_vid):
    task = task_status[task_id]
    title = task['title']
    video_id = g.session['origin_id']
    
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
            print(f"尝试补充字幕 {video_id} {title}")
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
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

    db = VideoDB()
    db_update_args = {
        "title": title,
        "cover": cover,
        "save_srt": subtitles_path if need_subtitle else None
    }

    if not session['auto_upload']:
        # rename_completed_file(origin_video_path, '.unuploaded')
        db_update_args += {
            "status": "downloaded" # 只有非自动上传时才让列表页识别已下载状态
        }
        db.update_video(db_vid, **db_update_args)
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
        db_update_args["status"] = "uploaded"
        db.update_video(db_vid, **db_update_args)

    print("开始上传...");
    try:
        db.update_video(db_vid, status='uploading')
        await uploader.start()
    except bilibili_api.exceptions.NetworkException as e:
        flash("bilibili_api 403，请尝试更新cookie信息", "warning")
        return redirect(url_for(Route.LOGIN))
    except bilibili_api.exceptions.ResponseCodeException as e:
        print(e)
        flash("需要输入验证码了，请稍后再投稿", "warning")
        return redirect(url_for(Route.LOGIN))

def create_progress_hook(task_id):
    def hook(d):
        if d['status'] == 'finished':
            task_status[task_id]['status'] = 'running'
            task_status[task_id]['progress'] = '100%'
        elif d['status'] == 'downloading':
            task_status[task_id]['status'] = 'running'
            task_status[task_id]['progress'] = d['_percent_str']
        elif d['status'] == 'error':
            task_status[task_id]['status'] = 'error'
            task_status[task_id]['progress'] = 'ERR'
    return hook

def run_yt_dlp(url, ydl_opts, task_id, db_vid):
    with YoutubeDL(ydl_opts) as ydl:
        print("开始下载...")
        ydl.download([url])
    task_status[task_id]['status'] = 'completed'
    # rename_completed_file(task_status[task_id]['path'])
    do_upload(task_id, db_vid)

def download_controller(session):
    user = session['login_name']

    try:
        bili = AccountUtil(config_path="/root/move_video/bili_cookie.json")
        bili_cookies = bili.verify_cookie()
        print("bilibili 登录信息有效：%s" % bili_cookies['user_name'])
    except Exception as e:
        raise(e)

    args = {
        "sessdata": bili_cookies['SESSDATA'],
        "bili_jct": bili_cookies['bili_jct'],
        "buvid3": bili_cookies['buvid3']
    }
    form = YouTubeDownloadForm(**args)

    if form.validate_on_submit():
        
        subtitle_map = {
            'en': "en",
            'cn': "zh-Hans",
        }
        need_subtitle = request.form.get('need_subtitle')
        session['need_subtitle'] = need_subtitle

        video_url = clean_reship_url(request.form.get('video_url'))
        session['video_url'] = video_url

        info = get_youtube_info(video_url)
        video_id = info["id"]
        session['origin_title'] = info["title"]
        session['origin_id'] = video_id
        session['origin_file_size'] = info["file_size"]
        print("获取了视频标题等...", info)

        session['resolution'] = request.form.get('resolution')
        session['SESSDATA'] = request.form.get('sessdata')
        session['bili_jct'] = request.form.get('bili_jct')
        session['buvid3'] = request.form.get('buvid3')
        session['auto_upload'] = request.form.get('auto_upload')
        session['tid'] = request.form.get('tid')
        session['tags'] = request.form.get('tags')

        task_id = str(uuid.uuid4())
        session['save_video'] = f"{video_id}.{session['resolution']}.mp4"
        # session['save_video'] = f"{video_id}.{session['resolution']}.tmp.mp4"
        session['save_srt_en'] = f"{video_id}.en.srt"
        session['save_srt_cn'] = f"{video_id}.zh-Hans.srt"
        save_path = os.path.join(session['save_dir'], session['save_video'])
        opts = {
            'writesubtitles': bool(need_subtitle), 
            'subtitleslangs': [subtitle_map.get(need_subtitle, '')], 
            'writesubtitlesformat': 'srt' if need_subtitle else None, 
            'writethumbnail': True,     
            'outtmpl': save_path, 
            'format': f"bv*[height<={session['resolution']}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            'progress_hooks': [create_progress_hook(task_id)],
        }
        task_status[task_id] = {
            'status': 'running', 
            'progress': '', 
            'id': video_id,
            'title': session['origin_title'],
            'path': save_path
        }

        db = VideoDB()
        db_vid = db.create_video(
            user = user,
            origin_id = video_id,
            origin_url = video_url, 
            save_path = save_path, 
            title = info["title"]
        )

        print('准备下载', task_id, '\n', opts)
        db.update_video(db_vid, status='downloading')
        thread = Thread(target=run_yt_dlp, args=(video_url, opts, task_id, db_vid))
        thread.start()

        return redirect(url_for(Route.LIST))
        
    return render_template('download2.html', form=form)