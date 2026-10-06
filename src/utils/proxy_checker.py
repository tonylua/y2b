"""代理状态检测工具"""
import os
import socket
import time
import subprocess
from typing import Dict, Optional


def check_proxy_status() -> Dict[str, any]:
    """
    检测代理状态

    返回:
        {
            'enabled': bool,  # 是否在 Docker 环境中（是否应该使用代理）
            'port_accessible': bool,  # 代理端口是否可访问
            'youtube_accessible': bool,  # 是否能通过代理访问 YouTube
            'latency': Optional[float],  # 端口连接延迟（毫秒）
            'status': str,  # 'ok' | 'youtube_blocked' | 'port_unavailable' | 'disabled'
            'message': str,  # 状态消息
        }
    """
    # 检查是否在 Docker 环境中
    is_docker = os.path.exists('/.dockerenv')

    if not is_docker:
        return {
            'enabled': False,
            'port_accessible': False,
            'youtube_accessible': False,
            'latency': None,
            'status': 'disabled',
            'message': 'Windows 环境'
        }

    # 在 Docker 环境中，检测代理端口
    proxy_host = '127.0.0.1'
    proxy_port = 1080

    try:
        # 检测端口
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((proxy_host, proxy_port))
        latency = (time.time() - start_time) * 1000  # 转换为毫秒
        sock.close()

        if result != 0:
            return {
                'enabled': True,
                'port_accessible': False,
                'youtube_accessible': False,
                'latency': None,
                'status': 'port_unavailable',
                'message': f'代理端口不可访问 (错误码: {result})'
            }

        # 端口可访问，测试 YouTube 连接
        youtube_ok = test_youtube_connection()

        if youtube_ok:
            return {
                'enabled': True,
                'port_accessible': True,
                'youtube_accessible': True,
                'latency': round(latency, 2),
                'status': 'ok',
                'message': f'代理正常 (延迟: {round(latency, 2)}ms)'
            }
        else:
            return {
                'enabled': True,
                'port_accessible': True,
                'youtube_accessible': False,
                'latency': round(latency, 2),
                'status': 'youtube_blocked',
                'message': f'代理端口正常但无法访问 YouTube'
            }

    except Exception as e:
        return {
            'enabled': True,
            'port_accessible': False,
            'youtube_accessible': False,
            'latency': None,
            'status': 'error',
            'message': f'检测失败: {str(e)}'
        }


def test_youtube_connection(timeout: int = 5) -> bool:
    """
    测试通过代理是否能访问 YouTube

    Args:
        timeout: 超时时间（秒）

    Returns:
        bool: 是否可以访问
    """
    try:
        result = subprocess.run(
            ['curl', '-x', 'socks5://127.0.0.1:1080', '-I', '-s', '-o', '/dev/null',
             '-w', '%{http_code}', '--connect-timeout', str(timeout), 'https://www.youtube.com'],
            capture_output=True,
            text=True,
            timeout=timeout + 2
        )
        # HTTP 状态码 200-399 视为成功
        return result.returncode == 0 and result.stdout.strip() in ['200', '301', '302', '303', '307', '308']
    except:
        return False


def trigger_node_switch() -> Dict[str, any]:
    """
    触发节点更换脚本

    返回:
        {
            'success': bool,
            'message': str
        }
    """
    # 检查是否在 Docker 环境
    if not os.path.exists('/.dockerenv'):
        return {
            'success': False,
            'message': 'Windows 环境不支持此功能'
        }

    try:
        # 触发宿主机的节点更换脚本
        # 使用 docker exec 从容器内调用宿主机命令可能需要特殊配置
        # 这里提供一个简单的实现：写入标记文件，由宿主机监控脚本处理
        marker_file = '/tmp/switch_proxy_node'
        with open(marker_file, 'w') as f:
            f.write(str(time.time()))

        return {
            'success': True,
            'message': '节点更换请求已发送，请等待约 10 秒后刷新'
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'请求失败: {str(e)}'
        }
