#!/usr/bin/env python3
"""
自动化升级 yt-dlp 到最新版本

此脚本会：
1. 检查当前安装的 yt-dlp 版本
2. 获取最新的 yt-dlp 版本
3. 如果有新版本，升级 yt-dlp
4. 更新 pyproject.toml 文件中的 yt-dlp 版本
"""
import os
import re
import subprocess
import json
import sys
from typing import Optional


def get_current_version() -> Optional[str]:
    """
    获取当前安装的 yt-dlp 版本
    
    Returns:
        Optional[str]: 当前版本号，如果获取失败则返回 None
    """
    try:
        # 尝试直接从 pyproject.toml 读取版本
        with open('pyproject.toml', 'r', encoding='utf-8') as f:
            content = f.read()
        
        version_match = re.search(r'yt-dlp==([^,\n]+)', content)
        if version_match:
            # 移除可能的引号
            version = version_match.group(1).strip('"\'')
            return version
        
        # 如果 pyproject.toml 中没有，则尝试使用 pip show
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'show', 'yt-dlp'],
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


def get_latest_version() -> Optional[str]:
    """
    获取最新的 yt-dlp 版本
    
    Returns:
        Optional[str]: 最新版本号，如果获取失败则返回 None
    """
    try:
        # 方法1：使用 yt-dlp 命令检查最新版本
        result = subprocess.run(
            ['yt-dlp', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        
        current_version = result.stdout.strip()
        print(f"当前 yt-dlp 命令版本: {current_version}")
        
        # 方法2：尝试使用 pip 列表获取可用版本
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'list', '--outdated'],
            capture_output=True,
            text=True,
            check=True
        )
        
        # 解析输出，查找 yt-dlp 的最新版本
        # 示例输出: "yt-dlp             2025.12.08  2025.12.25  wheel"
        version_match = re.search(r'yt-dlp\s+\d+\.\d+\.\d+\s+(\d+\.\d+\.\d+)', result.stdout)
        if version_match:
            return version_match.group(1)
        
        # 如果没有找到更新，返回当前版本
        return current_version
        
    except Exception as e:
        print(f"获取最新版本失败: {e}")
        return None


def upgrade_yt_dlp(version: str) -> bool:
    """
    升级 yt-dlp 到指定版本
    
    Args:
        version: 要升级到的版本号
    
    Returns:
        bool: 升级是否成功
    """
    try:
        print(f"正在升级 yt-dlp 到版本 {version}...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', f'yt-dlp=={version}'],
            capture_output=True,
            text=True,
            check=True
        )
        print("升级成功!")
        return True
    except Exception as e:
        print(f"升级失败: {e}")
        return False


def update_pyproject_toml(version: str) -> bool:
    """
    更新 pyproject.toml 文件中的 yt-dlp 版本
    
    Args:
        version: 新的版本号
    
    Returns:
        bool: 更新是否成功
    """
    try:
        # 读取 pyproject.toml 文件
        with open('pyproject.toml', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找并替换 yt-dlp 版本，确保正确的引号格式
        # 匹配整个 "yt-dlp==版本号" 字符串
        updated_content = re.sub(
            r'"yt-dlp==[^,\n]+"',
            f'"yt-dlp=={version}"',
            content
        )
        
        # 写回文件
        with open('pyproject.toml', 'w', encoding='utf-8') as f:
            f.write(updated_content)
        
        print(f"已更新 pyproject.toml 中的 yt-dlp 版本为 {version}")
        return True
    except Exception as e:
        print(f"更新 pyproject.toml 失败: {e}")
        return False


def main():
    """
    主函数，执行 yt-dlp 升级流程
    """
    print("开始检查并升级 yt-dlp...")
    
    # 尝试使用 uv 命令升级 yt-dlp
    try:
        print("正在使用 uv 升级 yt-dlp 到最新版本...")
        result = subprocess.run(
            ['uv', 'pip', 'install', '--upgrade', 'yt-dlp'],
            capture_output=True,
            text=True,
            check=True
        )
        
        print("yt-dlp 升级成功!")
        
        # 获取升级后的版本号
        result = subprocess.run(
            ['yt-dlp', '--version'],
            capture_output=True,
            text=True,
            check=True
        )
        
        new_version = result.stdout.strip()
        print(f"升级后的 yt-dlp 版本: {new_version}")
        
        # 更新 pyproject.toml
        update_pyproject_toml(new_version)
        
    except Exception as e:
        print(f"使用 uv 升级失败: {e}")
        
        # 尝试使用 pip 命令升级 yt-dlp
        try:
            print("尝试使用 pip 升级 yt-dlp...")
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'],
                capture_output=True,
                text=True,
                check=True
            )
            
            print("yt-dlp 升级成功!")
            
            # 获取升级后的版本号
            result = subprocess.run(
                ['yt-dlp', '--version'],
                capture_output=True,
                text=True,
                check=True
            )
            
            new_version = result.stdout.strip()
            print(f"升级后的 yt-dlp 版本: {new_version}")
            
            # 更新 pyproject.toml
            update_pyproject_toml(new_version)
            
        except Exception as e2:
            print(f"使用 pip 升级也失败: {e2}")
            print("继续执行程序...")


if __name__ == "__main__":
    main()
