import os
from flask import Flask, redirect, url_for, flash
from utils.constants import Route
from utils.db import VideoDB

def delete_video_and_related_files(video_id):
    db = VideoDB()
    record = db.read_video(video_id)
    path = record['save_path']
    id_to_match = record['origin_id']

    try:
        # 删除指定路径的文件
        if os.path.exists(path):
            os.remove(path)
            print(f'已删除 {video_id} : {path}')

        # 获取path所在目录
        directory = os.path.dirname(path)
        
        if os.path.exists(directory):
            # 遍历目录下所有文件，删除文件名中包含id的文件
            for filename in os.listdir(directory):
                if id_to_match in filename:
                    file_path = os.path.join(directory, filename)
                    if os.path.isfile(file_path):  # 确保是文件而不是目录
                        os.remove(file_path)
                        print(f'已删除与 {id_to_match} 相关的文件: {file_path}')
        
        # 删除数据库中的记录
        db.delete_video(video_id)
        print(f'数据库中关于 {video_id} 的记录已删除')
    except Exception as e:
        flash(e)  # 假设flash是一个用于显示消息的函数，例如Flask框架中的flash
        raise e  # 重新抛出异常以便外部可以捕获处理

def delete_controller(session, video_id):
    delete_video_and_related_files(video_id)
    return redirect(url_for(Route.LIST))
