from typing import List, Optional, Callable
import time
import logging
import re


def _parse_time(t: str) -> float:
    """Parse SRT time format 'HH:MM:SS,mmm' to seconds (float)."""
    # Remove whitespace
    t = t.strip()
    # Accept both ',' and '.' for milliseconds
    try:
        hh, mm, ss_ms = t.split(':')
        ss, ms = ss_ms.replace('.', ',').split(',')
        return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0
    except Exception:
        # fallback simple parse
        m = re.match(r"(?:(\d+):)?(\d+):(\d+)[,.](\d+)", t)
        if not m:
            raise ValueError(f"Invalid SRT time string: {t}")
        hh = int(m.group(1) or 0)
        mm = int(m.group(2))
        ss = int(m.group(3))
        ms = int(m.group(4))
        return hh * 3600 + mm * 60 + ss + ms / 1000.0

class SRTTranslator:
    def __init__(
        self,
        model_name: str = "Helsinki-NLP/opus-mt-en-zh",
        device: Optional[str] = None,
        batch_size: int = 8,
        max_chars: int = 1000
    ):
        """
        初始化本地字幕翻译器
        
        参数:
            model_name: 预训练模型名称/路径
            device: 指定设备 (None自动检测)
            batch_size: 翻译批处理大小
            max_chars: 单条字幕最大字符数
        """
        # delayed imports so the module can be loaded without heavy ML deps
        try:
            import torch
            from transformers import MarianMTModel, MarianTokenizer
        except Exception as e:
            raise RuntimeError("SRTTranslator requires torch and transformers to be installed") from e

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size
        self.max_chars = max_chars
        
        # 初始化模型
        # imported inside __init__ so unit tests that only use merging don't need heavy packages
        self.tokenizer = MarianTokenizer.from_pretrained(model_name)
        self.model = MarianMTModel.from_pretrained(
            model_name,
            resume_download=True
        ).to(self.device)
        
        logging.info(f"Initialized translator with {model_name} on {self.device}")

    def translate_texts(self, texts: List[str]) -> List[str]:
        """批量翻译文本列表"""
        if not texts:
            return []
            
        inputs = self.tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512
        ).to(self.device)
        
        outputs = self.model.generate(**inputs)
        return self.tokenizer.batch_decode(outputs, skip_special_tokens=True)

    def translate_srt_file(
        self,
        input_path: str,
        output_path: str,
        encoding: str = "utf-8",
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> None:
        """
        翻译整个SRT文件
        
        参数:
            input_path: 输入文件路径
            output_path: 输出文件路径
            encoding: 文件编码
            progress_callback: 进度回调函数 (current, total)
        """
        try:
            import srt
            with open(input_path, 'r', encoding=encoding) as f:
                subtitles = list(srt.parse(f.read()))
            
            total_subs = len(subtitles)
            translated_subs = []
            current_batch = []
            batch_indices = []
            
            for i, sub in enumerate(subtitles):
                if len(sub.content) > self.max_chars:
                    logging.warning(f"Subtitle {i} exceeds {self.max_chars} characters")
                    translated_subs.append(sub)
                    continue
                    
                current_batch.append(sub.content)
                batch_indices.append(i)
                
                if len(current_batch) >= self.batch_size:
                    self._process_batch(current_batch, batch_indices, subtitles, translated_subs)
                    if progress_callback:
                        progress_callback(len(translated_subs), total_subs)
                    current_batch = []
                    batch_indices = []
            
            if current_batch:
                self._process_batch(current_batch, batch_indices, subtitles, translated_subs)
                if progress_callback:
                    progress_callback(len(translated_subs), total_subs)
            
            # 写入输出文件
            with open(output_path, 'w', encoding=encoding) as f:
                f.write(srt.compose(translated_subs))
            
            logging.info(f"Translation completed. Output saved to {output_path}")
        except KeyboardInterrupt:
            logging.info("\n用户中断了字幕翻译")
            raise

    def _process_batch(
        self,
        batch: List[str],
        indices: List[int],
        original_subs: List[object],
        output_subs: List[object]
    ) -> None:
        """处理单个翻译批次（类内部方法）"""
        start_time = time.time()
        try:
            translated = self.translate_texts(batch)
            for idx, text in zip(indices, translated):
                original = original_subs[idx]
                # 延迟导入 srt 以便模块可以被测试导入
                import srt as _srt
                output_subs.append(_srt.Subtitle(
                    index=original.index,
                    start=original.start,
                    end=original.end,
                    content=text
                ))
            elapsed = time.time() - start_time
            logging.debug(f"Translated {len(batch)} lines in {elapsed:.2f}s")
        except Exception as e:
            logging.error(f"Translation failed: {str(e)}")
            # 失败时保留原文
            for idx in indices:
                output_subs.append(original_subs[idx])

    def merge_srt_files(
        self,
        original_path: str,
        translated_path: str,
        output_path: str,
        encoding: str = "utf-8",
    ) -> None:
        """
        将两个 SRT 文件（原文 + 翻译）合并为一个双语 SRT。

        每条字幕会把原文和译文放在同一个条目里，用换行分隔。
        对齐策略：按索引逐条合并；如果长度不一致，会把其中缺失的条目按原样追加。
        """
        merge_srt_files(original_path, translated_path, output_path, encoding=encoding)
def merge_srt_files(original_path: str, translated_path: str, output_path: str, encoding: str = "utf-8", align_by: str = "index") -> None:
    """
    将两个 SRT 文件（原文 + 翻译）合并为一个双语 SRT（模块级函数）。

    每条字幕会把原文和译文放在同一个条目里，用换行分隔。对齐策略：按索引逐条合并；
    如果长度不一致，会把其中缺失的条目按原样追加。
    """
    # Minimal SRT merge implementation that does not depend on the external `srt` package.
    def _read_blocks(path: str):
        text = open(path, 'r', encoding=encoding).read().strip()
        if not text:
            return []

        # SRT blocks are usually separated by two newlines; handle CRLF and LF
        blocks = [b.strip() for b in re.split(r"\r?\n\r?\n", text) if b.strip()]
        parsed = []
        for b in blocks:
            lines = b.splitlines()
            if len(lines) < 2:
                continue
            idx = lines[0].strip()
            times = lines[1].strip()
            content = "\n".join(l.rstrip() for l in lines[2:]).strip()
            # try extract start/end times
            start_s, end_s = None, None
            try:
                start_str, end_str = times.split('-->')
                start_s = _parse_time(start_str.strip())
                end_s = _parse_time(end_str.strip())
            except Exception:
                start_s = None
                end_s = None
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
        # Match by timestamp overlap: for each original, find the translated block with max overlap
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

        # Add leftover translated blocks that did not match
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

    


def main():
    """命令行接口，支持翻译和合并两种操作

    用法示例：
      - 翻译： python translate_srt.py input.srt output.srt
      - 只翻译： python translate_srt.py --translate-only input.srt output.srt
      - 合并： python translate_srt.py --merge --translated translated.srt input.srt output.srt --align-by time
    """
    import argparse
    parser = argparse.ArgumentParser(description='Offline SRT Translator / SRT Merger')
    parser.add_argument('input', nargs='?', help='Input SRT file path (for translate or merge)')
    parser.add_argument('output', nargs='?', help='Output SRT file path')
    parser.add_argument('--merge', action='store_true', help='Merge two srt files (original + translated)')
    parser.add_argument('--translated', help='When using --merge: the translated SRT path')
    parser.add_argument('--align-by', choices=['index', 'time'], default='index', help='Merge alignment strategy')
    parser.add_argument('--translate-only', action='store_true', help='Only translate input SRT to output (no merge)')
    parser.add_argument('--batch_size', type=int, default=8, help='Batch size for translation')
    parser.add_argument('--model', type=str, default="Helsinki-NLP/opus-mt-en-zh", help='Model name')
    parser.add_argument('--log', type=str, default="INFO", help='Logging level')
    args = parser.parse_args()

    logging.basicConfig(level=args.log.upper())

    if args.merge:
        if not args.input or not args.translated or not args.output:
            parser.error('for --merge you must provide input, --translated and output')
        merge_srt_files(args.input, args.translated, args.output, encoding='utf-8', align_by=args.align_by)
        print(f"Merged {args.input} + {args.translated} -> {args.output} (align_by={args.align_by})")
        return

    # Default: translate (if input+output provided) or translate-only
    if not args.input or not args.output:
        parser.error('input and output are required for translation')

    try:
        translator = SRTTranslator(
            model_name=args.model,
            batch_size=args.batch_size
        )
    except RuntimeError as e:
        print(f"Translator cannot initialize: {e}")
        raise

    translator.translate_srt_file(args.input, args.output)
    print(f"Translated {args.input} -> {args.output}")

if __name__ == "__main__":
    main()
