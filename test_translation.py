#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试翻译功能是否正常工作"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from utils.llm_client import LLMConfig, LLMClient
from utils.translate_srt import LLMTranslator

def test_translation():
    """测试批量翻译功能"""
    print("="*60)
    print("测试 DeepSeek 翻译功能（禁用推理模式）")
    print("="*60)

    cfg = LLMConfig()
    print(f"配置: model={cfg.model}, enabled={cfg.enabled}")

    client = LLMClient(cfg)
    translator = LLMTranslator(llm_client=client)

    test_texts = [
        'Hello world',
        'This is a test',
        'How are you today'
    ]

    print(f"\n待翻译文本: {test_texts}\n")

    try:
        result = translator.translate_texts(test_texts)
        print("\n✓ 翻译成功!")
        print(f"结果: {result}")
        return True
    except Exception as e:
        print(f"\n✗ 翻译失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_translation()
    sys.exit(0 if success else 1)
