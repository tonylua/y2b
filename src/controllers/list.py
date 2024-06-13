from flask import Flask, render_template
from utils.db import VideoDB
from utils.constants import VideoStatus

def list_controller(session):
    user = session['login_name']
    db = VideoDB()
    videos = db.list_videos(user)
    # print(videos, len(videos))
    return render_template('list.html', videos=videos, VideoStatus=VideoStatus)
