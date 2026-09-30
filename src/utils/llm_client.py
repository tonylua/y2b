"""LLM 客户端封装（云端 API）。

提供：
- 配置加载
- OpenAI 客户端初始化
- 错误重试
- Token 使用统计
"""
import json
import re
import logging
import os
import time
from typing import Optional, Dict, Any

from openai import OpenAI, APIError, APITimeoutError


def _strip_code_fences(text: str) -> str:
    """去掉 LLM 常见的 ```json ... ``` 包裹。"""
    t = (text or '').strip()
    if t.startswith('```'):
        t = re.sub(r'^```(?:json|JSON)?\s*', '', t)
        t = re.sub(r'\s*```$', '', t)
    return t.strip()


def _scan_balanced(text: str, start: int) -> int:
    """从 start（指向 '{'）开始扫描，返回配对的 '}' 下标；被截断返回 -1。"""
    depth = 0
    i = start
    in_str = False
    escaped = False
    while i < len(text):
        ch = text[i]
        if escaped:
            escaped = False
        elif ch == '\\':
            escaped = True
        elif ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def _escape_raw_newlines(text: str) -> str:
    """把 JSON 字符串内部的裸换行转成 \\n（模型偶尔会在值里换行）。"""
    out = []
    in_str = False
    escaped = False
    for ch in text:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == '\\':
            out.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            continue
        if in_str and ch in ('\n', '\r'):
            if ch == '\n':
                out.append('\\n')
            continue
        out.append(ch)
    return ''.join(out)


def parse_json_response(text: str) -> Dict[str, Any]:
    """宽容解析 LLM 返回：支持 markdown 代码块、前后多余文字、被截断的输出。

    大模型输出被 max_tokens 截断是很常见的失败形态，这里尽量救出已翻译的部分。
    """
    raw = _strip_code_fences(text)
    if not raw:
        raise ValueError('LLM 返回内容为空')

    start = raw.find('{')
    if start < 0:
        raise ValueError(f'LLM 返回里没有 JSON 对象: {raw[:120]!r}')

    candidates = []
    end = _scan_balanced(raw, start)
    if end > 0:
        candidates.append(raw[start:end + 1])
    else:
        # 输出被截断：丢掉最后一个不完整的键值对后补齐
        head = raw[start:]
        for cut in (head.rfind('",'), head.rfind('"'), head.rfind(',')):
            if cut > 0:
                candidates.append(head[:cut + 1] + '}')
        candidates.append(head + '}')

    tried = 0
    for cand in candidates:
        for attempt in (cand, _escape_raw_newlines(cand), re.sub(r',\s*([}\]])', r'\1', cand)):
            tried += 1
            try:
                data = json.loads(attempt)
            except Exception:
                continue
            if isinstance(data, dict):
                if tried > 1:
                    logging.warning(f'LLM JSON 返回经过修复后才解析成功（尝试 {tried} 次）')
                return data

    # 最后兜底：正则捞出所有完整的 "键": "值" 组合（能救截断、缺逗号等畸形输出）
    pairs = re.findall(r'"((?:[^"\\\n]|\\.)*)"\s*:\s*"((?:[^"\\\n]|\\.)*)"', raw)
    if pairs:
        repaired = {}
        for key, value in pairs:
            try:
                repaired[json.loads(f'"{key}"')] = json.loads(f'"{value}"')
            except Exception:
                repaired[key] = value
        logging.warning(f'LLM JSON 返回畸形，按正则捞回 {len(repaired)} 个键值对')
        return repaired

    raise ValueError(f'无法解析 LLM 返回的 JSON: {raw[:200]!r}')


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

    def chat_json(
        self,
        messages: list,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        attempts: int = 2
    ) -> Dict[str, Any]:
        """调用 LLM 并解析成 dict。返回不合法 JSON 时自动再要一次更严格的输出。"""
        last_error = None
        for attempt in range(attempts):
            content = self.chat(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            try:
                return parse_json_response(content)
            except ValueError as e:
                last_error = e
                logging.warning(
                    f"LLM 返回不是合法 JSON (attempt {attempt + 1}/{attempts}): {e}；"
                    f"原文: {str(content)[:300]}"
                )
                messages = list(messages) + [
                    {"role": "user", "content": "上一条回复无法解析，请只输出一个严格的 JSON 对象："
                                               "不要 markdown 代码块、不要注释、不要省略号、键值都用双引号。"}
                ]
        raise last_error
