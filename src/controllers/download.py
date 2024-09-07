import os
import traceback
# import uuid
import asyncio
# from threading import Thread
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, redirect, url_for, render_template, flash, jsonify
from yt_dlp import YoutubeDL
from forms.download import YouTubeDownloadForm
from utils.string import clean_reship_url
from utils.account import AccountUtil, get_youtube_info
from utils.constants import Route, VideoStatus
from utils.sys import join_root_path
from utils.db import VideoDB
from .upload import do_upload

# task_status = {}
# def create_progress_hook(task_id):
#     def hook(d):
#         if d['status'] == 'finished':
#             task_status[task_id]['status'] = VideoStatus.DOWNLOADING
#             task_status[task_id]['progress'] = '100%'
#         elif d['status'] == 'downloading':
#             task_status[task_id]['status'] = VideoStatus.DOWNLOADING
#             task_status[task_id]['progress'] = d['_percent_str']
#         elif d['status'] == 'error':
#             task_status[task_id]['status'] = VideoStatus.ERROR
#             task_status[task_id]['progress'] = 'ERR'
#     return hook

async def run_yt_dlp(session, url, video_id, ydl_opts):
    with YoutubeDL(ydl_opts) as ydl:
        print("开始下载...", video_id)
        try:
            ydl.download([url])
        except AttributeError as e:
            print('=== ERR ===', e, video_id)
            raise e
    # task_status[task_id]['status'] = VideoStatus.DOWNLOADED
    result = await do_upload(session, video_id)
    return True, result

async def yt_dlp_worker(session, url, video_id, ydl_opts):
    try:
        return await run_yt_dlp(session, url, video_id, ydl_opts)
    except Exception as e:
        traceback.print_exc()
        print('async_yt_dlp_in_thread ERR', e, video_id)
        # if isinstance(e, AttributeError):
        #     e = jsonify(e)
        db = VideoDB()
        db.update_video(video_id, status=VideoStatus.ERROR)
        return False, e

def yt_dlp_sync_wrapper(*args):
    """同步包装器，用于在非异步上下文中运行异步函数"""
    return asyncio.run(yt_dlp_worker(*args))

# def async_yt_dlp_in_thread(*args):
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop) 
#     try:
#         loop.run_until_complete(run_yt_dlp(*args))  
#     except Exception as e:
#         video_id = args[2]
#         print('async_yt_dlp_in_thread ERR', e, video_id)
#         db = VideoDB()
#         db.update_video(video_id, status=VideoStatus.ERROR)
#     finally:
#         loop.close() 

def download_controller(session):
    user = session['login_name']

    try:
        bili = AccountUtil(config_path=join_root_path("config/bili_cookie.json"))
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
        subtitle_locale = subtitle_map.get(need_subtitle, '') 

        video_url = clean_reship_url(request.form.get('video_url'))
        session['video_url'] = video_url

        info = get_youtube_info(video_url)
        orig_id = info["id"]
        session['origin_title'] = info["title"]
        session['origin_id'] = orig_id
        session['origin_file_size'] = info["file_size"]
        print("获取了视频标题等...", info)

        session['resolution'] = request.form.get('resolution')
        session['SESSDATA'] = request.form.get('sessdata')
        session['bili_jct'] = request.form.get('bili_jct')
        session['buvid3'] = request.form.get('buvid3')
        session['auto_upload'] = request.form.get('auto_upload')
        session['tid'] = request.form.get('tid')
        session['tags'] = request.form.get('tags')

        session['save_video'] = f"{orig_id}.{session['resolution']}.mp4"
        save_path = os.path.join(session['save_dir'], session['save_video'])
        save_srt = os.path.join(session['save_dir'], f"{orig_id}.{subtitle_locale}.srt") if subtitle_locale else '' 
        opts = {
            'writesubtitles': bool(need_subtitle), 
            'subtitleslangs': [subtitle_locale], 
            'writesubtitlesformat': 'srt' if need_subtitle else None, 
            'writethumbnail': True,     
            'outtmpl': save_path, 
            'format': f"bv*[height<={session['resolution']}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            # 'progress_hooks': [create_progress_hook(task_id)],
        }
        # task_status[task_id] = {
        #     'status': VideoStatus.DOWNLOADING, 
        #     'progress': '', 
        #     'id': orig_id,
        #     'title': session['origin_title'],
        #     'path': save_path
        # }

        db = VideoDB()
        video_id = db.create_video(
            user = user,
            origin_id = orig_id,
            origin_url = video_url, 
            save_path = save_path, 
            save_srt = save_srt,
            title = info["title"],
            subtitle_lang = need_subtitle
        )
        db.update_video(video_id, status=VideoStatus.DOWNLOADING)

        print('准备下载', video_id, '\n', opts)
        current_session = session._get_current_object()
        # thread = Thread(target=async_yt_dlp_in_thread, args=(current_session, video_url, opts, task_id, video_id))
        # thread.start()
        with ThreadPoolExecutor() as executor:
            future = executor.submit(
                yt_dlp_sync_wrapper, 
                current_session, 
                video_url, 
                video_id, 
                opts
            )
            result = future.result()
            is_succ, msg = result 
            if is_succ:
                return redirect(url_for(Route.LIST))
            flash(f"An error occurred: {msg}", 'warning')
            return redirect(url_for(Route.LOGIN))

        # return redirect(url_for(Route.LIST))
        
    return render_template('download.html', form=form)
