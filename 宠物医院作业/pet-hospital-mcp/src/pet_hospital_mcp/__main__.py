"""CLI entry point: ``python -m pet_hospital_mcp``."""

from __future__ import annotations

import uvicorn

from .config import Config
from .logging_config import configure_logging
from .server import create_app


def main() -> None:
    cfg = Config.from_env()
    configure_logging(cfg.log_level)
    app = create_app(cfg)
    # log_config=None keeps our JSON logging untouched by uvicorn.
    uvicorn.run(app, host=cfg.mcp_host, port=cfg.mcp_port, log_config=None)


if __name__ == "__main__":
    main()
