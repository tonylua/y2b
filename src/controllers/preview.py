import os
from flask import Flask, redirect, url_for, flash, render_template
from utils.sys import get_file_size, find_cover_images
from utils.constants import Route

def preview_controller(session):
    video_path = f"{session['save_dir']}/{session['save_video']}"
    subtitles_en_path = f"{session['save_dir']}/{session['save_srt_en']}"
    subtitles_cn_path = f"{session['save_dir']}/{session['save_srt_cn']}"
    
    video_exists = os.path.exists(video_path)
    if not (video_exists):
        flash(f"视频未找到，请重新尝试。{video_path}", "warning")
        return redirect(url_for(Route.LOGIN))
    
    cover = find_cover_images(session['save_dir'], record['origin_id'])
    if not (cover):
        flash(f"封面未找到，请重新尝试。", "warning")
        return redirect(url_for(Route.LOGIN))
    else:
        session['cover_path'] = cover

    subtitles_en_exist = os.path.exists(subtitles_en_path)
    subtitles_cn_exist = os.path.exists(subtitles_cn_path)

    video_size = get_file_size(video_path)
    session['video_size'] = video_size

    subtitle_en_name = None
    subtitle_cn_name = None
    if subtitles_en_exist:
        subtitle_en_name = session['save_srt_en']
    if subtitles_cn_exist:
        subtitle_cn_name = session['save_srt_cn']
    
    return render_template('preview.html', 
        video_path=url_for('static', filename=f"{session['save_dir_rel']}/{session['save_video']}"), 
        thumbnail_path=cover,
        subtitle_en_name=subtitle_en_name,
        subtitle_cn_name=subtitle_cn_name)
