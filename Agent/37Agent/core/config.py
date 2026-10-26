"""配置层：读取项目根目录下的 config.ini，提供 LLM 配置。

本层不依赖任何其他业务模块，是依赖图的最底层。
"""

import configparser
import os

# core/ 的上一级即项目根目录（config.ini 位于此处）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.ini")


class ConfigError(Exception):
    """配置缺失或格式错误时抛出。"""


def load_llm_config(path: str | None = None) -> "configparser.SectionProxy":
    """读取并返回 [llm] 配置段。

    Args:
        path: 可选的自定义配置文件路径；缺省使用项目根目录的 config.ini。
    """
    cfg = configparser.ConfigParser()
    read_files = cfg.read(path or CONFIG_PATH, encoding="utf-8")
    if not read_files or "llm" not in cfg:
        raise ConfigError(f"未找到有效的 [llm] 配置，请检查 {path or CONFIG_PATH}")
    return cfg["llm"]


# 搜索密钥在 config.ini 中的占位符特征（用于判断是否已真实填写）
_SEARCH_KEY_PLACEHOLDER = "在此"


def _read_raw_config(path: str | None = None) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(path or CONFIG_PATH, encoding="utf-8")
    return cfg


def load_search_config(path: str | None = None) -> dict:
    """读取 [search] 配置，并优先用环境变量 BAIDU_QIANFAN_API_KEY 覆盖。

    返回 dict：provider / api_key / configured。
    - 环境变量优先于 config.ini，方便在命令行 / CI 中临时注入密钥，避免写入文件。
    - configured 表示是否已拿到一个非占位的真实密钥。
    """
    cfg = _read_raw_config(path)
    section = cfg["search"] if cfg.has_section("search") else {}
    api_key = os.environ.get("BAIDU_QIANFAN_API_KEY") or section.get(
        "baidu_qianfan_api_key", ""
    )
    if _SEARCH_KEY_PLACEHOLDER in api_key:
        api_key = ""
    return {
        "provider": section.get("provider", "baidu_qianfan"),
        "api_key": api_key,
        "model": section.get("model", ""),
        "configured": bool(api_key),
    }


# 模块级默认配置，供各业务层直接引用
llm = load_llm_config()
search = load_search_config()
