from enum import Enum

class Route(str, Enum):
    LOGIN = 'login'
    DOWNLOAD = 'download'
    LIST = 'list_page'
    PREVIEW = 'preview'
    UPLOAD = 'upload'
    DOWNLOAD_PROGRESS = 'download_progress'

# 注意和 schema.sql 的同步
class VideoStatus(str, Enum):
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    DOWNLOADED = 'downloaded'
    UPLOADING = 'uploading'
    UPLOADED = 'uploaded'
    ERROR = 'error'

class DownloadStage(str, Enum):
    PREPARING = 'preparing'
    FETCHING_INFO = 'fetching_info'
    DOWNLOADING_VIDEO = 'downloading_video'
    DOWNLOADING_SUBTITLE = 'downloading_subtitle'
    PROCESSING_SUBTITLE = 'processing_subtitle'
    ADDING_SUBTITLE = 'adding_subtitle'
    PREPARING_UPLOAD = 'preparing_upload'
    UPLOADING = 'uploading'
    COMPLETED = 'completed'
    ERROR = 'error'


STAGE_NAMES = {
    DownloadStage.PREPARING: '准备中',
    DownloadStage.FETCHING_INFO: '获取视频信息',
    DownloadStage.DOWNLOADING_VIDEO: '下载视频',
    DownloadStage.DOWNLOADING_SUBTITLE: '下载字幕',
    DownloadStage.PROCESSING_SUBTITLE: '处理字幕',
    DownloadStage.ADDING_SUBTITLE: '添加字幕',
    DownloadStage.PREPARING_UPLOAD: '准备上传',
    DownloadStage.UPLOADING: '上传视频',
    DownloadStage.COMPLETED: '完成',
    DownloadStage.ERROR: '错误'
}
