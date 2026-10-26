"""编排层：会话管理与「模型→工具→模型」循环。

这是唯一知道对话流程的地方；它组合 llm 客户端与 tools 注册表，
对外暴露界面无关的能力（run_turn / ChatSession），不执行任何终端 I/O。
"""

from . import llm, tools

# 对话历史的总字符预算（≈ 一半即 token 数量级）。
# 本地小模型（如 qwen3-4b）上下文窗口有限，历史过长会导致：
# 1) LM Studio 截断上下文后模型"失忆"、答非所问；
# 2) 请求变慢。
# 因此每轮结束前把历史裁剪到预算内（保留最新内容）。
MAX_HISTORY_CHARS = 24000

# 系统提示词：约束小模型的工具使用行为，避免反复调用同一工具却不给答案。
SYSTEM_PROMPT = (
    "你是一个助手，可以通过提供的工具获取实时信息。使用工具时请遵守：\n"
    "1. 相同参数的工具调用只执行一次，不要用相同的问题反复调用；\n"
    "2. 工具返回结果后，基于结果直接回答用户，不要再次调用同样的工具；\n"
    "3. 与工具无关的问题（如计算、常识）直接回答，不要调用搜索工具；\n"
    "4. 始终围绕用户最新提出的问题回答。"
)


def _trim_history(messages: list, max_chars: int = MAX_HISTORY_CHARS) -> None:
    """把对话历史原地裁剪到 max_chars 以内（保留最新的消息）。

    裁剪规则：
    - 从最新消息向前累计字符数，超出预算的旧消息直接丢弃；
    - 裁剪后的第一条消息必须是 user 或 assistant（纯文本），
      不能是 tool 消息或带 tool_calls 的 assistant 消息，
      否则 OpenAI 兼容接口的对话模板会被破坏（tool 消息必须紧跟
      对应的 assistant.tool_calls）。
    """
    total = sum(len(str(m.get("content") or "")) for m in messages)
    if total <= max_chars:
        return

    kept = []
    acc = 0
    for m in reversed(messages):
        size = len(str(m.get("content") or ""))
        if acc + size > max_chars and kept:
            break
        kept.append(m)
        acc += size
    kept.reverse()

    # 边界修正：起始消息不能是 tool / tool_calls，向前丢弃直到合法
    i = 0
    while i < len(kept):
        m = kept[i]
        if m.get("role") == "tool" or m.get("tool_calls"):
            i += 1
        else:
            break
    kept = kept[i:]

    # 裁剪掉的内容给用户留个痕迹，避免模型困惑上下文缺失
    dropped = len(messages) - len(kept)
    if kept and kept[0].get("role") == "user":
        kept[0] = {
            "role": "user",
            "content": kept[0]["content"]
            + f"\n（系统提示：更早的 {dropped} 条历史消息因超出上下文预算已被省略）",
        }
    messages[:] = kept


def run_turn(messages, user_text, on_tool=None, max_rounds: int = 6, stream: bool = False):
    """在 messages 上跑一轮完整对话（含工具循环），返回最终助手文本。

    Args:
        messages:  对话历史（会被原地修改）。
        user_text: 本轮用户输入。
        on_tool:   可选回调 on_tool(name, result)，每次工具调用后触发（供前端展示）。
        max_rounds: 工具循环最大轮次，防止死循环。
        stream:    是否以流式方式调用 LLM（目前编排层仍按整轮收集结果）。

    Returns:
        助手的最终文本回复。
    """
    messages.append({"role": "user", "content": user_text})
    final = "（达到工具调用轮次上限，已停止）"  # 循环用尽时的兜底值
    for _ in range(max_rounds):
        resp = llm.chat(messages, tools=tools.TOOLS, stream=stream)
        msg = resp["choices"][0]["message"]

        if msg.get("tool_calls"):
            messages.append(msg)  # 保留含 tool_calls 的助手消息
            for tc in msg["tool_calls"]:
                fn_name, tool_result = tools.dispatch(tc)
                if callable(on_tool):
                    on_tool(fn_name, tool_result)
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
        final = msg.get("content", "") or "（模型未返回文本内容）"
        messages.append({"role": "assistant", "content": final})
        break
    else:
        # 达到轮次上限：必须补一条 assistant 消息收尾。
        # 否则历史以孤立的 tool 消息结尾，下一轮的对话模板是畸形的，
        # 会导致模型行为异常（如复读旧答案）。
        messages.append({"role": "assistant", "content": final})

    _trim_history(messages)
    return final


class ChatSession:
    """有状态的会话封装：内部维护 messages，send() 返回助手文本。

    前端持有 ChatSession 实例即可获得多轮对话能力，无需自己管理历史。
    """

    def __init__(self):
        # 系统提示词放最前，约束工具使用行为（对小模型尤其重要）
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def send(self, user_text, on_tool=None, stream: bool = False):
        """发送一条用户消息，返回最终助手文本。"""
        return run_turn(self.messages, user_text, on_tool=on_tool, stream=stream)
