"""文件系统工具：目录/文件列举、类型探测、读写、创建、删除、重命名。

全部基于 Python 标准库实现；删除/重命名操作统一走 base.refuse_destructive 防护。
"""

import mimetypes
import os
import shutil

from .base import refuse_destructive


def get_cwd():
    """获取当前工作目录的绝对路径。"""
    return os.getcwd()


def list_dir(path=""):
    """列出指定目录下的所有文件和子目录；path 为空时列出当前工作目录。"""
    target = path or os.getcwd()
    if not os.path.isdir(target):
        return f"路径不存在或不是目录：{target}"
    entries = sorted(os.listdir(target))
    if not entries:
        return f"（空目录）{target}"
    lines = []
    for name in entries:
        full = os.path.join(target, name)
        kind = "目录" if os.path.isdir(full) else "文件"
        lines.append(f"[{kind}] {name}")
    return "\n".join(lines)


def get_file_type(path):
    """获取指定路径的类型：区分目录/文件/符号链接，并给出扩展名与 MIME。"""
    if not os.path.exists(path):
        return f"路径不存在：{path}"
    if os.path.islink(path):
        kind = "符号链接"
    elif os.path.isdir(path):
        kind = "目录"
    else:
        kind = "文件"
    ext = os.path.splitext(path)[1].lower()
    mime, _ = mimetypes.guess_type(path)
    parts = [f"类型：{kind}", f"扩展名：{ext or '无'}", f"MIME：{mime or '未知'}"]
    if kind == "文件":
        parts.append(f"大小：{os.path.getsize(path)} 字节")
    return "\n".join(parts)


def read_file(path, max_chars=8000):
    """读取指定文本文件的内容（仅支持纯文本，超大文件截断到 max_chars）。"""
    if not os.path.isfile(path):
        return f"文件不存在：{path}"
    with open(path, "rb") as f:
        data = f.read()
    if b"\x00" in data[: min(len(data), 4096)]:
        return f"不是纯文本文件（疑似二进制），已拒绝读取：{path}"
    text = data.decode("utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n...（已截断，全文共 {len(text)} 字符）"
    return text


def create_file(dir_path, filename, content=""):
    """在指定目录 dir_path 下创建名为 filename 的文件并写入 content（文本）。"""
    root = dir_path or os.getcwd()
    os.makedirs(root, exist_ok=True)
    full = os.path.join(root, filename)
    if os.path.exists(full):
        return f"文件已存在，未覆盖：{full}"
    with open(full, "w", encoding="utf-8") as f:
        f.write(content or "")
    return f"已创建文件：{full}（写入 {len(content or '')} 字符）"


def edit_file(path, old_text, new_text):
    """编辑纯文本文件：把文件中的 old_text 全部替换为 new_text。

    仅支持纯文本文件；若文件为二进制或找不到 old_text 则返回提示。
    """
    if not os.path.isfile(path):
        return f"文件不存在：{path}"
    with open(path, "rb") as f:
        data = f.read()
    if b"\x00" in data[: min(len(data), 4096)]:
        return f"不是纯文本文件（疑似二进制），已拒绝编辑：{path}"
    text = data.decode("utf-8", errors="replace")
    if old_text not in text:
        return f"未在文件中找到待替换内容：{old_text!r}"
    count = text.count(old_text)
    text = text.replace(old_text, new_text)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return f"已更新文件：{path}（替换 {count} 处）"


def create_dir(path):
    """创建新目录（支持递归创建多级目录）。"""
    if not path:
        return "未提供目录路径"
    if os.path.exists(path):
        return f"路径已存在：{path}"
    os.makedirs(path, exist_ok=False)
    return f"已创建目录：{path}"


def delete_dir(path):
    """删除目录（支持非空目录，等效于递归删除）。"""
    if not os.path.exists(path):
        return f"目录不存在：{path}"
    if not os.path.isdir(path):
        return f"不是目录：{path}"
    ok, reason = refuse_destructive(path)
    if not ok:
        return reason
    shutil.rmtree(path)
    return f"已删除目录：{path}"


def delete_file(path):
    """删除指定文件。"""
    if not os.path.exists(path):
        return f"文件不存在：{path}"
    if os.path.isdir(path):
        return f"这是目录而非文件，请使用 delete_dir：{path}"
    ok, reason = refuse_destructive(path)
    if not ok:
        return reason
    os.remove(path)
    return f"已删除文件：{path}"


def rename_path(old_path, new_path):
    """重命名文件或目录：把 old_path 改名为 new_path（同盘用 os.rename，跨盘回退 shutil.move）。"""
    if not old_path or not new_path:
        return "需要提供 old_path 与 new_path"
    if not os.path.exists(old_path):
        return f"源路径不存在：{old_path}"
    ok, reason = refuse_destructive(old_path)
    if not ok:
        return reason
    parent = os.path.dirname(os.path.abspath(new_path))
    if parent and not os.path.isdir(parent):
        return f"目标父目录不存在：{parent}"
    if os.path.exists(new_path):
        return f"目标路径已存在，未覆盖：{new_path}"
    try:
        os.rename(old_path, new_path)
    except OSError:
        shutil.move(old_path, new_path)
    return f"已将 {old_path} 重命名为 {new_path}"
