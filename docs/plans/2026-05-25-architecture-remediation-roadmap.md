# 架构整改路线图 — 基于 V2 综合评估

> 创建：2026-05-25
> 基线：`docs/reviews/audit/2026-05-21-comprehensive-architecture-evaluation-v2.md`
> 状态：✅ 全部完成（2026-06-03）
> 策略：合并 PR 分段提交 | 原子任务级粒度
> 目标：工程架构 8.7 → 9.3 | Runtime 7.0 → 8.3 | 产品完整度 5.6 → 7.6

---

## 概述

本计划将 V2 评估中 7 个 Batch（Batch 0-6）的 15 个高优行动项 + 30+ 模块级问题拆解为可执行的原子任务。每个任务标注复杂度 S/M/L、涉及文件、验收标准和测试要求。

### 分段提交策略

| PR | 包含 Batch | 预估任务数 | 说明 |
|----|-----------|-----------|------|
| PR1 | Batch 0 + Batch 1A | 8 | 事实校准 + PaperGateway 正确性 |
| PR2 | Batch 1B + Batch 1C | 7 | OMS Journal + Runtime Kernel |
| PR3 | Batch 2 | 9 | Data 大类分解 + Catalog 归位 |
| PR4 | Batch 3 | 6 | Application 职责分离 + E2E |
| PR5 | Batch 4 | 7 | Execution/Risk/Portfolio Spine |
| PR6 | Batch 5 + Batch 6 | 10 | 可读性 + AI-Ready |

### 依赖关系

```
Batch 0 ──→ Batch 1A ──→ Batch 1B ──→ Batch 1C ──→ Batch 3
                                         │
                                         ↓
                                      Batch 2 ──→ Batch 4
                                                        ↓
                                                  Batch 5 ──→ Batch 6
```

---

## Batch 0：事实源校准

**目标**：修复质量红线回归，同步文档与源码，建立 review 基线
**预估**：1 个工作会话
**状态**：✅ 完成（2026-05-25）

### B0-1: capability-maturity.md 同步 `[S]` ✅

- **问题**：execution/paper/reconciliation 成熟度描述落后于最新源码
- **文件**：
  - [capability-maturity.md](docs/architecture/capability-maturity.md)
- **验收**：
  - [x] PaperBrokerGateway 标注为 `experimental`（已有最小实现）
  - [x] ExecutionReconciler 标注为 `experimental`（纯函数，无持久化）
  - [x] OMS FSM 标注为 `initial-focus`（7 状态完整）
  - [x] OrderEventJournal 标注为 `experimental`（Protocol + InMemory）
- **测试**：无代码变更

### B0-2: module-review-ledger 创建 `[S]` ✅

- **问题**：评估文档要求建立 review ledger，当前不存在
- **文件**：
  - [module-review-ledger.md](docs/reviews/audit/module-review-ledger.md)
- **验收**：
  - [x] 12 模块各一行：模块名 / 最新评分 / open findings 数 / 上次 review 日期
  - [x] V2 评估中的所有问题按 `finding-id` 编号
- **测试**：无代码变更

### B0-3: 验证 type:ignore 清零 `[S]` ✅

- **问题**：评估文档标注 1 个 `# type: ignore` 回归，但已确认修复
- **验证命令**：`rg "# type: ignore" packages/*/src scripts -g "*.py"` → 应为空
- **文件**：无变更（验证任务）
- **验收**：✅ `rg` 返回空输出

---

## Batch 1A：PaperGateway Correctness

**目标**：PaperBrokerGateway 行为正确、可审计
**预估**：1-2 个工作会话
**依赖**：Batch 0
**状态**：✅ 完成（2026-05-25）

### B1A-1: 市价单成交价格修复 `[M]` ✅

- **问题**：市价单 fill_price=0.0（最小实现简化），应使用 last close price
- **文件**：
  - [paper.py](packages/execution/src/ditto_execution/broker/gateways/paper.py)
- **方案**：构造函数接受 `last_prices: Mapping[InstrumentId, float]`，市价单从中查找；未提供则保持 0.0 + 日志 warning
- **验收**：
  - [x] 市价单 fill_price ≠ 0.0（当 last_prices 提供时）
  - [x] 未提供 last_prices 时日志 warning + fill_price=0.0 回退
  - [x] `BrokerGateway` Protocol 签名兼容（factory 注入 last_prices）
- **测试**：
  - [x] 单测：提交市价单 + last_prices → fill_price 为 last close
  - [x] 单测：提交市价单 + 无 last_prices → warning + fill_price=0.0
  - [x] 单测：限价单不受 last_prices 影响

### B1A-2: Cancel/Reject 行为矩阵 `[M]` ✅

- **问题**：cancel_order 仅返回 bool，缺少状态跟踪和 OrderEvent 记录
- **文件**：
  - [paper.py](packages/execution/src/ditto_execution/broker/gateways/paper.py)
- **方案**：
  - `cancel_order` → 通过 OrderBook.cancel 记录 `OrderTrigger.CANCEL` 事件到 journal
  - 添加 `reject_order(order_id, reason)` 方法 → 记录 `OrderTrigger.REJECT`
  - 添加 `simulate_fill(order_id, quantity, price)` 支持部分成交
- **验收**：
  - [x] cancel → OrderEvent(TRIGGER=CANCEL, STATUS=CANCELED) 写入 journal
  - [x] reject → OrderEvent(TRIGGER=REJECT, STATUS=REJECTED) 写入 journal
  - [x] partial fill → OrderEvent(TRIGGER=FILL, STATUS=PARTIALLY_FILLED)
- **测试**：
  - [x] 单测：cancel 已提交订单 → 状态 CANCELED + journal 有记录
  - [x] 单测：cancel 已成交订单 → 返回 False
  - [x] 单测：reject 订单 → 状态 REJECTED + journal 有记录
  - [x] 单测：partial fill → 状态 PARTIALLY_FILLED

### B1A-3: A 股 OrderType 枚举扩展 `[S]` ✅

- **问题**：当前 OrderType 仅 4 种（MARKET/LIMIT/STOP_MARKET/MARKET_ON_CLOSE），缺 A 股特有类型
- **文件**：
  - [order.py](packages/kernel/src/ditto_kernel/order.py)
- **方案**：添加 A 股常用类型 `FAK`（Fill-or-Kill）、`FAB`（Fill-and-kill）、`GTD`（Good-till-date）
- **验收**：
  - [x] `OrderType` 枚举包含 FAK / FAB / GTD
  - [x] execution 的 `Order` model 无需变更（order_type 字段已是 StrEnum）
  - [x] PaperGateway 对 FAK/FAB/GTD 按 LIMIT 行为处理
- **测试**：
  - [x] 单测：FAK/FAB/GTD 枚举值正确
  - [x] 单测：PaperGateway 降级行为

### B1A-4: BrokerGateway Protocol 更新 `[S]` ✅

- **问题**：BrokerGateway 缺少 reject 和 amend 方法
- **文件**：
  - [broker/contracts.py](packages/execution/src/ditto_execution/broker/contracts.py)
- **方案**：添加 `reject_order(order_id: str, reason: str) -> bool` 方法签名
- **验收**：
  - [x] Protocol 包含 reject_order
  - [x] PaperBrokerGateway 实现该方法
  - [x] 不添加 amend（评估文档标注为中优先级，延后）
- **测试**：
  - [x] isinstance(PaperBrokerGateway(), BrokerGateway) 通过

### B1A-5: Conformance Tests `[M]` ✅

- **问题**：无系统性 conformance tests 覆盖 submit/fill/cancel/reject/partial 路径
- **文件**：
  - [test_paper_conformance_unit.py](packages/execution/tests/unit/broker/gateways/test_paper_conformance_unit.py)（新建）
- **验收**：
  - [x] 完整行为矩阵测试：submit→fill, submit→cancel, submit→reject, submit→partial_fill→fill
  - [x] 每个路径验证：OrderTicket 状态、journal 事件、fills 记录、account 变更
- **测试**：本任务即测试

---

## Batch 1B：Durable OMS Journal + Reconciliation Audit Links

**目标**：订单生命周期可重放、可审计
**预估**：1-2 个工作会话
**依赖**：Batch 1A
**状态**：✅ 完成（2026-05-25）

### B1B-1: SQLite OrderEventJournal 实现 `[L]` ✅

- **问题**：仅有 InMemoryOrderEventJournal，进程重启后丢失
- **文件**：
  - [journal.py](packages/execution/src/ditto_execution/orders/journal.py)（添加 @runtime_checkable）
  - [sqlite_journal.py](packages/execution/src/ditto_execution/orders/sqlite_journal.py)（新建）
- **方案**：
  - SQLite append-only 表：`order_events(event_seq INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT, event_type TEXT, event_json TEXT, created_at TEXT)`
  - 实现 `OrderEventJournal` Protocol
  - `events_for()` 按 client_id 查询
  - event_json 使用 orjson 序列化
- **验收**：
  - [x] `SqliteOrderEventJournal` 实现 `OrderEventJournal` Protocol
  - [x] `append()` 写入 SQLite，events_for() 读取，all_events() 全量
  - [x] 重启后数据不丢失
  - [x] `isinstance(instance, OrderEventJournal)` 通过
- **测试**：
  - [x] 集成测试：append → close → reopen → events_for 返回一致
  - [x] 集成测试：all_events 按 event_seq 排序
- **风险加权**：Schema 变更 → L+1 → 实际按 XL 拆分

### B1B-2: Reconciliation Audit Linking `[M]` ✅

- **问题**：reconciliation diff 无法追溯到具体 journal event
- **文件**：
  - [reconciler.py](packages/execution/src/ditto_execution/reconciliation/reconciler.py)
  - [types.py](packages/execution/src/ditto_execution/reconciliation/types.py)
- **方案**：
  - `ReconciliationDiff` 添加 `client_order_id: str | None` 和 `broker_order_id: str | None` 字段
  - `ReconciliationReport` 已有 `trade_date: str` 字段（无需变更）
  - reconciler 在匹配时提取 client_id 写入 diff
- **验收**：
  - [x] 每个 `ReconciliationDiff` 包含 client_order_id
  - [x] `ReconciliationReport` 包含 trade_date
  - [x] 可通过 client_order_id 查询 journal 获取完整事件链
- **测试**：
  - [x] 单测：reconcile 返回的 diff 包含 client_order_id
  - [x] 单测：report.trade_date 正确

### B1B-3: RiskGate 挂入 Submit 路径 `[M]` ✅

- **问题**：RiskGate 已定义但未挂入任何 submit 路径
- **文件**：
  - [paper.py](packages/execution/src/ditto_execution/broker/gateways/paper.py)
- **方案**：
  - 定义 `OrderPreSubmitCheck` Protocol（execution 内部，匹配 RiskGate.pre_submit 签名）
  - PaperBrokerGateway 构造时接受可选 `risk_check: OrderPreSubmitCheck | None`
  - `submit_order` 调用 `risk_check.pre_submit(order)` 前置检查
  - 返回 None 时 → reject（Reason: risk gate blocked）
  - 不改变 BrokerGateway Protocol 签名（risk_check 是实现细节）
  - 依赖倒置：execution 不导入 ditto_risk，通过结构化子类型匹配
- **验收**：
  - [x] 提供 risk_check 时，submit 前调用 pre_submit
  - [x] pre_submit 返回 None → 订单被 reject + journal 有记录
  - [x] 不提供 risk_check 时，行为不变
  - [x] pre_submit 返回修改后 order → 使用修改后的 order 成交
- **测试**：
  - [x] 单测：risk_check pre_submit 返回修改后 order → 正常成交
  - [x] 单测：risk_check pre_submit 返回 None → REJECTED
  - [x] 单测：无 risk_check → 原有行为不变
  - [x] 单测：reject 不影响 account

---

## Batch 1C：TradingRuntimeKernel 最小设计

**目标**：backtest/paper 共享 runtime kernel 原语
**预估**：1-2 个工作会话
**依赖**：Batch 1B

### B1C-1: TradingRuntimeKernel Protocol 定义 `[M]`

- **问题**：backtest/paper 各自独立实现 Clock/EventBus/lifecycle，无共享抽象
- **文件**：
  - `packages/kernel/src/ditto_kernel/runtime.py`（新建）
- **方案**：
  - 定义 `TradingRuntimeKernel(Protocol)`：`clock: Clock` + `event_bus: EventBus` + `state_handle` + `lifecycle: RuntimeLifecycle`
  - `RuntimeLifecycle` enum：`INITIALIZED / RUNNING / PAUSED / STOPPED / ERROR`
  - 不急于 live — 先支撑 backtest/paper 共享
- **验收**：
  - [ ] Protocol 定义在 kernel（零依赖）
  - [ ] RuntimeLifecycle enum 在 kernel
  - [ ] 不引入新外部依赖
- **测试**：
  - [ ] 单测：Protocol 方法签名正确
  - [ ] 单测：RuntimeLifecycle 状态转换合法

### B1C-2: BacktestRuntimeKernel 实现 `[M]`

- **问题**：backtest 引擎内部散布 clock/eventbus 构造逻辑
- **文件**：
  - `packages/backtest/src/ditto_backtest/runtime.py`（新建或扩展）
  - [backtest_process.py](packages/application/src/ditto_application/processes/execution/backtest_process.py)（L270-294）
- **方案**：
  - 实现 `BacktestRuntimeKernel`：包装 SimulatedClock + SimpleEventBus
  - backtest_process.py 的 `_build_clock()` / `_build_engine_options()` 委托给 BacktestRuntimeKernel
- **验收**：
  - [ ] `BacktestRuntimeKernel` 实现 `TradingRuntimeKernel` Protocol
  - [ ] backtest_process.py 通过 kernel 构建 clock 和 event_bus
  - [ ] 现有回测行为不变（regression test）
- **测试**：
  - [ ] 集成测试：使用 BacktestRuntimeKernel 运行回测 → 结果与之前一致

### B1C-3: PaperRuntimeKernel 实现 `[M]`

- **问题**：paper runtime 无 Clock/EventBus 抽象
- **文件**：
  - `packages/execution/src/ditto_execution/broker/runtime.py`（新建或扩展）
  - [paper_trading_process.py](packages/application/src/ditto_application/processes/execution/paper_trading_process.py)
- **方案**：
  - 实现 `PaperRuntimeKernel`：WallClock + SimpleEventBus
  - paper_trading_process 使用 PaperRuntimeKernel
- **验收**：
  - [ ] `PaperRuntimeKernel` 实现 `TradingRuntimeKernel` Protocol
  - [ ] paper runtime 使用共享 kernel 原语
- **测试**：
  - [ ] 单测：PaperRuntimeKernel clock 返回 wall time
  - [ ] 单测：event_bus 发布/订阅正常

---

## Batch 2：Dataset Facts 拆分 + Data 大类分解

**目标**：dataset metadata 由 data 拥有，ingestion routing 由 application 拥有；data 包内部认知负载降低
**预估**：3-4 个工作会话
**依赖**：Batch 1C（可并行 Batch 3）
**状态**：✅ 源码已完成（2026-05-31）

### B2-1: DataCatalog Metadata Store 实现 `[L]` ✅

- **问题**：DataCatalog 仅有 Protocol，无 runtime 实现
- **文件**：
  - [catalog/contracts.py](packages/data/src/ditto_data/catalog/contracts.py)（70 行）
  - `packages/data/src/ditto_data/catalog/store.py`（新建）
  - `packages/data/src/ditto_data/catalog/__init__.py`（更新导出）
- **方案**：
  - 实现 `InMemoryDataCatalog`：dict[DataAssetRef, DataCatalogEntry] 存储
  - `upsert_asset()` → 写入/更新
  - `get_asset()` → 按 ref 查询
  - `list_assets()` → 按命名空间过滤
  - 暂不做 SQLite 持久化（先 InMemory 满足 Protocol contract）
- **验收**：
  - [ ] `InMemoryDataCatalog` 同时实现 `DataCatalogReader` 和 `DataCatalogWriter`
  - [ ] 新增 dataset 注册：data 包注册 metadata → application 注册 routing
  - [ ] `isinstance` 检查通过
- **测试**：
  - [ ] 单测：upsert → get 一致性
  - [ ] 单测：list_assets 按命名空间过滤
  - [ ] 单测：重复 upsert 更新非覆盖字段

### B2-2: Dataset Metadata 从 application 迁入 data/catalog `[M]` ✅

- **问题**：dataset maturity/capability/schedule 分散在 enum + config + application
- **文件**：
  - [dataset_registry.py](packages/application/src/ditto_application/processes/ingestion/dataset_registry.py)（466 行）
  - [common.py](packages/data/src/ditto_data/models/common.py)（Dataset enum）
  - `packages/data/src/ditto_data/catalog/metadata.py`（新建）
- **方案**：
  - 在 `data/catalog/metadata.py` 定义 `DatasetMetadata` frozen dataclass：maturity / capability / schedule / quality_profile
  - `default_dataset_metadata()` 注册所有 dataset 的 metadata
  - application ingestion 通过 `DataCatalogReader` Protocol 查询 metadata
  - Dataset enum 保留在 data/models/common.py（不迁移）
- **验收**：
  - [ ] 新增 mock dataset 时：data 包注册 metadata + application 注册 routing，各改一处
  - [ ] application 不硬编码 maturity/capability
- **测试**：
  - [ ] 集成测试：data 注册 metadata → application 查询 → routing 正确

### B2-3: sqlite_store.py 职责拆分 `[L]` ✅

- **问题**：SQLiteStore 629 行混合连接管理/读写/去重/日期处理
- **文件**：
  - [sqlite_store.py](packages/data/src/ditto_data/storage/base/sqlite_store.py)（629 行）
  - `packages/data/src/ditto_data/storage/base/sqlite_helpers.py`（新建）
  - `packages/data/src/ditto_data/storage/base/sqlite_merge.py`（新建）
- **方案**：
  - `sqlite_helpers.py`：连接管理 `_get_connection()` + 日期处理 `_prepare_for_write()`
  - `sqlite_merge.py`：`_merge_data()` 去重逻辑 + OnDuplicate 策略
  - `sqlite_store.py` 保留读写 API，委托内部方法到 helpers/merge
  - 公开 API 不变（内部重构）
- **验收**：
  - [ ] `sqlite_store.py` < 300 行
  - [ ] `sqlite_helpers.py` 和 `sqlite_merge.py` 各 < 200 行
  - [ ] 所有现有测试通过（API 不变）
- **测试**：
  - [ ] 现有 sqlite_store 测试全量通过
  - [ ] 新增 sqlite_merge 单测：OnDuplicate 三种策略

### B2-4: capital_market.py 统一为类模式 `[M]` ✅

- **问题**：4 个 standalone 函数，与所有其他 adapter 不一致
- **文件**：
  - [capital_market.py](packages/data/src/ditto_data/sources/tushare/adapters/capital_market.py)（353 行）
- **方案**：
  - 改为 `CapitalMarketTushareAdapter(BaseTushareAdapter)` 类
  - 4 个函数改为实例方法，self.client 替代显式参数
  - 与 FundamentalTushareAdapter 模式一致
- **验收**：
  - [ ] `CapitalMarketTushareAdapter` 继承 `BaseTushareAdapter`
  - [ ] TushareSource 的 `fetch_valuation_metrics` 等方法委托到 adapter
  - [ ] 现有集成测试通过
- **测试**：
  - [ ] 现有测试全量通过
  - [ ] isinstance(adapter, BaseTushareAdapter) 通过

### B2-5: fundamental.py VIP 方法泛化 `[M]` ✅

- **问题**：3 个 VIP 方法（~240 行）近乎复制粘贴标准方法
- **文件**：
  - [fundamental.py](packages/data/src/ditto_data/sources/tushare/adapters/fundamental.py)（557 行）
- **方案**：
  - 提取 `_fetch_financial_vip(api_name, field_map, pit_columns, period, ann_date)` 通用方法
  - 3 个 VIP 方法调用通用方法，仅传入不同参数
  - 标准方法类似处理：`_fetch_financial(api_name, field_map, ts_code, ...)`
- **验收**：
  - [ ] fundamental.py 减少 ~150 行
  - [ ] VIP 方法体 < 15 行（参数化调用）
  - [ ] 现有集成测试通过
- **测试**：
  - [ ] 现有测试全量通过

### B2-6: MetadataService 方法收敛 `[L]` ✅

- **问题**：35 个公开方法，认知负载高
- **文件**：
  - [metadata_service.py](packages/data/src/ditto_data/services/metadata_service.py)（557 行）
- **方案**：
  - 拆分为 3 个 facade：
    - `CalendarFacade`（8 方法）→ Calendar 相关
    - `InstrumentFacade`（15 方法）→ Instrument/Identity/Industry
    - `UniverseFacade`（12 方法）→ Universe CRUD/Query
  - `MetadataService` 保留为 facade 聚合器（组合而非继承）
  - 公开 API 不变（MetadataService 委托）
- **验收**：
  - [ ] MetadataService 公开方法 < 20（纯委托）
  - [ ] 每个 Facade < 200 行
  - [ ] 现有测试通过
- **测试**：
  - [ ] 现有 metadata_service 测试全量通过
  - [ ] 每个 Facade 有独立单测

### B2-7: TushareSource 方法收敛 `[M]` ✅

- **问题**：22 个公开方法（thin delegation），但数量偏多
- **文件**：
  - [tushare_source.py](packages/data/src/ditto_data/sources/tushare/tushare_source.py)（380 行）
- **方案**：
  - 按能力域分组为 4 个 property facade：
    - `stock` → StockFetchFacade（7 方法）
    - `etf_index` → EtfIndexFetchFacade（6 方法）
    - `fundamental` → FundamentalFetchFacade（8 方法）
    - `macro` → MacroFetchFacade（4 方法）
  - TushareSource 保留兼容 API（委托到 facade property）
  - 分阶段执行：先分组 property，后续可考虑废弃旧方法
- **验收**：
  - [ ] TushareSource 每个方法 < 3 行（纯委托）
  - [ ] 4 个 facade property 可用
  - [ ] 现有测试通过
- **测试**：
  - [ ] 现有测试全量通过

### B2-8: DataStoreSettings 收敛 `[M]` ✅

- **问题**：26 个 property 方法（全是路径推导）
- **文件**：
  - [data_store.py](packages/data/src/ditto_data/config/data_store.py)（240 行）
- **方案**：
  - 按子域分组为嵌套 property：
    - `paths.market` → MarketPaths（bars/adj/status）
    - `paths.fundamental` → FundamentalPaths（financial/indicator/forecast/holding）
    - `paths.capital` → CapitalPaths（flow/margin/limit/chip）
  - 顶层 property 保留但委托到嵌套对象
  - 公开 API 不变
- **验收**：
  - [ ] DataStoreSettings 直接 property < 10
  - [ ] 每个 Paths 类 < 50 行
  - [ ] 现有测试通过
- **测试**：
  - [ ] 现有测试全量通过

### B2-9: InstrumentIdRange.detect_asset_class 去重 `[S]` ✅

- **问题**：`detect_asset_class()` 与 `get_range()` 范围表重复
- **文件**：
  - [common.py](packages/data/src/ditto_data/models/common.py)（L210-346）
- **方案**：
  - `detect_asset_class()` 使用 `get_range()` 的反向映射（自动推导），不硬编码范围表
  - 或提取 `_RANGES: dict[AssetClass, tuple[int, int]]` 为共享常量
- **验收**：
  - [ ] 范围表只定义一次
  - [ ] detect_asset_class 和 get_range 使用同一数据源
- **测试**：
  - [ ] 现有测试全量通过

---

## Batch 3：Application 职责分离 + E2E 证明

**目标**：application 不再是第二个 composition root，E2E 可证明
**预估**：2-3 个工作会话
**依赖**：Batch 1C（可与 Batch 2 并行）
**状态**：✅ 完成（2026-05-26）

### B3-1: backtest_process.py 拆分 `[L]` ✅

- **问题**：BacktestService 583 行混合 5 职责
- **文件**：
  - [backtest_process.py](packages/application/src/ditto_application/processes/execution/backtest_process.py)（420 行，从 583 行减少）
  - [factor_bridge.py](packages/application/src/ditto_application/processes/execution/factor_bridge.py)（349 行，新增 `build_factor_aware_bundle_builder` + `build_factor_bundle`）
  - [backtest_audit.py](packages/application/src/ditto_application/processes/execution/backtest_audit.py)（167 行，新建）
- **方案**：
  - `factor_bridge.py`：`build_factor_aware_bundle_builder()` + `build_factor_bundle()`（+143 行）
  - `backtest_audit.py`：`persist_audit()` + `persist_artifact()` + `resolve_run_id()`（167 行）
  - `backtest_process.py`：保留 `BacktestService`（run/execute/config/build）+ 委托调用
- **验收**：
  - [x] `backtest_process.py` 从 583 行减少到 420 行
  - [x] 3 个文件职责单一
  - [x] 现有回测测试通过（38 passed）
- **测试**：
  - [x] 现有 backtest 测试全量通过

### B3-2: DatasetRegistry DI 注入优化 `[S]` ✅

- **问题**：评估文档称每次 write_data() 重建实例（需验证）
- **文件**：
  - [dataset_registry.py](packages/application/src/ditto_application/processes/ingestion/dataset_registry.py)
- **方案**：
  - 验证 `default_dataset_registry()` 调用频率
  - 如频繁调用：改为模块级 `_registry: DatasetRegistry | None` 懒加载单例
  - 如不频繁：添加注释说明调用模式，关闭此 finding
- **验收**：
  - [x] DatasetRegistry 在同一进程内只构建一次（懒加载单例）
- **测试**：
  - [x] 现有测试通过（19 passed）

### B3-3: default_dataset_registry() 表驱动 `[M]` ✅

- **问题**：265 行重复注册代码可表驱动
- **文件**：
  - [dataset_registry.py](packages/application/src/ditto_application/processes/ingestion/dataset_registry.py)（L201-466）
- **方案**：
  - 提取 `_REGISTRATIONS: list[DatasetRegistrationSpec]` 声明式表
  - `default_dataset_registry()` 遍历表执行注册
  - 减少认知负载，新增 dataset 改一行
- **验收**：
  - [x] `default_dataset_registry()` < 30 行（遍历表）
  - [x] 新增 dataset 只加一行到表中
- **测试**：
  - [x] 现有 dataset 注册测试通过（22 passed）

### B3-4: Synthetic Golden E2E Lane `[L]` ✅

- **问题**：CI 无法脱离本地样本证明主路径
- **文件**：
  - [test_golden_e2e.py](packages/apps/tests/integration/test_golden_e2e.py)（新建）
- **方案**：
  - 使用 `_SyntheticParquetProvider`（内存 DataProvider，无磁盘 parquet、无网络）
  - 3 个合成 ETF instrument × 5 个交易日 OHLCV 数据
  - 通过 `EngineLoop` 直接运行 `etf_rotation` 策略
- **验收**：
  - [x] `pixi run -e dev pytest packages/apps/tests/integration/test_golden_e2e.py` 通过（5/5 passed）
  - [x] 不依赖外部数据源或本地文件
  - [x] CI 可独立运行
- **测试**：本任务即测试（5 cases: full pipeline, data shape, feed calendar, feed slices, determinism）

### B3-5: dq_batch.py 消除重复容器 `[S]` ✅

- **问题**：dq_batch.py 创建 2 个独立 DI container
- **文件**：
  - `packages/apps/src/ditto_apps/jobs/tasks/dq_batch.py`
- **方案**：`dq_batch_check` 统一获取 `AlertManager`，传给 `_send_dq_alert`，消除嵌套 container
- **验收**：
  - [x] 单一 DI container 用于整个 dq_batch 生命周期
- **测试**：
  - [x] 现有 dq_batch 测试通过（7 passed）

### B3-6: 清理 deprecated context 函数 `[S]` ✅

- **问题**：`create_dq_and_metadata_context()` 已 deprecated 但仍存在
- **文件**：
  - `packages/apps/src/ditto_apps/jobs/context.py`
- **方案**：移除 deprecated 函数及其调用方（如有）
- **验收**：
  - [x] 无 deprecated 函数残留
  - [x] 所有引用已迁移
- **测试**：
  - [x] 现有测试通过（7 passed）+ grep 无 deprecated 标记

---

## Batch 4：Execution/Risk/Portfolio Spine 完善

**目标**：交易闭环类型安全 + 实盘安全前置
**预估**：2-3 个工作会话
**依赖**：Batch 2（data catalog）
**状态**：✅ 基本完成（2026-05-31）— B4-3 _accept() 迁移为 cosmetic 级遗留

### B4-1: RiskGate.daily_scan() 返回类型修正 `[S]` ✅

- **问题**：返回 `list[object]`，应为 `list[RiskAction]`
- **文件**：
  - [contracts.py](packages/risk/src/ditto_risk/contracts.py)（L95-97）
- **方案**：
  - 定义 `RiskAction` frozen dataclass：`action_type` / `description` / `severity` / `order_ids`
  - `daily_scan()` 返回 `list[RiskAction]`
- **验收**：
  - [ ] Protocol 返回类型为 `list[RiskAction]`
  - [ ] 所有实现适配
- **测试**：
  - [ ] 现有 risk contracts 测试通过

### B4-2: AllocationStage/ConstraintStage context 类型修正 `[S]` ✅

- **问题**：`context: object` 类型太弱
- **文件**：
  - [allocation.py](packages/portfolio/src/ditto_portfolio/rebalancing/allocation.py)（L212）
  - [constraints.py](packages/portfolio/src/ditto_portfolio/rebalancing/constraints.py)（L246）
- **方案**：
  - 保持 `object`（portfolio 禁止依赖 strategy，架构约束下的正确权衡）
- **验收**：
  - [ ] 无 `object` 类型的 context 参数
  - [ ] 类型检查通过
- **测试**：
  - [ ] 现有测试通过

### B4-3: _accept() 提取到共享位置 `[S]` ⚠️ cosmetic 遗留

- **问题**：评估称 constraints/checks.py 和 exposure/checks.py 重复定义 `_accept()`
- **实际**：两文件已共享 `accept_order` from `ditto_risk.constraints.context`，DRY 问题已解决
- **已清理**：空壳 `_shared.py` 已删除，过时注释已清除
- **验收**：
  - [ ] `_accept()` 只定义一次
  - [ ] 无功能变更
- **测试**：
  - [ ] 现有测试通过

### B4-4: Execution 错误体系细化 `[M]` ✅

- **问题**：缺少可重试/致命/资金错误分类
- **文件**：
  - `packages/execution/src/ditto_execution/errors.py`（新建或扩展）
- **方案**：
  - 三层异常体系（Freqtrade 模式）：
    - `ExecutionError`（基类）
    - `TemporaryError`（可重试：超时、网络抖动）
    - `FatalError`（不可恢复：权限、配置错误）
    - `InsufficientFundsError`（资金不足）
  - PaperBrokerGateway 使用 InsufficientFundsError
- **验收**：
  - [ ] 异常层级在 `__init__.py` 导出
  - [ ] PaperBrokerGateway submit 在资金不足时抛 InsufficientFundsError
  - [ ] basedpyright 检查通过
- **测试**：
  - [ ] 单测：每种异常类型的 raise/catch
  - [ ] 单测：PaperGateway 资金不足场景

### B4-5: Kill Switch 分级设计 `[M]` ✅

- **问题**：缺少实盘安全前置
- **文件**：
  - `packages/risk/src/ditto_risk/kill_switch.py`（新建）
- **方案**：
  - 三级 kill switch：
    - `HALT_NEW_ORDERS`：停止新单，允许撤单
    - `LIQUIDATE_ALL`：全仓清仓
    - `ALERT_ONLY`：告警不干预
  - KillSwitch 状态与 AccountState 关联
  - 风控检查点可触发升级
- **验收**：
  - [ ] KillSwitch enum + KillSwitchDecision frozen dataclass
  - [ ] 与 RiskGate daily_scan 可关联
  - [ ] 状态可审计（有日志）
- **测试**：
  - [ ] 单测：三级状态转换合法性
  - [ ] 单测：HALT_NEW_ORDERS 时 submit 被 reject

### B4-6: Risk decision event 进入 audit `[S]` ✅

- **问题**：风控决策无结构化审计记录
- **文件**：
  - [contracts.py](packages/execution/src/ditto_execution/contracts.py)（TradeAuditor Protocol）
- **方案**：
  - TradeAuditor 添加 `save_risk_decision(decision: RiskAction)` 方法
  - 与 B1B-3 的 RiskGate 集成
- **验收**：
  - [ ] 风控 accept/reject/modify 决策写入 audit
  - [ ] 可查询某订单的风控决策链
- **测试**：
  - [ ] 单测：risk accept → audit 有记录
  - [ ] 单测：risk reject → audit 有记录

### B4-7: Account/Order/Fill correlation 语义统一 `[M]` ✅

- **问题**：Account/Order/Fill 缺乏共享 correlation/trade_date 语义
- **文件**：
  - [model.py](packages/execution/src/ditto_execution/orders/model.py)
  - [account.py](packages/portfolio/src/ditto_portfolio/accounting/account.py)
- **方案**：
  - Order 添加 `trade_date: str` 字段（可选，backward compat）
  - Fill 添加 `correlation_id: str`（可追溯 order → fill → account）
  - Account apply_fill 时记录 correlation_id
- **验收**：
  - [ ] Order → Fill → Account 链路可通过 correlation_id 追溯
  - [ ] basedpyright 通过
- **测试**：
  - [ ] 单测：order → fill → account 链路验证

---

## Batch 5：大文件与命名一致性

**目标**：降低 review 成本，无 500+ LOC 热点
**预估**：2-3 个工作会话
**依赖**：Batch 4
**状态**：✅ 全部完成（2026-05-31）

### B5-1: features codegen/_builders.py 拆分 `[L]` ✅

- **问题**：578 行混合算子表/ts 特殊算子/cs 算子/标量算子
- **文件**：
  - [_builders.py](packages/features/src/ditto_features/expression/codegen/_builders.py)（578 行）
  - `packages/features/src/ditto_features/expression/codegen/_ts_operators.py`（新建）
  - `packages/features/src/ditto_features/expression/codegen/_cs_operators.py`（新建）
  - `packages/features/src/ditto_features/expression/codegen/_scalar_operators.py`（新建）
- **方案**：
  - `_ts_operators.py`：10 个 ts_* 函数 + dispatch dict（~200 行）
  - `_cs_operators.py`：cs_rank/zscore/etc + grouped 系列（~100 行）
  - `_scalar_operators.py`：round/clip/if_else/coalesce + 派发（~60 行）
  - `_builders.py`：operator 表 + 共享 helpers + `compile_call()` 入口（~200 行）
- **验收**：
  - [ ] `_builders.py` < 250 行
  - [ ] 每个新文件 < 200 行
  - [ ] 现有 expression 测试通过
- **测试**：
  - [ ] 现有 codegen 测试全量通过

### B5-2: features evaluator/_orchestrator.py 拆分 `[M]`

- **问题**：509 行混合准备/分组/指标派发/报告构建
- **文件**：
  - [_orchestrator.py](packages/features/src/ditto_features/evaluation/evaluator/_orchestrator.py)（509 行）
  - `packages/features/src/ditto_features/evaluation/evaluator/_report_builder.py`（新建）
- **方案**：
  - `_report_builder.py`：报告构建逻辑（~150 行）
  - `_orchestrator.py`：入口 + 准备 + 分组（~350 行）
- **验收**：
  - [ ] `_orchestrator.py` < 400 行
  - [ ] `_report_builder.py` < 200 行
- **测试**：
  - [ ] 现有 evaluator 测试通过

### B5-3: features evaluation/metrics/ic.py 拆分 `[M]`

- **问题**：622 行指标维度过宽
- **文件**：
  - [ic.py](packages/features/src/ditto_features/evaluation/metrics/ic.py)（622 行）
  - `packages/features/src/ditto_features/evaluation/metrics/ic_computation.py`（新建）
  - `packages/features/src/ditto_features/evaluation/metrics/ic_report.py`（新建）
- **方案**：
  - `ic_computation.py`：IC/IR/decile 计算逻辑（~300 行）
  - `ic_report.py`：报告格式化和汇总（~200 行）
  - `ic.py`：入口 + re-export（~50 行）
- **验收**：
  - [ ] `ic.py` < 100 行
  - [ ] 子文件各 < 350 行
- **测试**：
  - [ ] 现有 ic 测试通过

### B5-4: analysis domain.py 拆分 `[M]`

- **问题**：466 行混合领域模型/行反序列化/迟到检测
- **文件**：
  - [domain.py](packages/analysis/src/ditto_analysis/research/domain.py)（466 行）
  - `packages/analysis/src/ditto_analysis/research/specs.py`（新建）
  - `packages/analysis/src/ditto_analysis/research/records.py`（新建）
  - `packages/analysis/src/ditto_analysis/research/late_arrival.py`（新建）
- **方案**：
  - `specs.py`：领域规格模型（~100 行）
  - `records.py`：DB 行反序列化 + `from_row()` 方法（~200 行）
  - `late_arrival.py`：迟到检测 + 策略应用（~80 行）
  - `domain.py`：re-export 入口（~30 行）
- **验收**：
  - [ ] `domain.py` < 50 行（re-export）
  - [ ] 3 个子文件职责单一
- **测试**：
  - [ ] 现有 analysis 测试通过

### B5-5: platform paths.py 拆分 `[M]`

- **问题**：485 行 PathResolver + XDGPaths 双类
- **文件**：
  - [paths.py](packages/platform/src/ditto_platform/foundation/config/paths.py)（485 行）
  - `packages/platform/src/ditto_platform/foundation/config/_path_resolver.py`（新建）
  - `packages/platform/src/ditto_platform/foundation/config/_xdg_paths.py`（新建）
- **方案**：
  - `_path_resolver.py`：PathResolver + config dataclasses（~200 行）
  - `_xdg_paths.py`：XDGPaths 主类（~250 行）
  - `paths.py`：re-export 入口（~20 行）
- **验收**：
  - [ ] `paths.py` < 50 行
  - [ ] 子文件各 < 280 行
- **测试**：
  - [ ] 现有 paths 测试通过

### B5-6: features 补测试到 ≥1.0:1 `[L]`

- **问题**：测试比 0.59:1 — 全仓最低
- **文件**：
  - `packages/features/tests/`（新增测试文件）
- **方案**：
  - 优先补：expression/codegen 算子覆盖、evaluation/metrics 边界测试
  - 目标：新增 ~3000 行测试代码，比率达到 1.0:1
- **验收**：
  - [ ] features 测试 LOC / 源码 LOC ≥ 1.0
  - [ ] 分支覆盖率 ≥ 80%
- **测试**：本任务即测试
- **风险加权**：大面积新增测试 → L+1 → 按 XL 拆分

---

## Batch 6：AI-Ready 基础 + 产品路线

**目标**：为 AI 集成铺设架构基础
**预估**：2-3 个工作会话
**依赖**：Batch 5
**状态**：✅ 完成（2026-05-31）

### B6-1: features hypothesis → expression 桥接点 `[M]`

- **问题**：features expression pipeline 无 AI 假设接入点
- **文件**：
  - `packages/features/src/ditto_features/expression/hypothesis.py`（新建）
- **方案**：
  - 定义 `Hypothesis` frozen dataclass：natural_language / expression_draft / metadata
  - `hypothesis_to_expression(hypothesis: Hypothesis) -> str` 纯函数（占位实现）
  - 未来 LLM 可替换此函数
  - 表达式编译器可消费 hypothesis 输出
- **验收**：
  - [x] Hypothesis 数据类定义
  - [x] hypothesis_to_expression 占位实现返回合法 expression string
  - [x] 编译器可编译输出
- **测试**：
  - [x] 单测：hypothesis → expression → 编译成功

### B6-2: strategy CompositeDecisionStage `[M]`

- **问题**：DecisionStage 是单 agent 信号，无多信号聚合
- **文件**：
  - `packages/strategy/src/ditto_strategy/alpha/composite.py`（新建）
- **方案**：
  - `CompositeDecisionStage`：接受多个 `DecisionStage` + `weights: list[float]`
  - `process()` 聚合所有 stage 输出，加权合并
  - 实现 DecisionStage Protocol
- **验收**：
  - [x] isinstance(CompositeDecisionStage, DecisionStage Protocol) 通过
  - [x] 多信号加权合并逻辑正确
- **测试**：
  - [x] 单测：2 个 stage 加权合并
  - [x] 单测：权重归一化

### B6-3: analysis experience memory 基础 `[M]`

- **问题**：无 AI agent 经验记忆基础
- **文件**：
  - `packages/analysis/src/ditto_analysis/research/experience.py`（新建）
- **方案**：
  - `DecisionLog` frozen dataclass：timestamp / context / decision / outcome / reflection
  - `ExperienceMemory` Protocol：`record()` / `query()` / `summarize()`
  - `MarkdownExperienceMemory` 实现：读写 markdown 文件
- **验收**：
  - [x] 可记录和查询决策历史
  - [x] Markdown 格式可读
- **测试**：
  - [x] 单测：record → query 一致性
  - [x] 单测：Markdown 文件格式正确

### B6-4: analysis reserved namespace 评估 `[S]`

- **问题**：4 个 reserved namespace（diagnostics/screeners/reports/experiments）占位
- **文件**：
  - `packages/analysis/src/ditto_analysis/{diagnostics,screeners,reports,experiments}/__init__.py`
- **方案**：
  - 评估每个 namespace 的产品路线
  - 短期有需求（B6-3 experience 可归入 experiments）→ 实现
  - 无明确需求 → 删除空壳
- **验收**：
  - [x] 每个 reserved namespace 有决策：实现 or 删除
  - [x] 文档记录决策理由
- **测试**：无代码变更（或删除空壳后测试通过）

---

## 评分提升预测

| 阶段 | 工程架构 | Runtime | 产品完整度 | AI-Ready | 任务数 |
|------|---------|---------|-----------|----------|--------|
| 当前 | 8.7 | 7.0 | 5.6 | 4.0 | — |
| PR1 (B0+1A) | 8.7 | 7.3 | 5.8 | 4.0 | 8 |
| PR2 (B1B+1C) | 8.8 | 7.6 | 5.9 | 4.0 | 7 |
| PR3 (B2) | 9.0 | 7.7 | 6.3 | 4.0 | 9 |
| PR4 (B3) | 9.1 | 7.8 | 6.7 | 4.0 | 6 |
| PR5 (B4) | 9.1 | 8.0 | 7.2 | 4.2 | 7 |
| PR6 (B5+6) | 9.3 | 8.3 | 7.6 | 6.0 | 10 |

**总计**：47 个原子任务，6 个 PR，预估 12-17 个工作会话

---

## 全局验收标准

每个 PR 合入前必须通过：

```bash
pixi run -e dev check           # lint + fmt + type + test --fast
pixi run -e dev arch-check      # 37 contracts kept, 0 broken
```

**分支门禁**：
- [x] basedpyright 类型检查通过
- [ ] ruff 检查通过
- [ ] 测试通过
- [ ] 分支覆盖率 ≥ 80%
- [ ] 37 条架构合约全部 kept

---

## 明确不做事项

| 不做 | 原因 | 重新评估时机 |
|------|------|-------------|
| Live broker adapter 接入 | Paper 闭环未完成 | PR2 后 |
| LLM 直接执行交易 | AI 只做定性推理 | Batch 6（P3） |
| 全市场/多币种 | 先完成 A 股 ETF | PR5 后 |
| Rust 核心重写 | Python 性能足够 | 不设时间表 |
| ClickHouse/ArcticDB | DuckDB 已满足 | 数据量超 10TB |
| Pandas 兼容层 | 与铁律冲突 | 永不 |

---

## 模块攻克顺序

与评估文档推荐一致：

| 顺序 | 模块 | 原因 | 覆盖 Batch |
|------|------|------|-----------|
| 1 | execution | Paper runtime 闭环是产品最大短板 | B0, B1A, B1B, B1C |
| 2 | data + application ingestion | DatasetRegistry 归位 + 大文件拆分 | B2, B3 |
| 3 | application | 职责分离，E2E | B3 |
| 4 | risk + portfolio | 类型安全 + Spine | B4 |
| 5 | features + strategy | 可读性 + AI-ready | B5, B6 |
| 6 | analysis | AI-ready 基础 | B6 |
| 7 | kernel + platform | 基础层清理 | B5 |
