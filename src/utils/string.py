import os 
import re
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qs, ParseResult

def clean_reship_url(url, keep_query_key='v'):
    """
    修改URL，仅保留指定的查询参数（默认为'v'），其余查询参数移除。
    
    :param url: 原始URL字符串
    :param keep_query_key: 要保留的查询参数的键，默认为'v'
    :return: 修改后的URL字符串
    """
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        # 仅保留指定的查询参数
        filtered_query_params = {k: v for k, v in query_params.items() if k == keep_query_key}
        # 重新构造URL
        new_url = ParseResult(
            scheme=parsed_url.scheme,
            netloc=parsed_url.netloc,
            path=parsed_url.path,
            params=parsed_url.params,
            query=urlencode(filtered_query_params, doseq=True) if filtered_query_params else '',
            fragment=parsed_url.fragment
        ).geturl()
        return new_url
    except Exception as e:
        raise ValueError(f"Invalid URL or error processing it: {e}")

def truncate_str(s, n, ellipsis='...'):
    """
    截断字符串至指定长度，并在末尾追加指定的省略号（默认为 '...'）。
    
    :param s: 原始字符串。
    :param n: 截断后的最大长度。
    :param ellipsis: 超过长度后追加的省略号，默认为 '...'。
    :return: 截断后的字符串。
    """
    if len(s) > n:
        return s[:n] + ellipsis
    else:
        return s

def cleaned_text(text):
    """
    清理字符串中的多余空格，将连续的空格替换为单个空格，并去除首尾空格。
    
    :param text: 待清理的原始字符串
    :return: 清理后的字符串
    """
    return re.sub(r'\s+', ' ', text).strip()

def add_suffix_to_filename(file_path, suffix):
    """
    给定一个文件路径和一个后缀字符串
    
    :param file_path: 原始文件的路径
    :param suffix: 要添加到文件名的后缀字符串
    :return: 新的文件路径
    """
    # 分离文件路径中的目录部分和文件名部分
    directory, filename = os.path.split(file_path)
    # 分离文件名和扩展名
    base_name, extension = os.path.splitext(filename)
    # 构建新的文件名
    new_filename = f"{base_name}.{suffix}{extension}"
    # 结合目录和新的文件名得到新的文件路径
    new_file_path = os.path.join(directory, new_filename)
    return new_file_path

def abs_to_rel(abs_path: str, base_parent_level: int = 0) -> str:
    """将绝对路径转换为相对路径（Python raw字符串格式）
    """
    current_script_path = Path(__file__).resolve()
    base_dir = current_script_path
    for _ in range(base_parent_level):
        base_dir = base_dir.parent
    # 计算相对路径并规范化
    relative_path = os.path.relpath(abs_path, base_dir)
    return re.sub(r"\\+", "/", relative_path)
