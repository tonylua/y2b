#!/usr/bin/env python3
"""
监控 Docker 容器的代理节点切换请求
当检测到切换请求时，触发节点更换
"""
import os
import time
import subprocess
import sys

MARKER_FILE = "/tmp/switch_proxy_node"
CHECK_INTERVAL = 2  # 每2秒检查一次

def log(message):
    """打印日志并立即刷新"""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)

def switch_proxy_node():
    """执行节点切换"""
    log("检测到节点切换请求，正在切换...")

    try:
        # 直接执行 v2ray 自动更新脚本
        result = subprocess.run(
            ["/usr/local/bin/python3", "/root/.nullclaw/workspace/v2ray_auto_update.py"],
            capture_output=True,
            text=True,
            timeout=300  # 增加到5分钟
        )

        if result.returncode == 0:
            log("节点切换成功")
            log(f"输出: {result.stdout[-200:]}")  # 最后200字符
            return True
        else:
            log(f"节点切换失败 (退出码: {result.returncode})")
            log(f"错误: {result.stderr[-200:]}")
            return False

    except subprocess.TimeoutExpired:
        log("节点切换超时（超过2分钟）")
        return False
    except Exception as e:
        log(f"切换失败: {e}")
        return False

def main():
    log("代理节点切换监控已启动")
    log(f"监控文件: {MARKER_FILE}")

    last_mtime = 0

    while True:
        try:
            if os.path.exists(MARKER_FILE):
                current_mtime = os.path.getmtime(MARKER_FILE)

                # 如果文件被更新（新的切换请求）
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    switch_proxy_node()

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            log("监控已停止")
            sys.exit(0)
        except Exception as e:
            log(f"错误: {e}")
            time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
