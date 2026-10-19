import configparser
import json
import mimetypes
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

# 始终从脚本所在目录读取 config.ini，避免在不同工作目录下运行时找不到配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cfg = configparser.ConfigParser()
cfg.read(os.path.join(BASE_DIR, "config.ini"), encoding="utf-8")
llm = cfg["llm"]
messages = []


# ----------------------------------------------------------------------------
# 原有工具
# ----------------------------------------------------------------------------
def getDate():
    """获取当前电脑的日期和时间（调用本地 date 系统命令，不用 time/datetime）。"""
    if platform.system().lower() == "windows":
        result = subprocess.run(
            ["cmd", "/c", "date /t & time /t"],
            capture_output=True,
        )
        text = result.stdout.decode("gbk", errors="replace")
        return text.strip().replace("\r", " ").replace("\n", " ")
    else:
        result = subprocess.run(["date"], capture_output=True)
        return result.stdout.decode("utf-8", errors="replace").strip()


def isLeapYear(year):
    """判断输入的年份是否为闰年（用 Python 代码计算）。"""
    year = int(year)
    leap = (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
    return f"{year} 是闰年" if leap else f"{year} 不是闰年"


# ----------------------------------------------------------------------------
# 新增：本地文件操作工具（均使用 Python 标准库实现）
# ----------------------------------------------------------------------------
# 删除操作的防护：禁止删除盘符根目录与常见系统目录，避免灾难性误删。
_PROTECTED_DIRS = {
    "WINDOWS",
    "PROGRAM FILES",
    "PROGRAM FILES (X86)",
    "PROGRAMDATA",
    "SYSTEM VOLUME INFORMATION",
}


def _refuse_destructive(path):
    """对删除类操作做基本防护，返回 (允许?, 原因)。"""
    ap = os.path.abspath(os.path.normpath(path))
    # 盘符根目录，例如 C:\ 或 D:\
    if ap in (f"{c}:\\" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
        return False, f"拒绝操作：不允许删除盘符根目录 {ap}"
    # 常见系统目录（精确匹配整段路径的最后一段）
    tail = os.path.basename(ap).upper()
    if tail in _PROTECTED_DIRS:
        return False, f"拒绝操作：不允许删除系统目录 {ap}"
    return True, ""


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
    ok, reason = _refuse_destructive(path)
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
    ok, reason = _refuse_destructive(path)
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
    ok, reason = _refuse_destructive(old_path)
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


# ----------------------------------------------------------------------------
# 工具注册（OpenAI / 兼容接口 function-calling 格式）
# ----------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间。当用户想知道现在几点、今天几号、当前日期或时间时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断输入的年份是否为闰年。当用户问某一年是不是闰年、是否有闰月、全年是否 366 天时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "要判断的年份，例如 2026、2000、1900"}
                },
                "required": ["year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cwd",
            "description": "获取当前工作目录的绝对路径。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出指定目录下的所有文件和子目录。不传 path 时列出当前工作目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径，留空表示当前工作目录"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_type",
            "description": "获取指定路径的类型：区分目录/文件/符号链接，并给出扩展名与 MIME 类型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件或目录的路径"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取指定文本文件的内容（仅支持纯文本；超大文件会被截断）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要读取的文件路径"},
                    "max_chars": {"type": "integer", "description": "最多返回的字符数，默认 8000"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "在指定目录 dir_path 下创建名为 filename 的文件，并写入文本 content。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dir_path": {"type": "string", "description": "目标目录，留空表示当前工作目录"},
                    "filename": {"type": "string", "description": "新文件名，例如 note.txt"},
                    "content": {"type": "string", "description": "要写入的文本内容，可为空"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑纯文本文件：把文件中的 old_text 全部替换为 new_text。仅支持纯文本文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要编辑的文件路径"},
                    "old_text": {"type": "string", "description": "待被替换的原文本"},
                    "new_text": {"type": "string", "description": "替换后的新文本"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_dir",
            "description": "创建新目录（支持递归创建多级目录）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "要创建的目录路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_dir",
            "description": "删除目录（支持非空目录，等效于递归删除）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "要删除的目录路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "删除指定文件（不是目录）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "要删除的文件路径"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rename_path",
            "description": "重命名文件或目录：把 old_path 改名为 new_path。",
            "parameters": {
                "type": "object",
                "properties": {
                    "old_path": {"type": "string", "description": "原文件或目录路径"},
                    "new_path": {"type": "string", "description": "新的文件或目录路径"},
                },
                "required": ["old_path", "new_path"],
            },
        },
    },
]

# 工具名 -> 本地 Python 函数的映射
TOOL_FUNCTIONS = {
    "getDate": getDate,
    "isLeapYear": isLeapYear,
    "get_cwd": get_cwd,
    "list_dir": list_dir,
    "get_file_type": get_file_type,
    "read_file": read_file,
    "create_file": create_file,
    "edit_file": edit_file,
    "create_dir": create_dir,
    "delete_dir": delete_dir,
    "delete_file": delete_file,
    "rename_path": rename_path,
}


# ----------------------------------------------------------------------------
# 对话 / 工具调度（与 chat_leap.py 一致）
# ----------------------------------------------------------------------------
def _build_request(payload):
    headers = {"Content-Type": "application/json"}
    if llm["api_key"] and llm["api_key"] != "your-api-key":
        headers["Authorization"] = "Bearer " + llm["api_key"]
    return urllib.request.Request(
        llm["api_base"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )


def _chat(messages, tools=None, stream=False):
    payload = {
        "model": llm["model"],
        "messages": messages,
        "temperature": float(llm.get("temperature", 0.7)),
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = _build_request(payload)
    with urllib.request.urlopen(req) as resp:
        if stream:
            return resp
        return json.loads(resp.read().decode("utf-8"))


def _stream_print(resp):
    reply = ""
    for line in resp:
        line = line.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            content = json.loads(data)["choices"][0]["delta"].get("content", "")
        except (KeyError, IndexError, json.JSONDecodeError):
            continue
        if content:
            reply += content
            print(content, end="", flush=True)
    return reply


def _dispatch_tool(tc):
    fn_name = tc["function"]["name"]
    if fn_name not in TOOL_FUNCTIONS:
        return fn_name, f"未知工具：{fn_name}"
    raw_args = tc["function"].get("arguments", "{}") or "{}"
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        args = {}
    result = TOOL_FUNCTIONS[fn_name](**args)
    return fn_name, str(result)


def main():
    try:
        print("（直接回车或 Ctrl+C 退出）")
        while True:
            text = input("你的问题是：").strip()
            if not text:
                break
            messages.append({"role": "user", "content": text})

            # 多轮工具循环：模型可以连续调用多个工具（如先 get_cwd 再 list_dir），
            # 直到它不再请求工具、给出最终文字答案为止。
            for _ in range(6):  # 最多 6 轮，防止死循环
                resp = _chat(messages, tools=TOOLS, stream=False)
                msg = resp["choices"][0]["message"]

                if msg.get("tool_calls"):
                    messages.append(msg)
                    for tc in msg["tool_calls"]:
                        fn_name, tool_result = _dispatch_tool(tc)
                        print(f"（调用工具 {fn_name}：{tool_result}）")
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": fn_name,
                                "content": tool_result,
                            }
                        )
                    continue  # 把工具结果喂回模型，进入下一轮

                # 模型不再调用工具 => 输出最终回答
                content = msg.get("content", "") or "（模型未返回文本内容）"
                print(content)
                messages.append({"role": "assistant", "content": content})
                break
            else:
                print("（达到工具调用轮次上限，已停止）")
            print()
    except KeyboardInterrupt:
        print("\n已退出")


def _self_test():
    """在临时目录中演练 10 个文件操作工具，验证逻辑（不依赖 LLM，也不动用户真实文件）。"""
    tmp = tempfile.mkdtemp(prefix="agent_fs_test_")
    print("临时工作目录：", tmp)
    print("get_cwd      :", get_cwd())
    print("create_dir   :", create_dir(os.path.join(tmp, "sub")))
    print("create_file  :", create_file(os.path.join(tmp, "sub"), "a.txt", "hello world"))
    print("create_file  :", create_file(tmp, "b.txt", "line1\nline2"))
    print("list_dir     :\n" + list_dir(tmp))
    print("get_file_type:", get_file_type(os.path.join(tmp, "sub", "a.txt")))
    print("read_file    :", read_file(os.path.join(tmp, "sub", "a.txt")))
    print("edit_file    :", edit_file(os.path.join(tmp, "sub", "a.txt"), "world", "WORLD"))
    print("read_file    :", read_file(os.path.join(tmp, "sub", "a.txt")))
    print("delete_file  :", delete_file(os.path.join(tmp, "b.txt")))
    print("delete_dir   :", delete_dir(os.path.join(tmp, "sub")))
    print("安全守卫-删根:", delete_dir("C:\\"))
    print("安全守卫-删文:", delete_file("C:\\Windows"))
    # 重命名演示（文件 + 目录）
    demo = os.path.join(tmp, "rename_demo")
    create_dir(demo)
    create_file(demo, "old.txt", "x")
    print("rename 文件 :", rename_path(os.path.join(demo, "old.txt"), os.path.join(demo, "new.txt")))
    print("rename 目录 :", rename_path(demo, demo + "_renamed"))
    shutil.rmtree(demo + "_renamed", ignore_errors=True)
    # 清理临时目录
    shutil.rmtree(tmp, ignore_errors=True)
    print("isLeapYear   :", isLeapYear(2026), "/", isLeapYear(2000))
    print("getDate      :", getDate())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        _self_test()
    else:
        main()
