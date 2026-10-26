"""诊断层：在临时目录演练工具，验证核心逻辑。

不依赖 LLM，也不会触碰用户真实文件。run_self_test() 返回结构化结果，
由调用方决定是否以及如何展示——因此本模块本身不做终端 I/O。
"""

import os
import shutil
import tempfile

from . import tools


def run_self_test():
    """演练全部 12 个工具，返回 [(标签, 结果文本), ...]。"""
    results = []
    tmp = tempfile.mkdtemp(prefix="agent_fs_test_")
    try:
        results.append(("get_cwd", tools.TOOL_FUNCTIONS["get_cwd"]()))
        results.append(("create_dir", tools.TOOL_FUNCTIONS["create_dir"](os.path.join(tmp, "sub"))))
        results.append(("create_file", tools.TOOL_FUNCTIONS["create_file"](os.path.join(tmp, "sub"), "a.txt", "hello world")))
        results.append(("create_file", tools.TOOL_FUNCTIONS["create_file"](tmp, "b.txt", "line1\nline2")))
        results.append(("list_dir", tools.TOOL_FUNCTIONS["list_dir"](tmp)))
        results.append(("get_file_type", tools.TOOL_FUNCTIONS["get_file_type"](os.path.join(tmp, "sub", "a.txt"))))
        results.append(("read_file", tools.TOOL_FUNCTIONS["read_file"](os.path.join(tmp, "sub", "a.txt"))))
        results.append(("edit_file", tools.TOOL_FUNCTIONS["edit_file"](os.path.join(tmp, "sub", "a.txt"), "world", "WORLD")))
        results.append(("read_file", tools.TOOL_FUNCTIONS["read_file"](os.path.join(tmp, "sub", "a.txt"))))
        results.append(("delete_file", tools.TOOL_FUNCTIONS["delete_file"](os.path.join(tmp, "b.txt"))))
        results.append(("delete_dir", tools.TOOL_FUNCTIONS["delete_dir"](os.path.join(tmp, "sub"))))
        results.append(("安全守卫-删根", tools.TOOL_FUNCTIONS["delete_dir"]("C:\\")))
        results.append(("安全守卫-删文", tools.TOOL_FUNCTIONS["delete_file"]("C:\\Windows")))

        # 重命名演示（文件 + 目录）
        demo = os.path.join(tmp, "rename_demo")
        tools.TOOL_FUNCTIONS["create_dir"](demo)
        tools.TOOL_FUNCTIONS["create_file"](demo, "old.txt", "x")
        results.append(("rename 文件", tools.TOOL_FUNCTIONS["rename_path"](os.path.join(demo, "old.txt"), os.path.join(demo, "new.txt"))))
        results.append(("rename 目录", tools.TOOL_FUNCTIONS["rename_path"](demo, demo + "_renamed")))
        shutil.rmtree(demo + "_renamed", ignore_errors=True)

        results.append(("isLeapYear", tools.TOOL_FUNCTIONS["isLeapYear"](2026) + " / " + tools.TOOL_FUNCTIONS["isLeapYear"](2000)))
        results.append(("getDate", tools.TOOL_FUNCTIONS["getDate"]()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


if __name__ == "__main__":
    for label, value in run_self_test():
        print(f"{label:16}: {value}")
