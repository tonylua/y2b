import os
import re
import re
import glob
import shutil
import subprocess
from typing import List, Dict, Union, Tuple, Callable

def join_root_path(*paths):
    current_file_path = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file_path)
    root_dir = os.path.join(current_dir, '../..')
    return os.path.abspath(os.path.join(root_dir, *paths));

def rename_completed_file(file_path, replaced_str = ''):
    if '.tmp' in file_path:
        base_name, ext_with_tmp = file_path.rsplit('.tmp', 1)
        # 去掉或替换 .tmp 部分
        new_file_path = f"{base_name}{replaced_str}{ext_with_tmp}"
        try:
            os.rename(file_path, new_file_path)
            print(f"文件已成功重命名为: {new_file_path}")
        except OSError as e:
            print(f"重命名文件时发生错误: {e}")
    else:
        print("提供的文件名中没有找到 '.tmp' 标识符")

def find_cover_images(directory):
    """
    扫描指定目录，查找常见的封面图片格式文件。
    
    :param directory: 要扫描的目录路径
    :return: 第一张封面图的文件路径，如果没有找到则返回None
    """
    image_extensions = ['*.webp', '*.jpg', '*.jpeg', '*.png', '*.gif']
    cover_images = [file for ext in image_extensions for file in glob.glob(os.path.join(directory, ext))]
    return cover_images[0] if cover_images else None

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

# def run_cli_command2(command_name, args_list, output_handler=None):
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

def clear_video_directory(path):
    """
    清空指定的视频文件目录。如果目录存在，则先删除再重新创建。
    
    :param path: 静态文件目录的路径
    """
    if os.path.exists(path):
        shutil.rmtree(path)
        os.makedirs(path)

def get_file_size(file_path: str) -> int:
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

def list_files(directory_path: str, file_extension: str = '.mp4') -> List[Dict[str, Union[str, int]]]:
    """
    列出指定目录下特定扩展名的文件，并为每个文件创建包含文件名、完整路径及文件大小的字典。
    
    :param directory_path: 目录路径
    :param file_extension: 需要列出的文件扩展名
    :return: 包含文件信息的字典列表
    """
    if not os.path.exists(directory_path):
        return []
    filtered_files = [f for f in os.listdir(directory_path) if f.endswith(file_extension)]
    videos = [
        {
            'filename': filename,
            'full_path': os.path.join(directory_path, filename),
            'size': get_file_size(os.path.join(directory_path, filename))
        } 
        for filename in filtered_files
    ]
    return videos


