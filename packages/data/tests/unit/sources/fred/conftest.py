"""FRED 单测共享夹具 — 关闭默认节流与 429 退避的真实 sleep."""

from __future__ import annotations

import pytest
from ditto_data.sources.fred import client as fred_client_module


@pytest.fixture(autouse=True)
def _no_fred_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试内禁用 0.5s 默认请求间隔与 10s 起的 429 退避基值.

    节流与退避时序有专测（mock 时钟），其余测试不应真实 sleep.
    """
    monkeypatch.setattr(fred_client_module, "FRED_DEFAULT_MIN_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr(fred_client_module, "_RATE_LIMIT_BACKOFF_BASE_SECONDS", 0.001)
