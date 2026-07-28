# y2b

下载 YouTube 视频、添加双语字幕、上传到 Bilibili。

## 安装

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv sync
python config/init_cfg.py
python db/init_db.py
python src/index.py
```

- 更新 yt-dlp：`uv pip install 'yt-dlp==v2025.05.22'`（并手动更新 `pyproject.toml`）
- Windows 字体/ffmpeg：`winget install "FFmpeg (Essentials Build)"`
- Linux 中文字体：`sudo apt-get install fonts-arphic-ukai fonts-arphic-uming`

## CLI

```bash
# 1. 下载视频（返回 video_id）
python cli/download.py "https://www.youtube.com/watch?v=xxxxx"
# 输出: 完成! video_id=42

# 2. 添加双语字幕（下载+翻译+嵌入）
python cli/subtitle.py 42

# 3. 上传到 Bilibili
python cli/upload.py 42
```

### 仅下载字幕（不嵌入视频）

`subtitle.py` 支持只下载字幕，策略是**下载优先**：先从多个来源（YouTubeTranscriptApi → yt-dlp → youtube-dl）尽力下载目标语言；双语模式会尝试直接下载中英两份并合并（不走模型）。只有目标语言下载不到时才会**提示**是否用本地模型翻译，同意后才翻译。

```bash
# 用链接或视频 ID 直接下载，无需先入库；--lang: en/cn/bilingual（默认 bilingual）
python cli/subtitle.py --url "https://www.youtube.com/watch?v=xxxxx" -d --lang en

# 指定保存目录（默认 static/video/<日期>/）
python cli/subtitle.py --url "https://www.youtube.com/watch?v=xxxxx" -d --output ./subs

# 已入库记录只下载字幕；-y 表示下载不到时自动允许模型翻译（不询问）
python cli/subtitle.py 42 -d -y
```

- `--url` 支持 `watch?v=`、`youtu.be/`、`/shorts/`、`/embed/` 及裸视频 ID。
- 非交互环境（无法输入）默认**不翻译**，只保留已下载的字幕。
- 本地翻译模型方向为英译中（en→zh）。

### 程序化调用

```python
from src.utils.subtitle import download_subtitles
download_subtitles("<youtube_video_id>", "./out.srt", need_subtitle='bilingual')

# 已有原文/译文两个 SRT，直接合并（无需 torch/transformers）
from src.utils.translate_srt import merge_srt_files
merge_srt_files('video.en.srt', 'video.cn.srt', 'video.en_cn.srt')
```

嵌入字幕时字体/样式见 `src/utils/subtitle.py` 的 `prepare_ffmpeg_args`（Windows 会先把 SRT 转为 ASS）。

## Docker

```bash
# 代理配置见 ~/.docker/config.json 的 "proxies"，httpProxy/httpsProxy 指向本地代理

# 构建（非 pi 用 -f Dockerfile-amd64）
docker build --network=host -t flask-y2b:<VERSION> .

# 运行（--restart always 和 --rm 二选一）
docker run --restart always --net host -p 5000:5000 -e PORT=5000 \
  -v /root/move_video/static:/app/static \
  -v /root/move_video/config:/app/config \
  -v /root/move_video/db:/app/db \
  -d flask-y2b:<VERSION>

docker stats <containerId>    # 运行状态
docker logs -f <containerId>  # 实时输出
```

## DB

```bash
sqlite3 db/database.db
SELECT * FROM videos;
.schema videos
```

## 备注

- `bilibili_api` 上传补丁：编辑 `.../site-packages/bilibili_api/video_uploader.py`，
  把 `"porder": ...` 改为 `self.porder.__dict__() if self.porder else None`，并在 meta 中增加 `"source": self.source,`。
- flask 异步：`pip uninstall flask && pip install flask[async]`。
- yt-dlp 转换参数：`python cli_to_api.py --extractor-arg "youtube:player_client=ios"`。
