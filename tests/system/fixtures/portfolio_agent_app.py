"""Production app and DI over synthetic inputs; only the model is replaced."""

from __future__ import annotations

import hashlib
import importlib
import os
import sqlite3
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

import orjson
from ditto_agent.models.fake import ScriptedAgentModel
from ditto_agent.models.port import (
    ModelRequest,
    ModelResult,
    ModelToolCall,
    ModelToolInvoker,
    ModelUsage,
)
from ditto_apps.registry.agent import provider
from ditto_apps.registry.agent.model_provider import AgentModelProviderSettings
from ditto_apps.registry.fresh_runtime import create_fresh_runtime
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from scripts.evidence.portfolio_comparison_live_fixture import seed

if os.environ.get("DITTO_ENVIRONMENT") != "testing":
    raise RuntimeError("portfolio Agent fixture requires testing mode")
_root = Path(os.environ["DITTO_ACCEPTANCE_DATA_ROOT"]).resolve()
if not _root.is_relative_to(Path("/tmp").resolve()):
    raise RuntimeError("portfolio Agent fixture requires isolated /tmp state")
_state = _root / "state"
os.environ.update(
    {
        "DITTO_STATE_ROOT": str(_state),
        "SQLITE_PATH": str(_state / "metadata/metadata.sqlite"),
        "DITTO_TRADING_SQLITE_PATH": str(_state / "trading/trading.sqlite"),
        "ENVIRONMENT": "testing",
        "DITTO_AGENT_ENABLED": "true",
        "DITTO_AGENT_MODEL_CALLS_ENABLED": "true",
        "DITTO_AGENT_MODEL_PROVIDER": "fake",
        "DITTO_AGENT_MODEL_APPROVED_LICENSE_CLASSES": "approved-research",
        "DITTO_AGENT_AUTHOR_ENABLED": "false",
        "DITTO_AGENT_CAMPAIGN_ENABLED": "false",
        "DITTO_AGENT_DECISION_SHADOW_ENABLED": "false",
    }
)
create_fresh_runtime(_state)
_identity = seed(_state)
_model_evidence: list[Mapping[str, object]] = []


class _ComparisonModel(ScriptedAgentModel):
    """Return a cited claim only after the real guarded query has returned."""

    def __init__(self, invoker: ModelToolInvoker) -> None:
        super().__init__()
        self.invoker = invoker

    async def run(self, request: ModelRequest) -> ModelResult:
        call = ModelToolCall(
            call_id="comparison-read",
            tool_name="portfolio_comparison_evidence",
            arguments={
                "strategy_id": "cmp-live-strategy",
                "model_portfolio_id": "cmp-live-model",
                "paper_account_id": "cmp-live-paper",
                "manual_account_id": "cmp-live-manual",
                "paper_session_id": "cmp-live-session",
            },
        )
        evidence = await self.invoker.invoke(
            call.tool_name,
            orjson.dumps(dict(call.arguments)).decode(),
            call_id=call.call_id,
        )
        _model_evidence.append(jsonable_encoder(evidence))
        return ModelResult(
            final_output={
                "claims": [
                    {
                        "claim": "已读取精确组合证据。",
                        "evidence_refs": [evidence["evidence_id"]],
                    }
                ],
                "uncertainty": "确定性模型仅用于工程验收。",
            },
            tool_calls=(call,),
            usage=ModelUsage(requests=1, input_tokens=10, output_tokens=10),
            interruptions=(),
            continuation=None,
        )


def _model(
    settings: AgentModelProviderSettings, *, tool_invoker: ModelToolInvoker
) -> _ComparisonModel:
    if settings.provider.value != "fake":
        raise RuntimeError("system fixture must not construct a live model")
    return _ComparisonModel(tool_invoker)


app = importlib.import_module("ditto_apps.main").app
_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _fixture_lifespan(application: FastAPI) -> AsyncIterator[None]:
    with patch.object(provider, "build_agent_model", _model):
        async with _lifespan(application):
            yield


app.router.lifespan_context = _fixture_lifespan


@app.get("/system-fixture/portfolio")
async def fixture_evidence() -> dict[str, object]:
    """Expose input identities, immutable business rows, and actual tool output."""
    business_hashes: dict[str, str] = {}
    for name in ("metadata", "trading"):
        connection = sqlite3.connect(
            f"file:{_state / name / (name + '.sqlite')}?mode=ro", uri=True
        )
        try:
            rows = "\n".join(
                line for line in connection.iterdump() if line.startswith("INSERT INTO")
            )
            business_hashes[name] = hashlib.sha256(rows.encode()).hexdigest()
        finally:
            connection.close()
    return {
        "identity": _identity,
        "business_hashes": business_hashes,
        "model_evidence": _model_evidence,
    }
