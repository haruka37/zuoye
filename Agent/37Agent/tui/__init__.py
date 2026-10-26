"""tui — 基于 Textual 的终端界面前端。

本包是众多可能前端之一（未来还可有 web / desktop / mobile …）。
它只依赖 core 包，自身不实现任何业务逻辑。
"""

from .app import ChatApp

__all__ = ["ChatApp"]
