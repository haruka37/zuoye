"""工具基础：删除类操作的统一防护（避免灾难性误删）。

各业务工具模块共享这里的防护逻辑，保证安全策略只有一份来源。
"""

import os

# 禁止删除的常见系统目录（精确匹配路径最后一段，忽略大小写）
PROTECTED_DIRS = {
    "WINDOWS",
    "PROGRAM FILES",
    "PROGRAM FILES (X86)",
    "PROGRAMDATA",
    "SYSTEM VOLUME INFORMATION",
}


def refuse_destructive(path: str):
    """对删除/重命名等破坏性操作做基本防护。

    Returns:
        (允许?, 原因) 二元组。当不允许时，原因是一句可回传给模型的中文说明。
    """
    ap = os.path.abspath(os.path.normpath(path))
    # 盘符根目录，例如 C:\ 或 D:\
    if ap in (f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        return False, f"拒绝操作：不允许删除盘符根目录 {ap}"
    # 常见系统目录
    tail = os.path.basename(ap).upper()
    if tail in PROTECTED_DIRS:
        return False, f"拒绝操作：不允许删除系统目录 {ap}"
    return True, ""
