from enum import Enum

class Route(str, Enum):
    LOGIN = 'login'
    DOWNLOAD = 'download'
    LIST = 'list_page'
    PREVIEW = 'preview'
    UPLOAD = 'upload'
