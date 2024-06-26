import os
import secrets
from functools import wraps
from flask import Flask, g, session, request, flash, redirect, url_for  
from controllers.login import login_controller
# from controllers.download import download_controller, download_video_ajax, download_status_ajax
# from controllers.preview import preview_controller
from controllers.download2 import download_controller
from controllers.upload2 import upload_controller
from controllers.delete import delete_controller
from controllers.list import list_controller

current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path)

app = Flask(__name__, template_folder=f'{current_dir}/templates')
app.config['SECRET_KEY'] = secrets.token_urlsafe(32) 
app.config['SESSION_TYPE'] = 'filesystem'

@app.context_processor
def inject_global_vars():
    # 这里返回的字典中的键值对会作为全局变量注入到所有模板中
    return {
        'need_add_button': request.path != '/' and request.path != '/download',
    }

@app.before_request
def setup_session():
    session.permanent = True 
    # g.session = session

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'login_name' in session:
            print(session['login_name'], '已登录', request.headers.get('User-Agent'))
            return view(*args, **kwargs)
        flash('请先登录', 'danger') 
        return redirect(url_for('login'))
    return wrapped_view

@app.route('/', methods=['GET', 'POST'])
def login():
    return login_controller(session)

@app.route('/download', methods=['GET', 'POST'])
@login_required
def download():
    return download_controller(session)

@app.route('/delete/<video_id>', methods=['GET']) 
def delete(video_id):
    return delete_controller(session, video_id)

# @app.route('/download_video', methods=['POST'])
# def download_ajax():
#     return download_video_ajax(session)

# @app.route('/download_status/<task_id>', methods=['GET'])
# def download_status(task_id):
#     return download_status_ajax(task_id)

# @app.route('/preview', methods=['GET', 'POST'])
# @login_required
# def preview():
#     return preview_controller(session)

@app.route('/upload', methods=['POST']) 
async def upload():
    return await upload_controller(session)

@app.route('/list', methods=['GET'])
@login_required
def list_page():
    return list_controller(session)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
