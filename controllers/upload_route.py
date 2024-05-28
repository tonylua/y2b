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

    need_subtitle = session['need_subtitle']
    video_path = (
        f"{session['save_dir']}/with_srt_{session['save_video']}"
        if need_subtitle
        else f"{session['save_dir']}/{session['save_video']}"
    )

    # TODO 字幕 https://github.com/Nemo2011/bilibili-api/issues/748

    # TODO 加结尾

    if form.validate_on_submit():

        title = form.title.data
        subtitle_title_map = {
            'en': '英字',
            'cn': '中字'
        }
        title = f"[{subtitle_title_map.get(need_subtitle, '转')}] {title}"
        if (need_subtitle):
            srt = session[f"save_srt_{need_subtitle}"]
            subtitles_path = f"{session['save_dir']}/{srt}"
            subtitles_exist = os.path.exists(subtitles_path)
            if (subtitles_exist):
                print("加字幕...", title)
                run_cli_command('ffmpeg', [
                    "-i", video_path,
                    "-vf",
                    f"subtitles={subtitles_path}",
                    "-c:a",
                    "copy",
                    video_path
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
            cover = form.cover.data if form.cover.data else session['cover_path']
        )
        page = video_uploader.VideoUploaderPage(
            path = video_path,
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