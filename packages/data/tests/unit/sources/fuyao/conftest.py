"""fuyao 单测共享夹具 — 关闭默认节流与限流退避的真实 sleep."""

from __future__ import annotations

import pytest
from ditto_data.sources.fuyao import client as fuyao_client_module


@pytest.fixture(autouse=True)
def _no_fuyao_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    """测试内禁用 0.1s 默认请求间隔与 2s 起的限流退避基值.

    节流与退避时序有专测（mock 时钟），其余测试不应真实 sleep.
    """
    monkeypatch.setattr(fuyao_client_module, "FUYAO_DEFAULT_MIN_REQUEST_INTERVAL", 0.0)
    monkeypatch.setattr(
        fuyao_client_module, "_FUYAO_RATE_LIMIT_BACKOFF_BASE_SECONDS", 0.001
    )
