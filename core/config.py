"""FlashSloth 配置管理"""
import os, yaml
from typing import Optional

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "flashsloth.yml")


def load_config(path: Optional[str] = None) -> dict:
    """加载 YAML 配置"""
    path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def get_provider_config(config: dict) -> dict:
    return config.get("provider", {})


def get_publisher_config(config: dict, name: str) -> dict:
    return config.get("publishers", {}).get(name, {})


def get_builder_config(config: dict) -> dict:
    return config.get("builder", {})
