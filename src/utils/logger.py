"""统一日志系统 - 可核查、周期性过期自维护

功能：
1. 结构化日志（JSON格式）
2. 自动按天分割日志文件
3. 自动清理30天前的日志
4. 关键操作追踪（下载、上传、翻译、API调用）
"""
import os
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
import threading

# 日志根目录
LOG_DIR = Path(__file__).parent.parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

# 日志保留天数
LOG_RETENTION_DAYS = 30

# 最后一次清理时间（避免频繁扫描）
_last_cleanup = 0
_cleanup_lock = threading.Lock()


def _cleanup_old_logs():
    """清理30天前的日志文件"""
    global _last_cleanup
    now = time.time()

    # 每天最多清理一次
    with _cleanup_lock:
        if now - _last_cleanup < 86400:
            return
        _last_cleanup = now

    cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    cutoff_str = cutoff.strftime('%Y%m%d')

    deleted = 0
    for log_file in LOG_DIR.glob('*.log'):
        try:
            # 文件名格式: y2b_20241205.log
            date_part = log_file.stem.split('_')[-1]
            if date_part < cutoff_str:
                log_file.unlink()
                deleted += 1
        except Exception as e:
            logging.warning(f"清理旧日志失败 {log_file}: {e}")

    if deleted > 0:
        logging.info(f"已清理 {deleted} 个超过 {LOG_RETENTION_DAYS} 天的日志文件")


class StructuredLogger:
    """结构化日志记录器"""

    def __init__(self, name: str = 'y2b'):
        self.name = name
        self._ensure_log_file()
        _cleanup_old_logs()

    def _ensure_log_file(self):
        """确保今天的日志文件存在"""
        today = datetime.now().strftime('%Y%m%d')
        self.log_file = LOG_DIR / f'{self.name}_{today}.log'

    def _write_log(self, level: str, event: str, data: Dict[str, Any]):
        """写入结构化日志"""
        self._ensure_log_file()

        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'event': event,
            **data
        }

        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            # 回退到标准logging
            logging.error(f"写入结构化日志失败: {e}")

    def log_download_start(self, video_id: str, url: str, user: str, resolution: str, subtitle: str):
        """记录下载开始"""
        self._write_log('INFO', 'download_start', {
            'video_id': video_id,
            'url': url,
            'user': user,
            'resolution': resolution,
            'subtitle': subtitle
        })

    def log_download_progress(self, video_id: str, stage: str, percent: int, message: str = ''):
        """记录下载进度"""
        self._write_log('DEBUG', 'download_progress', {
            'video_id': video_id,
            'stage': stage,
            'percent': percent,
            'message': message
        })

    def log_download_complete(self, video_id: str, duration_seconds: float, file_size: int):
        """记录下载完成"""
        self._write_log('INFO', 'download_complete', {
            'video_id': video_id,
            'duration_seconds': round(duration_seconds, 2),
            'file_size_mb': round(file_size / 1024 / 1024, 2)
        })

    def log_download_error(self, video_id: str, error: str, stage: str):
        """记录下载错误"""
        self._write_log('ERROR', 'download_error', {
            'video_id': video_id,
            'error': str(error),
            'stage': stage
        })

    def log_upload_start(self, video_id: str, title: str, file_path: str):
        """记录上传开始"""
        self._write_log('INFO', 'upload_start', {
            'video_id': video_id,
            'title': title,
            'file_path': file_path
        })

    def log_upload_progress(self, video_id: str, percent: int):
        """记录上传进度"""
        self._write_log('DEBUG', 'upload_progress', {
            'video_id': video_id,
            'percent': percent
        })

    def log_upload_complete(self, video_id: str, bvid: str, duration_seconds: float):
        """记录上传完成"""
        self._write_log('INFO', 'upload_complete', {
            'video_id': video_id,
            'bvid': bvid,
            'duration_seconds': round(duration_seconds, 2)
        })

    def log_upload_error(self, video_id: str, error: str, error_type: str):
        """记录上传错误"""
        self._write_log('ERROR', 'upload_error', {
            'video_id': video_id,
            'error': str(error),
            'error_type': error_type
        })

    def log_llm_request(self, request_id: str, texts_count: int, chars_count: int, model: str):
        """记录LLM请求"""
        self._write_log('INFO', 'llm_request', {
            'request_id': request_id,
            'texts_count': texts_count,
            'chars_count': chars_count,
            'model': model
        })

    def log_llm_response(self, request_id: str, duration_seconds: float, tokens_used: Optional[int] = None, success: bool = True):
        """记录LLM响应"""
        self._write_log('INFO', 'llm_response', {
            'request_id': request_id,
            'duration_seconds': round(duration_seconds, 2),
            'tokens_used': tokens_used,
            'success': success
        })

    def log_llm_error(self, request_id: str, error: str, error_code: Optional[int] = None):
        """记录LLM错误"""
        self._write_log('ERROR', 'llm_error', {
            'request_id': request_id,
            'error': str(error),
            'error_code': error_code
        })

    def log_subtitle_download(self, video_id: str, lang: str, method: str, success: bool):
        """记录字幕下载"""
        self._write_log('INFO', 'subtitle_download', {
            'video_id': video_id,
            'lang': lang,
            'method': method,
            'success': success
        })

    def log_subtitle_translate_start(self, video_id: str, source_lang: str, target_lang: str, sentences_count: int):
        """记录字幕翻译开始"""
        self._write_log('INFO', 'subtitle_translate_start', {
            'video_id': video_id,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'sentences_count': sentences_count
        })

    def log_subtitle_translate_progress(self, video_id: str, completed: int, total: int):
        """记录字幕翻译进度"""
        self._write_log('DEBUG', 'subtitle_translate_progress', {
            'video_id': video_id,
            'completed': completed,
            'total': total,
            'percent': round(completed * 100 / total, 1) if total > 0 else 0
        })

    def log_subtitle_translate_complete(self, video_id: str, duration_seconds: float):
        """记录字幕翻译完成"""
        self._write_log('INFO', 'subtitle_translate_complete', {
            'video_id': video_id,
            'duration_seconds': round(duration_seconds, 2)
        })

    def log_ffmpeg_start(self, video_id: str, input_file: str, output_file: str, subtitle_file: str):
        """记录ffmpeg开始"""
        self._write_log('INFO', 'ffmpeg_start', {
            'video_id': video_id,
            'input_file': input_file,
            'output_file': output_file,
            'subtitle_file': subtitle_file
        })

    def log_ffmpeg_progress(self, video_id: str, percent: int, time_seconds: float):
        """记录ffmpeg进度"""
        self._write_log('DEBUG', 'ffmpeg_progress', {
            'video_id': video_id,
            'percent': percent,
            'time_seconds': round(time_seconds, 2)
        })

    def log_ffmpeg_complete(self, video_id: str, duration_seconds: float):
        """记录ffmpeg完成"""
        self._write_log('INFO', 'ffmpeg_complete', {
            'video_id': video_id,
            'duration_seconds': round(duration_seconds, 2)
        })

    def log_ffmpeg_error(self, video_id: str, error: str, returncode: Optional[int] = None):
        """记录ffmpeg错误"""
        self._write_log('ERROR', 'ffmpeg_error', {
            'video_id': video_id,
            'error': str(error),
            'returncode': returncode
        })


# 全局实例
structured_logger = StructuredLogger()
