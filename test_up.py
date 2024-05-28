from bilibili_api import sync, video_uploader, channel_series, Credential
from utils.account import AccountUtil
from utils.string import truncate_str

async def main():
    bili = AccountUtil(config_path="/root/move_video/bili_cookie.json")
    info = bili.verify_cookie()

    title = input("%s，请输入视频标题：" % info['user_name'])
    title = truncate_str(title, 75)

    credential_args = {
        "sessdata": info['SESSDATA'],
        "bili_jct": info['bili_jct'],
        "buvid3": info['buvid3']
    }
    credential = Credential(**credential_args)
    vu_meta = video_uploader.VideoMeta(
        tid = 231, 
        title = title, 
        tags = ['youtube'], 
        desc = 'via. youtube', 
        cover = 'static/video.webp',
        no_reprint = True
    )
    page = video_uploader.VideoUploaderPage(
        path = 'static/with_srt_video.mp4',
        title = title,
        description='', 
    )
    uploader = video_uploader.VideoUploader([page], vu_meta, credential)

    @uploader.on("__ALL__")
    async def ev(data):
        print(data)

    dict = await uploader.start()
    # aid = dict['aid']
    # await channel_series.add_aids_to_series(1118426, [aid], credential)

sync(main())
