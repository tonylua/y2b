
from flask import Flask, redirect, url_for, render_template
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

    if form.validate_on_submit():
        video_url = clean_reship_url(form.video_url.data)
        resolution = form.resolution.data

        session['video_url'] = video_url
        session['resolution'] = resolution
        session['SESSDATA'] = form.sessdata.data
        session['bili_jct'] = form.bili_jct.data
        session['buvid3'] = form.buvid3.data
        session['need_subtitle'] = form.need_subtitle.data

        # TODO threading 进度条

        clear_video_directory(session['save_dir'])

        print("获取视频标题...")
        session['origin_title'] = get_youtube_info(video_url)["title"]

        subtitle_map = {
            'en': ["--write-auto-subs", "--sub-langs", "en", "--convert-subs", "srt"],
            'cn': ["--write-auto-subs", "--sub-langs", "zh-Hans", "--convert-subs", "srt"]
        }
        cli_args = subtitle_map.get(session['need_subtitle'], []) + [
            "--write-thumbnail",
            "-P", f"{session['save_dir']}",
            "-f", f"bv*[height<={resolution}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            "-o", session['save_video'],
            video_url
        ]
        print("开始下载...", session['origin_title'], cli_args);
        run_cli_command('yt-dlp', cli_args)

        return redirect(url_for('preview'))  
        
    return render_template('download.html', form=form)