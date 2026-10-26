"""RunCli 工具：让 Agent 通过 Function Calling 调用本地已安装的任意命令行程序（CLI）。

说明（受控教学实验环境）：
- 本阶段按教学目标不实现命令白名单/黑名单或审批机制，命令以运行本程序的
  当前用户权限执行。
- 程序名与参数拼装为列表，subprocess 以 shell=False 执行，避免拼接 Shell
  命令字符串带来的注入风险。
- 执行后把 stdout / stderr / 退出码返回给 LLM，供其判断结果并决定下一步。
- 设置执行超时；对过长输出截断并标明截断情况，避免大量终端输出挤占上下文。
"""

import subprocess
import sys

# 单条命令执行超时（秒）
CLI_TIMEOUT = 30
# stdout / stderr 各自返回给 LLM 的最大字符数
MAX_STREAM_CHARS = 4000


class CliError(Exception):
    """可预期的执行错误，会被转换为工具结果文本。"""


def _decode(data) -> str:
    """把子进程输出字节解码为文本：优先 utf-8，失败时 Windows 回退 gbk。"""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    encodings = ["utf-8"]
    if sys.platform.startswith("win"):
        encodings.append("gbk")
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _clip(text: str, label: str) -> str:
    """过长输出截断，并标明截断情况。"""
    if len(text) <= MAX_STREAM_CHARS:
        return text
    return (
        text[:MAX_STREAM_CHARS]
        + f"\n…（{label} 过长已截断：原始 {len(text)} 字符，仅显示前 {MAX_STREAM_CHARS} 字符）"
    )


def _normalize_args(args) -> list:
    """把 args 规整为字符串列表；兼容 None / 单个字符串 / 列表或元组。"""
    if args is None:
        return []
    if isinstance(args, str):
        return [args] if args else []
    if isinstance(args, (list, tuple)):
        return [str(a) for a in args]
    return [str(args)]


def run_cli(command: str, args=None) -> str:
    """RunCli 工具：执行本地命令行程序，返回 stdout / stderr / 退出码给 LLM。"""
    command = (command or "").strip()
    if not command:
        return "RunCli 失败：command 为空，请提供要执行的程序名称。"

    argv = [command] + _normalize_args(args)

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            timeout=CLI_TIMEOUT,
            shell=False,  # 明确不经过 shell，避免拼接命令字符串的注入风险
            check=False,
        )
    except FileNotFoundError:
        return f"RunCli 失败：未找到程序「{command}」，请确认已安装并在 PATH 中。"
    except PermissionError:
        return f"RunCli 失败：没有权限执行「{command}」。"
    except subprocess.TimeoutExpired as e:
        # 超时：返回退出码为空并说明，已产生的部分输出一并提供
        out = _decode(getattr(e, "stdout", None))
        err = _decode(getattr(e, "stderr", None))
        lines = [
            "【命令执行结果】（超时被终止）",
            f"命令: {' '.join(argv)}",
            f"退出码: None（超过 {CLI_TIMEOUT}s 未结束，已被强制终止）",
            "--- stdout ---",
            _clip(out, "stdout") if out else "（无输出）",
            "--- stderr ---",
            _clip(err, "stderr") if err else "（无输出）",
        ]
        return "\n".join(lines)
    except OSError as e:
        return f"RunCli 失败：执行出错（{type(e).__name__}）：{e}"

    lines = [
        "【命令执行结果】",
        f"命令: {' '.join(argv)}",
        f"退出码: {proc.returncode}",
        "--- stdout ---",
        _clip(_decode(proc.stdout), "stdout") or "（无输出）",
        "--- stderr ---",
        _clip(_decode(proc.stderr), "stderr") or "（无输出）",
    ]
    return "\n".join(lines)
