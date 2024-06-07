import os
from flask import Flask, session, request, redirect, url_for, render_template, jsonify
from utils.db import VideoDB

def list_controller(session):
    db = VideoDB()
    videos = db.list_videos()
    # print(videos, len(videos))
    return render_template('list.html', videos=videos, num=len(videos))