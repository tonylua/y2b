import os
from flask import Flask, redirect, url_for, render_template
from bilibili_api import sync, video_uploader, Credential
from utils.string import cleaned_text, clean_reship_url, truncate_str
from utils.sys import run_cli_command
from forms.upload import BilibiliUploadForm

async def upload_controller(session):
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

        # TODO 选择是否加字幕
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