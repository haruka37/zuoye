"""工具注册层：汇总各业务模块的工具，提供 function-calling schema 与分发入口。

本文件是「工具»模型」契约的唯一来源：
- TOOL_FUNCTIONS：工具名 -> 本地 Python 函数
- TOOLS：OpenAI 兼容的 function-calling schema（描述 + 参数）
- dispatch()：按一次 tool_call 执行对应函数并返回 (函数名, 结果文本)
"""

import json

from . import cli, fetch, filesystem, search, system
from .base import PROTECTED_DIRS, refuse_destructive

# 工具名 -> 本地 Python 函数
TOOL_FUNCTIONS = {
    "getDate": system.getDate,
    "isLeapYear": system.isLeapYear,
    "get_cwd": filesystem.get_cwd,
    "list_dir": filesystem.list_dir,
    "get_file_type": filesystem.get_file_type,
    "read_file": filesystem.read_file,
    "create_file": filesystem.create_file,
    "edit_file": filesystem.edit_file,
    "create_dir": filesystem.create_dir,
    "delete_dir": filesystem.delete_dir,
    "delete_file": filesystem.delete_file,
    "rename_path": filesystem.rename_path,
    "searchWeb": search.search_web,
    "fetchWeb": fetch.fetch_web,
    "RunCli": cli.run_cli,
}

# OpenAI 兼容的 function-calling schema
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
    {
        "type": "function",
        "function": {
            "name": "searchWeb",
            "description": "联网搜索工具：根据关键词或问题，调用百度千帆智能搜索获取互联网最新信息，"
            "返回 AI 总结的摘要与参考来源的标题、链接。当问题需要实时信息、新闻、"
            "最新数据、当前事件或不确定事实时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或问题，例如「今天国际油价」「Python 最新稳定版本」",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetchWeb",
            "description": "网页正文抓取工具：传入一个网页 URL，抓取该网页并提取其主要正文内容，"
            "转换为 Markdown（保留标题、段落、列表、表格与链接，去除导航栏、广告、页脚等噪声）后返回，"
            "并附上原始 URL。当需要阅读或总结某个具体网页/文章的内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "要抓取的网页地址，必须是 http:// 或 https:// 开头的链接",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "RunCli",
            "description": "命令行工具：调用当前系统已安装的任意命令行程序（CLI）。"
            "传入可执行程序名 command 以及可选参数列表 args，工具会以非 Shell 方式（shell=False）"
            "执行该程序，并把 stdout、stderr 与退出码返回。适合让模型通过命令行完成文件处理、"
            "运行脚本、查看系统信息等任务。注意：参数应作为数组逐项传入，不要拼接成整条 Shell 命令。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的程序名或可执行文件路径，例如 python、curl、ls、node",
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "传给程序的参数列表，按顺序逐项填入，例如 [\"-c\", \"print(1+1)\"]；可留空",
                    },
                },
                "required": ["command"],
            },
        },
    },
]


def dispatch(tool_call):
    """执行一次工具调用，返回 (函数名, 结果文本)。

    该函数是编排层与工具实现之间的边界：编排层只传 tool_call，不关心具体实现。
    """
    fn_name = tool_call["function"]["name"]
    if fn_name not in TOOL_FUNCTIONS:
        return fn_name, f"未知工具：{fn_name}"
    raw_args = tool_call["function"].get("arguments", "{}") or "{}"
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        args = {}
    result = TOOL_FUNCTIONS[fn_name](**args)
    return fn_name, str(result)


__all__ = ["TOOL_FUNCTIONS", "TOOLS", "dispatch", "refuse_destructive", "PROTECTED_DIRS"]
