def pick(source, keys):
    """
    从一个字典或类似字典的对象中挑选指定的键值对。
    
    参数:
    - source: 原始字典对象或类似字典的对象。
    - keys: 一个包含想要保留的键的集合或列表。
    
    返回:
    - 一个新的字典，只包含指定的键值对。
    """
    # 确保source可以迭代，并且keys是可迭代的
    if not hasattr(source, '__getitem__') or not hasattr(keys, '__iter__'):
        raise TypeError("Source must be dict-like and keys must be iterable.")
    
    return {key: source.get(key) for key in keys}
