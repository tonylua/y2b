import threading
from typing import Dict, Optional
from datetime import datetime
from utils.constants import DownloadStage, STAGE_NAMES


class DownloadProgress:
    _instance = None
    _lock = threading.Lock()
    _progress_map: Dict[str, Dict] = {}

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def start_progress(self, video_id: str, title: str):
        with self._lock:
            video_id = str(video_id)
            self._progress_map[video_id] = {
                'video_id': video_id,
                'title': title,
                'stage': DownloadStage.PREPARING,
                'stage_name': STAGE_NAMES[DownloadStage.PREPARING],
                'progress': 0,
                'message': '',
                'started_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'completed': False,
                'error': None
            }

    def update_video_id(self, old_id: str, new_id: str):
        """更新视频ID，用于从临时ID切换到真实ID"""
        with self._lock:
            old_id = str(old_id)
            new_id = str(new_id)
            if old_id in self._progress_map:
                progress = self._progress_map.pop(old_id)
                progress['video_id'] = new_id
                self._progress_map[new_id] = progress

    def update_stage(
        self,
        video_id: str,
        stage: DownloadStage,
        progress: int = 0,
        message: str = ''
    ):
        with self._lock:
            video_id = str(video_id)
            if video_id not in self._progress_map:
                return
            self._progress_map[video_id].update({
                'stage': stage,
                'stage_name': STAGE_NAMES[stage],
                'progress': progress,
                'message': message,
                'updated_at': datetime.now().isoformat()
            })

    def complete_progress(self, video_id: str):
        with self._lock:
            video_id = str(video_id)
            if video_id not in self._progress_map:
                return
            self._progress_map[video_id].update({
                'stage': DownloadStage.COMPLETED,
                'stage_name': STAGE_NAMES[DownloadStage.COMPLETED],
                'progress': 100,
                'completed': True,
                'updated_at': datetime.now().isoformat()
            })

    def set_error(self, video_id: str, error_message: str):
        with self._lock:
            video_id = str(video_id)
            if video_id not in self._progress_map:
                return
            self._progress_map[video_id].update({
                'stage': DownloadStage.ERROR,
                'stage_name': STAGE_NAMES[DownloadStage.ERROR],
                'progress': self._progress_map[video_id].get('progress', 0),
                'message': error_message,
                'error': error_message,
                'completed': True,
                'updated_at': datetime.now().isoformat()
            })

    def get_progress(self, video_id: str) -> Optional[Dict]:
        with self._lock:
            return self._progress_map.get(str(video_id))

    def remove_progress(self, video_id: str):
        with self._lock:
            self._progress_map.pop(str(video_id), None)

    def get_all_progress(self) -> Dict[str, Dict]:
        with self._lock:
            return dict(self._progress_map)


download_progress = DownloadProgress()
