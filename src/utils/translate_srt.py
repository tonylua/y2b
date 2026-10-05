"""LLM-based SRT translator with intelligent sentence segmentation.

核心流程：
1. 句子重组：合并 YouTube 碎片字幕成完整句子
2. LLM 翻译：带上下文和术语表
3. 中文重切：按标点和长度切分
4. 时间轴重分配：按字数比例
"""
from typing import List, Optional, Callable, Dict
import time
import logging
import re
import json


class LLMTranslator:
    """基于 LLM 的字幕翻译器"""

    def __init__(
        self,
        llm_client,
        glossary: Optional[Dict[str, str]] = None,
        max_line_chars: int = 40,
        max_chars: int = 3000,
        batch_size: int = 5,
        batch_max_chars: int = 1200
    ):
        """
        初始化 LLM 翻译器

        参数:
            llm_client: LLMClient 实例（已初始化）
            glossary: 术语表
            max_line_chars: 中文每行最大字符数
            max_chars: 单句最大字符数（用于断句）
            batch_size: 单批最多几句
            batch_max_chars: 单批最多多少字符（按字符分批，避免输出被 max_tokens 截断）
        """
        self.llm_client = llm_client
        self.glossary = glossary or {}
        self.max_line_chars = max_line_chars
        self.max_chars = max_chars
        self.batch_size = batch_size
        self.batch_max_chars = batch_max_chars

        logging.info(f"Initialized LLM translator, batch_size={batch_size}, batch_max_chars={batch_max_chars}")

    def iter_batches(self, texts: List[str]):
        """按句数和字符数双上限切批，产出 (句下标列表, 字符数)。"""
        batch: List[int] = []
        chars = 0
        for i, text in enumerate(texts):
            if batch and (chars + len(text) > self.batch_max_chars or len(batch) >= self.batch_size):
                yield batch, chars
                batch, chars = [], 0
            batch.append(i)
            chars += len(text)
        if batch:
            yield batch, chars

    def _max_tokens_for(self, texts: List[str]) -> int:
        """按输入长度估输出预算：中文译文约为原文 1.5~2 倍，deepseek-flash 推理模型需要额外预留推理token。"""
        chars = sum(len(t) for t in texts)
        # deepseek-flash 推理模型：推理过程消耗大量token，需要预留足够空间
        # 实测：单句推理可达2500+ tokens，content才200 tokens
        # 策略：按字符数的4倍估算（覆盖推理+翻译），最小4096，最大16384
        estimated = int(chars * 4) + 1024
        return min(16384, max(4096, estimated))

    def _request_batch(self, texts: List[str], context_sentences: List[str] = None) -> Dict[str, str]:
        """发一次 LLM 请求，返回 {编号: 译文}。"""
        glossary_hint = ""
        if self.glossary:
            terms = [f"{en}: {zh}" for en, zh in list(self.glossary.items())[:20]]
            glossary_hint = f"\n**术语表（必须遵守）**：\n" + "\n".join(terms) + "\n"

        context_hint = ""
        if context_sentences:
            context_hint = "\n**前文上下文（参考，保持术语一致）**：\n" + "\n".join(f"- {s}" for s in context_sentences[-2:]) + "\n"

        numbered = "\n".join(f"{i+1}. {text}" for i, text in enumerate(texts))

        prompt = f"""你是专业的技术视频字幕翻译员。将以下英文句子翻译成中文，要求：
1. 符合中文表达习惯，避免机械直译
2. 保持技术术语一致性
3. 简洁流畅，适合口播字幕
{glossary_hint}{context_hint}
**待翻译句子**：
{numbered}

**输出格式**：严格的 JSON 对象，键为句子编号（字符串），值为中文翻译：
{{"1": "第一句中文", "2": "第二句中文", ...}}
"""
        return self.llm_client.chat_json(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self._max_tokens_for(texts),
        )

    def translate_texts(self, texts: List[str], context_sentences: List[str] = None) -> List[str]:
        """
        用 LLM 翻译文本列表，带上下文和术语表。

        参数:
            texts: 要翻译的句子列表
            context_sentences: 可选，前面的句子上下文（用于术语一致性）
        """
        if not texts:
            return []

        try:
            translations = self._request_batch(texts, context_sentences)
        except Exception as e:
            # 整批失败（网络/超长/截断）：退化成逐句翻译，别让一条失败毁掉整个字幕
            logging.error(f"LLM 批量翻译失败（{len(texts)} 句），逐句重试: {e}")
            if len(texts) == 1:
                # 单句翻译失败，直接抛出异常而非静默保留原文
                raise RuntimeError(f"LLM 单句翻译失败: {e}") from e
            return [
                single[0]
                for text in texts
                for single in [self.translate_texts([text], context_sentences=context_sentences)]
            ]

        # 按编号顺序提取翻译，缺号的单独重翻
        result: List[Optional[str]] = []
        missing: List[int] = []
        for i in range(len(texts)):
            value = translations.get(str(i + 1))
            if isinstance(value, str) and value.strip():
                result.append(value.strip())
            else:
                result.append(None)
                missing.append(i)

        for i in missing:
            logging.warning(f"第 {i + 1} 句没有拿到译文，单独重翻")
            try:
                result[i] = self.translate_texts([texts[i]], context_sentences=context_sentences)[0]
            except Exception as e:
                logging.error(f"第 {i + 1} 句单独重翻失败: {e}")
                # 抛出异常而非静默保留原文
                raise RuntimeError(f"字幕翻译失败（句 {i+1}）: {e}") from e

        return result  # type: ignore[return-value]

    def _merge_subtitles_to_sentences(self, subtitles: List[object]) -> List[Dict]:
        """
        将碎片化的字幕条目按句子边界合并成完整句子。

        合并规则：
        1. 英文句尾标点 (.!?:) 后强制断句
        2. 时间间隔超过 1.5 秒断句（说话停顿）
        3. 大写字母开头 + 前一条以标点结尾 → 新句
        4. 长度超过 max_chars 强制断句

        返回: [{'text': 完整句子, 'start_sec': 开始秒数, 'end_sec': 结束秒数}]
        """
        import srt as _srt
        from datetime import timedelta

        def to_seconds(td: timedelta) -> float:
            return td.total_seconds()

        sentences = []
        current_text = []
        current_start = None
        current_end = None

        for i, sub in enumerate(subtitles):
            start_sec = to_seconds(sub.start)
            end_sec = to_seconds(sub.end)
            text = sub.content.strip()

            if not text:
                continue

            # 初始化第一个句子
            if current_start is None:
                current_start = start_sec
                current_end = end_sec
                current_text.append(text)
                continue

            # 判断是否需要断句
            should_break = False
            prev_text = current_text[-1] if current_text else ''

            # 规则1：前一条以句尾标点结束
            if re.search(r'[.!?:]\s*$', prev_text):
                # 如果当前行以大写开头，很可能是新句
                if text and text[0].isupper():
                    should_break = True

            # 规则2：时间间隔超过1.5秒（说话停顿）
            if start_sec - current_end > 1.5:
                should_break = True

            # 规则3：累积长度过长
            combined_len = sum(len(t) for t in current_text) + len(text)
            if combined_len > self.max_chars:
                should_break = True

            if should_break and current_text:
                # 保存当前句子
                sentences.append({
                    'text': ' '.join(current_text),
                    'start_sec': current_start,
                    'end_sec': current_end
                })
                # 开始新句子
                current_text = [text]
                current_start = start_sec
                current_end = end_sec
            else:
                # 继续合并
                current_text.append(text)
                current_end = end_sec

        # 保存最后一个句子
        if current_text:
            sentences.append({
                'text': ' '.join(current_text),
                'start_sec': current_start,
                'end_sec': current_end
            })

        return sentences

    def _split_chinese_by_length(self, text: str, max_chars: int) -> List[str]:
        """
        按中文标点和长度切分文本。

        规则：
        - 强标点（。！？；…）：达到即断行
        - 弱标点（，、：）：仅超长时断行
        - 无标点超长：硬切
        """
        # 强标点：达到即断行；弱标点：仅超长时断行
        strong_punct = '。！？；…'
        weak_punct = '，、：'

        lines = []
        current_line = ''

        for char in text:
            current_line += char

            if char in strong_punct and current_line.strip():
                # 强标点：一句话结束，断行
                lines.append(current_line)
                current_line = ''
            elif len(current_line) >= max_chars:
                # 超长处理
                if char in weak_punct:
                    # 在弱标点处断行
                    lines.append(current_line)
                    current_line = ''
                elif char in strong_punct:
                    # 强标点也断（上面已处理）
                    pass
                else:
                    # 找最近的标点，没有就硬切
                    last_weak = max(
                        current_line.rfind(p) for p in weak_punct
                    )
                    if last_weak > len(current_line) * 0.3:  # 标点在后 70%
                        lines.append(current_line[:last_weak+1])
                        current_line = current_line[last_weak+1:]
                    else:
                        # 硬切
                        lines.append(current_line)
                        current_line = ''

        # 处理剩余部分
        if current_line.strip():
            lines.append(current_line)

        return [line.strip() for line in lines if line.strip()]

    def _redistribute_timing(self, lines: List[str], start_sec: float, end_sec: float) -> List[tuple]:
        """
        按各行字数比例重新分配时间轴。

        返回: [(line_text, line_start, line_end), ...]
        """
        if not lines:
            return []

        total_chars = sum(len(line) for line in lines)
        if total_chars == 0:
            return [(line, start_sec, end_sec) for line in lines]

        duration = end_sec - start_sec
        result = []
        current_time = start_sec

        for line in lines:
            line_duration = (len(line) / total_chars) * duration
            line_end = current_time + line_duration
            result.append((line, current_time, line_end))
            current_time = line_end

        return result

    def translate_srt_file(
        self,
        input_path: str,
        output_path: str,
        encoding: str = "utf-8",
        progress_callback: Optional[Callable[[int, int], None]] = None,
        bilingual: bool = False
    ) -> None:
        """
        翻译整个SRT文件

        参数:
            input_path: 输入文件路径
            output_path: 输出文件路径
            encoding: 文件编码
            progress_callback: 进度回调函数 (current, total)
            bilingual: True 时直接输出中英双语（英文整句 + 中文）
        """
        try:
            import srt as _srt
            from datetime import timedelta
            from .logger import structured_logger

            with open(input_path, 'r', encoding=encoding) as f:
                subtitles = list(_srt.parse(f.read()))

            # Step 1: 合并成句子
            sentences = self._merge_subtitles_to_sentences(subtitles)
            logging.info(f"Merged {len(subtitles)} subtitle entries into {len(sentences)} sentences")

            # Step 2: 批量翻译句子（带上下文）
            sentence_texts = [s['text'] for s in sentences]
            translated_sentences = []
            context = []  # 维护前文上下文

            # 记录翻译开始
            import os
            video_id = os.path.basename(input_path).split('.')[0]
            structured_logger.log_subtitle_translate_start(
                video_id, 'en', 'zh', len(sentence_texts)
            )
            translate_start_time = time.time()

            for batch_idx, (indices, batch_chars) in enumerate(self.iter_batches(sentence_texts)):
                batch = [sentence_texts[i] for i in indices]
                logging.info(f"翻译批次: {len(batch)} 句 / {batch_chars} 字符 (句 {indices[0] + 1}-{indices[-1] + 1})")

                # 翻译时带上前一个 batch 的最后 2 句
                translated_sentences.extend(self.translate_texts(batch, context_sentences=context))

                # 更新上下文（保留最后 2 句英文）
                context = sentence_texts[max(0, indices[-1] - 1):indices[-1] + 1]

                # 细粒度进度回调
                completed = indices[-1] + 1
                if progress_callback:
                    progress_callback(completed, len(sentence_texts))

                # 记录翻译进度
                structured_logger.log_subtitle_translate_progress(video_id, completed, len(sentence_texts))

            # Step 3 & 4: 中文重切 + 时间轴重分配
            result_subtitles = []
            sub_index = 1

            for sent, cn_text in zip(sentences, translated_sentences):
                # 按中文标点和长度切分
                cn_lines = self._split_chinese_by_length(cn_text, self.max_line_chars)

                # 按字数比例重新分配时间
                timed_lines = self._redistribute_timing(cn_lines, sent['start_sec'], sent['end_sec'])

                if bilingual:
                    # 双语模式：每个句子输出一条，英文整句在上，中文全部内容在下
                    result_subtitles.append(_srt.Subtitle(
                        index=sub_index,
                        start=timedelta(seconds=sent['start_sec']),
                        end=timedelta(seconds=sent['end_sec']),
                        content=f"{sent['text']}\n{cn_text}"
                    ))
                    sub_index += 1
                else:
                    # 纯中文模式：按切分后的行输出
                    for line_text, line_start, line_end in timed_lines:
                        result_subtitles.append(_srt.Subtitle(
                            index=sub_index,
                            start=timedelta(seconds=line_start),
                            end=timedelta(seconds=line_end),
                            content=line_text
                        ))
                        sub_index += 1

            # 记录翻译完成
            translate_duration = time.time() - translate_start_time
            structured_logger.log_subtitle_translate_complete(video_id, translate_duration)

            logging.info(f"Generated {len(result_subtitles)} subtitle entries ({'bilingual' if bilingual else 'Chinese-only'}) from {len(sentences)} sentences")

            # 写入输出文件
            with open(output_path, 'w', encoding=encoding) as f:
                f.write(_srt.compose(result_subtitles))

            logging.info(f"Translation completed. Output saved to {output_path}")

        except KeyboardInterrupt:
            logging.info("\n用户中断了字幕翻译")
            raise


def has_cjk(text: str) -> bool:
    """文本里是否含有中日韩字符。"""
    return bool(re.search(r'[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]', text or ''))


def translate_video_title(
    title: str,
    llm_client,
    glossary: Optional[Dict[str, str]] = None,
    max_len: int = 70,
) -> str:
    """用 LLM 把视频标题翻译成中文。

    已经是中文、LLM 不可用或翻译失败时，都返回原标题。
    """
    if not title or has_cjk(title):
        return title

    glossary_hint = ''
    if glossary:
        terms = [f"{en}: {zh}" for en, zh in list(glossary.items())[:20]]
        glossary_hint = "\n**术语表（必须遵守）**：\n" + "\n".join(terms) + "\n"

    prompt = f"""你是 B 站技术区 UP 主的标题编辑。把下面的英文视频标题翻译成中文标题。

要求：
1. 准确传达原意，符合中文技术圈的表达习惯，可适度润色得更抓人，但不要标题党、不要夸大
2. 品牌名、框架名、语言名、缩写保留英文原文（如 Rust、Leptos、Dioxus、Next.js、WebAssembly、Topcoat）
3. 不要加引号、书名号、括号补充说明、不要加 emoji
4. 不要输出任何解释，只输出 title 字段
{glossary_hint}
**原标题**：
{title}

**输出格式**：严格的 JSON 对象：
{{"title": "中文标题"}}
"""
    try:
        data = llm_client.chat_json(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
        )
        translated = str(data.get('title', '')).strip()
        translated = re.sub(r'^[\s"\'`《【]+|[\s"\'`》】]+$', '', translated)
        if not translated or not has_cjk(translated):
            logging.warning(f"标题翻译结果无效，保留原标题: {translated!r}")
            return title
        if len(translated) > max_len:
            translated = translated[:max_len]
        return translated
    except Exception as e:
        logging.error(f"LLM 标题翻译失败: {e}")
        return title


def _parse_time(time_str: str) -> float:
    """解析 SRT 时间戳为秒数"""
    parts = time_str.replace(',', ':').split(':')
    if len(parts) == 4:
        h, m, s, ms = parts
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
    return 0.0


def merge_srt_files(original_path: str, translated_path: str, output_path: str, encoding: str = "utf-8", align_by: str = "index") -> None:
    """
    将两个 SRT 文件（原文 + 翻译）合并为一个双语 SRT。

    每条字幕会把原文和译文放在同一个条目里，用换行分隔。
    """
    def _read_blocks(path: str):
        text = open(path, 'r', encoding=encoding).read().strip()
        if not text:
            return []

        blocks = [b.strip() for b in re.split(r"\r?\n\r?\n", text) if b.strip()]
        parsed = []
        for b in blocks:
            lines = b.splitlines()
            if len(lines) < 2:
                continue
            idx = lines[0].strip()
            times = lines[1].strip()
            content = "\n".join(l.rstrip() for l in lines[2:]).strip()

            start_s, end_s = None, None
            try:
                start_str, end_str = times.split('-->')
                start_s = _parse_time(start_str.strip())
                end_s = _parse_time(end_str.strip())
            except Exception:
                pass

            parsed.append({'index': idx, 'time': times, 'content': content, 'start': start_s, 'end': end_s})
        return parsed

    originals = _read_blocks(original_path)
    translated = _read_blocks(translated_path)

    merged_blocks = []
    if align_by == 'index':
        max_len = max(len(originals), len(translated))
        for i in range(max_len):
            orig = originals[i] if i < len(originals) else None
            trans = translated[i] if i < len(translated) else None

            if orig and trans:
                content = f"{orig['content']}\n{trans['content']}"
                times = orig['time']
                idx = orig['index']
            elif orig:
                content = orig['content']
                times = orig['time']
                idx = orig['index']
            else:
                content = trans['content']
                times = trans['time']
                idx = trans['index']

            merged_blocks.append({'index': idx, 'time': times, 'content': content})

    elif align_by == 'time':
        used_t = set()

        def overlap(a_start, a_end, b_start, b_end):
            if a_start is None or a_end is None or b_start is None or b_end is None:
                return 0.0
            return max(0.0, min(a_end, b_end) - max(a_start, b_start))

        for orig in originals:
            best_idx = None
            best_overlap = 0.0
            for j, tr in enumerate(translated):
                if j in used_t:
                    continue
                ov = overlap(orig.get('start'), orig.get('end'), tr.get('start'), tr.get('end'))
                if ov > best_overlap:
                    best_overlap = ov
                    best_idx = j

            if best_idx is not None and best_overlap > 0:
                tr = translated[best_idx]
                used_t.add(best_idx)
                content = f"{orig['content']}\n{tr['content']}"
            else:
                content = orig['content']

            merged_blocks.append({'index': orig['index'], 'time': orig['time'], 'content': content})

        for j, tr in enumerate(translated):
            if j in used_t:
                continue
            merged_blocks.append({'index': tr['index'], 'time': tr['time'], 'content': tr['content']})
    else:
        raise ValueError(f"Unknown align_by: {align_by}")

    with open(output_path, 'w', encoding=encoding) as f:
        for block in merged_blocks:
            f.write(f"{block['index']}\n")
            f.write(f"{block['time']}\n")
            f.write(f"{block['content']}\n\n")
