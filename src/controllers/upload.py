import os
import platform
from flask import request, redirect, url_for, flash
import bilibili_api
from bilibili_api import video_uploader, Credential
from bilibili_api.video_uploader import VideoUploaderEvents
from utils.stringUtil import cleaned_text, truncate_str
from utils.constants import Route, VideoStatus, DownloadStage
from utils.sys import find_cover_images, join_root_path, extract_cover_from_video
from utils.dict import pick
from utils.db import VideoDB
from utils.account import AccountUtil
from utils.subtitle import add_subtitle
from utils.progress import download_progress


async def do_upload(session, video_id):
    db = VideoDB()
    record = db.read_video(video_id)
    title = record['title']
    orig_id = record['origin_id']
    origin_video_path = record['save_path']
    video_path = origin_video_path
    subtitles_path = ''

    print(f"准备上传 {video_id} {title}")
    download_progress.update_stage(video_id, DownloadStage.PREPARING_UPLOAD, 20, '准备上传')

    try:
        title = truncate_str(cleaned_text(title), 77)
        save_dir, _ = os.path.split(video_path)
        
        download_progress.update_stage(video_id, DownloadStage.PREPARING_UPLOAD, 22, '检查封面...')
        cover = find_cover_images(save_dir, orig_id)
        if not cover:
            cover_path = os.path.join(save_dir, f"{orig_id}.jpg")
            if extract_cover_from_video(origin_video_path, cover_path):
                cover = cover_path
                print(f"已从视频提取封面: {cover}")
            else:
                download_progress.set_error(video_id, '封面不存在且无法从视频提取')
                raise FileNotFoundError('封面不存在', record['origin_id'])

        if session['need_subtitle']:
            download_progress.update_stage(video_id, DownloadStage.PROCESSING_SUBTITLE, 25, '开始处理字幕')
            
            def subtitle_progress_callback(percent: int, message: str):
                download_progress.update_stage(video_id, DownloadStage.PROCESSING_SUBTITLE, percent, message)
            
            subtitle_result = add_subtitle(
                record=record,
                orig_id=orig_id,
                title=title,
                video_path=video_path,
                origin_video_path=origin_video_path,
                progress_callback=subtitle_progress_callback
            )
            title = subtitle_result['title']
            video_path = subtitle_result['video_path']
            subtitles_path = subtitle_result['subtitles_path']
            download_progress.update_stage(video_id, DownloadStage.PROCESSING_SUBTITLE, 39, '字幕处理完成')

        db_update_args = {
            "title": title,
            "save_cover": cover,
            "save_srt": subtitles_path
        }

        if not session['auto_upload']:
            db_update_args.update({
                "status": VideoStatus.DOWNLOADED
            })
            print("not need auto_upload", db_update_args)
            db.update_video(video_id, **db_update_args)
            download_progress.complete_progress(video_id)
            return True, None

        download_progress.update_stage(video_id, DownloadStage.UPLOADING, 40, '准备上传到B站')

        args = {
            "sessdata": session['SESSDATA'],
            "bili_jct": session['bili_jct'],
            "buvid3": session['buvid3']
        }
        credential = Credential(**args)

        desc = f"via. {record['origin_url']}"
        tid = record['tid'] if record['tid'] else 231
        tags = record['tags'].split(',') if record['tags'] and len(record['tags']) else ['youtube']
        vu_data = {
            'tid': tid,
            'original': True,
            'source': 'youtube',
            'no_reprint': True,
            'title': title,
            'tags': tags,
            'desc': desc,
            'cover': cover
        }
        vu_meta = video_uploader.VideoMeta(**vu_data)
        page = video_uploader.VideoUploaderPage(
            path=video_path,
            title=title,
            description=desc
        )
        uploader = video_uploader.VideoUploader([page], vu_meta, credential)

        @uploader.on("__ALL__")
        async def ev(data, args=db_update_args):
            if data['name'] == VideoUploaderEvents.COMPLETED.value:
                args.update(pick(vu_data, ["desc", "tid", "tags"]))
                args["status"] = VideoStatus.UPLOADED
                db.update_video(video_id, **args)
                download_progress.complete_progress(video_id)
                print('上传完成', data)
            elif data['name'] == VideoUploaderEvents.FAILED.value:
                args["status"] = VideoStatus.ERROR
                db.update_video(video_id, **args)
                err_data = data.get('data', ())
                err_msg = '上传失败'
                if err_data and len(err_data) > 0:
                    err_info = err_data[0]
                    if isinstance(err_info, dict) and 'err' in err_info:
                        err_msg = f"上传失败: {err_info['err']}"
                    else:
                        err_msg = f"上传失败: {err_info}"
                download_progress.set_error(video_id, err_msg)
                print('上传失败', data)
            else:
                if data['name'] == 'UPLOAD':
                    progress = data.get('data', {}).get('p', 0)
                    download_progress.update_stage(video_id, DownloadStage.UPLOADING, 40 + progress * 0.6, f'上传中 {progress}%')
                print('上传中', data)

        print("开始上传...")
        try:
            db.update_video(video_id, status=VideoStatus.UPLOADING)
            download_progress.update_stage(video_id, DownloadStage.UPLOADING, 45, '开始上传')
            await uploader.start()
        except bilibili_api.exceptions.NetworkException as e:
            msg = "bilibili_api 403，请尝试更新cookie信息"
            download_progress.set_error(video_id, msg)
            return False, msg
        except bilibili_api.exceptions.ResponseCodeException as e:
            msg = "需要输入验证码了，请稍后再投稿"
            download_progress.set_error(video_id, msg)
            return False, msg
        return True, None
    except KeyboardInterrupt:
        print("\n用户中断了上传流程")
        download_progress.set_error(video_id, '用户中断操作')
        db.update_video(video_id, status=VideoStatus.ERROR)
        raise
    except Exception as e:
        print(f"上传过程出错: {e}")
        download_progress.set_error(video_id, str(e))
        db.update_video(video_id, status=VideoStatus.ERROR)
        raise


async def upload_controller(session):
    session['auto_upload'] = '1'
    try:
        bili = AccountUtil(config_path=join_root_path("config/bili_cookie.json"))
        bili_cookies = bili.verify_cookie()
        session.update(pick(bili_cookies, ["SESSDATA", "bili_jct", "buvid3"]))
    except Exception as e:
        raise(e)
    video_id = request.form.get('video_id')
    is_succ, msg = await do_upload(session, video_id)
    if not is_succ:
        flash(msg, 'warning')
        return redirect(url_for(Route.LOGIN))
    return redirect(url_for(Route.LIST))
