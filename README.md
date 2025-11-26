## uv

- uv venv --python 3.12 .venv
- source .venv/bin/activate
- uv sync
- python config/init_cfg.py
- python db/init_db.py
- python src/index.py

### update

- uv pip install 'yt-dlp==v2025.05.22'
- 手动更新 pyproject.toml

### fonts(win)

- winget install "FFmpeg (Essentials Build)"

## Docker

```
# ~/.docker/config.json
"proxies":
{
   "default":
   {
     "httpProxy": "http://127.0.0.1:7890",
     "httpsProxy": "http://127.0.0.1:7890",
     "noProxy": "localhost"
   }
}
}
```

```
# -f Dockerfile-amd64 非pi时
docker build --network=host -t flask-y2b:<VERSION> .

# --restart always 和 --rm 选其一
docker run --restart always --net host -p 5000:5000 -e PORT=5000 -v /root/move_video/static:/app/static -v /root/move_video/config:/app/config -v /root/move_video/db:/app/db -d flask-y2b:<VERSION>

# 查看运行状态
docker stats <containerId>

# 查看实时运行输出
docker logs -f <containerId>
```

---

</del> 
 
 ```

## 双语字幕（Bilingual SRT）

本项目现在支持生成双语字幕：把原始字幕与机器翻译的译文合并为一个 SRT 文件（原文在上，译文在下）。合并功能不依赖大型机器学习库，因此可以在不安装 torch / transformers 时使用；但如果需要自动翻译，仍需安装并配置这些库。

示例：

- 使用自动下载并生成双语（程序化调用）

```python
from src.utils.subtitle import download_subtitles
download_subtitles("<youtube_video_id>", "./out.srt", need_subtitle='bilingual')
```

- 如果已经有原文与译文两个 SRT 文件，可以直接合并：

```python
from src.utils.translate_srt import merge_srt_files
merge_srt_files('video.en.srt', 'video.cn.srt', 'video.en_cn.srt')
```

注意：ffmpeg 嵌入字幕时对字体和样式有一定要求（windows 会先把 SRT 转为 ASS），如果需要在视频上正确渲染中文或特殊字体，请参考 `src/utils/subtitle.py` 中 `prepare_ffmpeg_args` 的实现并调整 `FontName` 设置。
sudo apt-get install fonts-arphic-ukai fonts-arphic-uming
pip install -r requirements.txt
vim /usr/local/lib/python3.11/dist-packages/bilibili_api/video_uploader.py
# 或 vim app-venv/lib/python3.10/site-packages/bilibili_api/video_uploader.py
# 修改这行
"porder": self.porder.__dict__() if self.porder else None,
# 56x行meta中增加：
"source": self.source,
pip uninstall flask
pip install flask[async]
## DB
sudo apt-get install sqlite3
python db/init_db.py
sqlite3 db/database.db
SELECT * FROM videos;
.schema videos
## 转换参数
python cli_to_api.py --extractor-arg "youtube:player_client=ios"
</del>
