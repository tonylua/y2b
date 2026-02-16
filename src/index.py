import os
import re
import argparse
import secrets
import sys
from functools import wraps
from flask import Flask, session, request, flash, redirect, url_for, jsonify
from controllers.login import login_controller
from controllers.download import download_controller
from controllers.upload import upload_controller
from controllers.delete import delete_controller
from controllers.list import list_controller
from controllers.pending import fetch_pending_list
from utils.progress import download_progress
from utils.sys import clean_all_temp_video_files

clean_all_temp_video_files()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from upgrade_yt_dlp import main as upgrade_yt_dlp_main
    print("正在检查 yt-dlp 版本...")
    upgrade_yt_dlp_main()
except Exception as e:
    print(f"yt-dlp 升级检查失败: {e}")

# 命令行参数
arg_parser = argparse.ArgumentParser()
arg_parser.add_argument('--port', type=int, help='flask port', default=5003)
args = arg_parser.parse_args()

# Flask 应用配置
current_dir = os.path.dirname(os.path.abspath(__file__))
app = Flask(
    __name__, 
    template_folder=f'{current_dir}/templates', 
    static_folder=f'{current_dir}/../static',
    static_url_path='/static'
)
app.config['SECRET_KEY'] = secrets.token_urlsafe(32)
app.config['SESSION_TYPE'] = 'filesystem'

# 模板过滤器
@app.template_filter('static_path')
def static_path_filter(path):
    return re.sub(r'^.*[\\/]static[\\/]', '/static/', path.replace('\\', '/'))

app.jinja_env.filters['static_path'] = static_path_filter

# 全局模板变量
@app.context_processor
def inject_global_vars():
    return {
        'need_add_button': request.path != '/' and request.path != '/download',
    }

@app.before_request
def setup_session():
    session.permanent = True

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if 'login_name' in session:
            print(session['login_name'], '已登录', request.headers.get('User-Agent'))
            return view(*args, **kwargs)
        flash('请先登录', 'danger')
        return redirect(url_for('login'))
    return wrapped_view

# 路由定义
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

@app.route('/api/download/progress/<video_id>', methods=['GET'])
def get_download_progress(video_id):
    progress = download_progress.get_progress(video_id)
    if progress:
        return jsonify(progress)
    return '', 404

@app.route('/api/download/progress', methods=['GET'])
def get_all_download_progress():
    all_progress = download_progress.get_all_progress()
    return jsonify(list(all_progress.values()))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=args.port)
