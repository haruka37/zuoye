import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    host: str
    port: int


def load_config() -> Config:
    base_url = os.getenv("ANYTHINGLLM_BASE_URL", "http://localhost:3001").rstrip("/")
    api_key = os.getenv("ANYTHINGLLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANYTHINGLLM_API_KEY 未设置")
    return Config(
        base_url=base_url,
        api_key=api_key,
        host=os.getenv("MCP_HOST", "127.0.0.1"),
        port=int(os.getenv("MCP_PORT", "8000")),
    )