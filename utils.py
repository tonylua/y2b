import os
import shutil

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