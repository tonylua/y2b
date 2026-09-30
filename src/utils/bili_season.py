"""B 站创作中心「合集」（新版合集/SEASON）工具。

bilibili-api-python 17.4.2（截至 2026-06 的最新版）的 VideoMeta 不支持投稿时
指定合集，channel_series 模块又是旧版空间「列表」体系（api.bilibili.com/x/series），
与创作中心合集（member.bilibili.com/x2/creative/web/seasons，带"正片"分P）不是
一套系统。这里直接调用创作中心 Web API 补上这块能力，端点与浏览器投稿/编辑页同源：

  - 合集列表   GET  https://member.bilibili.com/x2/creative/web/seasons
  - 加入合集   POST https://member.bilibili.com/x2/creative/web/season/section/episodes/add
  - 查稿件 cid GET  https://member.bilibili.com/x/vupre/web/archive/view?bvid=...

实现参考 bilibili-API-collect docs/creativecenter/season.md 与 biliup PR#1598
（2026-02 合并，线上验证过）。

用法：上传完成后调用 `add_to_season_from_config()`，目标合集由
`config/_upload.json` 指定（season_id 或 season_title，二选一）：

    {
      "_comment": "上传后自动加入合集（可选）。season_id 与 season_title 二选一，优先 season_id",
      "season_id": 1100651,
      "season_title": ""
    }

合集加入失败只打印告警，不影响上传结果（视频已经发出去了）。
"""
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .sys import join_root_path

_SEASONS_URL = 'https://member.bilibili.com/x2/creative/web/seasons'
_EPISODES_ADD_URL = 'https://member.bilibili.com/x2/creative/web/season/section/episodes/add'
_ARCHIVE_VIEW_URL = 'https://member.bilibili.com/x/vupre/web/archive/view'
_PUBLIC_VIEW_URL = 'https://api.bilibili.com/x/web-interface/view'
_SECTION_URL = 'https://member.bilibili.com/x2/creative/web/season/section'

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://member.bilibili.com/platform/upload/video/frame',
    'Origin': 'https://member.bilibili.com',
}


def _bili_session(cookies: Dict[str, str]) -> requests.Session:
    """带 B 站 cookie 的 requests 会话。"""
    s = requests.Session()
    s.headers.update(_HEADERS)
    for name in ('SESSDATA', 'bili_jct', 'buvid3'):
        if cookies.get(name):
            s.cookies.set(name, cookies[name])
    return s


def _cookies_from_credential(credential) -> Dict[str, str]:
    """从 bilibili_api.Credential 提取 cookie 字典。"""
    return {
        'SESSDATA': credential.sessdata or '',
        'bili_jct': credential.bili_jct or '',
        'buvid3': credential.buvid3 or '',
    }


def list_seasons(cookies: Dict[str, str], pn: int = 1, ps: int = 50) -> List[Dict[str, Any]]:
    """列出账号下的所有合集（新版合集，含"正片"小节 id）。

    返回 [{season_id, title, section_id, section_title, ep_count}]，按 mtime 倒序。
    """
    sess = _bili_session(cookies)
    r = sess.get(_SEASONS_URL, params={
        'pn': pn, 'ps': ps, 'order': 'desc', 'sort': 'mtime', 'filter': 1,
    }, timeout=15)
    r.raise_for_status()
    payload = r.json()
    if payload.get('code') != 0:
        raise RuntimeError(f"获取合集列表失败: {payload.get('code')} {payload.get('message')}")

    seasons = []
    for item in payload.get('data', {}).get('seasons', []):
        info = item.get('season', {})
        sections = item.get('sections', {}).get('sections', [])
        first = sections[0] if sections else {}
        seasons.append({
            'season_id': info.get('id'),
            'title': info.get('title', ''),
            'section_id': first.get('id'),
            'section_title': first.get('title', ''),
            'ep_count': first.get('epCount'),
        })
    return seasons


def resolve_season(cookies: Dict[str, str],
                   season_id: Optional[int] = None,
                   season_title: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """按 id 或标题精确匹配合集，返回 list_seasons 中的一项。找不到返回 None。"""
    seasons = list_seasons(cookies)
    if season_id:
        for s in seasons:
            if s['season_id'] == int(season_id):
                return s
        # 按 id 没找到时，若同时配了标题则退而按标题匹配（换号、合集 id 变更的兜底）
    if season_title:
        for s in seasons:
            if s['title'] == season_title:
                return s
    return None


def get_archive_info(cookies: Dict[str, str],
                     aid: Optional[int] = None,
                     bvid: Optional[str] = None) -> Tuple[Optional[int], str]:
    """取自己稿件的 (cid, title)。

    优先用创作中心稿件接口（刚投稿、还在审核也能查，编辑页就靠它），
    失败再退公开 view API。
    """
    sess = _bili_session(cookies)

    if bvid:
        try:
            r = sess.get(_ARCHIVE_VIEW_URL, params={'bvid': bvid}, timeout=15)
            payload = r.json()
            if payload.get('code') == 0:
                videos = payload.get('data', {}).get('videos', [])
                archive = payload.get('data', {}).get('archive', {})
                if videos:
                    return videos[0].get('cid'), archive.get('title', '') or videos[0].get('title', '')
        except Exception as e:
            print(f'创作中心稿件接口查询失败: {e}')

    if aid:
        try:
            r = sess.get(_PUBLIC_VIEW_URL, params={'aid': aid}, timeout=15)
            payload = r.json()
            if payload.get('code') == 0:
                data = payload.get('data', {})
                return data.get('cid'), data.get('title', '')
        except Exception as e:
            print(f'公开 view API 查询失败: {e}')

    return None, ''


def is_video_in_season(cookies: Dict[str, str], section_id: int, aid: int,
                       max_pages: int = 5) -> bool:
    """视频是否已在合集小节中（用于避免重复添加）。

    合集视频多时分页查，最多 max_pages 页；接口异常视为「不在」，交由后续逻辑处理。
    """
    sess = _bili_session(cookies)
    try:
        for pn in range(1, max_pages + 1):
            r = sess.get(_SECTION_URL, params={'id': section_id, 'pn': pn, 'ps': 100},
                         timeout=15)
            payload = r.json()
            if payload.get('code') != 0:
                return False
            episodes = payload.get('data', {}).get('episodes', [])
            for ep in episodes:
                if ep.get('aid') == aid:
                    return True
            if len(episodes) < 100:
                break
    except Exception as e:
        print(f'查询合集成员失败: {e}')
    return False


def add_video_to_season(cookies: Dict[str, str], section_id: int,
                        aid: int, cid: int, title: str) -> Tuple[bool, str]:
    """把已投稿的视频加入合集（默认"正片"小节，追加到末尾）。

    返回 (是否成功, 说明消息)。
    """
    sess = _bili_session(cookies)
    bili_jct = cookies.get('bili_jct', '')
    body = {
        'sectionId': section_id,
        'episodes': [{
            'aid': aid,
            'cid': cid,
            'title': title,
            'charging_pay': 0,
        }],
        'csrf': bili_jct,
    }
    r = sess.post(_EPISODES_ADD_URL, params={'csrf': bili_jct}, json=body, timeout=15)
    r.raise_for_status()
    payload = r.json()
    if payload.get('code') != 0:
        return False, f"加入合集失败: {payload.get('code')} {payload.get('message')}"
    return True, 'ok'


def load_upload_config() -> Dict[str, Any]:
    """读取 config/_upload.json（不存在或损坏返回空 dict）。"""
    path = join_root_path('config/_upload.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f'读取 {path} 失败: {e}')
        return {}


def add_to_season_from_config(cookies: Dict[str, str],
                              aid: Optional[int], bvid: Optional[str],
                              title: str) -> Tuple[bool, str]:
    """按 config/_upload.json 的配置把刚上传的视频加入合集。

    未配置合集返回 (False, '')，调用方据此保持安静；
    其余情况返回 (是否成功, 人话消息)，任何异常都不抛出。
    """
    try:
        cfg = load_upload_config()
        season_id = cfg.get('season_id') or 0
        season_title = cfg.get('season_title') or ''
        if not season_id and not season_title:
            return False, ''

        season = resolve_season(cookies, season_id=season_id, season_title=season_title)
        if not season:
            target = f"id={season_id}" if season_id else f"标题 {season_title!r}"
            return False, f'未找到合集 {target}，可运行 python cli/seasons.py 查看已有合集'

        if not aid and bvid:
            # 上传回执缺 aid 时从 bvid 本地换算（纯函数，不发请求）
            from bilibili_api.utils.aid_bvid_transformer import bvid2aid
            aid = bvid2aid(bvid)
        if not aid:
            return False, f'无法确定稿件 aid（bvid={bvid}），未加入合集'

        cid, archive_title = get_archive_info(cookies, aid=aid, bvid=bvid)
        # 刚投稿可能立刻查不到，稍等重试一次
        if not cid:
            time.sleep(3)
            cid, archive_title = get_archive_info(cookies, aid=aid, bvid=bvid)
        if not cid:
            return False, f'无法获取稿件 cid（aid={aid} bvid={bvid}），未加入合集'

        if is_video_in_season(cookies, season['section_id'], aid):
            return True, f"视频已在合集「{season['title']}」中，跳过"

        ok, msg = add_video_to_season(
            cookies, season['section_id'], aid, cid, archive_title or title)
        if ok:
            return True, f"已加入合集「{season['title']}」"
        return False, msg
    except Exception as e:
        return False, f'加入合集时出错: {e}'
