def pick(source, keys):
    """
    从一个字典中挑选指定的键值对。
    
    参数:
    - source: 原始字典对象。
    - keys: 一个包含想要保留的键的集合或列表。
    
    返回:
    - 一个新的字典，只包含指定的键值对。
    """
    return {key: source[key] for key in keys if key in source}