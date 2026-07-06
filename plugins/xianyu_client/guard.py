"""风控熔断 — 移植自 goofish-cli

检测到 RiskControlError 后写入熔断时间戳，后续请求直接拒绝。
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import RiskControlError

FLASHSLOTH_HOME = Path(os.environ.get("FLASHSLOTH_HOME", Path.home() / ".hermes" / "flashsloth"))
STATE_PATH = FLASHSLOTH_HOME / "xianyu_circuit.json"
DEFAULT_BREAK_MINUTES = 10


def _break_seconds() -> int:
    try:
        return max(60, int(os.environ.get("XIANYU_CIRCUIT_BREAK_MINUTES", DEFAULT_BREAK_MINUTES)) * 60)
    except ValueError:
        return DEFAULT_BREAK_MINUTES * 60


def _load() -> float:
    if not STATE_PATH.exists():
        return 0.0
    try:
        return float(json.loads(STATE_PATH.read_text()).get("until", 0))
    except (json.JSONDecodeError, OSError, ValueError):
        return 0.0


def _save(until: float) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"until": until}))


def check() -> None:
    """检查是否处于熔断状态 — 是则抛 RiskControlError"""
    until = _load()
    if until and time.time() < until:
        remain = int(until - time.time())
        raise RiskControlError(
            f"风控熔断中，剩余 {remain}s。触发后自动冷却，或手动删除 {STATE_PATH}"
        )


def trip(reason: str = "") -> None:
    """触发熔断"""
    _save(time.time() + _break_seconds())


def reset() -> None:
    """手动解除熔断"""
    if STATE_PATH.exists():
        STATE_PATH.unlink()


@contextmanager
def watch():
    """包住写操作：命中 RGV587 自动熔断"""
    check()
    try:
        yield
    except RiskControlError:
        trip()
        raise
