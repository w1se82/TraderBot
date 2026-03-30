import logging
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent


def load_config(path: str | None = None) -> dict:
    load_dotenv(ROOT_DIR / ".env")

    if path is None:
        path = ROOT_DIR / "config" / "settings.yaml"

    with open(path) as f:
        config = yaml.safe_load(f)

    config["broker"]["api_key"] = os.environ["ALPACA_API_KEY"]
    config["broker"]["secret_key"] = os.environ["ALPACA_SECRET_KEY"]

    return config


def setup_logging(config: dict) -> None:
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO"))
    log_file = ROOT_DIR / log_cfg.get("file", "logs/traderbot.log")

    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-5s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file),
        ],
    )
