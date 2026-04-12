# V1 增强设计 — Regime/因子桥接/回测触发/信号推送/Universe/成本模型/数据验证

> **创建**: 2026-04-11
> **状态**: Draft
> **前置**: V1 Sprint Phase 0-3 全部完成（4323+ 测试通过）
> **目标**: 补齐 V1 发布前的 7 个关键能力缺口，实现"创建策略 → 配置因子 → 触发回测 → 信号推送 → 人工执行"完整闭环

---

## 1. 背景与动机

### 1.1 当前完成状态

V1 Sprint Phase 0-3 已全部完成：

| Phase | 状态 | 关键产出 |
|-------|------|----------|
| Phase 0: Foundation | ✅ | TradingStep Chain, DecisionFrame Schema, RunManifest Enrichment |
| Phase 1: Backtest Closed Loop | ✅ | BacktestQueryFacade, RunReadModel, 14 个 API 端点 |
| Phase 2: Manual Execution | ✅ | SignalSnapshot, ManualTracker, TradeService, ComparisonReport |
| Phase 3: Lineage/Replay | ✅ | ReplayValidator, LineageQueryFacade, ManifestDiff |

**策略模板**: ETF 轮动、ETF 趋势、选股轮动、选股趋势（4 套）
**内置 Stage**: Universe/Signal/Scoring/Filtering/Selection/RiskLockFilter/TrendFilter/RegimeStage（8 个）

### 1.2 V1 发布目标

- 完整回测 + 策略能力接入
- 不引入实盘和实时因子
- 人工执行和记录
- ETF 行业轮动/趋势 + 选股轮动/趋势
- Regime 策略必须有（仓位调节器级别）
- 传统多因子方向，弱化 AI/模型训练
- 全渠道信号推送（Telegram + Email + Webhook + API）

### 1.3 已识别的 7 个缺口

| # | 缺口 | 影响 |
|---|------|------|
| R1 | Regime 未集成到策略模板 | RegimeStage 存在但无实际仓位调节 |
| R2 | 因子表达式未桥接到策略 | 回测无法使用因子引擎 |
| R3 | 无 API 回测触发器 | 策略→回测链路断裂 |
| R4 | 信号推送未实现 | 人工执行缺少通知环节 <!-- V1-Status: 设计完成，实现推迟至 V1.1。V1 Sprint 清理了 `ditto_interfaces/services/telegram_signal.py`（过早实现，缺少 DeliveryRouter 抽象） --> |
| R5 | Universe 管理 API 缺失 | 策略无法指定股票池 |
| R6 | 成本模型不可配置 | 回测成本参数硬编码 |
| R7 | 数据链路未验证 | 端到端流程可能因数据缺口中断 |

---

## 2. 整体架构

```
V1 增强全景
│
├─ R1: Regime Score Engine                (~400 行, Engine 层)
│     └─ RegimeIndicator Protocol + 4 内置指标 + RegimeAwareAllocationStage
│
├─ R2: 声明式因子配置桥接                 (~250 行, App + Analytics 层)
│     └─ FactorBridge: StrategySpec.signal_expressions → 编译 → 注入 DecisionFrame
│
├─ R3: API 回测触发（异步）               (~250 行, App + Interfaces 层)
│     └─ POST /backtests/runs → 202 Accepted → 后台异步执行 → 状态轮询
│
├─ R4: 全渠道信号推送                      (~400 行, App + Interfaces 层)
│     └─ DeliveryRouter → Telegram/Email/Webhook/ApiOnly 四通道
│
├─ R5: Universe 管理 API                  (~150 行, App + Interfaces 层)
│     └─ 预设 Universe + 自定义 Universe CRUD
│
├─ R6: 成本模型 API 配置                  (~80 行, Interfaces + App 层)
│     └─ CostConfig: 佣金/印花税/滑点可配置化
│
└─ R7: 数据链路梳理 + 验证               (~100 行 + 文档)
      └─ 端到端数据就绪度确认 + 冒烟测试
```

### 2.1 执行优先级

**第一批（核心闭环）**: R7 → R1 + R2（并行）→ R3
- R7 先验证数据就绪度
- R1 和 R2 无互相依赖，可并行开发
- R3 依赖 R2（回测需要因子输入）

**第二批（运营闭环）**: R5 + R6（并行）→ R4
- R5/R6 独立，可随时开始
- R4 依赖 R3（推送需要回测产生的信号）

### 2.2 依赖关系

```
R7 (数据验证)
 ↓
R1 (Regime) ──┐
R2 (因子桥接) ─┤
              ↓
         R3 (回测触发)
              ↓
R5 (Universe) ─┐
R6 (成本模型) ──┤
               ↓
          R4 (信号推送)
```

### 2.3 工作量估算

| 模块 | 新代码 | 修改代码 | 新文件 | 修改文件 |
|------|--------|----------|--------|----------|
| R1: Regime | ~400 行 | ~50 行 | 2 | 5 |
| R2: 因子桥接 | ~250 行 | ~30 行 | 1 | 3 |
| R3: 回测触发 | ~250 行 | ~20 行 | 2 | 2 |
| R4: 信号推送 | ~400 行 | ~30 行 | 2 | 2 |
| R5: Universe | ~150 行 | ~10 行 | 3 | 1 |
| R6: 成本模型 | ~80 行 | ~20 行 | 0 | 3 |
| R7: 数据验证 | ~100 行 | - | 1 | - |
| **总计** | **~1630 行** | **~160 行** | **11** | **16** |

---

## 3. R1: Regime Score Engine

### 3.1 演进定位

```
V1:   Level 2 多维复合 Regime Score（纯统计，零 ML 依赖）
V1.1: + HMM 状态转移概率（hmmlearn，无监督 fit，非训练管线）
V2:   + 因子-Regime 交互分析（哪些因子在当前 Regime 表现好）
V3:   + 宏观周期四阶段（recovery/expansion/slowdown/recession）
```

### 3.2 核心类型

**Engine 层 — `packages/engine/src/ditto_engine/alpha/builtins/regime.py`（重构）**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

import polars as pl


class RegimeLabel(StrEnum):
    BULL = "bull"
    BEAR = "bear"
    NEUTRAL = "neutral"


@dataclass(frozen=True)
class RegimeResult:
    """Regime 检测结果"""
    score: float                          # 0-100 连续分数
    label: RegimeLabel                    # 离散标签
    position_ratio: float                 # 0.0-1.0 建议仓位比例
    indicators: dict[str, float] = field(default_factory=dict)  # 各指标明细


class RegimeIndicator(Protocol):
    """单一维度 Regime 指标，输出 0.0-1.0 分数"""
    name: str
    weight: float

    def compute(self, frame: pl.DataFrame) -> float:
        """计算指标值，返回 0.0-1.0"""
        ...


@dataclass(frozen=True)
class RegimeConfig:
    """Regime Score Engine 配置"""
    indicators: tuple[RegimeIndicator, ...] = ()
    bull_threshold: float = 70.0          # score ≥ 此值 → BULL
    bear_threshold: float = 30.0          # score ≤ 此值 → BEAR
    position_mapping: str = "linear"      # linear / stepped
    # stepped 映射: BULL=1.0, NEUTRAL=0.7, BEAR=0.3 (或 0.0 if score<20)
```

### 3.3 内置 4 个 RegimeIndicator

| Indicator | 输入 | 计算 | 输出 |
|-----------|------|------|------|
| `TrendIndicator` | DecisionFrame 中 MA20/MA60 列 | `ratio = short_ma / long_ma`; ratio > 1+threshold → 1.0, ratio < 1-threshold → 0.0, 线性插值 | 0.0-1.0 |
| `VolatilityIndicator` | DecisionFrame 中 realized_vol 列 | vol 分位数映射: vol < low(0.15) → 1.0, vol > high(0.30) → 0.0, 线性插值 | 0.0-1.0 |
| `BreadthIndicator` | 全市场涨跌统计（通过额外数据列） | `breadth = up_count / (up_count + down_count)` | 0.0-1.0 |
| `MomentumIndicator` | DecisionFrame 中 close 列 | N日涨幅的 rank 分位数 | 0.0-1.0 |

### 3.4 RegimeAwareAllocationStage

**新增文件: `packages/engine/src/ditto_engine/alpha/builtins/regime_allocation.py`**

行为：
1. 从 DecisionFrame 读取 `regime_score` / `regime_label` 列
2. 如果 `regime_label == BEAR` 且 `score < 20`: 完全空仓（所有权重置 0）
3. 否则：缩放所有持仓权重 `new_weight = original_weight * position_ratio`
4. 剩余权重归入现金：`cash_weight = 1 - sum(new_weights)`

### 3.5 模板集成

所有 4 个策略模板增加可选的 `regime_config` 参数：

```python
# ETF 轮动模板示例
@dataclass(frozen=True)
class ETFRotationConfig:
    # ...existing fields...
    regime_config: RegimeConfig | None = None  # 新增
```

Pipeline 变更（以 ETF 轮动为例）：
```
Signal → Score → RiskLockFilter → Select → Allocate → [RegimeAwareAllocation] → Constraint
                                                         ↑ 仅当 regime_config 不为 None
```

### 3.6 与现有 RegimeStage 的关系

现有 `RegimeStage`（MA_CROSS / VOLATILITY_THRESHOLD）重构为 `TrendIndicator` 和 `VolatilityIndicator` 的内部实现。`RegimeStage` 作为向后兼容的薄包装保留。

---

## 4. R2: 声明式因子配置桥接

### 4.1 核心问题

Analytics 层有强大的因子表达式编译器（Lexer → Parser → AST → Analyzer → Codegen），但 StrategySpec 无法表达"用哪些因子表达式作为信号源"。回测引擎的 DecisionFrame 需要包含 `signal_value` 列，但目前没有从表达式到 signal_value 的桥接。

### 4.2 核心类型

**Engine 层 — `packages/engine/src/ditto_engine/alpha/specs.py`（修改）**

```python
@dataclass(frozen=True)
class StrategySpec:
    # ...existing fields...
    signal_expressions: tuple[str, ...] = ()   # 新增：因子表达式列表
    signal_weights: tuple[float, ...] = ()     # 新增：表达式权重（等长于 signal_expressions）
```

**App 层 — 新增 `packages/app/src/ditto_app/process/execution/factor_bridge.py`**

```python
@dataclass(frozen=True)
class CompiledExpressions:
    """编译后的因子表达式集合"""
    expressions: tuple[str, ...]
    compiled: tuple[object, ...]      # 编译后的 callable
    weights: tuple[float, ...]
    diagnostics: list[str]            # 编译诊断信息


class FactorBridge:
    """桥接 Analytics 表达式编译器 → Engine DecisionFrame"""

    def compile_and_validate(
        self,
        expressions: tuple[str, ...],
        weights: tuple[float, ...],
    ) -> CompiledExpressions:
        """编译表达式，验证语法和语义正确性。
        调用 Analytics 层的 compile() 并收集 diagnostics。
        编译失败时抛出 ValueError（含详细错误信息）。"""

    def compute_signals(
        self,
        compiled: CompiledExpressions,
        data: pl.DataFrame,
    ) -> pl.DataFrame:
        """在行情数据上计算因子值。
        对每个表达式执行编译后的 callable，得到因子列。
        加权合成为 signal_value 列：score = sum(w_i * rank(f_i)) / sum(w_i)
        返回追加 signal_value 列后的 DataFrame。"""
```

### 4.3 端到端流程

```
1. 策略创建
   POST /strategies
   → signal_expressions: ["rank(close / delay(close, 20))", "-tsstd(close, 20)"]
   → signal_weights: [0.7, 0.3]
   → StrategySpec 存储

2. 策略创建验证
   → FactorBridge.compile_and_validate() 验证表达式语法
   → 编译失败则拒绝创建（400 Bad Request + 详细错误）

3. 回测触发（异步）
   POST /backtests/runs { strategy_id, start_date, end_date }
   → 参数校验 + 因子预编译
   → 创建 RunRecord (status=PENDING)
   → 提交到 BacktestTaskRunner 后台执行
   → 立即返回 202 Accepted + run_id

3a. 后台执行
   → 更新 status=RUNNING
   → 加载策略 → 构建引擎 → 执行回测
   → 成功: status=COMPLETED + 存储结果
   → 失败: status=FAILED + 记录错误

4. 回测引擎内部（每步）
   → DataFetchStep 获取行情 bar
   → FactorBridge.compute_signals() 计算因子值
   → signal_value 列注入 DecisionFrame
   → 策略模板的 SignalStage 直接使用 signal_value

5. 结果输出
   → RunRecord + NAV + TradeLog + Audit
```

### 4.4 架构约束

- FactorBridge 位于 App 层（桥接 Analytics + Engine，符合 App 层编排职责）
- 不违反 importlinter：App 可依赖 Analytics 和 Engine
- 表达式编译在回测启动时完成（一次性），不在每步重复
- 编译缓存可复用 Analytics 层现有的 `compile_cache.py`

### 4.5 表达式验证规则

| 规则 | 说明 |
|------|------|
| 语法正确 | Lexer + Parser 不报错 |
| 语义正确 | Analyzer 检查列名存在、函数参数类型 |
| 输出标量 | 每个表达式必须输出单列数值 |
| 权重匹配 | signal_weights 长度 = signal_expressions 长度 |
| 权重非负 | 所有 weight ≥ 0 |
| 至少一个 | signal_expressions 非空 |

---

## 5. R3: API 回测触发

### 5.1 API 设计

**新增端点: `POST /api/v1/backtests/runs`**

```python
class CreateBacktestRunRequest:
    strategy_id: str                              # 必填：策略 ID
    start_date: date                              # 必填：回测起始日
    end_date: date                                # 必填：回测结束日
    initial_capital: float = 1_000_000            # 初始资金
    universe_id: str | None = None                # 覆盖策略默认 universe
    params_override: dict[str, object] | None = None  # 覆盖策略参数
    cost_config: CostConfig | None = None         # 成本模型配置（R6）
    benchmark_id: str | None = None               # 基准指数 ID


class BacktestRunResponse:
    run_id: str
    strategy_id: str
    status: RunStatus
    created_at: str
```

**响应**: 202 Accepted，立即返回 run_id + status=PENDING，后台异步执行回测。
后续通过 `GET /backtests/runs/{id}` 轮询状态和结果。

### 5.2 异步执行架构（Prefect）

```
POST /backtests/runs
  → 参数校验 + 因子预编译
  → 创建 RunRecord (status=PENDING)
  → 提交 Prefect flow: run_backtest_flow(run_id, ...)
  → 立即返回 202 Accepted + run_id

Prefect Worker (后台独立进程):
  → 更新 status=RUNNING
  → 加载策略 → 编译因子 → 构建引擎 → 执行回测
  → 成功: status=COMPLETED + 存储结果 (artifacts + NAV + TradeLog)
  → 失败: status=FAILED + 记录 error_message

GET /backtests/runs/{id}
  → 返回当前状态 + 结果（如果已完成）
```

**状态机**: `PENDING → RUNNING → COMPLETED | FAILED`

**Prefect 配置**:
- V1 使用 Prefect 本地模式（无需 Prefect Server），`prefect worker start` 启动
- 并发控制: Prefect work pool 的 `concurrency_limit` 参数
- 重试策略: `retries=1, retry_delay_seconds=60`（回测失败自动重试一次）

### 5.3 BacktestCommandHandler + Prefect Flow

**新增文件:**

| 文件 | 层 | 内容 |
|------|----|------|
| `packages/app/src/ditto_app/command/backtest.py` | App | BacktestRunHandler — 参数校验 + 任务提交 |
| `interfaces/src/ditto_interfaces/jobs/backtest_job.py` | Interfaces | `run_backtest_flow` — Prefect flow 定义 |

```python
# app/command/backtest.py
class BacktestRunHandler:
    """编排 策略校验 → 任务提交 → 立即返回"""

    def __init__(
        self,
        strategy_reader: StrategyQueryFacade,
        factor_bridge: FactorBridge,
        run_service: StrategyRunService,
        universe_reader: UniverseQueryFacade,  # R5
    ): ...

    async def handle(self, command: BacktestRunCommand) -> str:
        # 1. 参数校验（策略存在性、日期合法性）
        # 2. FactorBridge.compile_and_validate() 预验证因子表达式
        #    编译失败则立即返回 400（不提交任务）
        # 3. 创建 RunRecord (status=PENDING)
        # 4. 提交 Prefect flow: run_backtest_flow.delay(run_id, ...)
        # 5. 立即返回 run_id


# interfaces/jobs/backtest_job.py
@flow(
    name="run-backtest",
    retries=1,
    retry_delay_seconds=60,
    tags=["backtest"],
)
def run_backtest_flow(
    run_id: str,
    strategy_id: str,
    start_date: str,
    end_date: str,
    initial_capital: float,
    universe_id: str | None,
    params_override: dict | None,
    cost_config: dict | None,
    benchmark_id: str | None,
) -> None:
    """Prefect flow: 完整回测执行。

    在 Prefect Worker 独立进程中运行，不阻塞 API。
    """
    # 1. 更新 status=RUNNING
    # 2. 加载 StrategySpec
    # 3. FactorBridge.compile_and_validate()
    # 4. 构建 BacktestService + 引擎配置
    # 5. 执行回测 → BacktestReport
    # 6. 存储结果 (RunRecord + artifacts)
    # 7. 更新 status=COMPLETED
    # 异常: 更新 status=FAILED + error_message
```

### 5.4 设计决策

- **Prefect 异步执行**: `POST` 立即返回 202 Accepted，回测在 Prefect Worker 独立进程执行
- **CPU 密集友好**: Prefect Worker 独立进程，不阻塞 API 事件循环
- **任务持久化**: Prefect 本地模式即提供任务持久化，进程重启不丢任务
- **重试机制**: 内置 `retries=1`，回测失败自动重试一次（排除瞬时故障）
- **手动重试**: `POST /backtests/runs/{id}/retry` 用相同参数重新提交（创建新 RunRecord 关联 parent_run_id）
- **并发控制**: Prefect work pool 的 concurrency_limit 参数
- **状态查询**: 复用现有 `GET /backtests/runs/{id}` 端点，RunRecord.status 反映实时状态
- **进度跟踪**: RunRecord 新增 progress_pct / current_step / completed_days / total_days，引擎每步更新
- **取消**: `POST /backtests/runs/{id}/cancel`，引擎在 step 间隙检查取消标志优雅退出
- **错误处理**: 回测失败时 status=FAILED + error_message 字段，用户可查看失败原因
- **参数覆盖**: `params_override` 允许同一策略跑不同参数，支持快速参数扫描
- **V1.1 演进**: 引擎 checkpoint 序列化，支持真暂停/恢复断点续跑；可升级 Prefect Server/Cloud
- **复用信号调度**: 每日 SignalSnapshotProcess 同样可以作为 Prefect flow 运行，统一任务架构

### 5.5 任务管理 API 补充

```python
# 进度跟踪 — RunRecord 新增字段
# packages/data/src/ditto_data/models/strategy_run.py 修改
@dataclass(frozen=True)
class StrategyRunRecord:
    # ...existing fields...
    progress_pct: float = 0.0        # 0.0 - 1.0 实时进度
    current_step: str = ""           # 当前执行步骤名
    completed_days: int = 0          # 已完成交易日数
    total_days: int = 0              # 总交易日数
    error_message: str | None = None # 失败原因


# 取消端点
# POST /backtests/runs/{id}/cancel
# → Prefect flow cancellation
# → 引擎在 EngineLoop 日循环中检查取消标志，优雅退出
# → 已计算的部分结果（已完成天数的 NAV + TradeLog）仍保存

# 重试端点
# POST /backtests/runs/{id}/retry
# → 使用相同参数重新提交 Prefect flow
# → 创建新 RunRecord，parent_run_id 指向原 run
# → 返回新 run_id

# 进度回调机制
# EngineLoop 在每步完成后触发回调:
class ProgressCallback(Protocol):
    def on_step_complete(
        self,
        run_id: str,
        completed_days: int,
        total_days: int,
        current_step: str,
    ) -> None: ...

# Prefect flow 中注入回调实现，更新 RunRecord 进度字段
```

---

## 6. R4: 全渠道信号推送

> **V1 实施状态（2026-04-12）**: 设计保留，**实现推迟至 V1.1**。
> V1 Sprint 清理了 `ditto_interfaces/services/telegram_signal.py`（过早的单一通道实现，
> 缺少 DeliveryRouter 抽象层）。当前 V1 仅保留 API-only 模式（信号存 DB，
> 用户通过 API 查询）。DeliveryRouter + Telegram/Email/Webhook 通道待 V1.1 实现。

### 6.1 架构

```
SignalSnapshotProcess 产生 TradeIntent
  ↓
DeliveryRouter
  ├─ TelegramDelivery     # via Telegram Bot API
  ├─ EmailDelivery        # via SMTP (httpx → 邮件服务)
  ├─ WebhookDelivery      # via httpx POST (自定义 HTTP)
  └─ ApiOnlyDelivery      # 仅存 DB，不推送（默认）
```

### 6.2 核心类型

**App 层 — 新增 `packages/app/src/ditto_app/process/execution/delivery.py`**

```python
class DeliveryChannel(Protocol):
    """信号推送通道 Protocol"""
    name: str

    def send(self, signal: SignalMessage) -> DeliveryResult:
        """推送信号，返回推送结果"""
        ...


@dataclass(frozen=True)
class SignalMessage:
    """推送信号内容"""
    strategy_name: str
    signal_date: date
    regime_label: RegimeLabel | None
    regime_score: float | None
    buy_intents: tuple[TradeIntent, ...]
    sell_intents: tuple[TradeIntent, ...]
    position_ratio: float | None
    current_holdings_count: int
    target_holdings_count: int


@dataclass(frozen=True)
class DeliveryResult:
    channel: str
    success: bool
    error: str | None = None


class DeliveryRouter:
    """多通道信号推送路由器"""

    def __init__(self, channels: tuple[DeliveryChannel, ...]): ...

    def deliver(self, signal: SignalMessage) -> list[DeliveryResult]:
        """向所有配置通道推送信号。fire-and-forget: 推送失败不阻塞信号生成。"""
```

### 6.3 推送通道实现

**新增文件: `packages/app/src/ditto_app/process/execution/delivery_channels.py`**

| 通道 | 依赖 | 配置 | 说明 |
|------|------|------|------|
| `TelegramDelivery` | httpx | bot_token, chat_id | Markdown 格式消息 |
| `EmailDelivery` | httpx → SMTP relay | smtp_host, smtp_port, from_addr, to_addrs | HTML 邮件 |
| `WebhookDelivery` | httpx | url, secret, headers | JSON POST + HMAC 签名 |
| `ApiOnlyDelivery` | 无 | 无 | 默认通道，仅存 DB |

### 6.4 信号内容模板

```
📊 策略信号 - ETF行业轮动
日期: 2026-04-11
Regime: BULL (score: 78)

买入信号:
  + 512010.SS (证券ETF) 目标仓位 12%
  + 512660.SS (军工ETF) 目标仓位 10%

卖出信号:
  - 512880.SS (银行ETF) 清仓

当前持仓: 8 只 | 建议持仓: 10 只
仓位比例: 85% (Regime 调节后)
```

### 6.5 关键设计决策

- 推送失败不阻塞信号生成（fire-and-forget + 日志记录）
- 配置存储在 config YAML（V1 简单方案，不存 DB）
- 每个策略可配置不同的推送通道组合
- HMAC 签名用于 Webhook 安全验证

---

## 7. R5: Universe 管理 API

### 7.1 API 设计

```python
# 查询
GET  /api/v1/universes              # 列出所有 universe（预设 + 自定义）
GET  /api/v1/universes/{id}         # 详情（含成分列表）
GET  /api/v1/universes/{id}/members # 成分股/ETF 列表

# 自定义管理
POST   /api/v1/universes            # 创建自定义 universe
PUT    /api/v1/universes/{id}       # 更新成分
DELETE /api/v1/universes/{id}       # 删除自定义（预设不可删）
```

### 7.2 预设 Universe

| ID | 名称 | 说明 | 数据来源 |
|----|------|------|----------|
| `etf_full` | 全市场 ETF | ~800 只 | data 层现有 instrument + universe |
| `industry_etf` | 行业 ETF | ~50 只 | 行业分类过滤 |
| `csi300` | 沪深 300 | 300 只 | 指数成分数据 |
| `csi500` | 中证 500 | 500 只 | 指数成分数据 |
| `gem` | 创业板指 | 100 只 | 指数成分数据 |

### 7.3 新增文件

| 文件 | 层 | 内容 |
|------|----|------|
| `interfaces/src/ditto_interfaces/api/routes/universe.py` | Interfaces | API 路由 |
| `packages/app/src/ditto_app/query/universe.py` | App | UniverseQueryFacade |
| `packages/app/src/ditto_app/command/universe.py` | App | CreateCustomUniverseCommand + Handler |

### 7.4 关键设计决策

- 预设 universe 由 data 层现有 universe storage 驱动（已有数据）
- 自定义 universe 存 SQLite（复用 data 层基础设施）
- Universe 成员变更通过 version 字段管理
- 预设 universe 不可删除/修改，自定义 universe 可以

---

## 8. R6: 成本模型 API 配置

### 8.1 CostConfig Model

```python
@dataclass(frozen=True)
class CostConfig:
    commission_rate: float = 0.0003      # 佣金率（万三）
    commission_min: float = 5.0          # 最低佣金（元）
    stamp_duty_rate: float = 0.001       # 印花税（千一，卖出）
    slippage_bps: float = 1.0            # 滑点（基点）
    impact_model: str = "none"           # none / linear / square_root
```

### 8.2 集成点

- `CreateBacktestRunRequest.cost_config` 覆盖引擎默认值
- `BacktestRunHandler` 将 CostConfig 注入引擎构建过程
- 默认值是 A 股标准费率（与现有 Reality Model 一致）

### 8.3 改动范围

| 文件 | 改动 |
|------|------|
| `interfaces/src/ditto_interfaces/models/backtest.py` | 新增 CostConfig model |
| `packages/app/src/ditto_app/command/backtest.py` | 注入成本配置 |
| `packages/app/src/ditto_app/process/execution/backtest_process.py` | BacktestService 接受 CostConfig |

约 80 行改动，非常轻量。

---

## 9. R7: 数据链路梳理 + 验证

### 9.1 验证清单

| # | 数据项 | 验证内容 | 负责模块 |
|---|--------|----------|----------|
| 1 | ETF 日线 bar | 开高低收量 → DataFetchStep 可获取？ | R3 |
| 2 | 因子基础列 | close/delay/rank 等表达式所需列 → 数据源覆盖？ | R2 |
| 3 | Universe 成分 | 沪深 300/中证 500 成分列表 → 历史成分数据？ | R5 |
| 4 | Regime 数据 | 全市场涨跌统计 → BreadthIndicator 需要？ | R1 |
| 5 | 基准数据 | 指数 NAV → benchmark 查询？ | R3 |
| 6 | 行业分类 | 行业 ETF 映射 → 行业轮动策略需要？ | R5 |

### 9.2 产出

- **数据就绪度报告**: 标注哪些就绪、哪些需要补数据、补数据方案
- **端到端冒烟测试**: 从数据采集到回测结果的完整流程验证脚本

---

## 10. 设计决策记录

| # | 决策 | 理由 | 影响 |
|---|------|------|------|
| D1 | Regime 做 Level 2 多维复合（非 HMM） | 传统多因子标配，零 ML 依赖，~400 行 | V1.1 可加 HMM |
| D2 | 因子表达式声明式配置 | 复用 Analytics 编译器，灵活度高 | 策略 API 需支持表达式字段 |
| D3 | V1 Prefect 异步回测触发 | 回测是 CPU 密集型，需要任务管理（进度/取消/重试），Prefect 已在依赖列表 | V1.1 可加引擎 checkpoint 暂停/恢复 |
| D4 | 全渠道推送 fire-and-forget | 推送失败不阻塞核心流程 | 需要推送日志 + 重试机制 |
| D5 | 预设 + 自定义 Universe 双模式 | 预设满足大部分场景，自定义满足进阶 | 需要预设 Universe 初始化逻辑 |
| D6 | 成本模型可配置化 | A 股费率结构不同券商有差异 | 默认值覆盖主流场景 |
| D7 | 数据链路验证先行 | 避免开发完后发现数据缺口 | R7 必须最先执行 |

---

## 11. 模块间接口依赖

```
┌─────────────────────────────────────────────────────┐
│                    Interfaces 层                      │
│  POST /backtests/runs    GET /universes              │
│  (R3)                    (R5)                        │
│  CostConfig (R6)                                     │
└───────────┬──────────────────────┬───────────────────┘
            │                      │
┌───────────▼──────────┐  ┌───────▼──────────────────┐
│      App 层          │  │        App 层              │
│  BacktestRunHandler  │  │  DeliveryRouter            │
│  FactorBridge (R2)   │  │  (R4)                      │
│  (R3)                │  └───────────────────────────┘
└───┬──────────┬───────┘
    │          │
┌───▼──┐  ┌───▼───────────────────────────────────────┐
│Engine│  │              Engine 层                      │
│(R1)  │  │  RegimeScoreEngine + RegimeAwareAllocation │
│      │  │  (R1)                                      │
└──────┘  └────────────────────────────────────────────┘
```

---

## 12. 测试策略

### 12.1 测试要求

- 分支覆盖率 ≥ 80%
- TDD: RED → GREEN → REFACTOR
- 所有新文件必须通过 `pixi run -e dev arch-check`

### 12.2 测试矩阵

| 模块 | 单元测试 | 集成测试 | 关键测试场景 |
|------|----------|----------|-------------|
| R1 | ✅ | - | RegimeScore 各指标边界值、仓位映射阶梯函数、BULL<20 完全空仓 |
| R2 | ✅ | ✅ | 表达式编译成功/失败、多因子加权合成、缺失列处理 |
| R3 | ✅ | ✅ | 正常触发、策略不存在、日期非法、参数覆盖 |
| R4 | ✅ | - | 各通道 send 成功/失败、fire-and-forget 不阻塞、HMAC 签名 |
| R5 | ✅ | - | 预设查询、自定义 CRUD、预设不可删 |
| R6 | ✅ | - | 默认值正确、自定义覆盖生效 |
| R7 | - | ✅ | 端到端冒烟测试（数据→因子→回测→结果） |

### 12.3 关键测试用例

**R1 — RegimeScoreEngine:**
- 全部指标 BULL → score=100, label=BULL, ratio=1.0
- 全部指标 BEAR → score=0, label=BEAR, ratio=0.0
- score=20 → BEAR, 空仓（ratio=0.0）
- score=50 → NEUTRAL, ratio=0.5
- 缺失列 → graceful fallback（使用 RegimeConfig.default_regime）

**R2 — FactorBridge:**
- 有效表达式编译成功
- 无效表达式编译失败（含诊断信息）
- 多因子加权合成: rank 归一化 → 加权平均
- signal_weights 长度不匹配 → ValueError
- 空数据 → 返回空 DataFrame

**R3 — BacktestRunHandler:**
- 正常流程: 创建 → 执行 → 存储 → 返回 run_id
- 策略不存在 → 404
- 日期范围非法 → 400
- 因子编译失败 → 400（含编译错误）

---

## 13. importlinter 合规性

| 模块 | 涉及层级 | 合规说明 |
|------|----------|----------|
| R1 | Engine | Engine 内部重构，零新增外部依赖 |
| R2 | App → Analytics + Engine | App 可依赖 Analytics 和 Engine，合规 |
| R3 | Interfaces → App → Engine | 标准依赖方向，合规 |
| R4 | App → Infra (httpx) | App 可依赖 Infra，合规 |
| R5 | Interfaces → App → Data | 标准依赖方向，合规 |
| R6 | Interfaces → App | API Model + Handler 参数传递，合规 |
| R7 | 无代码层变更 | 文档 + 验证脚本 |

---

## 14. V1.1 演进预留

| 能力 | 来源 | 依赖 |
|------|------|------|
| HMM Regime 检测 | R1 扩展 | hmmlearn/scipy |
| 异步回测任务 | R3 扩展 | Prefect |
| 引擎 checkpoint 暂停/恢复 | R3 扩展 | 引擎状态序列化 |
| 参数优化 | R3 扩展 | Optuna |
| 组合优化 (MVO/Risk Parity) | 新模块 | cvxpy/scipy |
| 回测报告 HTML 渲染 | R3 扩展 | jinja2/plotly |
| 实盘执行 | R4 扩展 | 券商 API |
