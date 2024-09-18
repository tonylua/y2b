import os
import secrets
from functools import wraps
from flask import Flask, g, session, request, flash, redirect, url_for  
from controllers.login import login_controller
# from controllers.download import download_controller, download_video_ajax, download_status_ajax
# from controllers.preview import preview_controller
from controllers.download import download_controller
from controllers.upload import upload_controller
from controllers.delete import delete_controller
from controllers.list import list_controller
from controllers.pending import fetch_pending_list

current_file_path = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file_path)

app = Flask(__name__, 
    template_folder=f'{current_dir}/templates', 
    static_folder=f'{current_dir}/../static',
    static_url_path='/static'
)
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
    url = request.args.get('url', default=None, type=str)
    return download_controller(session, url)

@app.route('/delete/<video_id>', methods=['GET']) 
def delete(video_id):
    return delete_controller(session, video_id)

@app.route('/fetch_pending_list', methods=['GET'])
def fetch_pending():
    return fetch_pending_list()

@app.route('/upload', methods=['POST']) 
async def upload():
    return await upload_controller(session)

@app.route('/list', methods=['GET'])
@login_required
def list_page():
    return list_controller(session)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
