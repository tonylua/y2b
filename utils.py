import os
import shutil
from yt_dlp import YoutubeDL

def clear_static_directory(static_path):
    if os.path.exists(static_path):
        shutil.rmtree(static_path)
        os.makedirs(static_path)

def get_file_size(file_path):
    size = os.path.getsize(file_path)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            break
        size /= 1024.0
    return f"{size:.2f} {unit}"

def get_youtube_info(video_url):
    with YoutubeDL() as ydl: 
        info_dict = ydl.extract_info(video_url, download=False)
        url = info_dict.get("url", None)
        id = info_dict.get("id", None)
        title = info_dict.get('title', None)
        return {
            "url": url, 
            "id": id, 
            "title": title
        }