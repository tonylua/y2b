import sys
import os
from datetime import datetime

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_project_root():
    return _root


def setup_path():
    src_path = os.path.join(_root, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    if _root not in sys.path:
        sys.path.insert(0, _root)


def cli_progress(percent, message):
    print(f"\r[{percent:3d}%] {message}", end='', flush=True)


def cli_progress_done():
    print()


def default_save_dir():
    date_str = datetime.now().strftime('%Y%m%d')
    save_dir = os.path.join(_root, 'static', 'video', date_str)
    os.makedirs(save_dir, exist_ok=True)
    return save_dir


def load_bili_cookies(cookie_path=None):
    setup_path()
    from utils.account import AccountUtil
    from utils.sys import join_root_path
    if not cookie_path:
        cookie_path = join_root_path("config/bili_cookie.json")
    bili = AccountUtil(config_path=cookie_path)
    cookies = bili.verify_cookie()
    return cookies
