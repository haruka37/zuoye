"""网页正文抓取工具：基于本地 curl + trafilatura 提取网页 Markdown 正文。

设计要点：
- 用 subprocess（参数列表形式，绝不使用 shell=True）调用系统 curl 下载网页 HTML。
- 用 trafilatura 抽取正文并转 Markdown（去除导航/广告/页脚等噪声，
  尽量保留标题、段落、列表、表格与链接）。
- trafilatura 为按需延迟导入：未安装时仅本工具报错，不影响 core 其余功能。
- 任何失败都返回清晰的中文错误文本给 LLM，不向上抛出异常。
"""

import subprocess

# curl 单次请求超时（秒）
CURL_TIMEOUT = 30
# 正文 Markdown 最大字符数（防止超大页面撑爆上下文）；超出则截断并提示
MAX_MARKDOWN_CHARS = 20000
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class FetchError(Exception):
    """可预期的抓取错误，会被转换为工具结果文本。"""


def _fetch_html(url: str) -> str:
    """用 curl 下载网页 HTML，成功返回解码后的文本，失败抛 FetchError。"""
    # 参数列表形式调用，杜绝 shell 注入；不使用 shell=True
    cmd = [
        "curl", "-sS", "-L", "-f",
        "--max-time", str(CURL_TIMEOUT),
        "-A", USER_AGENT,
        "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=CURL_TIMEOUT + 5,
            check=False,
        )
    except FileNotFoundError:
        raise FetchError("未找到 curl 程序，请确认系统已安装 curl 并在 PATH 中。")
    except subprocess.TimeoutExpired:
        raise FetchError(f"网页访问超时（>{CURL_TIMEOUT}s），请稍后重试或更换链接。")

    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip() or (
            f"curl 退出码 {proc.returncode}"
        )
        raise FetchError(f"curl 请求失败（退出码 {proc.returncode}）：{err[:300]}")

    data = proc.stdout
    if not data:
        raise FetchError("未能获取网页内容（返回为空）。")

    # 编码解码：优先用 charset_normalizer 探测，回退 utf-8
    try:
        import charset_normalizer

        html = str(charset_normalizer.from_bytes(data).best())
    except Exception:
        html = data.decode("utf-8", errors="replace")
    return html


def _extract_markdown(html: str) -> str:
    """用 trafilatura 抽取正文并转 Markdown；失败抛 FetchError。"""
    try:
        import trafilatura
    except ImportError:
        raise FetchError("缺少依赖库 trafilatura，请先执行 pip install trafilatura。")
    try:
        md = trafilatura.extract(
            html,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
    except TypeError:
        # 兼容旧版本：忽略未知参数，仅做基础抽取
        md = trafilatura.extract(html)
    except Exception as e:
        raise FetchError(f"HTML 解析失败：{type(e).__name__}: {e}")

    if not md or not md.strip():
        raise FetchError(
            "无法从该页面提取正文（可能为纯 JS 渲染页面、登录页或内容为空）。"
        )
    return md.strip()


def fetch_web(url: str) -> str:
    """fetchWeb 工具：抓取指定网页并提取 Markdown 正文（附原始 URL）返回给 LLM。"""
    url = (url or "").strip()
    if not url:
        return "fetchWeb 失败：url 为空，请提供有效的网页地址。"
    if not (url.startswith("http://") or url.startswith("https://")):
        return "fetchWeb 失败：仅支持 http/https 链接。"

    try:
        html = _fetch_html(url)
        md = _extract_markdown(html)
    except FetchError as e:
        return f"fetchWeb 失败：{e}"

    if len(md) > MAX_MARKDOWN_CHARS:
        md = md[:MAX_MARKDOWN_CHARS]
        md += f"\n\n…（内容过长已截断至前 {MAX_MARKDOWN_CHARS} 字符）"

    return f"【网页正文】(来源: {url})\n{md}"
