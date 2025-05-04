import bilibili_api
from bilibili_api import sync, video_uploader, channel_series, Credential
from utils.account import AccountUtil
from utils.string import truncate_str
from utils.sys import join_root_path 
from typing import List
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter



async def main():
    video_id = '4_uYqae42uc'
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    transcript = transcript_list.find_transcript(['en', 'zh-Hans'])
    translated_transcript = transcript.translate('zh-Hans')
    # print(2222, translated_transcript, type(translated_transcript))
    formatter = SRTFormatter()
    srt_formatted = formatter.format_transcript(translated_transcript.fetch())
    with open('static/video/test_trans.srt', 'w', encoding='utf-8') as srt_file:
        srt_file.write(srt_formatted)
    # YouTubeTranscriptApi.get_transcript(video_id, languages=['zh-Hans'])

    # bili = AccountUtil(config_path="/root/move_video/bili_cookie.json")
    # info = bili.verify_cookie()

    # title = input("%s，请输入视频标题：" % info['user_name'])
    # title = truncate_str(title, 75)
    



    # ff_args: List[str] = [
    #     "-i", "/root/move_video/static/video/user2/video.mp4",
    #     "-vf",
    #     "subtitles=/root/move_video/static/video/user2/video.zh-Hans.srt",
    #     "-c:a",
    #     "copy",
    #     "/root/move_video/static/video/user2/video_with_srttt.mp4"
    # ]
    # ff_args = ff_args[:3] + ["subtitles=/root/move_video/static/video/user2/video.zh-Hans.srt:force_style='FontName=AR PL UKai CN'"] + ff_args[4:]

    # print("测试加中文字幕...", ff_args)
    # run_cli_command('ffmpeg', ff_args)




    # credential_args = {
    #     "sessdata": info['SESSDATA'],
    #     "bili_jct": info['bili_jct'],
    #     "buvid3": info['buvid3']
    # }
    # credential = Credential(**credential_args)
    # vu_meta = video_uploader.VideoMeta(
    #     tid = 231, 
    #     title = title, 
    #     tags = ['youtube'], 
    #     desc = 'via. youtube', 
    #     cover = 'static/video/test.webp',
    #     no_reprint = True
    # )
    # page = video_uploader.VideoUploaderPage(
    #     path = 'static/video/test.mp4',
    #     title = title,
    #     description='', 
    # )
    # uploader = video_uploader.VideoUploader([page], vu_meta, credential)

    # @uploader.on("__ALL__")
    # async def ev(data):
    #     print(data)

    # try:
    #     await uploader.start()
    # except bilibili_api.exceptions.NetworkException as e:
    #     print("bilibili_api 403，请尝试更新cookie信息")
    # except bilibili_api.exceptions.ResponseCodeException as e:
    #     print("需要输入验证码了\r\n", e)

sync(main())
