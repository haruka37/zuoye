"""联网搜索工具：基于百度千帆「百度搜索」API（POST /v2/ai_search/web_search）。

与「智能搜索生成」不同，本接口返回的是原始搜索结果列表（references），
每项含标题、链接与摘要片段。鉴权复用 config 中的 baidu_qianfan_api_key，
本文件不硬编码任何密钥。任何失败都返回清晰的中文错误文本给 LLM，不向上抛异常。
"""

import json
import socket
import urllib.error
import urllib.request

from .. import config

# 百度搜索接口地址（Bearer API Key 鉴权，返回 references 搜索结果列表）
WEB_SEARCH_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"

# 单次网页结果返回条数。
# 注意：条数越多返回给 LLM 的上下文越大，本地小模型上下文有限，
# 过长的工具结果会挤占上下文甚至导致模型行为异常，因此默认只取 5 条。
DEFAULT_TOP_K = 5
# 单条摘要返回给 LLM 的最大字符数
SNIPPET_MAX_CHARS = 200
# 整个搜索结果文本的最大字符数（超出截断并标明）
MAX_RESULT_CHARS = 3000
# 单次请求超时（秒）
TIMEOUT = 30


class SearchError(Exception):
    """可预期的搜索错误，会被转换为工具结果文本。"""


def _truncate_query(query: str) -> str:
    """百度搜索限制 content 长度 72（一个汉字计 2 个字符），超出只取前半段。"""
    measure, out = 0, []
    for ch in query:
        measure += 2 if ord(ch) > 0x2E80 else 1
        if measure > 72:
            break
        out.append(ch)
    return "".join(out)


def _fetch(query: str, api_key: str) -> dict:
    """调用百度搜索接口，返回解析后的 JSON（异常时抛 SearchError）。"""
    payload = {
        "messages": [{"role": "user", "content": query}],
        "search_source": "baidu_search_v2",
        "resource_type_filter": [{"type": "web", "top_k": DEFAULT_TOP_K}],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        WEB_SEARCH_URL,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + api_key,
        },
        method="POST",
    )

    raw = ""
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise SearchError(f"HTTP {e.code}：{body[:500]}")
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise SearchError(f"网络错误（{type(e).__name__}）：{reason}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise SearchError("响应不是合法 JSON，无法解析搜索结果")


def _extract_references(data: dict) -> list:
    """从响应中抽取搜索结果列表（兼容 references / search_result / refer 等字段名）。"""
    if not isinstance(data, dict):
        return []
    for key in ("references", "search_result", "refer", "results", "data"):
        items = data.get(key)
        if isinstance(items, list) and items:
            return items
    return []


def _norm_ref(item) -> dict:
    if not isinstance(item, dict):
        return {"title": "", "url": "", "snippet": ""}
    title = item.get("title") or item.get("name") or item.get("site_name") or ""
    url = (
        item.get("url")
        or item.get("link")
        or item.get("source")
        or item.get("web_anchor")
        or ""
    )
    snippet = (
        item.get("snippet")
        or item.get("content")
        or item.get("abstract")
        or item.get("description")
        or ""
    )
    return {"title": str(title), "url": str(url), "snippet": str(snippet)}


def _format_result(refs: list) -> str:
    lines = ["【联网搜索结果】"]
    for i, r in enumerate(refs, 1):
        nr = _norm_ref(r)
        title = nr["title"] or "(无标题)"
        url = nr["url"] or "(无链接)"
        lines.append(f"{i}. {title}")
        lines.append(f"   URL: {url}")
        if nr["snippet"]:
            snippet = nr["snippet"]
            if len(snippet) > SNIPPET_MAX_CHARS:
                snippet = snippet[:SNIPPET_MAX_CHARS] + "…（摘要已截断）"
            lines.append(f"   摘要: {snippet}")
    text = "\n".join(lines)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + f"\n…（搜索结果整体过长已截断：原始 {len(text)} 字符）"
    return text


def search_web(query: str) -> str:
    """联网搜索工具：根据关键词/问题调用百度搜索，返回「标题 + 链接 + 摘要」列表给 LLM。"""
    query = (query or "").strip()
    if not query:
        return "搜索失败：query 为空，请提供搜索关键词或问题。"

    # 每次调用都重新读取配置（兼顾环境变量与文件配置）
    cfg = config.load_search_config()
    api_key = cfg.get("api_key", "")
    if not api_key:
        return (
            "搜索功能未配置：缺少 baidu_qianfan_api_key。"
            "请在 config.ini 的 [search] 小节填入，或设置环境变量 BAIDU_QIANFAN_API_KEY。"
        )

    q = _truncate_query(query)
    try:
        data = _fetch(q, api_key)
    except SearchError as e:
        return f"搜索请求失败：{e}"

    # API 层错误（响应体里带 code / message）
    for err_key in ("error", "message", "error_msg"):
        err = data.get(err_key)
        if isinstance(err, str) and err.strip():
            return f"搜索服务返回错误：{err}"
    code = data.get("code")
    if code not in (None, 0, "0"):
        return f"搜索服务返回错误（code={code}）：{data.get('message', '')}"

    refs = _extract_references(data)
    if not refs:
        return "搜索服务未返回任何结果（references 为空）。"
    return _format_result(refs)
