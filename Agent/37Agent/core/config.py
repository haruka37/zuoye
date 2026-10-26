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


# 当 config.ini 完全不存在时使用的默认 LLM 配置：指向本地 LM Studio，
# 这样 clone 项目后无需创建 config.ini 即可启动（前提是本机已运行 LM Studio）。
DEFAULT_LLM = {
    "api_base": "http://localhost:1234/v1",
    "api_key": "lm-studio",
    "model": "qwen/qwen3-4b-2507",
    "temperature": "0.7",
}


def _default_llm_section() -> "configparser.SectionProxy":
    cfg = configparser.ConfigParser()
    cfg["llm"] = dict(DEFAULT_LLM)
    return cfg["llm"]


def load_llm_config(path: str | None = None) -> "configparser.SectionProxy":
    """读取并返回 [llm] 配置段。

    Args:
        path: 可选的自定义配置文件路径；缺省使用项目根目录的 config.ini。

    行为：
    - 配置文件（config.ini）完全不存在时，回退到 DEFAULT_LLM（本地 LM Studio），
      避免 clone 后必须手动建配置文件才能启动。
    - 配置文件存在但缺少 [llm] 段 / 格式错误时，抛出 ConfigError 提示检查文件。
    """
    effective = path or CONFIG_PATH
    cfg = configparser.ConfigParser()
    read_files = cfg.read(effective, encoding="utf-8")
    if "llm" in cfg:
        return cfg["llm"]
    if not read_files:
        # 配置文件缺失：使用默认值，保证可导入、可启动
        return _default_llm_section()
    raise ConfigError(f"未找到有效的 [llm] 配置，请检查 {effective}")


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
