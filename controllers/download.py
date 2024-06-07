import os
import uuid
from flask import Flask, request, redirect, url_for, render_template, jsonify
from threading import Thread
from yt_dlp import YoutubeDL
from utils.string import clean_reship_url
from utils.account import AccountUtil, get_youtube_info
from forms.download import YouTubeDownloadForm
from utils.sys import run_cli_command, clear_video_directory

def download_controller(session):
    user = session['login_name']
    session['save_dir_rel'] = f"video/{user}"
    session['save_dir'] = f"/root/move_video/static/{session['save_dir_rel']}"
    session['save_video'] = 'video.mp4'
    session['save_srt_en'] = 'video.en.srt'
    session['save_srt_cn'] = 'video.zh-Hans.srt'

    try:
        bili = AccountUtil(config_path="/root/move_video/bili_cookie.json")
        bili_cookies = bili.verify_cookie()
        # for key, value in bili_cookies.items():
        #     session[key] = value
        print("bilibili 登录信息有效：%s" % bili_cookies['user_name'])
    except Exception as e:
        raise(e)

    args = {
        "sessdata": bili_cookies['SESSDATA'],
        "bili_jct": bili_cookies['bili_jct'],
        "buvid3": bili_cookies['buvid3']
    }
    form = YouTubeDownloadForm(**args)

    # if form.validate_on_submit():
    #     video_url = clean_reship_url(form.video_url.data)
    #     resolution = form.resolution.data

    #     session['video_url'] = video_url
    #     session['resolution'] = resolution
    #     session['SESSDATA'] = form.sessdata.data
    #     session['bili_jct'] = form.bili_jct.data
    #     session['buvid3'] = form.buvid3.data
    #     session['need_subtitle'] = form.need_subtitle.data

    #     # TODO threading 进度条

    #     clear_video_directory(session['save_dir'])

    #     print(user, "获取视频标题...")
    #     session['origin_title'] = get_youtube_info(video_url)["title"]

    #     subtitle_map = {
    #         'en': ["--write-auto-subs", "--sub-langs", "en", "--convert-subs", "srt"],
    #         'cn': ["--write-auto-subs", "--sub-langs", "zh-Hans", "--convert-subs", "srt"]
    #     }
    #     cli_args = subtitle_map.get(session['need_subtitle'], []) + [
    #         "--write-thumbnail",
    #         "-P", f"{session['save_dir']}",
    #         "-f", f"bv*[height<={resolution}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
    #         "-o", session['save_video'],
    #         video_url
    #     ]
    #     print("开始下载...", session['origin_title'], cli_args);
    #     run_cli_command('yt-dlp', cli_args)

    #     return redirect(url_for('preview'))  
        
    return render_template('download.html', form=form)

task_status = {}

def create_progress_hook(task_id):
    # https://github.com/yt-dlp/yt-dlp/blob/2e5a47da400b645aadbda6afd1156bd89c744f48/yt_dlp/YoutubeDL.py#L363
    # https://github.com/yt-dlp/yt-dlp/blob/2e5a47da400b645aadbda6afd1156bd89c744f48/yt_dlp/downloader/common.py#L362
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

def run_yt_dlp(url, ydl_opts, task_id):
    with YoutubeDL(ydl_opts) as ydl:
        print("开始下载...")
        ydl.download([url])
    task_status[task_id]['status'] = 'completed'
    task_status[task_id]['progress'] = '100%'

def download_status_ajax(task_id):
    if task_id in task_status:
        return jsonify(task_status[task_id])
    else:
        return jsonify({'status': 'not_found'}), 404

def download_video_ajax(session):
    clear_video_directory(session['save_dir'])

    subtitle_map = {
        'en': "en",
        'cn': "zh-Hans",
    }
    need_subtitle = request.form.get('need_subtitle')

    resolution = request.form.get('resolution')
    video_url = clean_reship_url(request.form.get('video_url'))

    info = get_youtube_info(video_url)
    session['origin_title'] = info["title"]
    session['origin_id'] = info["id"]
    session['origin_file_size'] = info["file_size"]
    print("获取了视频标题等...", info)

    session['video_url'] = video_url
    session['resolution'] = resolution
    session['SESSDATA'] = request.form.get('sessdata')
    session['bili_jct'] = request.form.get('bili_jct')
    session['buvid3'] = request.form.get('buvid3')
    session['need_subtitle'] = need_subtitle
    session['auto_upload'] = request.form.get('auto_upload')

    task_id = str(uuid.uuid4())
    task_status[task_id] = {'status': 'running', 'progress': '', 'title': session['origin_title']}
    progress_hook = create_progress_hook(task_id)

    opts = {
        'writesubtitles': bool(need_subtitle), 
        'subtitleslangs': [subtitle_map.get(need_subtitle, '')], 
        'writesubtitlesformat': 'srt' if need_subtitle else None, 
        'writethumbnail': True,     
        'outtmpl': os.path.join(session['save_dir'], session['save_video']), 
        'format': f"bv*[height<={resolution}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
        'progress_hooks': [progress_hook],
    }
    print('准备下载', task_id, '\n', opts)
    thread = Thread(target=run_yt_dlp, args=(video_url, opts, task_id))
    thread.start()

    return jsonify({'task_id': task_id}), 202