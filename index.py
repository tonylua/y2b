import subprocess
import secrets
import string
import os
import shutil
from bilibili_api import sync, video_uploader, Credential
from flask import Flask, session, render_template, redirect, url_for, flash
from utils import AccountUtil, run_cli_command, clear_static_directory, get_file_size, get_youtube_info, cleaned_text, clean_reship_url, truncate_str
from download import YouTubeDownloadForm
from upload import BilibiliUploadForm

app = Flask(__name__, template_folder='/root/move_video/templates')
app.config['SECRET_KEY'] = secrets.token_urlsafe(32) 
app.config['SESSION_TYPE'] = 'filesystem'

@app.before_request
def setup_session():
    session.permanent = True 

@app.route('/', methods=['GET', 'POST'])
def index():
    session['save_dir'] = '/root/move_video/static'
    session['save_video'] = 'video.mp4'
    session['save_cover'] = 'video.webp'
    session['save_srt_en'] = 'video.en.srt'
    session['save_srt_cn'] = 'video.zh-Hans.srt'

    try:
        bili = AccountUtil(config_path="/root/move_video/bili_cookie.json")
        bili_cookies = bili.verify_cookie()
        # for key, value in bili_cookies.items():
        #     session[key] = value
        print("登录信息有效：%s" % bili_cookies['user_name'])
    except Exception as e:
        raise(e)

    form = YouTubeDownloadForm(
        sessdata=bili_cookies['SESSDATA'],
        bili_jct=bili_cookies['bili_jct'],
        buvid3=bili_cookies['buvid3']
    )
    if form.validate_on_submit():

        video_url = form.video_url.data
        resolution = form.resolution.data

        session['video_url'] = video_url
        session['resolution'] = resolution
        session['SESSDATA'] = form.sessdata.data
        session['bili_jct'] = form.bili_jct.data
        session['buvid3'] = form.buvid3.data

        clear_static_directory(session['save_dir'])

        print("获取视频标题...")
        session['origin_title'] = get_youtube_info(video_url)["title"]
        
        # TODO threading 进度条

        print("开始下载...", session['origin_title']);
        run_cli_command('yt-dlp', [
            "--write-auto-subs",
            "--sub-langs", "en,zh-Hans",
            "--convert-subs", "srt",
            "--write-thumbnail",
            "-P", f"{session['save_dir']}",
            "-f", f"bv*[height<={resolution}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]",
            "-o", session['save_video'],
            video_url
        ])

        return redirect(url_for('preview'))  
    
    return render_template('download.html', form=form)

@app.route('/preview', methods=['GET', 'POST'])
def preview():
    video_path = f"{session['save_dir']}/{session['save_video']}"
    thumbnail_path = f"{session['save_dir']}/{session['save_cover']}"
    subtitles_en_path = f"{session['save_dir']}/{session['save_srt_en']}"
    subtitles_cn_path = f"{session['save_dir']}/{session['save_srt_cn']}"
    
    video_exists = os.path.exists(video_path)
    thumbnail_exists = os.path.exists(thumbnail_path)
    subtitles_en_exist = os.path.exists(subtitles_en_path)
    subtitles_cn_exist = os.path.exists(subtitles_cn_path)
    
    if not (video_exists and thumbnail_exists):
        flash(f"视频或封面未找到，请重新尝试。{video_path}, {thumbnail_path}", "warning")
        return redirect(url_for('index'))
    
    video_size = get_file_size(video_path)
    session['video_size'] = video_size

    subtitle_en_name = None
    subtitle_cn_name = None
    if subtitles_en_exist:
        subtitle_en_name = session['save_srt_en']
    if subtitles_cn_exist:
        subtitle_cn_name = session['save_srt_cn']
    
    return render_template('preview.html', 
        video_path=url_for('static', filename=session['save_video']), 
        thumbnail_path=url_for('static', filename=session['save_cover']),
        subtitle_en_name=subtitle_en_name,
        subtitle_cn_name=subtitle_cn_name)

@app.route('/upload', methods=['GET', 'POST'])  
async def upload():
    form = BilibiliUploadForm(
        title=session['origin_title'],
        sessdata=session['SESSDATA'],
        bili_jct=session['bili_jct'],
        buvid3=session['buvid3']
    )

    video_path = f"{session['save_dir']}/{session['save_video']}"
    video_with_srt_path = f"{session['save_dir']}/with_srt_{session['save_video']}"
    thumbnail_path = f"{session['save_dir']}/{session['save_cover']}"
    subtitles_en_path = f"{session['save_dir']}/{session['save_srt_en']}"
    subtitles_en_exist = os.path.exists(subtitles_en_path)

    # TODO 字幕 https://github.com/Nemo2011/bilibili-api/issues/748
    # ffmpeg -i static/video.mp4 -vf "subtitles=static/video.en.srt" -c:a copy static/video_with_srt.mp4

    # TODO 加结尾

    if form.validate_on_submit():

        title = form.title.data
        if (subtitles_en_exist):
            title = f"[英字] {title}"
            print("加字幕...")
            run_cli_command('ffmpeg', [
                "-i", video_path,
                "-vf",
                f"subtitles={subtitles_en_path}",
                "-c:a",
                "copy",
                video_with_srt_path
            ])
        title = truncate_str(cleaned_text(title), 75)

        args = {
            "sessdata": form.sessdata.data,
            "bili_jct": form.bili_jct.data,
            "buvid3": form.buvid3.data
        }
        credential = Credential(**args)
        vu_meta = video_uploader.VideoMeta (
            tid = form.tid.data if form.tid.data else 231, 
            original = True, # TODO 设置转载报错
            source = 'youtube',
            no_reprint = True,
            title = title, 
            tags = form.tags.data.split(',') if len(form.tags.data) else ['youtube'], 
            desc = form.desc.data if form.desc.data else f"via. {clean_reship_url(session['video_url'])}", 
            cover = form.cover.data if form.cover.data else thumbnail_path
        )
        page = video_uploader.VideoUploaderPage(
            path = video_with_srt_path if subtitles_en_exist else video_path,
            title = title,
            description = form.desc.data
        )
        uploader = video_uploader.VideoUploader([page], vu_meta, credential)

        @uploader.on("__ALL__")
        async def ev(data):
            print(data)

        print("开始上传...");
        await uploader.start()

        return redirect(url_for('index'))

    return render_template('upload.html', form=form)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
