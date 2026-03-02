#!/usr/bin/env python3
"""
自动化升级 bilibili-api-python 到最新版本

此脚本会：
1. 检查当前安装的 bilibili-api-python 版本
2. 获取最新的 bilibili-api-python 版本
3. 如果有新版本，升级 bilibili-api-python
4. 更新 pyproject.toml 文件中的 bilibili-api-python 版本
5. 如果当天已经检查过，则跳过
"""
import os
import re
import subprocess
import sys
from datetime import datetime
from typing import Optional


def get_last_check_date() -> Optional[str]:
    """
    获取上次检查日期

    Returns:
        Optional[str]: 上次检查日期 (YYYY-MM-DD)，如果没有记录则返回 None
    """
    try:
        check_file = '.bilibili-api-last-check'
        if os.path.exists(check_file):
            with open(check_file, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return None
    except Exception as e:
        print(f"读取上次检查日期失败: {e}")
        return None


def save_last_check_date():
    """保存今天的检查日期"""
    try:
        check_file = '.bilibili-api-last-check'
        today = datetime.now().strftime('%Y-%m-%d')
        with open(check_file, 'w', encoding='utf-8') as f:
            f.write(today)
    except Exception as e:
        print(f"保存检查日期失败: {e}")


def is_today_checked() -> bool:
    """
    检查今天是否已经检查过

    Returns:
        bool: 今天是否已经检查过
    """
    last_check = get_last_check_date()
    if not last_check:
        return False
    today = datetime.now().strftime('%Y-%m-%d')
    return last_check == today


def get_current_version() -> Optional[str]:
    """
    获取当前安装的 bilibili-api-python 版本

    Returns:
        Optional[str]: 当前版本号，如果获取失败则返回 None
    """
    try:
        # 尝试直接从 pyproject.toml 读取版本
        with open('pyproject.toml', 'r', encoding='utf-8') as f:
            content = f.read()

        version_match = re.search(r'bilibili-api-python==([^,\n"]+)', content)
        if version_match:
            # 移除可能的引号
            version = version_match.group(1).strip('"\'')
            return version

        # 如果 pyproject.toml 中没有，则尝试使用 pip show
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', 'bilibili-api-python'],
            capture_output=True,
            text=True,
            check=True
        )

        version_match = re.search(r'Version: (.*)', result.stdout)
        if version_match:
            return version_match.group(1).strip()
        return None
    except Exception as e:
        print(f"获取当前版本失败: {e}")
        return None


def get_installed_version() -> Optional[str]:
    """
    获取实际安装的 bilibili-api-python 版本

    Returns:
        Optional[str]: 安装的版本号，如果获取失败则返回 None
    """
    # 优先尝试使用 uv pip show
    try:
        result = subprocess.run(
            ['uv', 'pip', 'show', 'bilibili-api-python'],
            capture_output=True,
            text=True,
            check=True
        )

        version_match = re.search(r'Version: (.*)', result.stdout)
        if version_match:
            return version_match.group(1).strip()
    except Exception:
        pass

    # 回退到 pip show
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', 'bilibili-api-python'],
            capture_output=True,
            text=True,
            check=True
        )

        version_match = re.search(r'Version: (.*)', result.stdout)
        if version_match:
            return version_match.group(1).strip()
        return None
    except Exception as e:
        print(f"获取安装版本失败: {e}")
        return None


def update_pyproject_toml(version: str) -> bool:
    """
    更新 pyproject.toml 文件中的 bilibili-api-python 版本

    Args:
        version: 新的版本号

    Returns:
        bool: 更新是否成功
    """
    try:
        # 读取 pyproject.toml 文件
        with open('pyproject.toml', 'r', encoding='utf-8') as f:
            content = f.read()

        # 查找并替换 bilibili-api-python 版本，确保正确的引号格式
        # 匹配整个 "bilibili-api-python==版本号" 字符串
        updated_content = re.sub(
            r'"bilibili-api-python==[^,\n"]+"',
            f'"bilibili-api-python=={version}"',
            content
        )

        # 写回文件
        with open('pyproject.toml', 'w', encoding='utf-8') as f:
            f.write(updated_content)

        print(f"已更新 pyproject.toml 中的 bilibili-api-python 版本为 {version}")
        return True
    except Exception as e:
        print(f"更新 pyproject.toml 失败: {e}")
        return False


def main():
    """
    主函数，执行 bilibili-api-python 升级流程
    """
    # 检查今天是否已经检查过
    if is_today_checked():
        print("今天已经检查过 bilibili-api-python 更新，跳过检查")
        return

    print("开始检查并升级 bilibili-api-python...")

    current_version = get_current_version()
    print(f"当前 pyproject.toml 中的版本: {current_version}")

    # 尝试使用 uv 命令升级 bilibili-api-python
    try:
        print("正在使用 uv 升级 bilibili-api-python 到最新版本...")
        result = subprocess.run(
            ['uv', 'pip', 'install', '--upgrade', 'bilibili-api-python'],
            capture_output=True,
            text=True,
            check=True
        )

        print("bilibili-api-python 升级成功!")

        # 获取升级后的版本号
        new_version = get_installed_version()
        if new_version:
            print(f"升级后的 bilibili-api-python 版本: {new_version}")

            # 更新 pyproject.toml
            update_pyproject_toml(new_version)

    except Exception as e:
        print(f"使用 uv 升级失败: {e}")

        # 尝试使用 pip 命令升级 bilibili-api-python
        try:
            print("尝试使用 pip 升级 bilibili-api-python...")
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', 'bilibili-api-python'],
                capture_output=True,
                text=True,
                check=True
            )

            print("bilibili-api-python 升级成功!")

            # 获取升级后的版本号
            new_version = get_installed_version()
            if new_version:
                print(f"升级后的 bilibili-api-python 版本: {new_version}")

                # 更新 pyproject.toml
                update_pyproject_toml(new_version)

        except Exception as e2:
            print(f"使用 pip 升级也失败: {e2}")
            print("继续执行程序...")

    # 保存今天的检查日期
    save_last_check_date()
    print("已记录今天的检查日期")


if __name__ == "__main__":
    main()
