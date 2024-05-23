from bilibili_api import sync, video_uploader, Credential

async def main():
    credential_args = {
        "sessdata": "e2b72b40%2C1731670127%2C69181%2A52CjDz_EYzZWmNRgBN7X5UP4d52LHP_J6F_Iia-4qOC80RBxnfuyEsiTuiZjAQSpYC7_4SVm5sc1ppZGN6aHVzTU8xUk1MNnhvUnVJSEVlQ1FMU0N6T0Zwc3VxVGtLY3QtM1BaU3lHWGhNWm1ZMll5WTZKem5UM0JyR1ZoNlhWeWprR3VQdExvU0x3IIEC",
        "bili_jct": "59f0068d272bbc781a36da16c9c47a1a",
        "buvid3": "9EFE8179-BC6D-6E30-1F14-3729A77033B863745infoc"
    }
    credential = Credential(**credential_args)
    vu_meta = video_uploader.VideoMeta(
        tid = 130, 
        title = 'title', 
        tags = ['音乐综合', '音乐'], 
        desc = '', 
        cover = 'video.webp',
        no_reprint = True
    )
    page = video_uploader.VideoUploaderPage(
        path = 'video.mp4',
        title = 'TestTitle1',
        description='Test简介1', 
    )
    uploader = video_uploader.VideoUploader([page], vu_meta, credential)

    @uploader.on("__ALL__")
    async def ev(data):
        print(data)

    await uploader.start()

sync(main())
