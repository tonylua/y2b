"""术语确认管理器 - 用于Web UI的术语确认流程"""
import json
import os
import threading
from typing import Dict, Optional
from .sys import join_root_path

class TermManager:
    """管理待确认术语的状态"""

    def __init__(self):
        self.pending_dir = join_root_path('temp', 'pending_terms')
        os.makedirs(self.pending_dir, exist_ok=True)
        self.confirm_events = {}  # video_id -> threading.Event
        self.confirmed_results = {}  # video_id -> Dict[str, str]

    def _get_pending_file(self, video_id: str) -> str:
        """获取待确认术语的临时文件路径"""
        return os.path.join(self.pending_dir, f"{video_id}.json")

    def set_pending_terms(self, video_id: str, terms: Dict[str, str]):
        """设置待确认术语并等待用户确认"""
        pending_file = self._get_pending_file(video_id)
        with open(pending_file, 'w', encoding='utf-8') as f:
            json.dump(terms, f, ensure_ascii=False, indent=2)

        # 创建事件用于阻塞等待
        event = threading.Event()
        self.confirm_events[video_id] = event

        # 阻塞等待前端确认（最多等待10分钟）
        event.wait(timeout=600)

        # 获取确认结果
        result = self.confirmed_results.pop(video_id, {})

        # 清理
        if os.path.exists(pending_file):
            os.remove(pending_file)
        self.confirm_events.pop(video_id, None)

        return result

    def get_pending_terms(self, video_id: str) -> Optional[Dict[str, str]]:
        """获取待确认术语（供前端调用）"""
        pending_file = self._get_pending_file(video_id)
        if not os.path.exists(pending_file):
            return None

        with open(pending_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def confirm_terms(self, video_id: str, accepted_terms: Dict[str, str]):
        """提交确认结果（供前端调用）"""
        self.confirmed_results[video_id] = accepted_terms

        # 唤醒等待的后台线程
        event = self.confirm_events.get(video_id)
        if event:
            event.set()

    def has_pending(self, video_id: str) -> bool:
        """检查是否有待确认术语"""
        return os.path.exists(self._get_pending_file(video_id))

# 全局单例
_term_manager = None

def get_term_manager() -> TermManager:
    global _term_manager
    if _term_manager is None:
        _term_manager = TermManager()
    return _term_manager
