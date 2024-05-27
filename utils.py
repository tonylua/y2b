import os
import re
import shutil
import subprocess
import requests
from json import JSONDecodeError
import json
import re
from _exception import CookieException, ExceptionEnum
from yt_dlp import YoutubeDL
from urllib.parse import urlparse, urlencode, parse_qs, ParseResult

def clean_reship_url(url, keep_query_key='v'):
    """
    修改URL，仅保留指定的查询参数（默认为'v'），其余查询参数移除。
    
    :param url: 原始URL字符串
    :param keep_query_key: 要保留的查询参数的键，默认为'v'
    :return: 修改后的URL字符串
    """
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        # 仅保留指定的查询参数
        filtered_query_params = {k: v for k, v in query_params.items() if k == keep_query_key}
        # 重新构造URL
        new_url = ParseResult(
            scheme=parsed_url.scheme,
            netloc=parsed_url.netloc,
            path=parsed_url.path,
            params=parsed_url.params,
            query=urlencode(filtered_query_params, doseq=True) if filtered_query_params else '',
            fragment=parsed_url.fragment
        ).geturl()
        return new_url
    except Exception as e:
        raise ValueError(f"Invalid URL or error processing it: {e}")

def truncate_str(s, n, ellipsis='...'):
    """
    截断字符串至指定长度，并在末尾追加指定的省略号（默认为 '...'）。
    
    :param s: 原始字符串。
    :param n: 截断后的最大长度。
    :param ellipsis: 超过长度后追加的省略号，默认为 '...'。
    :return: 截断后的字符串。
    """
    if len(s) > n:
        return s[:n] + ellipsis
    else:
        return s

def run_cli_command(command_name, args_list):
    """
    实时执行命令行命令并打印输出，同时处理异常情况。
    
    :param command_name: 命令名称（字符串）
    :param args_list: 命令的参数列表（列表）
    :raise subprocess.CalledProcessError: 如果命令执行失败
    """
    cmd = [command_name] + args_list
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  
            universal_newlines=True,  
            bufsize=1,  
        )

        for line in process.stdout:  
            print(line.strip())  

        exit_code = process.wait()  
        if exit_code != 0:
            raise subprocess.CalledProcessError(exit_code, cmd)
    finally:
        # 确保子进程被正确关闭（在某些情况下可能需要）
        process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

# def run_cli_command(command_name, args_list, output_handler=None):
#     """
#     执行命令行命令的通用函数。
    
#     :param command_name: 命令名称（字符串）
#     :param args_list: 命令的参数列表（列表）
#     :param output_handler: 输出处理函数，接收 stdout 和 stderr 作为参数（可选）
#     :return: 如果命令成功执行，返回 True；否则，返回 False
#     """
#     cmd = [command_name] + args_list  # 合并命令名与参数列表
    
#     try:
#         result = subprocess.run(
#             cmd,
#             check=True,  # 如果命令执行失败（非零退出状态），将抛出 CalledProcessError
#             text=True,  # 使输出为文本而非字节
#             capture_output=True  # 捕获标准输出和标准错误
#         )
#         if output_handler:
#             output_handler(result.stdout, result.stderr)
#         print(f"{command_name}命令执行成功!")
#         return True
#     except subprocess.CalledProcessError as e:
#         error_message = f"{command_name}命令执行失败: {e.stderr}"
#         if output_handler:
#             output_handler(e.stdout, e.stderr)
#         else:
#             print(error_message)
#         return False

def cleaned_text(text):
    """
    清理字符串中的多余空格，将连续的空格替换为单个空格，并去除首尾空格。
    
    :param text: 待清理的原始字符串
    :return: 清理后的字符串
    """
    return re.sub(r'\s+', ' ', text).strip()

def clear_static_directory(static_path):
    """
    清空指定的静态文件目录。如果目录存在，则先删除再重新创建。
    
    :param static_path: 静态文件目录的路径
    """
    if os.path.exists(static_path):
        shutil.rmtree(static_path)
        os.makedirs(static_path)

def get_file_size(file_path):
    """
    获取文件大小，并以易于阅读的单位（B, KB, MB, GB）返回。
    
    :param file_path: 文件的路径
    :return: 文件大小的字符串表示，包括单位
    """
    size = os.path.getsize(file_path)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.2f} {unit}"

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
        return {
            "url": url, 
            "id": video_id, 
            "title": cleaned_text(title)
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

