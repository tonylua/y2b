"""LLM 客户端封装（云端 API）。

提供：
- 配置加载
- OpenAI 客户端初始化
- 错误重试
- Token 使用统计
"""
import json
import logging
import os
import time
from typing import Optional, Dict, Any

from openai import OpenAI, APIError, APITimeoutError


class LLMConfig:
    """LLM 配置加载"""
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(__file__), '..', '..', 'config', '_llm.json'
            )

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载配置，不存在或解析失败返回禁用状态"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load LLM config from {self.config_path}: {e}")
            return {"enabled": False}

    @property
    def enabled(self) -> bool:
        return self.config.get('enabled', False)

    @property
    def base_url(self) -> str:
        return self.config.get('base_url', 'https://api.deepseek.com/v1')

    @property
    def api_key(self) -> str:
        return self.config.get('api_key', '')

    @property
    def model(self) -> str:
        return self.config.get('model', 'deepseek-chat')

    def feature_enabled(self, feature: str) -> bool:
        return self.config.get('features', {}).get(feature, False)

    def get_translation_config(self) -> Dict[str, Any]:
        return self.config.get('translation', {
            'mode': 'sentence',
            'max_line_chars': 40,
            'temperature': 0.3,
            'max_tokens': 2048
        })


class LLMClient:
    """LLM 客户端，处理调用和重试"""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = None

        if config.enabled:
            self._init_client()

    def _init_client(self):
        """初始化 OpenAI 客户端"""
        if not self.config.api_key:
            raise ValueError("LLM enabled but api_key is empty in config/_llm.json")

        self.client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout=60.0
        )
        logging.info(f"Initialized LLM client: {self.config.model} @ {self.config.base_url}")

    def chat(
        self,
        messages: list,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        retries: int = 3
    ) -> str:
        """调用 LLM，返回文本内容"""
        if not self.client:
            raise RuntimeError("LLM client not initialized")

        trans_cfg = self.config.get_translation_config()
        if temperature is None:
            temperature = trans_cfg.get('temperature', 0.3)
        if max_tokens is None:
            max_tokens = trans_cfg.get('max_tokens', 2048)

        last_error = None
        for attempt in range(retries):
            try:
                kwargs = {
                    'model': self.config.model,
                    'messages': messages,
                    'temperature': temperature,
                    'max_tokens': max_tokens
                }
                if response_format:
                    kwargs['response_format'] = response_format

                resp = self.client.chat.completions.create(**kwargs)
                return resp.choices[0].message.content

            except (APIError, APITimeoutError) as e:
                last_error = e
                if attempt < retries - 1:
                    wait = 2 ** attempt
                    logging.warning(f"LLM API error (attempt {attempt+1}/{retries}): {e}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logging.error(f"LLM API failed after {retries} retries: {e}")

        raise last_error
