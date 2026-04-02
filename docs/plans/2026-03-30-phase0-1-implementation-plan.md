# Ditto 架构重构 — Phase 0 + Phase 1 实施计划

**日期**: 2026-03-30
**状态**: 待实施
**关联设计**: [hybrid-plane-design](2026-03-30-architecture-hybrid-plane-design.md)

---

## Context

**问题**：当前 Ditto 架构缺少量化系统核心支柱（Clock 抽象、DataProvider 统一接口、Pipeline 模型），Core 直接耦合 DataHub 存储层，无法实现回测/实盘统一代码路径。

**方案**：基于 hybrid-plane-design，先扩展 Kernel 抽象层（Phase 0），再收拢 Data 平面数据访问（Phase 1），为后续 Engine/Analytics 平面重构奠基。

**产出**：10 个 PR（含 2 个前置约束调优 PR），Kernel 从 6 类型扩展到 17 类型，DataHub 新增 `query/` 子模块 + `BacktestProvider`/`LiveProvider`。

---

## Phase -1：前置约束调优（规则预对齐）

**目的**：解决当前项目约束与 Phase 0 目标的 3 处冲突，避免开发过程中 CI/CLAUDE.md 规则报错。

**详细设计**：[pre-phase0-constraint-tuning](2026-03-30-pre-phase0-constraint-tuning.md)

### Task -1a: 更新 Kernel CLAUDE.md 准入标准 `[XS]`

- **验收**：CLAUDE.md 准入标准允许 Protocol + 薄实现，去掉类型数量硬上限
- **文件**：
  - 修改 `packages/kernel/CLAUDE.md`
- **变更内容**：
  - 新增「Protocol / 薄实现」准入标准（5 条：预期跨层使用、零业务逻辑、无外部依赖、实现体 < 30 行、无 I/O）
  - 去掉"kernel 类型数量超过 20 个"红线，改为 PR 描述理由说明机制
  - 更新 Kernel 定位为"类型 + Protocol 抽象 + 薄实现"
  - 准入标准第 1 条从"已被 2 个包导入"改为"预期被 2 个包消费"

### Task -1b: 修正 architecture.md 术语 `[XS]`

- **验收**：所有 "Server" 术语替换为 "Port"
- **文件**：
  - 修改 `.claude/rules/architecture.md`
- **变更内容**：
  - `Server` → `Port`、`Server Service` → `Port Service`、`Server Flow` → `Port Flow`
  - 与实际包名 `ditto_port` 对齐

### Phase -1 完成标准

- [ ] `packages/kernel/CLAUDE.md` 允许 Protocol + 薄实现准入
- [ ] 类型数量硬上限已移除
- [ ] `.claude/rules/architecture.md` 术语与实际包名一致
- [ ] `pixi run -e dev check` 全通过

---

## Phase 0：Kernel 扩展（纯增量）

**原则**：每个 PR 独立可验证，`pixi run -e dev check` 全通过。

**执行顺序**：0a → 0b → 0d → 0c（0c 依赖前三者的 `Context`）

### Task 0a: Clock Protocol + SimulatedClock + RealtimeClock `[S]`

- **验收**：Clock Protocol 定义完整，两个实现通过单元测试，`pixi run -e dev check` 通过
- **前置**：Task -1a 已完成（Kernel CLAUDE.md 已允许 Protocol + 薄实现）
- **文件**：
  - 新建 `packages/kernel/src/ditto_kernel/clock.py`
  - 新建 `packages/kernel/tests/unit/test_clock.py`
  - 修改 `packages/kernel/src/ditto_kernel/__init__.py` — 添加 Clock/SimulatedClock/RealtimeClock 导出
- **关键设计**：
  - `Clock(Protocol)`: `now`, `today`, `advance_to` 三个成员
  - `SimulatedClock`: 可推进时间，`advance_to` 断言不回退
  - `RealtimeClock`: 读取系统时间，`advance_to` 抛 RuntimeError
  - 零外部依赖，仅用 `datetime` 标准库

### Task 0b: DataProvider Protocol + BarQuery + InstrumentQuery `[S]`

- **验收**：DataProvider Protocol + 查询契约定义完整，Protocol 一致性测试通过
- **文件**：
  - 新建 `packages/kernel/src/ditto_kernel/provider.py`
  - 新建 `packages/kernel/tests/unit/test_provider.py`
  - 修改 `packages/kernel/src/ditto_kernel/__init__.py` — 添加 DataProvider/BarQuery/InstrumentQuery 导出
- **关键设计**：
  - `AnyFrame = Any` 类型别名 — Protocol 层不引入 polars 依赖，实际实现用 `pl.DataFrame`
  - `BarQuery(frozen=True)`: instruments, start, end, frequency, adj
  - `InstrumentQuery(frozen=True)`: asset_class, exchange, universe（均可 None）
  - `DataProvider(Protocol)`: get_bars, get_instruments, get_schedule, get_factor
  - frequency/adj 保持 `str` 类型，由实现侧验证

### Task 0d: DomainEvent + EventBus + SimpleEventBus `[S]`

- **验收**：EventBus Protocol + SimpleEventBus 实现完整，发布/订阅测试通过
- **文件**：
  - 新建 `packages/kernel/src/ditto_kernel/events.py`
  - 新建 `packages/kernel/tests/unit/test_events.py`
  - 修改 `packages/kernel/src/ditto_kernel/__init__.py` — 添加 DomainEvent/EventBus/SimpleEventBus 导出
- **关键设计**：
  - `DomainEvent(frozen=True)`: event_type, timestamp, payload
  - `EventBus(Protocol)`: publish, subscribe
  - `SimpleEventBus`: 进程内同步分发，handler 按订阅顺序调用，handler 异常直接传播（不吞异常）
  - 无 unsubscribe（YAGNI）

### Task 0c: Stage/Pipeline Protocol + Context `[M]`

- **依赖**：0a, 0b, 0d（Context 引用 Clock/DataProvider/EventBus）
- **验收**：Pipeline 组合执行测试通过，Stage Protocol 一致性验证
- **文件**：
  - 新建 `packages/kernel/src/ditto_kernel/pipeline.py`
  - 新建 `packages/kernel/tests/unit/test_pipeline.py`
  - 修改 `packages/kernel/src/ditto_kernel/__init__.py` — 添加 Context/Pipeline/Stage 导出
  - 修改 `packages/kernel/pyproject.toml` — 版本升至 0.2.0
- **关键设计**：
  - `Context(frozen=True)`: clock, provider, events, metadata（default_factory=dict）
  - `Stage(Protocol[TInput, TOutput])`: name 属性 + process 方法
  - `Pipeline(Generic[TInput, TOutput])`: 不可变，execute 按序执行 stages，add_stage 返回新 Pipeline
  - Pipeline 内部用 `Any` 传递中间结果（类型擦除不可避免）
  - 允许单个 `# type: ignore[return-value]` 在 execute 方法中
- **测试辅助**：在 test 文件内定义 StubClock/StubDataProvider/StubEventBus（不放 conftest）

### Phase 0 完成标准

- [ ] Kernel 17 个公共符号全部在 `__init__.py` 导出
- [ ] `pixi run -e dev check` 全通过
- [ ] 分支覆盖率 ≥ 80%

---

## Phase 1：Data 平面收拢（datahub 内部操作）

**目标**：在 DataHub 内部新增 `query/` 子模块，实现 `BacktestProvider` 和 `LiveProvider`，让 core 的 `DataFeed` 改为消费 `DataProvider` Protocol。

**验证标准**：现有回测流程不改行为。

### Task 1a: 新建 datahub/query/ 子模块 + 查询契约 `[M]`

- **验收**：query 子模块创建完成，提供面向消费者的查询函数
- **文件**：
  - 新建 `packages/data/src/ditto_data/query/__init__.py`
  - 新建 `packages/data/src/ditto_data/query/metadata.py` — 元数据查询（instrument, calendar, universe）
  - 新建 `packages/data/src/ditto_data/query/market.py` — 行情查询（bars, adj, PIT）
  - 修改 `packages/data/src/ditto_data/__init__.py` — 如需导出 query 入口
- **关键设计**：
  - query 层是现有 services 的消费者端门面（facade），不重复实现逻辑
  - 组合 `MetadataService`、`MarketService` 等，提供简化查询接口
  - 查询参数使用 kernel 的 `BarQuery`、`InstrumentQuery`
  - 返回类型使用 `pl.DataFrame`（此处 polars 可用）

### Task 1b: BacktestProvider 实现 `[M]`

- **验收**：BacktestProvider 实现 DataProvider Protocol，通过一致性测试
- **文件**：
  - 新建 `packages/data/src/ditto_data/query/provider.py`
  - 新建 `packages/data/tests/unit/test_backtest_provider.py`（或 integration）
- **关键设计**：
  - `BacktestProvider` 实现 `kernel.DataProvider` Protocol
  - 组合 `MetadataService`、`MarketService` 等现有服务
  - `get_bars()` → 调用 `MarketService` 查询 + adj 处理
  - `get_instruments()` → 调用 `MetadataService` 查询
  - `get_schedule()` → 调用 `MetadataService` 查询交易日历
  - `get_factor()` → 调用因子存储查询
  - 构造参数由 app 层注入（DI）

### Task 1c: core/data_feed.py 改为消费 DataProvider `[L]`

- **风险**：中等 — 影响回测核心数据流
- **验收**：回测行为不变（golden test），DataFeed 通过 DataProvider 获取数据
- **文件**：
  - 修改 `packages/core/src/ditto_core/backtest/data_feed.py`
  - 修改相关测试文件
  - 可能涉及 `packages/core/src/ditto_core/backtest/engine.py` — 调整构造参数
- **关键设计**：
  - `ParquetDataFeed` 当前直接读 parquet 文件 → 改为通过 `DataProvider.get_bars()` 获取
  - 保留 `DataFeed` Protocol 接口不变（内部实现切换）
  - `Slice` 数据结构保持不变
  - 需要同步修改 `EngineLoop` 构造逻辑，注入 DataProvider
  - **回归测试**：确保现有回测端到端流程输出不变

### Task 1d: LiveProvider + 缓存 `[M]`

- **验收**：LiveProvider 实现 DataProvider Protocol，支持实时数据查询
- **文件**：
  - 修改 `packages/data/src/ditto_data/query/provider.py` — 添加 LiveProvider
  - 新建测试文件
- **关键设计**：
  - `LiveProvider` 实现 `DataProvider` Protocol
  - 用于实盘/实时场景，读取最新已摄取数据
  - 可选缓存层（利用 `ditto_infra.foundation.cache.DataCache`）
  - 与 `BacktestProvider` 共享查询逻辑（提取公共基类或 mixin）

### Phase 1 完成标准

- [ ] `datahub/query/` 子模块包含查询门面 + Provider 实现
- [ ] `BacktestProvider` + `LiveProvider` 满足 `kernel.DataProvider` Protocol
- [ ] core 的 `DataFeed` 通过 DataProvider 获取数据
- [ ] 现有回测流程行为不变（golden test 对比）
- [ ] `pixi run -e dev check` 全通过
- [ ] 分支覆盖率 ≥ 80%

---

## 关键文件索引

| 文件 | 角色 |
|------|------|
| `packages/kernel/CLAUDE.md` | 架构契约，-1a 首次更新（Phase -1 前置） |
| `.claude/rules/architecture.md` | 架构规则，-1b 术语修正（Phase -1 前置） |
| `packages/kernel/src/ditto_kernel/__init__.py` | 统一导出，每个 PR 都改 |
| `packages/kernel/pyproject.toml` | 保持零依赖，0c 升版本 |
| `packages/core/src/ditto_core/backtest/data_feed.py` | Phase 1 核心改造点 |
| `packages/core/src/ditto_core/backtest/engine.py` | 回测主循环，可能需调整注入 |
| `packages/data/src/ditto_data/services/` | Provider 实现的底层依赖 |
| `apps/port/src/ditto_port/registry/` | DI 容器，Phase 1 需新增 Provider 注册 |
| `.importlinter` | Phase 0/1 无需修改（无新包、无新依赖方向） |

## 风险与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| Kernel "纯类型"原则被打破 | ~~中~~ 已缓解 | Phase -1 已更新 CLAUDE.md 准入标准，明确"薄实现"准入条件（<30 行、无外部依赖、无业务逻辑、无 I/O） |
| AnyFrame 丢失 DataFrame 类型安全 | 低 | 仅 Protocol 层用 Any，实现和消费者侧用 pl.DataFrame |
| Pipeline.execute 的 type: ignore | 低 | 单行、不可避免、文档说明 |
| 1c DataFeed 改造影响回测 | 中 | golden test 对比改造前后回测输出 |
| Phase 1 需修改 DI 注册 | 中 | 新增 Provider 到 port/registry/，不改变现有注册 |

## 验证策略

每个 PR 提交前：
```bash
pixi run -e dev check          # lint + fmt + type + test --fast
```

每个 Phase 结束后：
```bash
pixi run -e dev ci             # CI 完整检查
pixi run -e dev arch-check     # 架构边界检查
```
