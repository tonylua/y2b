import os
import traceback
import asyncio
import threading
from datetime import datetime
from flask import request, redirect, url_for, render_template, flash, jsonify
from yt_dlp import YoutubeDL
from forms.download import YouTubeDownloadForm
from utils.stringUtil import clean_reship_url
from utils.account import AccountUtil, get_youtube_info
from utils.constants import Route, VideoStatus, DownloadStage
from utils.sys import join_root_path, clean_temp_files
from utils.db import VideoDB
from utils.progress import download_progress
from .upload import do_upload


async def run_yt_dlp(session, url, video_id, ydl_opts, final_save_path, temp_save_path):
    download_progress.update_stage(video_id, DownloadStage.DOWNLOADING_VIDEO, 0, '开始下载视频')
    
    if os.path.exists(final_save_path):
        print("文件已存在，跳过下载")
        download_progress.update_stage(video_id, DownloadStage.DOWNLOADING_VIDEO, 100, '使用已存在的视频文件')
    else:
        with YoutubeDL(ydl_opts) as ydl:
            print("开始下载...", video_id)
            try:
                ydl.download([url])
                
                if os.path.exists(temp_save_path):
                    os.rename(temp_save_path, final_save_path)
                    print(f"文件已重命名: {temp_save_path} -> {final_save_path}")
                    download_progress.update_stage(video_id, DownloadStage.DOWNLOADING_VIDEO, 100, '视频下载完成')
                else:
                    raise Exception(f"临时文件不存在: {temp_save_path}")
            except Exception as e:
                if os.path.exists(temp_save_path):
                    os.remove(temp_save_path)
                    print(f"已清理临时文件: {temp_save_path}")
                raise e
    
    download_progress.update_stage(video_id, DownloadStage.PREPARING_UPLOAD, 0, '准备上传')
    result = await do_upload(session, video_id)
    return True, result


async def yt_dlp_worker(session, url, video_id, ydl_opts, final_save_path, temp_save_path):
    try:
        return await run_yt_dlp(session, url, video_id, ydl_opts, final_save_path, temp_save_path)
    except Exception as e:
        traceback.print_exc()
        print('run_yt_dlp ERR', e, video_id)
        download_progress.set_error(video_id, str(e))
        db = VideoDB()
        db.update_video(video_id, status=VideoStatus.ERROR)
        return False, e


def yt_dlp_sync_wrapper(*args):
    return asyncio.run(yt_dlp_worker(*args))


def download_controller(session, url):
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
        "buvid3": bili_cookies['buvid3'],
        "video_url": url
    }
    form = YouTubeDownloadForm(**args)

    if form.validate_on_submit():
        subtitle_map = {
            'en': "en",
            'cn': "zh-Hans",
            'bilingual': "en",
        }
        need_subtitle = request.form.get('need_subtitle')
        session['need_subtitle'] = need_subtitle
        subtitle_locale = subtitle_map.get(need_subtitle, '')

        video_url = clean_reship_url(request.form.get('video_url'))
        session['video_url'] = video_url

        session['resolution'] = request.form.get('resolution')
        session['SESSDATA'] = request.form.get('sessdata')
        session['bili_jct'] = request.form.get('bili_jct')
        session['buvid3'] = request.form.get('buvid3')
        session['auto_upload'] = request.form.get('auto_upload')
        session['tid'] = request.form.get('tid')
        session['tags'] = request.form.get('tags')

        temp_id = f"temp_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        download_progress.start_progress(temp_id, '正在准备...')
        download_progress.update_stage(temp_id, DownloadStage.PREPARING, 0, '正在初始化...')

        print('准备处理下载请求...')
        current_session = session._get_current_object()
        
        def background_task():
            video_id = None
            temp_save_path = None
            try:
                download_progress.update_stage(temp_id, DownloadStage.FETCHING_INFO, 5, '正在获取视频信息...')
                info = get_youtube_info(video_url)
                orig_id = info["id"]
                current_session['origin_title'] = info["title"]
                current_session['origin_id'] = orig_id
                current_session['origin_file_size'] = info["file_size"]
                print("获取了视频标题等...", info)

                current_session['save_video'] = f"{orig_id}.{current_session['resolution']}.mp4"
                final_save_path = os.path.join(current_session['save_dir'], current_session['save_video'])
                temp_save_path = os.path.join(current_session['save_dir'], f"{orig_id}.{current_session['resolution']}.tmp.mp4")
                save_srt = os.path.join(current_session['save_dir'], f"{orig_id}.{subtitle_locale}.srt") if subtitle_locale else ''

                opts = {
                    'writesubtitles': bool(need_subtitle),
                    'subtitleslangs': [subtitle_locale],
                    'writesubtitlesformat': 'srt' if need_subtitle else None,
                    'writethumbnail': True,
                    'outtmpl': temp_save_path,
                    'format': f"bv*[height<={current_session['resolution']}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
                }

                db = VideoDB()
                existing_video = db.query_video_by_origin_id(user, orig_id)
                if existing_video:
                    video_id = existing_video['id']
                    print(f"Video {orig_id} already exists for user {user}; reusing record {video_id}")
                    db.update_video(video_id, save_path=final_save_path, save_srt=save_srt, subtitle_lang=need_subtitle, status=VideoStatus.DOWNLOADING)
                else:
                    video_id = db.create_video(
                        user=user,
                        origin_id=orig_id,
                        origin_url=video_url,
                        save_path=final_save_path,
                        save_srt=save_srt,
                        title=info["title"],
                        subtitle_lang=need_subtitle
                    )
                    db.update_video(video_id, status=VideoStatus.DOWNLOADING)

                download_progress.update_video_id(temp_id, str(video_id))
                download_progress.update_stage(str(video_id), DownloadStage.FETCHING_INFO, 10, '视频信息获取完成')

                print('准备下载', video_id, '\n', opts)

                result = yt_dlp_sync_wrapper(
                    current_session,
                    video_url,
                    str(video_id),
                    opts,
                    final_save_path,
                    temp_save_path
                )
                is_succ, msg = result
                if is_succ:
                    download_progress.complete_progress(str(video_id))
                else:
                    download_progress.set_error(str(video_id), str(msg))
            except KeyboardInterrupt:
                print("\n用户中断了后台任务")
                if temp_save_path and os.path.exists(temp_save_path):
                    os.remove(temp_save_path)
                    print(f"已清理临时文件: {temp_save_path}")
                if video_id:
                    download_progress.set_error(str(video_id), '用户中断操作')
                    db = VideoDB()
                    db.update_video(video_id, status=VideoStatus.ERROR)
                else:
                    download_progress.set_error(temp_id, '用户中断操作')
            except Exception as e:
                traceback.print_exc()
                print(f'后台任务出错: {e}')
                if temp_save_path and os.path.exists(temp_save_path):
                    os.remove(temp_save_path)
                    print(f"已清理临时文件: {temp_save_path}")
                if video_id:
                    download_progress.set_error(str(video_id), str(e))
                else:
                    download_progress.set_error(temp_id, str(e))

        thread = threading.Thread(target=background_task)
        thread.daemon = True
        thread.start()
        
        return jsonify({'video_id': temp_id, 'status': 'started'})

    return render_template('download.html', form=form)
