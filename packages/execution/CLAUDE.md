# Execution 层架构规范

## 定位

Execution 是**交易执行平面**，负责：
- 订单管理与成交处理（OMS）
- 券商网关抽象（Broker Gateway）
- 执行现实模拟（费用、滑点、交收）
- 交易审计与对账
- 交易持久化（SQLite storage）

**核心原则**：
- 执行层是交易系统的最后一道门，不依赖回测或分析
- Broker Gateway 是与外部券商系统的唯一接口
- 当前后端攻坚范围只定义并验证 `BrokerGateway` Protocol、事件语义、审计/对账 contract 和 conformance fixtures；不实现真实券商 adapter、认证、SDK client 或生产下单连接
- 执行现实模拟（reality/）封装了 A 股交易规则（T+1、涨跌停、费用等）
- 审计记录所有交易行为，不可篡改

## 允许依赖

```
ditto_execution → ditto_kernel ✅
ditto_execution → ditto_portfolio ✅
ditto_execution → ditto_platform ✅
```

外部依赖：orjson

## 禁止依赖

```
ditto_execution → ditto_data ❌
ditto_execution → ditto_features ❌
ditto_execution → ditto_strategy ❌
ditto_execution → ditto_backtest ❌
ditto_execution → ditto_analysis ❌
ditto_execution → ditto_application ❌
ditto_execution → ditto_apps ❌
```

## 内部目录职责

```
ditto_execution/
├── broker/               # 券商网关抽象
│   ├── contracts.py      # BrokerGateway Protocol
│   ├── runtime.py        # PaperRuntimeKernel（继承 BaseRuntimeKernel，RealtimeClock + SimpleEventBus）
│   └── gateways/         # 网关实现；真实券商 adapter 暂保留，不在当前范围
│       └── paper.py      # PaperBrokerGateway（冒烟测试级别模拟网关）
├── orders/               # 订单管理（OMS Lite — FSM + Journal + 双 ID）
│   ├── ids.py            # ClientOrderId / BrokerOrderId 值对象
│   ├── status.py         # OrderStatus(StrEnum) — 7 状态 + is_terminal
│   ├── trigger.py        # OrderTrigger(StrEnum) — 5 触发器
│   ├── model.py          # Order(frozen dataclass) + OrderType + OrderSide
│   ├── event.py          # OrderEvent(frozen) — 状态变更事件
│   ├── fsm.py            # FSM 转换表 + transition() 纯函数
│   ├── ticket.py         # OrderTicket(frozen) — 集成 FSM 状态转换
│   ├── journal.py        # OrderEventJournal Protocol + InMemoryOrderEventJournal
│   ├── book.py           # OrderBook(mutable) + OrderBookReadOnly
│   └── store.py          # 订单存储接口（Protocol placeholder）
├── fills/                # 成交处理
│   ├── store.py          # 成交存储接口
│   └── outcomes.py       # 成交结果
├── reality/              # 执行现实模拟
│   ├── __init__.py       # re-export（AShareFeeModel / SimpleFeeModel）
│   ├── fee.py            # 费用计算（AShareFeeModel / SimpleFeeModel）
│   └── ...
├── audit/                # 交易审计
│   ├── models.py         # 审计模型
│   └── execution_audit_service.py  # 审计服务
├── storage/              # 持久化
│   ├── deps.py           # 依赖注入（ExecutionReaders / ExecutionWriters）
│   └── sqlite/
│       ├── __init__.py
│       ├── trade/        # 交易数据存储
│       │   ├── service.py    # 读写服务
│       │   ├── fills.py      # 成交存储
│       │   ├── intents.py    # 意图存储
│       │   ├── positions.py  # 持仓快照存储
│       │   └── _sql.py       # SQL 工具（allowlists / WHERE 构建）
│       └── reconciliation.py # 对账 repair workflow 状态存储
├── di/                   # 依赖注入 Provider
│   ├── _factory.py       # Execution Provider 工厂
│   └── storage.py        # 存储层 DI Provider
├── reconciliation/       # 对账（reconcile()/plan_repair() 纯函数 + executor orchestration）
├── brokerage.py          # 券商模拟入口
├── storage.py            # 存储入口
├── planner.py            # 执行计划器
├── _planner_types.py     # 计划器内部类型
├── cost_estimate.py      # 成本估算
├── market_precheck.py    # 市场预检
├── quantity_rounding.py  # 数量取整
├── target_diff.py        # 目标差分计算
├── trade_builder.py      # 交易构建器
├── targets.py            # 目标持仓计算
├── rules.py              # execution-owned 规则提供器；交易规则类型来自 ditto_kernel.trading
├── models.py             # 交易模型
├── contracts.py          # 执行契约
├── errors.py             # 错误定义
└── events.py             # 领域事件
```

## 测试位置

```
packages/execution/tests/
├── unit/
│   ├── test_order_events_unit.py
│   ├── broker/
│   │   ├── test_contracts_unit.py
│   │   └── test_gateway_conformance_unit.py
│   ├── orders/                # OMS Lite 测试
│   │   ├── test_ids_unit.py
│   │   ├── test_fsm_unit.py
│   │   ├── test_journal_unit.py
│   │   ├── test_ticket_unit.py
│   │   ├── test_book_unit.py
│   │   └── test_orders_exports_unit.py
│   ├── execution_legacy/    # 遗留执行测试
│   │   ├── test_trade_builder_unit.py
│   │   ├── test_fill_model_unit.py
│   │   ├── test_fills_unit.py
│   │   ├── test_settlement_unit.py
│   │   ├── test_planner_unit.py
│   │   ├── test_brokerage_unit.py
│   │   ├── test_slippage_unit.py
│   │   ├── test_fee_model_unit.py
│   │   ├── test_rules_unit.py
│   │   └── test_brokerage_helpers_unit.py
│   ├── trade/
│   │   └── test_trade_service_unit.py
│   └── audit/
│       ├── test_audit_trade_fill_unit.py
│       └── test_execution_audit_service_unit.py
```

## 典型导入示例

```python
# 券商网关
from ditto_execution.broker.contracts import BrokerGateway

# 执行计划
from ditto_execution.planner import ExecutionPlanner
from ditto_execution.trade_builder import TradeBuilder

# 执行现实
from ditto_execution.reality.fee import calculate_commission
from ditto_execution.reality.slippage import SlippageModel

# 审计
from ditto_execution.audit.execution_audit_service import ExecutionAuditService
```

## Known Gaps / Planned Work

- **~~OMS Lite（EXEC-P1-01）~~**：✅ 已实现（Phase 2）。`orders/` 包含完整 FSM、Journal、双 ID、OrderBook、OrderTicket。
- **~~Broker Gateways（EXEC-P1-02）~~**：✅ 已实现（PaperBrokerGateway）。`broker/gateways/paper.py` 提供冒烟测试级别的模拟网关，支持 order submit/fill/account/connect。`BrokerGateway` Protocol 定义在 `broker/contracts.py`。
- **~~Reconciliation（EXEC-P1-03）~~**：✅ 已实现。`reconciliation/` 导出 `reconcile()` 纯函数（无副作用）+ `plan_repair()` 纯函数（无副作用 repair action planning）+ `RepairActionExecutor`（审批状态门禁、handler dispatch、执行结果落库、audit sink 端口）+ `ReconciliationReport` / `ReconciliationDiff` / `RepairPlan` / `RepairActionRecord` / `RepairExecutionResult` 类型定义。状态字段使用 `Literal["matched", "mismatch", "pending"]` 类型；`SQLiteRepairWorkflowStore` 持久化 action 审批/执行状态并阻止未审批写操作执行；当前 handler 覆盖 read-only broker refresh、审批后 broker fill import（通过窄端口解析完整 `FillRecord` 并幂等写入本地 fill store）、审批后 local fill amendment（通过 `replace_fill()` 只替换已存在本地 fill）和审批后 order-status review/update（通过 `trade_intents.status` 的窄端口带 transition guard 更新本地状态）；`ExecutionRepairAuditSink` 可把执行结果写入共享 `execution_audit`，并保留 fill 相关 action 的 `fill_id`。后续重点转向 broker Protocol/conformance、事件 contract 和 protocol-level seams，真实券商接入实现保持 deferred。
- **Audit Spine（EXEC-P1-04）**：`execution_audit` 已有顶层 `correlation_id` / `order_id` / `fill_id` 关联键和 `query_timeline()` 读模型；`account_snapshots` 已持久化 run-scoped 账户快照；`actual_positions` 已持久化 run-scoped 持仓快照并提供旧表迁移；`broker_events` 已持久化 run-scoped 标准化券商事件；`STANDARD_BROKER_EVENT_TYPES` / `require_standard_broker_event_type(...)` 定义并校验 recording wrapper 可写入的标准 broker event taxonomy；`BrokerEventRecordingGateway` 可在不修改 `BrokerGateway` Protocol 的情况下把 connect/order_ack/fill/fill_query_error/cancel/reject/account_update 写入 normalized broker events，`get_account()` 会写入含 cash/NAV/exposure/position_count 的 deterministic `account_update` snapshot，并在保存前 fail closed 校验 event type，支持可选 broker-order ID lookup，也能在 wrapper 重建后仅从同 run/broker/order 的 recorded `order_ack` 事件恢复 broker-order ID，并在可选 lookup 返回 `None` 或 blank/whitespace 值时回退到 same-broker recorded ack recovery，blank/whitespace `OrderTicket.broker_order_id` 也会先按 missing 处理再进入 lookup/recorded-ack recovery，重复 `order_ack` callbacks 会保留首条 canonical ack ID 并用 deterministic `attempt-N` 后缀保存后续尝试，且 recorded-ack recovery 会跳过历史/外部写入的 blank/whitespace 顶层/payload broker-order ID 继续寻找有效 ack，非 ack broker events 或同 run/order 的其他 broker ack 即使携带 broker-order link 也不会成为 reconnect 恢复权威，以 event-time-scoped connect IDs 保留多次 connect/reconnect lifecycle 证据，并在相同 event_time 碰撞时追加 deterministic attempt suffix，以 attempt-scoped cancel/reject/fill_query_error IDs 保留重复响应尝试并避免相同 event_time 响应折叠，以 order-scoped、cumulative/leaves-progress-aware 且 economics/link-revision-aware 的稳定 fill event ID 支撑 replay 幂等、避免跨订单 fill ID 覆盖、保留同一 fill ID 的后续累计进度，并保存同一进度下价格/费用/滑点或 broker-order link 修正证据；提交后的立即 fill 查询失败会被记录为 `fill_query_error`，不会把已成功提交的 `OrderTicket` 伪装成提交失败，直接 `query_fills(...)` 失败也会记录错误后继续向调用方抛出异常，`cancel_order(...)` / `reject_order(...)` 失败会先记录 `failed` broker event 再原样重抛；SQLite `broker_events` 对重复 `event_id` 保留首次 callback 的 event_time/status/payload，同时允许后续 duplicate 补齐先前为空或空白的顶层 link key（例如乱序 fill 后 ack 才知道的 `broker_order_id`）；`query_operating_timeline()` 已可在同一 SQLite 存储中合并 `execution_audit`、`order_events`、run-scoped `actual_positions`、`account_snapshots` 与 `broker_events`，并按 broker event_time 排列 late replayed callbacks，同时在 payload 中保留本地写入 `created_at`。剩余缺口是更长 callback ordering/replay sequence conformance；不包含真实券商 adapter 实现。
- **Planner Decomposition（EXEC-P2-01）**：`planner.py` 约 530 LOC 混合 target diff / market precheck / rounding / cost 逻辑，计划拆分为聚焦模块。
- **A-Share Rules（EXEC-P2-02）**：规则行为散布在 execution、backtest、kernel 中，需要跨包协调收拢。

## 常用验证命令

```bash
pixi run -e dev pytest packages/execution/tests/unit -q
pixi run -e dev type packages/execution/src
pixi run -e dev arch-check
```
