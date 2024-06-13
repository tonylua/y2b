import os
from flask import Flask, redirect, url_for, flash
from utils.constants import Route
from utils.db import VideoDB

def delete_controller(session, video_id):
    db = VideoDB()
    record = db.read_video(video_id)
    path = record['save_path']

    try:
        if os.path.exists(path):
            os.remove(path)
        db.delete_video(video_id)
        print('已删除', video_id, path)
    except Exception as e:
        flash(e)
        raise(e)

    return redirect(url_for(Route.LIST))
