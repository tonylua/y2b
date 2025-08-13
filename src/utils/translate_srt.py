import torch
from transformers import MarianMTModel, MarianTokenizer
import srt
from typing import List, Optional
import time
import logging

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
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.batch_size = batch_size
        self.max_chars = max_chars
        
        # 初始化模型
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
        encoding: str = "utf-8"
    ) -> None:
        """
        翻译整个SRT文件
        
        参数:
            input_path: 输入文件路径
            output_path: 输出文件路径
            encoding: 文件编码
        """
        # 解析SRT文件
        with open(input_path, 'r', encoding=encoding) as f:
            subtitles = list(srt.parse(f.read()))
        
        # 分批处理
        translated_subs = []
        current_batch = []
        batch_indices = []
        
        for i, sub in enumerate(subtitles):
            if len(sub.content) > self.max_chars:
                logging.warning(f"Subtitle {i} exceeds {self.max_chars} characters")
                translated_subs.append(sub)  # 保留原文
                continue
                
            current_batch.append(sub.content)
            batch_indices.append(i)
            
            if len(current_batch) >= self.batch_size:
                self._process_batch(current_batch, batch_indices, subtitles, translated_subs)
                current_batch = []
                batch_indices = []
        
        # 处理剩余批次
        if current_batch:
            self._process_batch(current_batch, batch_indices, subtitles, translated_subs)
        
        # 写入输出文件
        with open(output_path, 'w', encoding=encoding) as f:
            f.write(srt.compose(translated_subs))
        
        logging.info(f"Translation completed. Output saved to {output_path}")

    def _process_batch(
        self,
        batch: List[str],
        indices: List[int],
        original_subs: List[srt.Subtitle],
        output_subs: List[srt.Subtitle]
    ) -> None:
        """处理单个翻译批次"""
        start_time = time.time()
        try:
            translated = self.translate_texts(batch)
            for idx, text in zip(indices, translated):
                original = original_subs[idx]
                output_subs.append(srt.Subtitle(
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


def main():
    """命令行接口"""
    import argparse
    parser = argparse.ArgumentParser(description='Offline SRT Translator')
    parser.add_argument('input', help='Input SRT file path')
    parser.add_argument('output', help='Output SRT file path')
    parser.add_argument('--batch_size', type=int, default=8, help='Batch size for translation')
    parser.add_argument('--model', type=str, default="Helsinki-NLP/opus-mt-en-zh", help='Model name')
    parser.add_argument('--log', type=str, default="INFO", help='Logging level')
    args = parser.parse_args()
    
    logging.basicConfig(level=args.log.upper())
    
    translator = SRTTranslator(
        model_name=args.model,
        batch_size=args.batch_size
    )
    translator.translate_srt_file(args.input, args.output)

if __name__ == "__main__":
    main()
