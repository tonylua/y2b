import time
from typing import Callable, TypeVar, Any, Optional, Tuple, Dict
from functools import wraps

# # 使用示例
# if __name__ == "__main__":
#     # 示例1: 基本用法
#     @retry(max_retries=3, retry_delay=0.5)
#     def download_subtitles(video_id: str, save_path: str, need_subtitle: str) -> bool:
#         print(f"尝试下载 {video_id}...")
#         # 模拟失败
#         if video_id == "fail":
#             raise ConnectionError("连接失败")
#         return True
#
#     # 示例2: 自定义重试条件
#     @retry(
#         should_retry=lambda x: x is None,  # 返回None时重试
#         before_retry=lambda attempt, e: print(f"第{attempt}次重试...")
#     )
#     def get_data() -> Optional[Dict]:
#         print("获取数据...")
#         return None  # 模拟失败
#
#     # 测试
#     try:
#         download_subtitles("fail", "test.srt", "en")
#     except Exception as e:
#         print(f"最终失败: {e}")
#
#     try:
#         get_data()
#     except Exception as e:
#         print(f"数据获取失败: {e}")
# 
# 典型应用场景：
# 1. 网络请求：
# @retry(exceptions=(requests.ConnectionError, requests.Timeout))
# def fetch_url(url): ...
# 2. 数据库操作：
# @retry(exceptions=(sqlalchemy.exc.OperationalError,))
# def query_db(): ...
# 3. 带业务逻辑的重试：
# @retry(should_retry=lambda r: r["status"] != "done")
# def check_status(): ...

T = TypeVar('T')  # 泛型类型，表示任意返回类型

def retry(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    exceptions: Tuple[Exception, ...] = (Exception,),
    should_retry: Optional[Callable[[Any], bool]] = None,
    before_retry: Optional[Callable[[int, Exception], None]] = None,
):
    """
    通用重试装饰器
    
    Args:
        max_retries: 最大重试次数
        retry_delay: 重试间隔(秒)
        exceptions: 要捕获的异常类型
        should_retry: 自定义重试判断函数 (接收异常或返回值)
        before_retry: 重试前的回调 (接收重试次数和异常)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if result is None:
                        print(f"[Retry] Got None result, triggering retry {attempt}")
                        raise RetryableError("Result is None")
                    # 如果有自定义判断函数且返回False则重试
                    if should_retry and should_retry(result):
                        raise RetryableError(result)
                    return result
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        break
                        
                    if before_retry:
                        before_retry(attempt, e)
                        
                    time.sleep(retry_delay)
            raise last_exception  # 抛出最后一次异常
        return wrapper
    return decorator

class RetryableError(Exception):
    """用于should_retry触发重试的异常"""
    def __init__(self, result: Any):
        self.result = result

