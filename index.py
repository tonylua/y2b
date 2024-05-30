import secrets
import os
from functools import wraps
from flask import Flask, session, request, flash, redirect, url_for  
from controllers.login import login_controller
from controllers.download import download_controller, download_video_ajax, download_status_ajax
from controllers.preview import preview_controller
from controllers.upload import upload_controller

app = Flask(__name__, template_folder='/root/move_video/templates')
app.config['SECRET_KEY'] = secrets.token_urlsafe(32) 
app.config['SESSION_TYPE'] = 'filesystem'

@app.before_request
def setup_session():
    session.permanent = True 

def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if 'login_name' not in session:
            flash('请先登录', 'danger') 
            return redirect(url_for('login'))
        print(session['login_name'], '已登录', request.headers.get('User-Agent'))
        return view(**kwargs)
    return wrapped_view

@app.route('/', methods=['GET', 'POST'])
def login():
    return login_controller(session)

@app.route('/download', methods=['GET', 'POST'])
@login_required
def download():
    return download_controller(session)

@app.route('/download_video', methods=['POST'])
def download_ajax():
    return download_video_ajax(session)

@app.route('/download_status/<task_id>', methods=['GET'])
def download_status(task_id):
    return download_status_ajax(task_id)

@app.route('/preview', methods=['GET', 'POST'])
@login_required
def preview():
    return preview_controller(session)

@app.route('/upload', methods=['GET', 'POST']) 
async def upload():
    return await upload_controller(session)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
