# 翻译质量改进总结

## 改进内容

### 1. 智能断句（sentence 模式）

**问题**：YouTube 字幕按显示时长切分，一句话被切成多条碎片，逐条翻译导致：
- 语义割裂：半句话独立翻译，上下文丢失
- 机械直译：`is take this array` → `是采取这个数组`（不符合中文习惯）
- 断句错位：中文硬套英文断点，可能在词中间切开

**解决方案**：三步流水线
```
碎片字幕 → [重组句子] → 完整英文句 → [整句翻译] → 完整中文句 → [中文重切] → 适合显示的行
```

1. **重组句子**：按句尾标点（`.!?`）、停顿间隔（>1.5s）、大写开头合并碎片
2. **整句翻译**：用 beam search（num_beams=4）翻译完整句子，保留语义
3. **中文重切**：按中文标点和意群断句
   - 强标点（`。！？；…`）：达到即断行
   - 弱标点（`，、：`）：仅超长时断行
   - 每行长度上限可配置（默认 40 字符）
4. **时间轴重分配**：按各行字数比例从原句时间跨度重新分配

### 2. 模型升级

- 旧模型：`Helsinki-NLP/opus-mt-en-zh`（2018 年基础版）
- 新模型：`Helsinki-NLP/opus-mt-tc-big-en-zh`（tc-big 版本）
  - 训练数据量更大
  - 对技术/编程内容支持更好
  - 长句、习语处理能力更强
  - 仍为 CPU-only 轻量模型（~500MB）

### 3. 术语表机制

- 位置：`config/glossary.json`
- 格式：`{ "英文": "中文", "_注释": "以_开头的键被忽略" }`
- 替换时机：翻译完成后，大小写不敏感强制替换
- 示例：
  ```json
  {
    "array": "数组",
    "callback": "回调",
    "promise": "Promise",
    "_说明": "编程术语，保持一致性"
  }
  ```

### 4. 双语模式优化

- 旧方案：按 index 合并英文/中文两个 SRT，要求条目数完全一致
- 新方案：sentence 模式直接输出双语条目（英文整句在上、中文翻译在下）
  - 天然对齐，无需后处理
  - 避免断句导致的条目数不匹配

### 5. 代码清理

- 移除旧的 `_translate_full` 和 `_translate_batch` 方法
- 移除无效的 `domain` 提示（MarianMT 不支持指令）
- 修正 beam search 参数（添加 `num_beams=4`）

## 效果对比

运行 `python demo_translation_quality.py` 查看详细对比。

### 场景 1：碎片翻译 vs 整句翻译

**输入（3 条碎片）**：
```
[1] So what we're going to do
[2] is take this array
[3] and sort it in place.
```

**旧方案（逐条翻译）**：
```
[1] 所以我们要做的
[2] 是采取这个数组        ❌ 机械直译
[3] 并就地排序它。
```

**新方案（sentence 模式）**：
```
合并: So what we're going to do is take this array and sort it in place.
翻译: 那么我们要做的是获取这个数组并就地排序。
重切: [按中文标点和长度切分成适合显示的行]
```

### 场景 2：断句错位 vs 中文重切

**长句**：`First, we need to initialize the array with default values, then iterate through each element.`

**旧方案（硬套英文断点）**：
```
[1] 首先，我们需要用默认值初    ❌ 切在词中间
[2] 始化数组，然后遍历每个元
[3] 素。
```

**新方案（按中文标点重切，max_line_chars=20）**：
```
[1] 首先，我们需要用默认值初始化数组，   ✅ 按逗号断句
[2] 然后遍历每个元素。
```

### 场景 3：术语不一致 vs 术语表

**输入**：`We pass a callback to the array method.`

**无术语表**：`我们向数组方法传递一个回叫函数。` ❌ callback → 回叫

**有术语表**：`我们向数组方法传递一个回调函数。` ✅ callback → 回调

## 使用说明

### 下载字幕时自动应用

```bash
# sentence 模式已是默认，无需额外参数
python cli/subtitle.py --url "https://youtube.com/watch?v=xxxxx" -d --lang bilingual
```

### 程序化调用

```python
from src.utils.subtitle import download_subtitles

# translate_mode='sentence' 已是默认
download_subtitles(
    video_id="xxxxx",
    save_path="./output.srt",
    need_subtitle='bilingual'
)
```

### 自定义术语表

编辑 `config/glossary.json`，添加项目特定术语：
```json
{
  "React": "React",
  "hook": "钩子",
  "component": "组件",
  "_注释": "React 相关术语"
}
```

### 调整中文断句长度

```python
from src.utils.translate_srt import SRTTranslator

tr = SRTTranslator(
    translate_mode='sentence',
    max_line_chars=30  # 默认 40，可根据视频分辨率调整
)
```

## 技术细节

### 句子重组规则

1. **强制断句**（新句子开始）：
   - 前一条以句尾标点结束（`.!?`）
   - 时间间隔 > 1.5 秒（说话停顿）
   - 当前条首字母大写 + 前一条非句尾标点
   
2. **保持合并**：
   - 连续字幕，无明显停顿
   - 小写开头（句子中间）
   - 前一条以逗号等弱标点结束

### 中文断句规则

- **强标点**（`。！？；…`）：出现即断行，一句话结束
- **弱标点**（`，、：`）：仅当前行超长时在此处断行
- **比例分配时间轴**：
  ```
  原句跨度 = 4.5s，切成 3 行（10/15/5 字符）
  → 行1: 1.5s, 行2: 2.25s, 行3: 0.75s
  ```

### 测试覆盖

- `tests/test_sentence_mode.py`：核心逻辑单元测试
  - 句子重组（停顿/标点/大小写）
  - 中文断句（强/弱标点）
  - 时间轴分配
  - 术语表替换
  - 双语输出

- `demo_translation_quality.py`：实际效果演示

## 后续优化方向

如需进一步提升质量，可考虑：

1. **更强模型**（需增加依赖）：
   - `NLLB-200-distilled-600M` + CTranslate2（CPU 加速，质量更好）
   - `Qwen2.5-3B-Instruct`（Ollama，中文母语级，可一步完成断句+翻译）

2. **上下文窗口**：翻译时带入前后 1-2 句，提升连贯性

3. **领域适配**：针对不同视频类型（编程/科普/娱乐）微调 beam search 参数

当前方案在 CPU 轻量约束下已达到较好平衡。
