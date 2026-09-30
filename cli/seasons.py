"""列出当前 B 站账号下的所有合集（新版合集/SEASON）。

用于给 config/_upload.json 填 season_id：

    python cli/seasons.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import setup_path, load_bili_cookies

setup_path()

from utils.bili_season import list_seasons


def main():
    cookies = load_bili_cookies()
    print(f"登录用户: {cookies.get('user_name', 'unknown')}\n")
    seasons = list_seasons(cookies)
    if not seasons:
        print('账号下没有合集（可在 B 站网页端「创作中心-内容管理-合集管理」创建）')
        return
    print(f"{'season_id':<12} {'section_id':<12} {'视频数':<6} 标题")
    for s in seasons:
        print(f"{s['season_id']:<12} {s['section_id']:<12} {str(s['ep_count']):<6} {s['title']}")
    print('\n把目标合集的 season_id 填入 config/_upload.json 即可在上传后自动加入该合集。')


if __name__ == '__main__':
    main()
