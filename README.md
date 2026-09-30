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
- 本地翻译模型方向为英译中（en→zh），默认模型 `Helsinki-NLP/opus-mt-tc-big-en-zh`。

### 翻译质量：LLM 智能翻译

字幕翻译使用 LLM（大语言模型），流程为：

1. **重组句子**：把 YouTube 碎片化的字幕条按句尾标点、说话停顿（时间间隔 >1.5s）、大写开头等规则合并成完整英文句子；
2. **LLM 翻译**：以完整句子为单位翻译，带上下文（前2句）和术语表，避免半句翻译导致的语义割裂；
3. **中文重切**：按中文标点（强标点断句、弱标点仅超长时断）和长度上限重新切分成适合显示的行；
4. **时间轴重分配**：把原句时间跨度按各行字数比例重新分配。

双语模式（bilingual）下每个句子输出一条：英文整句在上、中文在下，天然对齐。

### 配置 LLM

**必需配置**：编辑 `config/_llm.json` 填写 API key

```json
{
  "enabled": true,
  "base_url": "https://api.deepseek.com/v1",
  "api_key": "sk-your-key",
  "model": "deepseek-chat",
  
  "features": {
    "term_extraction": true,      // 术语自动识别
    "context_translation": true   // 带上下文翻译
  }
}
```

**支持的服务**：
- DeepSeek（推荐）：约 ¥0.02/视频（10分钟），质量好
- OpenAI：兼容 API，修改 `base_url` 和 `model`
- 其他兼容 OpenAI API 的服务

**成本**：实时显示 token 消耗，翻译完成后显示总成本。

### 术语表

`config/glossary.json` 维护技术术语的固定译法（`{ "英文": "中文" }`，以 `_` 开头的键是注释）。翻译时会在**译文后**做大小写不敏感的强制替换，保证 `array→数组`、`callback→回调` 等术语一致。直接编辑该文件即可增删术语，无需改代码。

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
