import os
import re
import glob
import shutil
import subprocess
from typing import List, Dict, Union, Callable, Optional


def join_root_path(*paths):
    current_file_path = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file_path)
    root_dir = os.path.join(current_dir, '../..')
    return os.path.abspath(os.path.join(root_dir, *paths))


def rename_completed_file(file_path, replaced_str=''):
    if '.tmp' in file_path:
        base_name, ext_with_tmp = file_path.rsplit('.tmp', 1)
        new_file_path = f"{base_name}{replaced_str}{ext_with_tmp}"
        try:
            os.rename(file_path, new_file_path)
            print(f"文件已成功重命名为: {new_file_path}")
        except OSError as e:
            print(f"重命名文件时发生错误: {e}")
    else:
        print("提供的文件名中没有找到 '.tmp' 标识符")


def find_cover_images(directory, id):
    image_extensions = ['*.webp', '*.jpg', '*.jpeg', '*.png', '*.gif']
    cover_images = [file for ext in image_extensions
                   for file in glob.glob(os.path.join(directory, ext))]
    for img_path in cover_images:
        filename = os.path.basename(img_path).lower()
        if str(id).lower() in filename:
            return img_path
    return cover_images[0] if cover_images else None


def extract_cover_from_video(video_path: str, output_path: str) -> bool:
    try:
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', video_path, '-ss', '00:00:01', '-vframes', '1', output_path],
            capture_output=True,
            text=True
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except Exception as e:
        print(f"从视频提取封面失败: {e}")
        return False


def run_cli_command(
    command_name,
    args_list,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    total_duration: Optional[float] = None
):
    cmd = [command_name] + args_list

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )

        time_pattern = re.compile(r'time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})')

        for line in process.stdout:
            print(line.strip())

            if progress_callback and total_duration and 'frame=' in line:
                match = time_pattern.search(line)
                if match:
                    hours = int(match.group(1))
                    minutes = int(match.group(2))
                    seconds = int(match.group(3))
                    centisecs = int(match.group(4))
                    current_time = hours * 3600 + minutes * 60 + seconds + centisecs / 100
                    percent = min(99, int((current_time / total_duration) * 100))
                    progress_callback(percent, f'正在嵌入字幕... {percent}%')

        exit_code = process.wait()
        if exit_code != 0:
            raise subprocess.CalledProcessError(exit_code, cmd)
    finally:
        process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


def clear_video_directory(path):
    if os.path.exists(path):
        shutil.rmtree(path)
        os.makedirs(path)


def get_video_duration(video_path: str) -> Optional[float]:
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception as e:
        print(f"获取视频时长失败: {e}")
    return None


def get_file_size(file_path: str) -> str:
    size = os.path.getsize(file_path)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.2f} {unit}"


def clean_temp_files(directory: str, pattern: str = '*.tmp.*'):
    """
    清理目录中的临时文件
    
    :param directory: 要清理的目录路径
    :param pattern: 临时文件的匹配模式，默认为 '*.tmp.*'
    :return: 清理的文件数量
    """
    if not os.path.exists(directory):
        return 0
    
    cleaned_count = 0
    for filename in os.listdir(directory):
        if '.tmp.' in filename:
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"已清理临时文件: {file_path}")
                    cleaned_count += 1
            except Exception as e:
                print(f"清理临时文件失败 {file_path}: {e}")
    
    return cleaned_count


def clean_all_temp_video_files():
    """
    清理所有视频目录中的临时文件
    """
    video_dir = join_root_path('static/video')
    if not os.path.exists(video_dir):
        return 0
    
    total_cleaned = 0
    for root, dirs, files in os.walk(video_dir):
        cleaned = clean_temp_files(root)
        total_cleaned += cleaned
    
    if total_cleaned > 0:
        print(f"共清理了 {total_cleaned} 个临时文件")
    return total_cleaned


def list_files(directory_path: str, file_extension: str = '.mp4') -> List[Dict[str, Union[str, int]]]:
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


