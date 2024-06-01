import os
import subprocess
from flask import Flask, redirect, url_for, render_template, flash
import bilibili_api
from bilibili_api import sync, video_uploader, Credential
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
from utils.string import cleaned_text, truncate_str
from utils.sys import run_cli_command, clear_video_directory
from utils.constants import Route
from forms.upload import BilibiliUploadForm

async def upload_controller(session):
    form = BilibiliUploadForm(
        title=session['origin_title'],
        sessdata=session['SESSDATA'],
        bili_jct=session['bili_jct'],
        buvid3=session['buvid3']
    )

    need_subtitle = session['need_subtitle']
    origin_video_path = f"{session['save_dir']}/{session['save_video']}"
    video_path = origin_video_path

    # TODO 加结尾

    if form.validate_on_submit():

        title = form.title.data

        # TODO srt字幕直接上传 https://github.com/Nemo2011/bilibili-api/issues/748
        subtitle_title_map = {
            'en': '英字',
            'cn': '中字'
        }
        if (need_subtitle):
            srt = session[f"save_srt_{need_subtitle}"]
            subtitles_path = f"{session['save_dir']}/{srt}"
            subtitles_exist = os.path.exists(subtitles_path)

            if not subtitles_exist:
                video_id = session['origin_id']
                try:
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
                except Exception as e:
                    print(e)

            if (subtitles_exist):
                video_path = f"{session['save_dir']}/with_srt_{session['save_video']}"
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
            desc = form.desc.data if form.desc.data else f"via. {session['video_url']}", 
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
        try:
            await uploader.start()
        except bilibili_api.exceptions.NetworkException as e:
            flash("bilibili_api 403，请尝试更新cookie信息", "warning")
            return redirect(url_for(Route.LOGIN))
        except bilibili_api.exceptions.ResponseCodeException as e:
            print(e)
            flash("需要输入验证码了，请稍后再投稿", "warning")
            return redirect(url_for(Route.LOGIN))

        # clear_video_directory(session['save_dir'])

        return redirect(url_for(Route.DOWNLOAD))
    
    return render_template('upload.html', form=form)