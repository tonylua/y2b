import os
import re
import shutil
import subprocess
from yt_dlp import YoutubeDL

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
