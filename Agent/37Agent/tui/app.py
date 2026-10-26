"""tui/app.py — 基于 Textual 的终端聊天界面。

界面职责：
- 展示用户/助手消息与工具调用过程；
- 把用户输入交给 core.ChatSession 处理；
- 用后台 worker 跑 LLM 调用，避免阻塞终端 UI。

所有业务逻辑都在 core 包，本文件只做「展示 + 调度」。
"""

from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, RichLog

from core.agent import ChatSession


class ChatApp(App):
    """Agent 的 Textual 终端前端。"""

    CSS = """
    Screen { layout: vertical; }

    #chat {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }

    #prompt {
        dock: bottom;
        margin: 1 1 0 1;
    }
    """

    TITLE = "Agent TUI"
    SUB_TITLE = "core + textual"

    def compose(self) -> ComposeResult:
        yield Header()
        yield RichLog(id="chat", wrap=True, markup=True, highlight=False)
        yield Input(
            placeholder="你的问题是（回车发送，Ctrl+C 退出）",
            id="prompt",
        )
        yield Footer()

    def on_mount(self) -> None:
        # 会话状态由 core 负责，前端只持有引用
        self.session = ChatSession()
        self.chat = self.query_one("#chat", RichLog)
        self.prompt = self.query_one("#prompt", Input)
        self.chat.write("欢迎使用 Agent（输入问题开始，Ctrl+C 退出）")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        self.prompt.value = ""
        if not text:
            return
        await self._run_agent(text)

    async def _run_agent(self, text: str) -> None:
        self.chat.write(f"[bold cyan]你：[/]{text}")
        self.prompt.disabled = True  # 处理中禁用输入，防止并发发送

        # 工具调用发生在 worker 线程，需通过 call_from_thread 安全回写 UI
        def on_tool(name, result):
            self.call_from_thread(
                self.chat.write, f"[dim]（调用工具 {name}：{result}）[/]"
            )

        def work():
            return self.session.send(text, on_tool=on_tool)

        try:
            # 新版 Textual 的 Worker 不可直接 await，需用 worker.wait() 等待结果
            worker = self.run_worker(work, thread=True, exit_on_error=False)
            reply = await worker.wait()
        except Exception as exc:  # 网络 / LLM 服务不可达等
            reply = f"[red]出错了：{exc}[/]"
        finally:
            self.prompt.disabled = False

        self.chat.write(f"[bold green]助手：[/]{reply}")
        self.chat.write("")
        self.prompt.focus()
