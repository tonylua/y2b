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

## 清理旧版本地翻译缓存

2026-09 重构为 LLM-only 翻译（commit 9f6f115）之前，本项目用 MarianMT 本地模型翻译字幕，
会在机器上留下约 3GB 遗留物：HuggingFace 缓存里的 opus-mt 模型权重 + 项目 venv 里的
`torch`/`transformers`/`sentencepiece`/`sacremoses`。升级后可用下面任一方式回收。

**推荐：清理脚本**（Windows/Linux 通用，默认 dry-run 预览，加 `--yes` 才执行）：

```bash
python cleanup_legacy_models.py          # 预览会删什么
python cleanup_legacy_models.py --yes    # 实际执行
```

脚本只删两样东西：HF 缓存里 `Helsinki-NLP/opus-mt-en-zh`、`opus-mt-tc-big-en-zh`
两个模型的目录，以及**本项目 `.venv` 内**的上述 4 个包。HF 缓存里的其他模型、系统
Python、其他项目的 venv、uv/pip 下载缓存一律不碰。若 `pyproject.toml` 仍声明这些
依赖（尚未升级的旧部署），脚本会自动中止。

**或手动 one-liner**：

```bash
# Linux / macOS：删模型权重（尊重 HF_HOME）
rm -rf "${HF_HOME:-$HOME/.cache/huggingface}/hub/models--Helsinki-NLP--opus-mt-tc-big-en-zh" \
       "${HF_HOME:-$HOME/.cache/huggingface}/hub/models--Helsinki-NLP--opus-mt-en-zh"

# Windows PowerShell
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface\hub\models--Helsinki-NLP--opus-mt-tc-big-en-zh",
                            "$env:USERPROFILE\.cache\huggingface\hub\models--Helsinki-NLP--opus-mt-en-zh" -ErrorAction SilentlyContinue

# venv 旧依赖（项目根目录执行；按 pyproject.toml 同步，多余包会被移除）
uv sync
```

注意：`uv cache clean` 是全局的，会清掉**其他项目**共用的 torch 轮子（下次要重新下载 1GB+），本项目清理不需要它。

## 上传后自动加入合集

`bilibili-api-python` 17.4.2（2026-06 最新版）的 `VideoMeta` 不支持投稿时指定合集，
项目改为直接调用创作中心合集 API（与浏览器投稿页同源，见 `src/utils/bili_season.py`）。
上传成功后（Web 和 CLI 两条路径都会触发），会按 `config/_upload.json` 把视频追加到
指定合集的「正片」小节末尾：

```json
{
  "season_id": 1100651,
  "season_title": ""
}
```

- `season_id` 与 `season_title` 二选一，优先 `season_id`；两者都留空则不启用。
- 查看账号下所有合集及其 `season_id`：`python cli/seasons.py`
- 该文件被 gitignore（账号相关），每台部署机各自配置。
- 加合集失败只打日志、不影响上传结果；找不到合集/取不到 cid 时会输出原因。

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
