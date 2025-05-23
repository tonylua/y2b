from enum import Enum

class Route(str, Enum):
    LOGIN = 'login'
    DOWNLOAD = 'download'
    LIST = 'list_page'
    PREVIEW = 'preview'
    UPLOAD = 'upload'

# 注意和 schema.sql 的同步
class VideoStatus(str, Enum):
    PENDING = 'pending'
    DOWNLOADING = 'downloading'
    DOWNLOADED = 'downloaded'
    UPLOADING = 'uploading'
    UPLOADED = 'uploaded'
    ERROR = 'error'
