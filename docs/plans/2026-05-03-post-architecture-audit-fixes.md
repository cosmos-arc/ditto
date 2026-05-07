# Post-Architecture Audit Fixes

> **Status:** PLANNING
> **Created:** 2026-05-03
> **Source:** 架构重构完成度审计（brainstorming session 同日）

**Goal:** 修复架构审计中发现的所有遗漏和偏差——配置清理、依赖一致性、Platform 业务泄漏、空壳契约实现、文档遗留引用。

**Architecture:** 纯修复和补全，不引入新功能。所有变更保持 `check + arch-check` 通过。

**Tech Stack:** Python 3.13, ruff, basedpyright, pytest, import-linter.

---

## 审计结论修正

审计初步报告将以下项目标记为问题，**源码分析后确认为非问题**：

| 初步判断 | 修正后 | 原因 |
|---------|--------|------|
| kernel 含领域概念（strategy/quality/research） | **合理放置** | `kernel.strategy` 被 7 包 97 处引用（纯枚举+frozen dataclass）；`kernel.quality` 被 3 包 28 处引用；`kernel.research` 被 2 包 12 处引用。零行为，零外部依赖，符合 kernel "跨模块稳定值对象" 定位 |
| portfolio 依赖声明不足（缺 data/strategy） | **声明正确** | portfolio 源码零 import data/strategy，通过上层 application 注入。设计文档依赖矩阵有误 |
| 无 adapters/ 模式 | **等效替代** | 项目用 `storage/` 替代 `adapters/` 命名，功能等价，命名更直白 |
| backtest 无独立 simulated_broker | **合理内联** | 回测通过 steps/execution.py 处理，当前阶段无独立模拟券商需求 |
| application/runtime/ 为空 | **合理占位** | runtime 职责（事件循环/时钟/模式切换）由 builders/ 承担，runtime 暂为扩展保留 |
| platform observability metrics 含业务名 | **务实妥协** | metrics 需要知道业务域度量名，allowlist 已管控。全面清理 ROI 低 |

---

## Execution Rules

1. 每个 task 单独提交，提交前至少运行 task 内指定验证命令。
2. 不引入新功能，不改变外部行为。
3. 每次 import 变更先用 `rg` 定位引用，再改，再跑 `type + arch-check`。
4. 不用 `TYPE_CHECKING` 延迟导入。

## Global Verification Commands

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # import-linter + smell check
```

---

## Phase 1: 配置与命名清理

### Task 1.1: 删除遗留 egg-info `[S]`

**问题:** `packages/platform/src/ditto_infra.egg-info/` 和 `packages/application/src/ditto_app.egg-info/` 是 rename 时未清理的构建产物。

**文件:**
- Delete: `packages/platform/src/ditto_infra.egg-info/`
- Delete: `packages/application/src/ditto_app.egg-info/`

**步骤:**
1. `rm -rf packages/platform/src/ditto_infra.egg-info`
2. `rm -rf packages/application/src/ditto_app.egg-info`
3. 确认 `.gitignore` 已覆盖 `*.egg-info`（否则添加）

**验证:** `find packages/ -name "*.egg-info" -type d` 仅剩 12 个当前包的 egg-info

---

### Task 1.2: 对齐 kernel 版本号 `[S]`

**问题:** kernel 版本 `0.2.0`，其他 11 包 `0.1.0`，root pyproject `version = "0.1.0"`。

**文件:**
- Modify: `packages/kernel/src/ditto_kernel/_version.py` → `0.1.0`
- Modify: `packages/kernel/src/ditto_kernel/__init__.py` 版本引用

**验证:** `pixi run -e dev test --fast`

---

### Task 1.3: 重命名 AnalyticsError → FeaturesError `[M]`

**问题:** `ditto_features/errors.py` 中类名 `AnalyticsError` 是从 analytics 包迁出时的遗留命名，与包名不一致。

**文件:**
- Modify: `packages/features/src/ditto_features/errors.py`
- Modify: `packages/features/src/ditto_features/expression/diagnostics.py`（子类定义）
- Modify: `packages/kernel/tests/unit/test_exceptions.py`（跨包测试断言）
- Modify: 所有 import `AnalyticsError` 的文件

**步骤:**
1. `rg -n "AnalyticsError" packages/ --include="*.py"` 定位所有引用
2. 重命名类 `AnalyticsError` → `FeaturesError`
3. 更新 docstring：`"""Features domain exception root."""`
4. 更新所有 import 和 isinstance 断言
5. 如果 `ditto_kernel.__init__` 未 re-export 此类（当前未），则无需修改 kernel

**验证:** `pixi run -e dev check`

---

## Phase 2: 依赖一致性修复

### Task 2.1: 修正 analysis pyproject 依赖 `[S]`

**问题:** analysis pyproject 声明 `ditto-data`、`ditto-features` 依赖，但源码零 import data/features。`ditto-platform` 依赖合理（analysis 使用 `SQLiteClient`）。

**文件:**
- Modify: `packages/analysis/pyproject.toml`

**步骤:**
1. 从 dependencies 移除 `"ditto-data"` 和 `"ditto-features"`
2. 保留 `"ditto-kernel"`、`"ditto-platform"`、`"polars"`、`"numpy"`、`"orjson"`

**验证:** `pixi run -e dev type && pixi run -e dev pytest packages/analysis/tests/ -q`

---

### Task 2.2: 修正 analysis importlinter 规则 `[S]`

**问题:** `analysis-no-production-dependency` 合约禁止 analysis → platform，但 analysis 实际使用 `ditto_platform.foundation.storage.SQLiteClient`。Platform 是技术基础设施不是业务包，应允许。

**文件:**
- Modify: `.importlinter`

**步骤:**
1. 在 `analysis-no-production-dependency` 合约中：
   - 从 forbidden 列表移除 `ditto_platform`
   - 保留禁止 `ditto_data`、`ditto_features`、`ditto_strategy`、`ditto_portfolio`、`ditto_risk`、`ditto_execution`、`ditto_backtest`、`ditto_application`、`ditto_apps`
2. 或者添加 ignore_imports: `ditto_analysis.** -> ditto_platform.foundation.storage.**`

**验证:** `pixi run -e dev arch-check`

---

### Task 2.3: apps pyproject 声明核心依赖 `[S]`

**问题:** `ditto-apps` pyproject 声明零依赖，但实际 import `ditto_application` 等。虽然 pixi 全局安装可工作，但单独 `pip install ditto-apps` 会失败。

**文件:**
- Modify: `packages/apps/pyproject.toml`

**步骤:**
1. 添加最小核心依赖：`"ditto-application"`、`"ditto-platform"`
   （其余通过 application 的传递依赖自动拉入）

**验证:** `pixi run -e dev check`

---

## Phase 3: Platform 业务泄漏修复

### Task 3.1: 迁移 TradingSettings 到 Application `[M]`

**问题:** `TradingSettings` 含纯交易策略配置（`risk_free_rate`、`benchmark`、`max_position_pct`、`cost_bps`、`slippage_bps`），属于业务配置，违反 platform "零业务逻辑，零领域概念" 铁律。

**文件:**
- Move: `TradingSettings` class 从 `packages/platform/src/ditto_platform/foundation/config/settings.py`
- To: `packages/application/src/ditto_application/config.py`（新文件或已有文件）
- Modify: `packages/apps/src/ditto_apps/registry/infra/config.py`（消费端）
- Modify: `packages/application/src/ditto_application/providers.py`（消费端）
- Move tests: `packages/platform/tests/unit/config/test_trading_settings_unit.py` → `packages/application/tests/unit/config/`
- Modify: `packages/platform/src/ditto_platform/foundation/config/settings.py`（Settings 类移除 trading 字段）
- Modify: platform `__init__.py` / `__all__` 移除 `TradingSettings`
- Modify: architecture smell checker allowlist

**步骤:**
1. `rg -n "TradingSettings" packages/ --include="*.py"` 定位所有引用
2. 在 `ditto_application/config.py` 创建（或追加）`TradingSettings` class
3. 更新 `ditto_application.providers` 的 import 路径
4. 更新 `ditto_apps.registry.infra.config` 的 import 路径
5. 从 platform settings.py 删除 `TradingSettings` class，从 `Settings` 移除 `trading` 字段
6. 迁移测试文件
7. 更新 architecture smell checker 的 `PLATFORM_PREFIX_ALLOWLIST`（移除 `portfolio_value` 等不再需要的条目——如果 TradingSettings 是唯一业务泄漏）
8. 注意：platform 的 `Settings.trading: TradingSettings | None = None` 字段也需要移除，apps 的 config 加载逻辑需要更新

**验证:**
```bash
pixi run -e dev pytest packages/application/tests/unit -q
pixi run -e dev pytest packages/platform/tests/unit -q
pixi run -e dev pytest packages/apps/tests/registry -q
pixi run -e dev type
pixi run -e dev arch-check
```

---

## Phase 4: 契约与错误实现

### Task 4.1: 实现 risk/errors.py `[S]`

**问题:** 当前只有 docstring 占位符，缺少 `RiskError` 基类和子类型。

**文件:**
- Modify: `packages/risk/src/ditto_risk/errors.py`
- Create: `packages/risk/tests/unit/test_errors_unit.py`

**实现:**
```python
from ditto_kernel.exceptions import DittoError

class RiskError(DittoError):
    """风控域基础异常."""

class ConstraintViolationError(RiskError):
    """约束违规异常."""

class ExposureLimitError(RiskError):
    """暴露超限异常."""

class DrawdownThresholdError(RiskError):
    """回撤超限异常."""

__all__ = [
    "ConstraintViolationError",
    "DrawdownThresholdError",
    "ExposureLimitError",
    "RiskError",
]
```

**测试:**
```python
def test_risk_error_hierarchy() -> None:
    from ditto_kernel.exceptions import DittoError
    from ditto_risk.errors import (
        ConstraintViolationError,
        DrawdownThresholdError,
        ExposureLimitError,
        RiskError,
    )
    assert issubclass(RiskError, DittoError)
    assert issubclass(ConstraintViolationError, RiskError)
    assert issubclass(ExposureLimitError, RiskError)
    assert issubclass(DrawdownThresholdError, RiskError)
```

**验证:** `pixi run -e dev pytest packages/risk/tests/unit -q`

---

### Task 4.2: 实现 strategy/contracts.py `[M]`

**问题:** 当前只有 docstring 占位符，缺少 Protocol 定义。

**文件:**
- Modify: `packages/strategy/src/ditto_strategy/contracts.py`
- Create: `packages/strategy/tests/unit/test_contracts_unit.py`

**设计原则:** 只定义 strategy 消费者需要的 Protocol。检查现有消费者（application、backtest）实际依赖的接口。

**步骤:**
1. `rg -n "from ditto_strategy" packages/application/ packages/backtest/ --include="*.py"` 识别外部消费者实际使用的类型
2. 基于实际消费模式定义 Protocol（如 `SignalProvider`、`StrategyRunner`）
3. 如果当前所有交互都通过具体类，定义最小 Protocol 覆盖最关键的交互面
4. 编写 Protocol 类型检查测试

**注意:** 具体 Protocol 方法签名需要根据源码实际使用模式确定，不能臆造。本 task 需要先调研 application/backtest 对 strategy 的消费模式。

**验证:** `pixi run -e dev pytest packages/strategy/tests/unit -q && pixi run -e dev type`

---

### Task 4.3: 实现 portfolio/contracts.py `[M]`

**问题:** 当前只有 docstring 占位符。

**文件:**
- Modify: `packages/portfolio/src/ditto_portfolio/contracts.py`
- Create: `packages/portfolio/tests/unit/test_contracts_unit.py`

**步骤:**
1. 调研 execution/application 对 portfolio 的消费模式
2. 定义 `PortfolioState`、`RebalanceTarget` Protocol
3. 编写测试

**验证:** `pixi run -e dev pytest packages/portfolio/tests/unit -q && pixi run -e dev type`

---

### Task 4.4: 实现 risk/contracts.py `[M]`

**问题:** 当前只有 docstring 占位符。

**文件:**
- Modify: `packages/risk/src/ditto_risk/contracts.py`
- Create: `packages/risk/tests/unit/test_contracts_unit.py`

**步骤:**
1. 调研 execution/application/backtest 对 risk 的消费模式
2. 定义 `RiskChecker`、`RiskReport` Protocol
3. 编写测试

**验证:** `pixi run -e dev pytest packages/risk/tests/unit -q && pixi run -e dev type`

---

### Task 4.5: 实现 execution/contracts.py + BrokerGateway `[M]`

**问题:** 顶层 contracts.py 是空壳；`broker/contracts.py` 的 `BrokerGateway` 无方法签名。

**文件:**
- Modify: `packages/execution/src/ditto_execution/contracts.py`
- Modify: `packages/execution/src/ditto_execution/broker/contracts.py`
- Create: `packages/execution/tests/unit/test_contracts_unit.py`

**步骤:**
1. 调研 application/backtest 对 execution 的消费模式
2. 顶层 contracts.py：定义 `OrderRouter`、`FillReceiver`、`TradeAuditor` Protocol
3. broker/contracts.py：基于现有 `ditto_execution.models` 定义 `BrokerGateway` 方法签名
   - `submit_order`、`cancel_order`、`query_fills` 等
4. 编写测试

**注意:** BrokerGateway 方法签名必须与 `ditto_execution.models` 中的 Order/Fill 类型兼容。

**验证:** `pixi run -e dev pytest packages/execution/tests/unit -q && pixi run -e dev type`

---

## Phase 5: 文档清理

### Task 5.1: 清理文档遗留旧包名引用 `[S]`

**问题:** 7 个文档文件共 215 处引用旧包名（`ditto_interfaces`/`ditto_engine` 等），主要是 `README.md` 和 `docs/`。

**文件:**
- Modify: `README.md`
- Modify: `docs/configuration.md`
- Modify: `docs/ops-manual.md`
- Modify: `docs/adr/0006-hybrid-plane-v2-accepted-deviations.md`
- Modify: `docs/adr/0007-datafeed-lookback-strategy.md`
- Modify: `docs/adr/0008-strategy-artifact-io-layering.md`
- Modify: `docs/adr/0009-impact-model-governance.md`
- `docs/verification-plan-2025.md`（大量遗留，考虑标注为历史文档或添加废弃声明）

**替换映射:**
```text
ditto_interfaces → ditto_apps
ditto_engine → ditto_strategy / ditto_portfolio / ditto_risk / ditto_execution / ditto_backtest (按上下文)
ditto_analytics → ditto_features / ditto_analysis (按上下文)
ditto_infra → ditto_platform
ditto_app → ditto_application
interfaces/src → packages/apps/src
interfaces/tests → packages/apps/tests
packages/engine → 按上下文替换
packages/analytics → packages/features 或 packages/analysis
packages/infra → packages/platform
packages/app → packages/application
```

**注意:** ADR 文档如果描述的是历史决策，可以添加 `[历史参考]` 前缀而非全面替换。`verification-plan-2025.md` 因引用量大，建议在文件头部添加废弃声明。

**验证:** `rg -n "ditto_engine|ditto_analytics|ditto_infra|ditto_interfaces|from ditto_app " README.md docs/ --include="*.md" -g '!docs/plans/*' -g '!docs/reviews/*'` 应仅剩标注为历史的内容

---

## Task Summary

| Phase | Task | 复杂度 | 依赖 | 估计文件数 |
|-------|------|--------|------|-----------|
| 1 | 1.1 删除遗留 egg-info | S | 无 | 2 delete |
| 1 | 1.2 对齐 kernel 版本号 | S | 无 | 1 modify |
| 1 | 1.3 重命名 AnalyticsError → FeaturesError | M | 无 | ~5 modify |
| 2 | 2.1 修正 analysis pyproject | S | 无 | 1 modify |
| 2 | 2.2 修正 analysis importlinter | S | 2.1 | 1 modify |
| 2 | 2.3 apps pyproject 核心依赖 | S | 无 | 1 modify |
| 3 | 3.1 迁移 TradingSettings | M | 无 | ~8 modify |
| 4 | 4.1 实现 risk/errors.py | S | 无 | 2 modify/create |
| 4 | 4.2 实现 strategy/contracts.py | M | 无 | 2 modify/create |
| 4 | 4.3 实现 portfolio/contracts.py | M | 无 | 2 modify/create |
| 4 | 4.4 实现 risk/contracts.py | M | 4.1 | 2 modify/create |
| 4 | 4.5 实现 execution/contracts.py + BrokerGateway | M | 无 | 3 modify/create |
| 5 | 5.1 清理文档遗留引用 | S | 无 | ~8 modify |

**执行顺序:** Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
**Phase 内部:** 可并行（除 2.2 依赖 2.1、4.4 依赖 4.1）
**总 Task 数:** 13
**最终验证:** `pixi run -e dev check && pixi run -e dev arch-check`

---

Plan complete. Use `superpowers:executing-plans` in the implementation session and execute one task at a time.
