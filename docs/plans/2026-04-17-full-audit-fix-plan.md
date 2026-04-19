# 全架构审计修复计划

## Context

基于 6 Phase 自底向上审计（138 项发现：P0×2, P1×34, P2×55, P3×47），结合业界最佳实践（LEAN/NautilusTrader/OpenBB），制定全架构修复计划。同时整合 V1 剩余交付任务（`2026-04-17-v1-remaining-delivery-and-v11-enhancement.md`），V1 功能落地必须符合审计新架构。

**核心问题**：
- P0 正确性风险：异常双重定义导致静默吞没
- Data 层 God Package（60% 代码，综合 7.5/10）
- 92 个 Reader/Writer 类（46R + 46W，YAGNI 最严重违规）
- Ports 用 dataclass 而非 Protocol（违反 DIP）
- DataSource ABC 25 个抽象方法（God Interface，违反 ISP）
- EngineLoop 348 行（step-chain 模式，结构良好但需 Protocol 抽象）
- Kernel 定位模糊，部分类型放错位置

## 决策确认（与用户逐项确认）

| # | 决策项 | 选择 | 理由 |
|---|--------|------|------|
| 1 | Data 层策略 | B: 内部模块化 + Sources Plugin 化 | 渐进式，importlinter 已验证 |
| 2 | Ports 抽象 | A: Protocol 全替换 | Python DIP 正统，一次性投入 |
| 3 | Reader/Writer | A: 泛型参数化 | 削减 ~80 文件，LEAN 模式验证 |
| 4 | Kernel 边界 | A: Rich Kernel + 子域重组 | LEAN Symbol 模式，面向 Live |
| 5 | DataSource | A: Fetcher Protocol 拆分 | OpenBB 400+ Fetcher 验证 |
| 6 | 异常体系 | A: 2 层统一异常 | DittoError → 域根(DataError/DerivedError/EngineError...) → 具体 |
| 7 | EngineLoop | A: TradingLoop Protocol 轻量提取 | 实际 348 行结构良好，仅提取接口，不拆分类 |
| 8 | Trade CQRS | A: 纯化 CQRS | 与 market/fundamental/capital 一致 |

---

## Phase 0: P0 紧急修复 + 快速 P1

**目标**：消除正确性风险，修复已知 bug。预计改动 ~30 文件。

### 0.1 异常体系统一（P0 + P1）

**问题**：DataSourceError/SourceFetchError 在两个文件定义，继承链不同，导致静默异常吞没。11 个异常直接继承 Exception，无统一根。interfaces/kernel 双根（DittoException/DataError）无共同祖先。

**设计原则**（基于 Clean Architecture / DDD 最佳实践调研）：
- 单一统一根 — 所有框架均用单一根（Starlette HTTPException, SQLAlchemy StatementError）
- 每层仅拥有自己的异常 — 域层定义域异常，Infra 仅做防腐转换
- 域异常携带域上下文 — 不靠堆栈跟踪诊断
- 中间件统一映射 — 域异常在 API 边界映射为 HTTP 响应

**最终层级**（2 层：全局根 + 域根）：

```
DittoError(Exception)                         ← kernel 全局根（替代 DittoException）
  ├── DataError(DittoError)                  ← 原始数据域
  │     ├── IdentifierError, CalendarError, ValidationError
  │     ├── DataSourceError                   ← 唯一权威定义
  │     │     ├── NetworkError, AuthError, SourceFetchError
  │     │     ├── SourceConfigurationError    ← 从 base.py 合并
  │     │     ├── SourceAuthenticationError   ← 从 base.py 合并
  │     │     ├── SourceRateLimitError        ← 从 base.py 合并
  │     │     └── SourceTransformationError   ← 从 base.py 合并
  │     ├── PersistenceError
  │     ├── NotTradingDayError                ← 新纳入
  │     ├── DataChangedError                  ← 新纳入
  │     └── LateArrivalRejectedError          ← 新纳入
  ├── DerivedError(DittoError)                ← 衍生数据域（从 Exception 提升，保持独立）
  │     ├── DerivedNotFoundError, DerivedVersionError
  │     ├── DerivedValidationError, DerivedNotImplementedError
  │     ~~DerivedMaterializationError~~       ← 删除（0 raise）
  │     ~~DerivedDependencyError~~            ← 删除（0 raise）
  ├── EngineError(DittoError)                 ← 引擎域（新建）
  ├── AnalyticsError(DittoError)              ← 分析域（新建）
  ├── AppError(DittoError)                    ← 应用域（新建）
  └── InfraError(DittoError)                  ← 基础设施域（新建）
       ├── ConfigInitError, LockAcquisitionError
```

**修改**：

1. **建立统一异常体系**：
   - `ditto_kernel.exceptions.DittoError(Exception)` — 全局根（替代 DittoException）
   - 现有 `DataError` 改为继承 `DittoError`
   - 每个包定义自己的域根：`EngineError(DittoError)`、`AnalyticsError(DittoError)`、`AppError(DittoError)`、`InfraError(DittoError)`

2. **消除双重定义**：
   - 删除 `data/sources/base.py` 中的 `DataSourceError`、`SourceFetchError` 及其子类（~175 行）
   - `data/errors.py` 中的版本作为唯一权威定义
   - `sources/base.py` 从 `errors.py` 导入所需异常
   - `base.py` 中 `SourceConfigurationError`/`SourceAuthenticationError`/`SourceRateLimitError`/`SourceTransformationError` 合并到 `data/errors.py` 的 `DataSourceError` 下

3. **DerivedError 提升**：
   - `DerivedError` 从 `Exception` 改为继承 `DittoError`（保持与 DataError 平行，不合并）
   - 删除 2 个死子类：`DerivedMaterializationError`、`DerivedDependencyError`

4. **修复散落异常**：
   - 11 个直接继承 `Exception` 的异常改为继承对应域根
   - `ingestion.py` 3 个遗漏异常纳入 `DataError`
   - Engine/Analytics/App/Infra 的 inline 异常纳入各自域根

5. **合并 DittoException**：
   - `interfaces/exceptions.py` 的 `DittoException` 替换为 `DittoError`
   - `interfaces/api/errors.py` 的 `APIError` 改为继承 `DittoError`
   - 中间件新增 `data_error_handler` 层，将 `DataError` 映射为 API HTTP 响应

6. **解决名称冲突**：
   - `interfaces/exceptions.py:50` 的 `ValidationError` 重命名为 `RouteValidationError`
   - `data/errors.py:214` 的 `ValidationError` 保持（它是 Data 域的）

**关键文件**：
- `packages/kernel/src/ditto_kernel/exceptions.py` — 新增 DittoError，DataError 改继承
- `packages/data/src/ditto_data/errors.py` — 重构继承链，合并 base.py 子类，DerivedError 提升
- `packages/data/src/ditto_data/sources/base.py` — 删除重复定义，改为导入
- `packages/data/src/ditto_data/models/ingestion.py` — 3 个异常改为继承 DataError
- `interfaces/src/ditto_interfaces/exceptions.py` — DittoException → DittoError，重命名 ValidationError
- `interfaces/src/ditto_interfaces/api/errors.py` — APIError 改继承 DittoError
- `interfaces/src/ditto_interfaces/middleware.py` — 新增 data_error_handler
- `packages/engine/src/ditto_engine/exceptions.py` — 建立域根（新建）
- `packages/analytics/src/ditto_analytics/exceptions.py` — 建立域根（新建）
- `packages/app/src/ditto_app/exceptions.py` — 建立域根（新建）
- `packages/infra/src/ditto_infra/exceptions.py` — 建立域根（新建）

### 0.2 _KNOWN_DATASETS 统一（P1 bug）

**问题**：5 处独立维护，CLI ops.py 缺少 `index_weight`（已确认 bug）。

**修改**：

1. `data/models/common.py` 的 `Dataset` StrEnum 作为唯一真源
2. API/CLI/App 中所有硬编码列表改为从 `Dataset` 枚举派生
3. Coordinator 的 9 数据集列表改为从枚举过滤

**关键文件**：
- `packages/data/src/ditto_data/models/common.py` — Dataset 枚举（真源）
- `interfaces/src/ditto_interfaces/api/routes/ingestion.py:26` — 改为引用 Dataset
- `interfaces/src/ditto_interfaces/cli/commands/ops.py:17` — 改为引用 Dataset（修复 bug）
- `packages/app/src/ditto_app/config.py` — 改为引用 Dataset
- `packages/app/src/ditto_app/process/ingestion/coordinator.py:287` — 改为引用 Dataset

### 0.3 DI 注册补全（P1）

**问题**：代码审查确认仅 1 个真正缺口（原计划称 8+，实际验证为 1 个）。

**修改**：
- `ReconcileSourcesHandler` 未在 DI Provider 注册 — 需补注册
- `IngestDateHandler` 通过 context manager 模式调用，不注册（设计如此）

**关键文件**：
- `packages/app/src/ditto_app/builders/` — 注册 ReconcileSourcesHandler

### 0.4 Kernel 类型迁移（P1）

**问题**：部分类型不符合 Kernel 准入标准。

**修改**：
- `L3CheckResult`、`ReconciliationResult` → 迁移到 `ditto_app.quality`（用户确认按原计划迁出）
- `RiskScope` → 迁移到 `ditto_engine.risk`（仅 Engine 消费）
- `MacroCategory`、`MacroFrequency` → 迁移到 `ditto_data`（Data + App 消费）

**关键文件**：
- `packages/kernel/src/ditto_kernel/quality.py:110,133` — 删除
- `packages/kernel/src/ditto_kernel/enums.py:81,88,110` — 删除/迁移
- 目标包对应模块 — 接收

### 0.5 快速修复（P1 小项）

- T-P1-1/T-P1-2：5 个放错目录的测试文件移到正确位置
- AP-P1-1：CancelRunHandler/RetryRunHandler 补充 Command DTO
- A-P1-1：obv_ma20 添加 obv 依赖声明
- I-P1-1~3：Infra 中硬编码的 Data 层目录结构提取到配置

### 0.6 V1 P0-1: Kernel 测试补齐（合并）

**与审计关系**：必须在 0.4 Kernel 类型迁移之后执行——被测类型已迁移到新位置。

**修改**：
- `quality.py` 测试 → 迁移后在 `app` 层写测试（原 L3CheckResult/ReconciliationResult 已迁出）
- `math.py` 测试 → kernel 原位写（未迁移）
- `specs.py` 测试 → kernel 原位写（未迁移）
- 额外：`exceptions.py` 测试（新增 DittoError，需验证继承链）

### 0.7 V1 P0-2: R4 信号推送端到端验证（合并到 0.3）

**与审计关系**：Phase 0.3 已修复 DI 注册缺失（含 DeliveryRouter），E2E 验证紧跟其后。

**修改**：在 0.3 DI 注册补全后，执行配置通知渠道 + 端到端集成测试。

### 0.8 V1 P1-4: numpy 显式依赖（合并）

**与审计关系**：无冲突，归入 0.5 快速修复。

**修改**：`pixi.toml` 添加 `numpy >=2.0,<3`。

---

## Phase 1: Kernel Rich Domain Model 重组 ✅ 已完成

**目标**：Kernel 从纯值类型扩展为 Rich Domain Model，按子域重组。预计改动 ~40 文件。

**实际结果**（2026-04-18 完成）：
- 改动 64+ 文件（27 源码 + 37 测试），删除 3 旧文件（enums.py / specs.py / types.py）
- 新建 4 个子域文件：instrument.py / order.py / market.py / strategy.py
- 5711 测试全部通过，lint/type/arch 检查通过

### 1.1 按子域重组文件结构 ✅

**当前**（按技术类型）：`enums.py`, `identity.py`, `types.py`, `specs.py`, `quality.py` ...

**实际结果**（按业务子域）：
```
ditto_kernel/
├── identity.py        # 保留：跨子域的 ID 类型
├── clock.py           # 保留：Clock Protocol + 实现
├── events.py          # 保留：EventBus Protocol + 实现
├── exceptions.py      # 保留：DittoError 根（Phase 0 新增）
├── instrument.py      # ✅ 新：AssetClass / Exchange / InstrumentIngestParams
├── order.py           # ✅ 新：OrderSide
├── market.py          # ✅ 新：CalendarId / GrainId / TimeSpec / MacroCategory / MacroFrequency / MacroDataProvider Protocol
├── strategy.py        # ✅ 新：DerivedRole / DerivedSpec / MaterializationProfile / ExecutionPolicy / ImpactModel / RiskScope / RunStatus / DecisionFrame Protocol
├── quality.py         # ✅ 精简：仅 DQLevel / DQSeverity / DQIssue / DQResult（Phase 0 迁出 L3CheckResult/ReconciliationResult）
├── research.py        # 保留：研究相关类型
├── math.py            # 保留：数学工具
└── (已删除) enums.py, specs.py, types.py
```

**偏离说明**：
- `trade.py` 未创建 — 当前 kernel 中无 Trade 相关类型需要独立文件
- `types.py` 已删除 — InstrumentIngestParams 并入 instrument.py
- RiskScope 留在 strategy.py — 实际消费者为 4 个包（Engine/Data/Interfaces/App），迁入 engine 会违反 importlinter

### 1.2 frozen dataclass 添加纯计算方法 ✅

**原则**：
- 只添加无外部依赖的纯计算（@property 或 cached_property）
- 不引入任何 I/O、状态变更、外部服务调用

**实际新增的 `@property`**（26 个测试覆盖）：
| 类型 | 属性 | 说明 |
|------|------|------|
| `InstrumentIngestParams` | `has_identifier` | 是否存在有效标识符 |
| `InstrumentIngestParams` | `primary_identifier` | 按优先级返回主标识符 |
| `TimeSpec` | `has_availability_time` | 是否指定可用时间键 |
| `ExecutionPolicy` | `is_pit_mode` | 是否为 PIT 模式 |
| `DQIssue` | `is_error` | 是否为 ERROR 级别 |

### 1.4 V1.1 Phase 6: Regime 宏观指标（合并 MacroDataProvider）

**与审计关系**：V1.1 原计划将 `MacroDataProvider` Protocol 放在 kernel，需对齐新的子域结构。

**架构调整**：
- `MacroDataProvider` Protocol 放在 `kernel/market.py`（宏观 → market 子域）
- App 层桥接编排（MacroService → MacroDataProvider → RegimeIndicator）保持不变
- 新增的 `InterestRateIndicator`/`InflationIndicator`/`LiquidityIndicator` 在 `engine/alpha/builtins/regime/` 下，不违反分层

**问题**：`DecisionFrame = pl.DataFrame` 无 schema 保护。

**实际方案**（偏离原计划）：在 `kernel/strategy.py` 定义 `DecisionFrame` 为 Protocol（零依赖），使用 `Sequence` 代替 polars 类型。`FrameCol` + `validate_frame` 保留在 engine 中。

```python
# kernel/strategy.py — 零依赖 Protocol
class DecisionFrame(Protocol):
    @property
    def instruments(self) -> Sequence[str]: ...
    @property
    def signals(self) -> Sequence[str]: ...
    @property
    def scores(self) -> Sequence[float]: ...
```

**偏离原因**：原计划将 DecisionFrame 作为 frozen dataclass 迁入 kernel，但其实现依赖 polars（违反 kernel 零外部依赖）。Protocol 方案既满足跨层共享需求，又不引入依赖。

**关键文件**：
- `packages/kernel/src/ditto_kernel/` — 全部现有文件重组
- `packages/engine/src/ditto_engine/alpha/frame.py` — DecisionFrame Protocol 实现方
- 所有导入 kernel 类型的文件 — 更新 import 路径（实际 64+ 文件）

### V1-1 间歇：V1 P1-1 LIMIT 单启用（独立）

**与审计关系**：不涉及被重构文件，可在 Phase 1 后安全执行。

**修改**：
- `engine/execution/planner.py` — `_make_order()` 支持 MARKET/LIMIT 选择
- `engine/alpha/specs.py` — StrategySpec 新增 `default_order_type` 字段
- 单元测试

### V1-2 间歇：V1 P1-3 HTML 回测报告（独立）

**与审计关系**：不涉及被重构文件。

**修改**：
- 新增 `engine/backtest/report_renderer.py` — HTML 报告生成器
- 新增 `engine/backtest/templates/report.html` — Jinja2 模板
- 无新依赖（Jinja2 已在 infra 使用）

---

## Phase 2: Data 层 Protocol 化 + Reader/Writer 参数化

**目标**：Port dataclass → Protocol，Reader/Writer 分类参数化，trade/ CQRS 纯化。
预计改动 ~100 文件（删除 ~60，新增 ~30，修改 ~10）。

### 2.1 Port Protocol 替换

**当前**：Port 是 dataclass（参数聚合器），违反 DIP。

**目标**：每个子域定义 Protocol 接口：
```python
# data/providers/protocols.py
class BarReader(Protocol):
    def read(self, instrument_id: str, start: date, end: date) -> pl.DataFrame: ...
    def count(self, instrument_id: str, start: date, end: date) -> int: ...

class BarWriter(Protocol):
    def save(self, data: pl.DataFrame) -> None: ...
    def exists(self, instrument_id: str, trade_date: date) -> bool: ...
```

**步骤**：
1. 在 `data/providers/` 下定义所有 Protocol 接口
2. 现有 Reader/Writer 类实现对应 Protocol（`class StockBarsReader: ...` 添加 Protocol 基类）
3. 上层（Service/App）依赖 Protocol 而非具体类
4. 删除 Port dataclass

### 2.2 Reader/Writer 分类参数化

**当前**：92 个文件（46R + 46W），按子域分布。代码审查确认需区分两类：

**分类策略**：
- **机械类（~70 个）**：market/fundamental/capital 子域，每个仅在 DATASET 字符串上不同 → 泛型参数化
- **复杂类（~22 个）**：runtime/、metadata/、publication_safety/ 下有额外逻辑（认证、manifest、quarantine）→ 保留独立类，仅实现 Protocol 接口

**机械类目标**：
```python
class DatasetReader:
    """通用读取器，通过 Dataset 枚举参数化"""
    def __init__(self, store: ParquetStore, dataset: Dataset):
        self._store = store
        self._dataset = dataset

    def read(self, **kwargs) -> pl.DataFrame:
        return self._store.read(self._dataset, **kwargs)

    def count(self, **kwargs) -> int:
        return self._store.count(self._dataset, **kwargs)
```

**步骤**：
1. 实现 `DatasetReader` / `DatasetWriter` 泛型类
2. 创建 `ReaderRegistry` 按 Dataset 枚举注册实例
3. 逐个子域迁移：market → fundamental → capital
4. 删除机械类具体文件（~60 个）
5. 复杂类保留独立文件，添加 Protocol 基类声明
6. 更新 Service 层注入方式

### 2.3 trade/ CQRS 纯化

**当前**：Writer 包含完整 CRUD + 直接 SQL。

**修改**：
- `TradeIntentWriter` → 拆为 `IntentReader` + `IntentWriter`
- `FillWriter` → 拆为 `FillReader` + `FillWriter`
- `PositionWriter` → 拆为 `PositionReader` + `PositionWriter`
- 直接 SQL 封装到 Storage 层
- `TradeService` 注入 Reader + Writer

**关键文件**：
- `packages/data/src/ditto_data/storage/` — 删除 ~60 个机械文件，保留 ~22 个复杂类
- `packages/data/src/ditto_data/providers/` — 新增 Protocol 定义
- `packages/data/src/ditto_data/services/trade/` — CQRS 拆分
- `packages/data/src/ditto_data/services/trade/service.py` — 更新注入

### 2.4 importlinter 内部子域边界

**新增规则**：
- `data-sources-cross-isolation`：禁止 sources/market 导入 sources/fundamental 等
- `data-services-cqrs-mutual-exclusion`：Reader 禁止调用写方法（类似 R8）

---

## Phase 3: DataSource Fetcher Protocol

**目标**：25 方法 God Interface → 每种数据类型一个 Fetcher Protocol。
预计改动 ~40 文件。

### 3.1 Fetcher Protocol 定义

```python
# data/sources/fetcher.py
class Fetcher(Protocol[Q: FetchQuery, D: Dataset]):
    async def fetch(self, query: Q) -> pl.DataFrame: ...
    def transform(self, raw: pl.DataFrame) -> pl.DataFrame: ...
    def validate(self, data: pl.DataFrame) -> None: ...
```

### 3.2 DataSource 基类降级

- `DataSource` 从 ABC（25 抽象方法）降级为 Mixin（公共能力：重试/限流/缓存/认证）
- 每个 Tushare 数据类型实现自己的 Fetcher（如 `DailyBarFetcher`、`IndexWeightFetcher`）
- 新增数据源只需实现 Fetcher，无需修改基类

### 3.3 Source Plugin 架构

```python
# data/sources/registry.py
class SourceRegistry:
    def register(self, name: str, fetcher: type[Fetcher]) -> None: ...
    def get(self, dataset: Dataset) -> Fetcher: ...
```

为未来物理拆包（ditto_sources）预留接口。

**关键文件**：
- `packages/data/src/ditto_data/sources/base.py` — 大幅重构
- `packages/data/src/ditto_data/sources/tushare/` — 按 Fetcher 拆分
- `packages/data/src/ditto_data/sources/tdx/` — 适配 Fetcher
- `packages/data/src/ditto_data/sources/fred/` — 适配 Fetcher

---

## Phase 4: Engine TradingLoop Protocol 轻量提取

**目标**：为回测/实盘统一接口提取 TradingLoop Protocol，不拆分 EngineLoop 类。
代码审查确认 EngineLoop 实际 348 行（非原估 630 行），step-chain 模式结构良好，无需拆分。
预计改动 ~5 文件。

### 4.1 TradingLoop Protocol

```python
# engine/backtest/protocol.py
class TradingLoop(Protocol):
    clock: Clock
    def run(self, config: EngineConfig) -> BacktestResult: ...

class Clock(Protocol):
    def now(self) -> datetime: ...
    def advance_to(self, dt: datetime) -> None: ...
```

### 4.2 EngineLoop 实现 Protocol

- `EngineLoop` 添加 `TradingLoop` Protocol 声明（不重命名、不拆分）
- 现有 step-chain 模式保持不变
- 为未来 LiveLoop 实现预留接口

**关键文件**：
- `packages/engine/src/ditto_engine/backtest/protocol.py` — 新增 TradingLoop/Clock Protocol
- `packages/engine/src/ditto_engine/backtest/engine.py:191` — EngineLoop 实现 Protocol

### V1-3 间歇：V1 P1-2 PostTrade 风控通知（重新设计）

**与审计关系**：V1 原计划在 `engine/risk/post_trade.py` 直接注入 `AlertManager`（Infra），违反 Engine 禁止依赖 Infra 的架构约束。**必须重新设计**。

**新方案（Event 回调模式）**：
```python
# engine/risk/post_trade.py — 纯业务逻辑，不依赖 Infra
class CompositePostTradeGuard:
    def __init__(self, rules: list[PostTradeRule], callbacks: list[Callable] | None = None):
        ...

    def scan(self, ...) -> PostTradeReport:
        report = self._evaluate(...)
        for cb in (self._callbacks or []):
            cb(report)
        return report
```

- Engine 层只定义 `Callable[[PostTradeReport], None]` 回调接口
- App 层注入具体通知实现（AlertManager callback）
- 符合依赖倒置：Engine 定义接口，App 提供实现

**关键文件**：
- `packages/engine/src/ditto_engine/risk/post_trade.py` — 添加 callbacks 参数
- `packages/app/src/ditto_app/process/execution/` — 注册 AlertManager 回调
- 单元测试

---

## Phase 5: Infra 领域知识清理 + 收尾

**目标**：消除 Infra 中的 3 处领域知识泄漏，补全测试覆盖。

### 5.1 Infra 领域知识迁移

- Data 层目录结构硬编码 → 迁移到 Data 层配置
- Tushare token 验证 → 迁移到 Data 层 Source
- Dataset metadata checksum → 迁移到 Data 层

### 5.2 测试覆盖补全

- kernel 6 个未测模块补测试
- notification 4 个未测文件补测试
- analytics compiler 子模块补独立测试

### 5.3 文档同步

- 更新所有包级 CLAUDE.md 反映新架构
- 更新 importlinter 规则
- 更新 ADR 记录决策

### V1.1 功能（审计 Phase 2-4 完成后执行）

**V1.1 Phase 7: 归因分析增强**（与 Data 层重构无关，在 analytics 层）：
- Brinson 分解 + 交易成本归因
- 归因 API 端点

**V1.1 Phase 4: 组合优化**（依赖 Phase 1 Kernel 重组后的 WeightAllocator Protocol）：
- MeanVarianceOptimizer + RiskParityOptimizer
- 新增依赖：cvxpy, scipy

**V1.1 Phase 5: 参数优化**（依赖 Phase 4 TradingLoop Protocol 的稳定接口）：
- GridSearch + Bayesian (Optuna) + OverfitDetector
- WalkForwardOrchestrator

**V1.1 S2: 风控参数动态配置**（依赖 Phase 4 RiskLock 重构）：
- RiskConfig dataclass 替代硬编码阈值

**V1.1 S3: 多策略运行基础接口**（依赖 Phase 4 TradingLoop Protocol）：
- StrategyInstance + StrategyRegistry Protocol

---

## 执行顺序与依赖关系

```
Phase 0 (P0 修复 + V1 P0 合并)  — 改动 ~30 文件
  ├── 0.1 异常体系 ────────────────────── 独立（含 ingestion.py 3 个遗漏异常）
  ├── 0.2 _KNOWN_DATASETS ─────────────── 独立
  ├── 0.3 DI 注册 ─────────────────────── 范围缩小（仅 ReconcileSourcesHandler）
  ├── 0.4 Kernel 类型迁移 ──────────────── 独立
  ├── 0.5 快速修复 + V1 P1-4 numpy ────── 合并
  ├── 0.6 V1 P0-1 Kernel 测试 ← 依赖 0.4
  └── 0.7 V1 P0-3 设计文档更新 ────────── 最后

V1-1 间歇（独立功能）
  ├── V1 P1-1 LIMIT 单启用 ───────────── 独立
  └── V1 P1-3 HTML 回测报告 ──────────── 独立

Phase 1 (Kernel Rich Domain + V1.1 Phase 6 合并)
  ├── 1.1 子域重组
  ├── 1.2 计算方法添加
  ├── 1.3 DecisionFrame schema
  └── 1.4 V1.1 Phase 6 Regime 宏观指标 ── MacroDataProvider 对齐新子域

V1-2 间歇
  └── V1 P1-2 PostTrade 通知 ──────────── 重新设计为 Event 回调模式

Phase 2 (Data Protocol + 分类参数化) — 改动 ~100 文件（删除 ~60）
  ├── 2.1 Port Protocol 替换
  ├── 2.2 Reader/Writer 分类参数化（~70 机械类参数化 + ~22 复杂类保留）
  ├── 2.3 trade/ CQRS 纯化
  └── 2.4 importlinter 规则

Phase 3 (DataSource Fetcher) ← 依赖 Phase 2.1
  ├── 3.1 Fetcher Protocol
  ├── 3.2 DataSource 降级
  └── 3.3 Source Plugin

Phase 4 (TradingLoop Protocol 轻量提取) — 改动 ~5 文件（原 ~30）
  ├── 4.1 TradingLoop Protocol 定义
  └── 4.2 EngineLoop 实现 Protocol

Phase 5 (收尾) ← 依赖所有前序
  ├── 5.1 Infra 清理
  ├── 5.2 测试补全
  ├── 5.3 文档同步
  └── V1.1 功能（Phase 4/5/7 + S2/S3）← 架构稳定后执行
```

**回滚策略**：每个 Phase 开始前创建 git tag（`audit/pre-phase-N`），确保可回退。

## 验证方案

每个 Phase 完成后必须通过：

```bash
# 类型检查
pixi run -e dev type

# Lint
pixi run -e dev lint

# 测试（确保无回归）
pixi run -e dev test

# 架构边界
pixi run -e dev arch-check

# 完整 CI
pixi run -e dev check
```

**Phase 0 额外验证**：
- 确认 `except DittoError` 能捕获所有域异常（含 DataError/DerivedError/EngineError 等）
- 确认 `except DataSourceError` 能捕获所有来源的异常（base.py 重复已消除）
- 确认中间件 `data_error_handler` 正确将 DataError 映射为 HTTP 响应
- 确认 `_KNOWN_DATASETS` 所有位置与 Dataset 枚举一致
- 确认 DI 注册无缺失
- 确认无异常直接继承 Exception（grep 验证）

**Phase 1 额外验证**：
- 确认 Kernel 无外部依赖（`basedpyright --verify-kernel-isolation`）
- 确认 frozen dataclass 计算方法无副作用

**Phase 2 额外验证**：
- 确认 Protocol 实现覆盖所有子域
- 确认 Reader/Writer 参数化后功能等价
- 确认 trade/ CQRS 分离后无混合读写

**Phase 4 额外验证**：
- 确认 EngineLoop 回测结果与重构前数值一致（轻量改动，回归风险低）
- 确认 TradingLoop Protocol 可被未来 LiveLoop 实现（接口验证）
