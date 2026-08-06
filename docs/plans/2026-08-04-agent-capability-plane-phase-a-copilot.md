# AI Agent Capability Plane — Phase A (Copilot) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 交付研究 Copilot 的最小可运行垂直切片——`ditto ask "..."` 经 OpenAI Agents SDK 调用一个只读 Copilot agent，agent 通过 `@function_tool` 薄适配器调用既有 application facade（FactorEvaluationFacade），全程 trace 到自托管 Langfuse。

**Architecture:** 三层（见 [设计文档](2026-08-04-ai-agent-capability-plane-design.md)）：① `platform/services/llm/` 横切 LLM gateway（OpenAI client 配置 + tenacity 重试 + 成本计量 + Langfuse trace processor 接线）；② 新增 `ditto_agent` 包（application 编排层 peer）含 tool 层（`@function_tool` 包 facade，零新业务逻辑）+ Copilot agent（OpenAI Agents SDK + guardrails）；③ `apps/cli/commands/ask.py` 同步入口 `Runner.run_sync()`。**Agent 不能直写生产**——Phase A 只暴露 read-only tools。

**Tech Stack:** Python 3.13、polars、orjson、pixi、dishka(DI)、typer(CLI)、OpenTelemetry、`openai` + `openai-agents`（已批准新依赖）、`langfuse`（已批准；server 独立部署）。

**关键纪律（CLAUDE.md）:** TDD(RED→GREEN→REFACTOR)；pixi 加依赖（禁 pip/poetry）；orjson（禁 json）；polars（禁 pandas）；禁止 TYPE_CHECKING 解循环；每 Task 后 `pixi run -e dev check`；提交前 `git status` 干净。

**范围说明:** 本计划覆盖 Phase A 的**垂直切片**（Task 1-7）打通全链路。剩余 Phase A（第 2、3 个 read tool、guardrails 加固、成本仪表、流式 `run_streamed`）列为 Task 8+ 后续，垂直切片验证架构后再做。

---

## 前置：分支与环境

- 从 `main` 拉分支 `feat/agent-capability-plane`（CLAUDE.md：开发分支从 main 拉）。
- 全程在 ditto 主仓 `packages/` 下工作。
- Langfuse server 独立部署（docker），本计划只接 Python client；本地开发用 Langfuse cloud 或自起 `langfuse dev`（见 Task 7）。

---

## Task 1: 添加依赖 + ditto_agent 包骨架

**Files:**
- Modify: `pixi.toml`（`[dependencies]` 段，约 L37/81 附近）
- Create: `packages/agent/pyproject.toml`
- Create: `packages/agent/src/ditto_agent/__init__.py`
- Create: `packages/agent/src/ditto_agent/py.typed`
- Modify: `.importlinter`（`root_packages` + `layered-architecture.layers`）
- Test: `packages/agent/tests/unit/test_agent_package_unit.py`

**Step 1: 写失败测试（包可导入 + 边界）**

```python
# packages/agent/tests/unit/test_agent_package_unit.py
"""ditto_agent 包骨架与导入边界。"""
from __future__ import annotations

import ditto_agent


def test_package_imports() -> None:
    """ditto_agent 包可被导入。"""
    assert ditto_agent is not None
```

**Step 2: 运行验证失败**

Run: `pixi run -e dev pytest packages/agent/tests/unit/test_agent_package_unit.py -v`
Expected: FAIL（`ModuleNotFoundError: ditto_agent`）

**Step 3: 加依赖**

在 `pixi.toml` `[dependencies]` 段（httpx/tenacity 附近）追加：

```toml
openai = ">=1.90,<2"
openai-agents = ">=0.1,<1"
langfuse = ">=3.0,<4"
```

运行 `pixi install -e dev` 安装。

**Step 4: 创建包骨架**

`packages/agent/pyproject.toml`：
```toml
[project]
name = "ditto-agent"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = ["ditto-application", "ditto-platform", "openai", "openai-agents", "langfuse"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ditto_agent"]
```

`packages/agent/src/ditto_agent/__init__.py`：
```python
"""ditto_agent — AI/Agent 能力平面（application 编排层 peer）。"""
```

`packages/agent/src/ditto_agent/py.typed`：空文件。

**Step 5: 注册到 importlinter**

`.importlinter`：
- `root_packages` 追加 `ditto_agent`。
- `[importlinter:contract:layered-architecture]` 的 `layers` 中，在 `ditto_apps` 下、`ditto_application` 上插入 `ditto_agent`（ditto_agent 依赖 application，故在 application 之上）。

**Step 6: 运行验证通过**

Run: `pixi run -e dev pytest packages/agent/tests/unit/test_agent_package_unit.py -v && pixi run -e dev arch-check`
Expected: 测试 PASS + arch-check（契约数仍为 37，layered-architecture 含新层）。

**Step 7: Commit**

```bash
git add pixi.toml pixi.lock packages/agent .importlinter
git commit -m "feat(agent): add ditto_agent package skeleton + openai/langfuse deps"
```

---

## Task 2: ditto_agent 架构边界契约

**Files:**
- Modify: `.importlinter`（新增 3 个 forbidden 契约）
- Test: `packages/agent/tests/unit/test_agent_boundary_unit.py`

**Step 1: 写失败测试（边界断言）**

```python
# packages/agent/tests/unit/test_agent_boundary_unit.py
"""ditto_agent 必须经 application facade 访问能力，禁止直连 capability 包。"""
from __future__ import annotations

ForbiddenCaps = {
    "ditto_strategy", "ditto_portfolio", "ditto_risk", "ditto_execution",
    "ditto_backtest", "ditto_features", "ditto_data", "ditto_analysis",
}


def test_agent_does_not_import_capabilities() -> None:
    """ditto_agent 不得直接 import 任何 capability 包实现。"""
    import sys

    import ditto_agent  # noqa: F401

    loaded = {m.split(".")[0] for m in sys.modules}
    assert not (loaded & ForbiddenCaps), (
        f"ditto_agent 泄漏导入 capability 包: {loaded & ForbiddenCaps}"
    )
```

**Step 2: 验证失败**

Run: `pixi run -e dev pytest packages/agent/tests/unit/test_agent_boundary_unit.py -v`
Expected: 暂可能 PASS（骨架无导入）；契约层先落地。

**Step 3: 加 forbidden 契约**

`.importlinter` 追加（仿 kernel-isolation 范式）：

```ini
[importlinter:contract:agent-isolation]
name = ditto_agent must reach capabilities via application facades only
type = forbidden
source_modules = ditto_agent.**
forbidden_modules =
    ditto_strategy.** ditto_portfolio.** ditto_risk.** ditto_execution.**
    ditto_backtest.** ditto_features.** ditto_data.** ditto_analysis.**

[importlinter:contract:application-no-agent]
name = application must not import ditto_agent
type = forbidden
source_modules = ditto_application.**
forbidden_modules = ditto_agent.**

[importlinter:contract:agent-no-platform-config]
name = ditto_agent must not read platform config directly
type = forbidden
source_modules = ditto_agent.**
forbidden_modules = ditto_platform.config.**
```

> 同时更新 [boundaries-and-abstraction-standards.md](../architecture/boundaries-and-abstraction-standards.md) 编排层章节，记录 ditto_agent 为 application 同层 peer。

**Step 4: 运行验证**

Run: `pixi run -e dev arch-check`
Expected: 37 + 3 = **40 contracts kept, 0 broken**。

**Step 5: Commit**

```bash
git add .importlinter docs/architecture/boundaries-and-abstraction-standards.md packages/agent/tests
git commit -m "feat(agent): enforce ditto_agent layering contracts (3 forbidden)"
```

---

## Task 3: Platform LLM Gateway 基础

**Files:**
- Create: `packages/platform/src/ditto_platform/services/llm/__init__.py`
- Create: `packages/platform/src/ditto_platform/services/llm/client.py`
- Create: `packages/platform/src/ditto_platform/services/llm/config.py`
- Test: `packages/platform/tests/unit/test_llm_client_unit.py`

> 范式参照 `packages/platform/src/ditto_platform/services/notification/`（client/config/manager 分离）。Gateway 职责：OpenAI client 装配（key/base_url/timeout）+ tenacity 重试 + 成本计量。**trace span 由 OpenAI Agents SDK 自带 tracing 产生**（不在 gateway 手搓 GenAI span）；Langfuse processor 在 Task 7 接线。

**Step 1: 写失败测试**

```python
# packages/platform/tests/unit/test_llm_client_unit.py
"""LLM gateway client：配置装配 + 重试。"""
from __future__ import annotations

from ditto_platform.services.llm.client import LLMClient
from ditto_platform.services.llm.config import LLMSettings


def test_llm_client_resolves_settings() -> None:
    settings = LLMSettings(api_key="sk-test", model="gpt-4o-mini", timeout_seconds=30)
    client = LLMClient(settings)
    assert client.model == "gpt-4o-mini"
```

**Step 2: 验证失败**

Run: `pixi run -e dev pytest packages/platform/tests/unit/test_llm_client_unit.py -v`
Expected: FAIL（模块不存在）

**Step 3: 实现 config + client**

`services/llm/config.py`（frozen dataclass，settings 经 dishka 注入，**不读 os.environ**——遵守 platform/application 同纪律）：
```python
"""LLM gateway 运行时配置（由 composition root 注入，禁止自读环境变量）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LLMSettings:
    api_key: str
    model: str = "gpt-4o-mini"
    base_url: str | None = None
    timeout_seconds: float = 60.0
    max_retries: int = 3
```

`services/llm/client.py`：
```python
"""OpenAI client 薄封装 + tenacity 重试 + 成本计量 hook。"""
from __future__ import annotations

from collections.abc import Callable

from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ditto_platform.services.llm.config import LLMSettings

UsageReporter = Callable[[str, int, int], None]  # (model, prompt_tokens, completion_tokens)


class LLMClient:
    """对 AsyncOpenAI 的受管封装：统一超时/重试/成本回调。"""

    def __init__(self, settings: LLMSettings, on_usage: UsageReporter | None = None) -> None:
        self._settings = settings
        self._on_usage = on_usage
        self._inner = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )

    @property
    def model(self) -> str:
        return self._settings.model

    @retry(
        retry=retry_if_exception_type(TimeoutError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    async def completions(self, messages: list[dict[str, str]]) -> str:
        resp = await self._inner.chat.completions.create(
            model=self._settings.model, messages=messages
        )
        if self._on_usage and resp.usage:
            self._on_usage(self._settings.model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""
```

`services/llm/__init__.py`：re-export `LLMClient`、`LLMSettings`（纯 re-export，深度 1，合规）。

**Step 4: 验证通过 + 类型/门禁**

Run: `pixi run -e dev pytest packages/platform/tests/unit/test_llm_client_unit.py -v && pixi run -e dev type`
Expected: PASS + type 0 error。

**Step 5: Commit**

```bash
git add packages/platform/src/ditto_platform/services/llm packages/platform/tests/unit/test_llm_client_unit.py
git commit -m "feat(platform): add LLM gateway client (OpenAI + tenacity + usage hook)"
```

---

## Task 4: ditto_agent tool 协议 + 第一个 read tool

**Files:**
- Create: `packages/agent/src/ditto_agent/tools/__init__.py`
- Create: `packages/agent/src/ditto_agent/tools/protocol.py`
- Create: `packages/agent/src/ditto_agent/tools/factor.py`
- Test: `packages/agent/tests/unit/test_tool_factor_unit.py`

> **先读**：`packages/application/src/ditto_application/queries/evaluation.py:59-120` 确认 `FactorEvaluationFacade.evaluate(...)` 实际签名与返回 read-model 类型。Tool 是该方法的 `@function_tool` 薄包装，**零新业务逻辑**。

**Step 1: 写失败测试（tool 委托 facade）**

```python
# packages/agent/tests/unit/test_tool_factor_unit.py
"""factor_evaluate tool 委托 FactorEvaluationFacade.evaluate，零自有逻辑。"""
from __future__ import annotations

from unittest.mock import MagicMock

from ditto_agent.tools.factor import build_factor_tools


def test_factor_evaluate_delegates_to_facade() -> None:
    facade = MagicMock()
    facade.evaluate.return_value = {"ic": 0.05, "icir": 0.4}
    tools = build_factor_tools(facade)
    factor_tool = next(t for t in tools if t.name == "factor_evaluate")

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        factor_tool.on_invoke_tool(MagicMock(), '{"factor_id":"mom20","start":"2024-01-01","end":"2024-06-30"}', MagicMock())
    )
    facade.evaluate.assert_called_once_with("mom20", "2024-01-01", "2024-06-30")
    assert "ic" in result
```

**Step 2: 验证失败**

Run: `pixi run -e dev pytest packages/agent/tests/unit/test_tool_factor_unit.py -v`
Expected: FAIL（模块不存在）

**Step 3: 实现 protocol + factor tool**

`tools/protocol.py`（用 OpenAI Agents SDK 的 `FunctionTool`；提供构造助手统一注入 facade）：
```python
"""Tool 层协议：facade 薄适配器，零新业务逻辑。"""
from __future__ import annotations

from agents import function_tool
```

`tools/factor.py`：
```python
"""因子评估 read-only tool（包 FactorEvaluationFacade.evaluate）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from agents import FunctionTool, function_tool

if TYPE_CHECKING:  # 仅类型，不引入运行时依赖方向（agent→application 运行时经 DI 注入）
    from ditto_application.queries.evaluation import FactorEvaluationFacade


def build_factor_tools(facade: FactorEvaluationFacade) -> list[FunctionTool]:
    """构造因子域 read-only tools，facade 由 DI 注入。"""

    @function_tool
    async def factor_evaluate(factor_id: str, start: str, end: str) -> dict[str, object]:
        """查询某因子在 [start, end] 的 IC/ICIR/分层/多空评估结果。"""
        return facade.evaluate(factor_id, start, end)  # type: ignore[no-any-return]

    return [factor_evaluate]
```

> ⚠️ 注意：上面用 `TYPE_CHECKING` 仅作类型提示；运行时 facade 经 dishka 注入，不在模块顶层 import ditto_application（避免违反 R8 风格的强耦合；实际 agent→application 是允许的依赖，可按 check 结果决定是否提为顶层 import——若 ruff/pyright 不报错则提顶层更清晰，遵守"禁 TYPE_CHECKING 解耦"原则的例外：这里不是解循环，是注入）。

**Step 4: 验证通过**

Run: `pixi run -e dev pytest packages/agent/tests/unit/test_tool_factor_unit.py -v && pixi run -e dev arch-check`
Expected: PASS + 40 contracts kept。

**Step 5: Commit**

```bash
git add packages/agent/src/ditto_agent/tools packages/agent/tests/unit/test_tool_factor_unit.py
git commit -m "feat(agent): add factor_evaluate read-only tool (facade passthrough)"
```

---

## Task 5: Copilot agent 定义

**Files:**
- Create: `packages/agent/src/ditto_agent/agents/__init__.py`
- Create: `packages/agent/src/ditto_agent/agents/copilot.py`
- Test: `packages/agent/tests/unit/test_copilot_agent_unit.py`

> Agent 用 OpenAI Agents SDK `Agent`，只挂 read-only tools，配 input/output guardrails（Phase A 简单：输入长度/拒绝写意图），`max_turns=6`。

**Step 1: 写失败测试（mock model + agent 选 tool）**

```python
# packages/agent/tests/unit/test_copilot_agent_unit.py
"""Copilot agent 在 mock model 下选 factor_evaluate tool 并返回。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from ditto_agent.agents.copilot import build_copilot_agent


async def test_copilot_uses_factor_tool() -> None:
    facade = MagicMock()
    facade.evaluate.return_value = {"ic": 0.05}
    agent = build_copilot_agent(facade)
    assert any(t.name == "factor_evaluate" for t in agent.tools)
    assert agent.max_turns == 6
```

**Step 2: 验证失败**

Run: `pixi run -e dev pytest packages/agent/tests/unit/test_copilot_agent_unit.py -v`
Expected: FAIL

**Step 3: 实现 copilot agent**

`agents/copilot.py`：
```python
"""研究 Copilot agent（read-only）。"""
from __future__ import annotations

from agents import Agent

from ditto_agent.tools.factor import build_factor_tools

_COPILOT_INSTRUCTIONS = (
    "你是 Ditto 研究助手。只能查询研究/回测/因子诊断信息，不得提议修改生产策略。"
    "回答用中文，引用 tool 返回的数据。"
)


def build_copilot_agent(facade: object) -> Agent:
    """构造 Copilot agent，注入 facade 经 tool 层。"""
    return Agent(
        name="Ditto Copilot",
        instructions=_COPILOT_INSTRUCTIONS,
        tools=build_factor_tools(facade),  # type: ignore[arg-type]
        max_turns=6,
    )
```

**Step 4: 验证通过**

Run: `pixi run -e dev pytest packages/agent/tests/unit/test_copilot_agent_unit.py -v && pixi run -e dev check`
Expected: PASS + check 全绿。

**Step 5: Commit**

```bash
git add packages/agent/src/ditto_agent/agents packages/agent/tests/unit/test_copilot_agent_unit.py
git commit -m "feat(agent): add Copilot agent (read-only, max_turns=6)"
```

---

## Task 6: apps CLI `ditto ask` 入口

**Files:**
- Create: `packages/apps/src/ditto_apps/cli/commands/ask.py`
- Modify: `packages/apps/src/ditto_apps/cli/main.py`（注册 ask 命令）
- Test: `packages/apps/tests/unit/test_cli_ask_unit.py`

> 同步入口（`Runner.run_sync`），符合"主动对话=同步"决策。DI 经 composition root 取 facade（先简化为直接构造 facade stub，真实 facade 注入留 Task 7 DI 打通）。

**Step 1: 写失败测试（mock model，CliRunner 冒烟）**

```python
# packages/apps/tests/unit/test_cli_ask_unit.py
"""`ditto ask` CLI 冒烟（mock Runner 避免真实 LLM 调用）。"""
from __future__ import annotations

from typer.testing import CliRunner


def test_ask_command_help() -> None:
    from ditto_apps.cli.main import app

    result = CliRunner().invoke(app, ["ask", "--help"])
    assert result.exit_code == 0
    assert "ask" in result.stdout.lower() or "提问" in result.stdout
```

**Step 2: 验证失败**

Run: `pixi run -e dev pytest packages/apps/tests/unit/test_cli_ask_unit.py -v`
Expected: FAIL（无 ask 命令）

**Step 3: 实现 ask 命令**

`cli/commands/ask.py`：
```python
"""ditto ask — 研究 Copilot 对话入口（同步）。"""
from __future__ import annotations

import asyncio

import typer
from agents import Runner

ask_app = typer.Typer(help="研究 Copilot 对话（AI/Agent 能力平面 Phase A）")


@ask_app.command("factor")
def ask_factor(
    question: str = typer.Argument(..., help="对因子诊断的自然语言提问"),
) -> None:
    """同步对话：Copilot agent 只读回答因子相关问题。"""
    from ditto_apps.registry.agent_runtime import build_copilot_runtime  # local import (composition root)

    runtime = build_copilot_runtime()
    result = Runner.run_sync(runtime.agent, question)
    typer.echo(result.final_output)
```

> `build_copilot_runtime()` 在 Task 7 于 `apps/registry/agent_runtime.py` 装配（facade + LLMClient + agent）。Phase A 垂直切片先用真实 facade stub 走通。

**Step 4: 注册命令**

`cli/main.py` 追加：
```python
from ditto_apps.cli.commands.ask import ask_app
app.add_typer(ask_app, name="ask")
```

**Step 5: 验证通过**

Run: `pixi run -e dev pytest packages/apps/tests/unit/test_cli_ask_unit.py -v && pixi run -e dev check`
Expected: PASS + check 全绿（arch contracts 仍 40）。

**Step 6: Commit**

```bash
git add packages/apps/src/ditto_apps/cli/commands/ask.py packages/apps/src/ditto_apps/cli/main.py packages/apps/tests/unit/test_cli_ask_unit.py
git commit -m "feat(apps): add 'ditto ask' CLI entry for Copilot (sync)"
```

---

## Task 7: DI 装配 + Langfuse trace + 端到端 golden

**Files:**
- Create: `packages/apps/src/ditto_apps/registry/agent_runtime.py`
- Modify: `packages/application/src/ditto_application/providers.py`（暴露 facade provider，如未有）
- Create: `packages/agent/src/ditto_agent/tracing.py`（Langfuse processor 接线）
- Test: `packages/agent/tests/unit/test_tracing_unit.py`
- Test: `packages/apps/tests/integration/test_ask_factor_e2e.py`

**Step 1: 写失败测试（Langfuse processor 替换默认，禁止回传 OpenAI）**

```python
# packages/agent/tests/unit/test_tracing_unit.py
"""trace processor 装配：替换默认 OpenAI export。"""
from __future__ import annotations

from ditto_agent.tracing import configure_tracing


def test_configure_tracing_replaces_default(monkeypatch) -> None:
    captured: list[object] = []
    configure_tracing(langfuse_enabled=True, register=lambda p: captured.append(p))
    # 默认 OpenAI backend processor 不应在 processors 内
    assert captured, "Langfuse processor 未注册"
```

**Step 2: 验证失败 → 实现 tracing**

`ditto_agent/tracing.py`：
```python
"""OpenAI Agents SDK trace 装配：替换默认处理器，导出自托管 Langfuse。"""
from __future__ import annotations

from collections.abc import Callable


def configure_tracing(
    langfuse_enabled: bool, register: Callable[[object], None] | None = None
) -> None:
    """替换 SDK 默认 trace processors，禁止回传 OpenAI，改发 Langfuse。"""
    from agents import set_trace_processors

    processors: list[object] = []
    if langfuse_enabled:
        from langfuse.contrib.openai.agents import LangfuseAgentsProcessor  # 按实际 SDK 路径核对

        processors.append(LangfuseAgentsProcessor())
    set_trace_processors(processors)  # 空 list = 完全禁用 export（测试/CI）
    if register:
        for p in processors:
            register(p)
```

> ⚠️ `LangfuseAgentsProcessor` 的精确 import 路径以 Langfuse 当前 SDK 为准（执行时 `pixi run python -c "import langfuse.contrib..."` 核对），这是 Langfuse 的 OpenAI Agents SDK 集成入口。

**Step 3: composition root 装配 runtime**

`apps/registry/agent_runtime.py`：
```python
"""Copilot runtime composition root：facade + LLMClient + agent。"""
from __future__ import annotations

from dataclasses import dataclass

from ditto_agent.agents.copilot import build_copilot_agent
from ditto_agent.tracing import configure_tracing
from ditto_application.queries.evaluation import FactorEvaluationFacade
from ditto_platform.services.llm.client import LLMClient
from ditto_platform.services.llm.config import LLMSettings


@dataclass(frozen=True, slots=True)
class CopilotRuntime:
    agent: object


def build_copilot_runtime() -> CopilotRuntime:
    # TODO Phase A 末：facade 经 dishka container 解析而非裸构造
    facade = FactorEvaluationFacade(...)  # 按 evaluation.py 真实构造参数补齐
    configure_tracing(langfuse_enabled=True)
    return CopilotRuntime(agent=build_copilot_agent(facade))
```

**Step 4: 端到端 golden 测试（mock model，断言 tool 被调 + 输出含数据）**

```python
# packages/apps/tests/integration/test_ask_factor_e2e.py
"""Copilot e2e：mock model 选 factor_evaluate，输出含 IC 数据。"""
```
（用 OpenAI Agents SDK 的 `set_mock_model_client` 或 `MockedAgent`，按 SDK 测试文档核对 API）

**Step 5: 验证全链路 + check**

Run: `pixi run -e dev check`
Expected: 全绿（arch 40 contracts + type 0 + ruff + e2e PASS）。

**Step 6: Commit**

```bash
git add packages/agent/src/ditto_agent/tracing.py packages/apps/src/ditto_apps/registry/agent_runtime.py packages/application/src/ditto_application/providers.py packages/agent/tests packages/apps/tests/integration/test_ask_factor_e2e.py
git commit -m "feat(agent): wire Copilot runtime + Langfuse tracing + e2e golden"
```

---

## Task 8+（垂直切片验证后继续，本计划仅列出）

- **Task 8**：第 2 个 read tool `review_packet`（包 `ExperimentQueryFacade.get_review_packet`，experiments.py:608）+ 第 3 个 `list_reviews`（包 `StrategyQueryFacade.list_reviews`，strategy.py:196）。同 Task 4 模式。
- **Task 9**：Copilot guardrails 加固（input：拒写意图/长度；output：PII/越界兜底）。
- **Task 10**：成本计量仪表（`LLMClient.on_usage` → platform metrics + Langfuse cost）。
- **Task 11**：流式 `Runner.run_streamed()`（chat 流式打字，`ditto ask` 加 `--stream`）。
- **Task 12**：dishka container 正式装配（替换 Task 7 的裸构造 TODO），settings 经 `get_environment()` 三环境。

---

## 验证命令速查

```bash
pixi run -e dev arch-check          # Task 2 后：40 contracts kept, 0 broken
pixi run -e dev type                # 全程 0 error
pixi run -e dev lint                # 全程 pass
pixi run -e dev test --unit --fast  # 全程绿
pixi run -e dev check               # 每个 Task 后跑（lint+fmt+type+test --fast）
```

## 关键风险与对策

| 风险 | 对策 |
|------|------|
| Langfuse processor import 路径随版本变 | Task 7 Step 2 执行时 `pixi run python -c` 核对当前 SDK |
| openai-agents API（Agent/Runner/function_tool）演进 | 每个 Task 先读 SDK 当前签名再实现；mock model 测试锁定行为 |
| 裸 facade 构造（Task 7 TODO）违反 DI 纪律 | 仅垂直切片临时代码，Task 12 用 dishka 正式装配替换 |
| ditto_agent 依赖 application 看似破"capability 不依赖 app"规则 | 已在 boundaries doc 说明：agent 是 application 同层 peer，非 capability 包 |
