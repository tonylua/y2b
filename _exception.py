from enum import Enum


class ExceptionEnum(Enum):
    COOKIE_CONFIG_ERR = 0
    INVALID_COOKIE_ERR = 1

class CookieException(Exception):
    """
    ATTRIBUTE:
      @ msg: The error message
      @ errno: The error code
        0: Cookies are not configured in the json file
        1: invalid Cookie
    """
    def __init__(self, err, msg):
        self.errno = err
        self.msg = msg

    def __str__(self):
        return "[Cookie error: %s] %s" % (self.errno.value, self.msg)
