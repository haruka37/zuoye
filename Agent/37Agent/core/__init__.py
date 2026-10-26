"""core — Agent 业务核心包（与任何界面无关，纯 Python）。

分层架构（自底向上）
========================
1. config   配置层     读取项目根目录 config.ini，提供 LLM 配置。
2. llm     客户端层    封装对 OpenAI 兼容 /chat/completions 接口的 HTTP 调用。
3. tools   业务工具层  按领域模块化（system / filesystem），并汇总 function-calling schema 与分发。
4. agent   编排层      会话管理与「模型→工具→模型」循环，是唯一知道对话流程的地方。
5. diagnostics 诊断层 临时目录自检，验证工具逻辑（不依赖 LLM）。

设计约定（扩展前端时遵循）
========================
- 任何前端（tui / web / desktop / mobile …）都只依赖本包，不直接实现业务逻辑。
- 前端包与 core 平级，各自是一个独立目录，例如：
      core/   tui/   web/   desktop/   mobile/
- 前端通过 `from core.agent import ChatSession` 拿到会话能力，
  用 `on_tool=callback` 把工具调用过程回传给界面展示。
- core 内不得出现 input() / print() 等终端 I/O，保证可在 GUI / 服务端 / 测试环境复用。
"""

from .agent import ChatSession, run_turn
from . import tools
from . import llm
from . import config

__all__ = ["ChatSession", "run_turn", "tools", "llm", "config"]
