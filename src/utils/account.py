import re
import requests
import json
from json import JSONDecodeError
from typing import List, Dict, Any
from yt_dlp import YoutubeDL
from .sys import join_root_path
from .string import cleaned_text
from ._exception import CookieException, ExceptionEnum

def load_app_accounts() -> List[Dict[str, Any]]:
    """
    加载并解析应用账户信息。
    
    从指定的JSON文件中读取用户账户数据，该文件应包含一个名为'users'的键，
    其值为一个字典列表，每个字典代表一个用户，包含'username'和'password'键。
    
    :return: 一个字典列表，即 'users' 字段，每个字典包含用户信息。例如：
             [
                 {'username': 'user1', 'password': 'hashed_password1'},
                 {'username': 'user2', 'password': 'hashed_password2'}
             ]
    """
    with open(join_root_path('config/app_accounts.json'), 'r') as file:
        accounts_data = json.load(file)
    return accounts_data['users']

def get_youtube_info(video_url):
    """
    从YouTube视频URL中提取信息，包括视频链接、ID和标题（清理多余空格后）。
    
    :param video_url: YouTube视频的URL
    :return: 包含视频信息的字典，键为'url', 'id', 'title'
    """
    with YoutubeDL() as ydl: 
        info_dict = ydl.extract_info(video_url, download=False)
        url = info_dict.get("url", None)
        video_id = info_dict.get("id", None)
        title = info_dict.get('title', None)
        file_size = info_dict.get('filesize_approx', 0)
        return {
            "url": url, 
            "id": video_id, 
            "title": cleaned_text(title),
            "file_size": file_size
        }

# https://github.com/SP-FA/autoBilibili
class AccountUtil:
    def __init__(self, config_path: str):
        """
        config_path 需要将 Cookie 信息填入一个配置文件 config.json 中，文件需要以下字段：
        {
            "uid": "",
            "SESSDATA": "",
            "bili_jct": "",
            "buvid3": ""
        }
        """
        try:
            with open(config_path) as f:
                cookie = json.load(f)
            self.uid = cookie['uid']
            self.session = requests.session()
            self.session.cookies['SESSDATA'] = cookie['SESSDATA']
            self.session.cookies['bili_jct'] = cookie['bili_jct']
            self.session.cookies['buvid3'] = cookie['buvid3']
        except (KeyError, JSONDecodeError):
            raise CookieException(ExceptionEnum.COOKIE_CONFIG_ERR, 'Cookies are not configured in ' + config_path)
        self.headers = {
            'origin': 'https://space.bilibili.com',
            'User-Agent': "Mozilla/5.0 (Windows NT 6.3; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/39.0.2171.95 Safari/537.36"
        }
    def verify_cookie(self):
        """
        Verify that Cookies are available

        EXCEPTION:
          CookieException
          @ errno 0: invalid Cookie
          @ errno 1: Cookies are not configured in the init method correctly
        """
        url = 'https://space.bilibili.com/%s/favlist' % self.uid
        homePage = self.session.get(url, headers=self.headers)
        home_page = homePage.content.decode("utf-8")
        if '个人空间' not in home_page:
            raise CookieException(ExceptionEnum.INVALID_COOKIE_ERR, 'Invalid Cookie.')
        user_name = re.findall(r'关注(.*)账号', home_page)[0]
        # print('Valid Cookie, user name: %s' % user_name)
        self.session.cookies['user_name'] = user_name
        return self.session.cookies
