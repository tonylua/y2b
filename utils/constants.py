from enum import Enum

class Route(str, Enum):
    LOGIN = 'login'
    DOWNLOAD = 'download'
    PREVIEW = 'preview'
    UPLOAD = 'upload'
