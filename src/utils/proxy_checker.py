"""代理状态检测工具"""
import os
import socket
import time
from typing import Dict, Optional


def check_proxy_status() -> Dict[str, any]:
    """
    检测代理状态

    返回:
        {
            'enabled': bool,  # 是否在 Docker 环境中（是否应该使用代理）
            'port_accessible': bool,  # 代理端口是否可访问
            'latency': Optional[float],  # 连接延迟（毫秒）
            'status': str,  # 'ok' | 'port_unavailable' | 'disabled'
            'message': str,  # 状态消息
        }
    """
    # 检查是否在 Docker 环境中
    is_docker = os.path.exists('/.dockerenv')

    if not is_docker:
        return {
            'enabled': False,
            'port_accessible': False,
            'latency': None,
            'status': 'disabled',
            'message': 'Windows 环境，不使用代理'
        }

    # 在 Docker 环境中，检测代理端口
    proxy_host = '127.0.0.1'
    proxy_port = 1080

    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((proxy_host, proxy_port))
        latency = (time.time() - start_time) * 1000  # 转换为毫秒
        sock.close()

        if result == 0:
            return {
                'enabled': True,
                'port_accessible': True,
                'latency': round(latency, 2),
                'status': 'ok',
                'message': f'代理正常 (延迟: {round(latency, 2)}ms)'
            }
        else:
            return {
                'enabled': True,
                'port_accessible': False,
                'latency': None,
                'status': 'port_unavailable',
                'message': f'代理端口不可访问 (错误码: {result})'
            }
    except Exception as e:
        return {
            'enabled': True,
            'port_accessible': False,
            'latency': None,
            'status': 'error',
            'message': f'代理检测失败: {str(e)}'
        }
