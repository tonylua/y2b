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
    def hook(d):
        print(d['status'], '_percent_str' in d, "+++++++")
        if d['status'] == 'finished':
            task_status[task_id]['status'] = 'completed'
            task_status[task_id]['progress'] = 1
        elif d['status'] == 'downloading':
            task_status[task_id]['status'] = 'running'
            task_status[task_id]['progress'] = d['_percent_str']
    return hook

def run_yt_dlp(url, ydl_opts, task_id):
    with YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        title = info_dict.get('title', None)
        file_size = info_dict.get('filesize_approx', 0)
        task_status[task_id] = {'status': 'running', 'progress': '0%', 'total': file_size}
        print("开始下载...", title)
        ydl.download([url])
    task_status[task_id]['status'] = 'completed'

def download_status_ajax(task_id):
    # print('@@@', task_id, task_status, task_id in task_status)
    if task_id in task_status:
        return jsonify(task_status[task_id])
    else:
        return jsonify({'status': 'not_found'}), 404

def download_video_ajax(session):
    user = session['login_name']
    video_url = clean_reship_url(request.form.get('video_url'))
    resolution = request.form.get('resolution')
    session['video_url'] = video_url
    session['resolution'] = resolution
    session['SESSDATA'] = request.form.get('sessdata')
    session['bili_jct'] = request.form.get('bili_jct')
    session['buvid3'] = request.form.get('buvid3')
    need_subtitle = request.form.get('need_subtitle')
    session['need_subtitle'] = need_subtitle

    clear_video_directory(session['save_dir'])

    print(user, "获取视频标题...")
    session['origin_title'] = get_youtube_info(video_url)["title"]

    task_id = str(uuid.uuid4())
    print('init task_id', task_id)
    task_status[task_id] = {'status': 'running', 'progress': '0%'}
    progress_hook = create_progress_hook(task_id)

    ydl_opts = {
        'writesubtitles': need_subtitle, 
        'subtitleslangs': [need_subtitle], 
        'writesubtitlesformat': 'srt' if need_subtitle else None, 
        'writethumbnail': True,  
        'outtmpl': os.path.join(session['save_dir'], session['save_video']), 
        'format': 'bv*[height<={resolution}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]'.format(resolution=resolution), 
        'progress_hooks': [progress_hook],
    }

    thread = Thread(target=run_yt_dlp, args=(video_url, ydl_opts, task_id))
    thread.start()
    return jsonify({'task_id': task_id}), 202