import argparse
import torch
from transformers import MarianMTModel, MarianTokenizer
import srt
from typing import List
import time

class LocalTranslator:
    def __init__(self, model_name="Helsinki-NLP/opus-mt-en-zh"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = MarianTokenizer.from_pretrained(model_name)
        self.model = MarianMTModel.from_pretrained(model_name, resume_download=True).to(self.device)
        print(f"Loaded {model_name} on {self.device}")

    def translate_batch(self, texts: List[str]) -> List[str]:
        """批量翻译提高效率"""
        inputs = self.tokenizer(
            texts, 
            return_tensors="pt", 
            padding=True, 
            truncation=True,
            max_length=512
        ).to(self.device)
        
        outputs = self.model.generate(**inputs)
        return self.tokenizer.batch_decode(outputs, skip_special_tokens=True)

def parse_srt(file_path: str) -> List[srt.Subtitle]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return list(srt.parse(f.read()))

def translate_srt(
    input_file: str, 
    output_file: str,
    batch_size: int = 8,
    max_chars: int = 1000
):
    # 初始化本地翻译器
    translator = LocalTranslator()
    
    # 解析SRT文件
    subtitles = parse_srt(input_file)
    
    # 批量处理提高效率
    translated_subs = []
    current_batch = []
    batch_indices = []
    
    for i, sub in enumerate(subtitles):
        if len(sub.content) > max_chars:
            print(f"Warning: Subtitle {i} exceeds {max_chars} characters")
            translated_subs.append(sub)  # 跳过过长的文本
            continue
            
        current_batch.append(sub.content)
        batch_indices.append(i)
        
        if len(current_batch) >= batch_size:
            # 翻译当前批次
            start_time = time.time()
            translated_texts = translator.translate_batch(current_batch)
            print(f"Translated {len(current_batch)} lines in {time.time()-start_time:.2f}s")
            
            # 创建翻译后的字幕
            for idx, text in zip(batch_indices, translated_texts):
                original = subtitles[idx]
                translated_subs.append(srt.Subtitle(
                    index=original.index,
                    start=original.start,
                    end=original.end,
                    content=text
                ))
            
            # 重置批次
            current_batch = []
            batch_indices = []
    
    # 处理剩余批次
    if current_batch:
        translated_texts = translator.translate_batch(current_batch)
        for idx, text in zip(batch_indices, translated_texts):
            original = subtitles[idx]
            translated_subs.append(srt.Subtitle(
                index=original.index,
                start=original.start,
                end=original.end,
                content=text
            ))
    
    # 写入输出文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(srt.compose(translated_subs))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Offline SRT Translator using OPUS-MT')
    parser.add_argument('input', help='Input SRT file path')
    parser.add_argument('output', help='Output SRT file path')
    parser.add_argument('--batch_size', type=int, default=8, help='Translation batch size')
    args = parser.parse_args()
    
    translate_srt(args.input, args.output, args.batch_size)
    print(f"Translation complete. Output saved to {args.output}")
