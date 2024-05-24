from bilibili_api import sync, video_uploader, channel_series, Credential

async def main():

    credential_args = {
        "sessdata": "9e922d3e%2C1731980286%2Caff7a%2A52CjCgRPRYqstg4NpsvFe1t38d8ubJsYRC0uktnayrPadatkQPbOs9auaF0v-DQb_PvP8SVlZnTGV5LVRjSVY4d0pobXNTalhrbzg2Z2lyZWUtdGtkMU1kME1tbUxhRTBpMUFnV0xvVWtWU0JMNXpOMl9oMmpiZUtfM1pOMXRxc1o2NXlTdWxnN3N3IIEC",
        "bili_jct": "7befea972c4dca03cf48d4fa88715350",
        "buvid3": "9EFE8179-BC6D-6E30-1F14-3729A77033B863745infoc"
    }
    credential = Credential(**credential_args)
    vu_meta = video_uploader.VideoMeta(
        tid = 231, 
        title = '[英字] How to Create a Flask + React Project | Python Backend + React Frontend', 
        tags = ['youtube'], 
        desc = '', 
        cover = 'static/video.webp',
        no_reprint = True
    )
    page = video_uploader.VideoUploaderPage(
        path = 'static/with_srt_video.mp4',
        title = '[英字] How to Create a Flask + React Project | Python Backend + React Frontend',
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
