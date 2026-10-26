"""tui 入口：python tui/main.py 或 python -m tui 均可启动。"""

from tui.app import ChatApp


def main() -> None:
    ChatApp().run()


if __name__ == "__main__":
    main()
