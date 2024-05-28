import os
from flask import Flask, redirect, url_for, flash, render_template
from utils.sys import get_file_size

def preview_controller(session):
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