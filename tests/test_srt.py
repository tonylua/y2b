import os
from src.utils.subtitle import download_subtitles

"""
测试下载中文字幕功能

此脚本用于测试 download_subtitles 函数是否能正确下载指定视频的中文字幕，
并保存到指定路径。
"""

def main():
    """
    主函数，用于执行字幕下载测试
    
    调用 download_subtitles 函数下载指定视频 ID 的中文字幕，
    并保存到当前脚本所在目录下的 123.srt 文件中。
    """
    save_srt = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"123.srt") 
    download_subtitles("AAkrmfkC1L4", save_srt, "cn")

if __name__ == "__main__":
    main()
