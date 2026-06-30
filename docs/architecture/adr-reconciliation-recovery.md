# ADR: Reconciliation Recovery Policy

**状态**: Accepted, updated with pure repair planning, persisted workflow state, executor orchestration, approved fill-import handling, approved local-fill amendment handling, approved order-status review handling, persisted repair-execution audit, normalized broker-event storage, broker-event recording gateway, and operating timeline aggregation
**日期**: 2026-05-18；更新: 2026-06-01
**上下文**: `packages/execution/src/ditto_execution/reconciliation/`

## 背景

执行对账（reconciliation）是将期望状态（如策略信号推导的目标持仓）与实际状态（如券商回报的实际持仓）进行比对的过程。当检测到差异时，系统需要决定如何处理：是自动修复、人工介入，还是仅记录告警。

在量化交易系统中，自动修复引入的风险较高（错误修复可能导致更大的偏离），而检测逻辑本身是确定性且无副作用的。因此需要明确区分"检测"与"恢复"两个关注点。

## 决策

对账检测模块仅负责 **检测** 期望与实际之间的差异。
它 **不会** 自动修复或更新任何状态。

恢复（repair）分为四层：

1. `plan_repair()`：纯函数，把 `ReconciliationReport.diffs` 转换为 typed repair actions。
2. `SQLiteRepairWorkflowStore`：持久化 action、审批状态和执行记录，不直接修复交易状态。
3. `RepairActionExecutor`：消费 `ready` / `approved` action，执行状态门禁、handler dispatch、执行结果落库和可选 audit sink。
4. Repair handlers：面向具体动作的执行器。当前默认实现包含 read-only `BrokerRefreshRepairHandler`、审批后写入本地成交的 `ImportBrokerFillRepairHandler`、审批后替换本地成交的 `AmendLocalFillRepairHandler`，以及审批后更新本地订单状态的 `ReviewOrderStatusRepairHandler`；其他 mutating handler 仍需显式实现和注入。

当前实现第 1、2、3 层，以及 read-only broker refresh handler、审批后 broker-fill import handler、审批后 local-fill amendment handler 和审批后 order-status review handler。它们定义恢复语义、审批状态和执行编排；默认仍不会绕过审批修改交易状态。

这意味着：
- `reconcile()` 是纯函数，无副作用
- 输出 `ReconciliationReport` 仅描述"发生了什么偏差"
- `plan_repair()` 也是纯函数，无副作用
- `SQLiteRepairWorkflowStore` 给 action 分配确定性 ID，并保存 `ready` / `pending_review` / `approved` / `rejected` / `executed` 状态
- 读操作类动作（如 broker refresh）可进入 `ready` 状态，并可由 `RepairActionExecutor` 通过 `BrokerRefreshRepairHandler` 查询 broker fills 后记录为 executed
- 写操作类动作（如导入额外成交、修正本地 fill、调整 order status）默认标记为 `requires_manual_review=True`
- 已审批的 broker-fill import action 可由 `ImportBrokerFillRepairHandler` 通过窄端口解析完整 `FillRecord`，幂等写入本地 fill store，并在 broker/source 不可解析时保持 action 可重试
- 已审批的 local-fill amendment action 可由 `AmendLocalFillRepairHandler` 通过 `FillAmendmentSource` 解析完整替换记录，并通过 `LocalFillRepairPort.replace_fill()` 只替换已存在的本地 fill；本地 fill/source 缺失时保持 action 可重试
- 已审批的 order-status review action 可由 `ReviewOrderStatusRepairHandler` 通过 `OrderStatusReviewSource` 解析已复核状态，并通过 `LocalOrderStatusRepairPort.update_order_status()` 带乐观保护地更新本地状态；本地订单/source 缺失或并发状态冲突时保持 action 可重试
- 未审批的写操作不会被 executor dispatch；被拒绝的 action 也不会执行
- 写操作需要调用方显式注入 action handler，避免 reconciliation 包隐式绑定某个存储或 broker mutation 语义
- `ExecutionRepairAuditSink` 可将 `RepairActionExecutor` 的 `RepairExecutionResult` 映射为 `RepairExecutionPayload`，并以 `repair_execution` 记录写入共享 `execution_audit`；fill 相关 repair 会保留 `fill_id`
- `execution_audit` 暴露顶层 `correlation_id` / `order_id` / `fill_id` link keys，并提供 `query_timeline(...)` 读模型查询 pre-trade、fill 和 repair audit rows
- `account_snapshots` 持久化 run-scoped 账户快照；`actual_positions` 持久化 run-scoped 持仓快照并通过 `(run_id, strategy_id, instrument_id, snapshot_date)` 保持业务唯一性；`broker_events` 持久化 run-scoped 标准化券商网关事件；`BrokerEventRecordingGateway` 可在不修改 `BrokerGateway` 协议的情况下记录 connect/order_ack/fill/fill_query_error/cancel/reject 事件，并通过可选 lookup 或同 run/broker/order 的 recorded `order_ack` 事件把 broker-order ID 写入顶层列和 payload，且 blank/whitespace ticket ack ID 会先按 missing 处理再进入 recovery；重复 `order_ack` callbacks 对同 run/order/status 保留首条 canonical event ID，并用 deterministic `attempt-N` 后缀保存后续回调证据；非 ack broker events 以及同 run/order 的其他 broker ack 可用于审计和查询 link key，但不会作为 reconnect broker-order ID 恢复权威；connect/reconnect 与 cancel/reject/fill_query_error 响应事件均使用 event-time-scoped attempt ID 保留重复尝试证据，且同一 `event_time` 碰撞时追加 deterministic `attempt-N` 后缀而不是折叠；SQLite `broker_events` 对重复 `event_id` 保留首次 callback 的 event_time/status/payload，同时允许后续 duplicate 补齐先前为空或空白的顶层 link key；`ExecutionAuditService.query_operating_timeline(...)` 在同一 SQLite 存储中合并 audit rows、append-only `order_events`、run-scoped `actual_positions`、`account_snapshots` 和 `broker_events`，并按 broker `event_time` 排列 late replayed callbacks，同时在 payload 中保留本地写入 `created_at`

## 后果

**正面**：
- 对账逻辑保持简单、可测试（纯函数，无副作用）
- 恢复策略可以独立演化，不影响检测逻辑
- repair action 为 executor、审计和人工审批提供统一语言
- 审批状态和执行结果已有 SQLite 持久化主干，可跨进程恢复
- executor 已有状态门禁、handler dispatch 和 audit sink 端口
- repair execution 已接入共享 `execution_audit`，不再停留在 fake sink / 测试桩层面，且已有 order/fill/correlation 维度的 audit timeline 查询入口
- operating timeline 已能把 audit rows、order journal events、run-scoped 实际持仓快照、账户快照和标准化 broker events 放到同一查询结果里，便于对账和人工排查；late replayed broker callbacks 按 broker event_time 排序，同时在 payload 中保留本地写入 `created_at`
- broker-event recording 已通过 wrapper 进入 `BrokerGateway` conformance，不需要把审计写入职责塞进具体 broker adapter 协议；connect/reconnect lifecycle event 使用 event-time-scoped ID 保留多次连接尝试证据，且同一 event_time 碰撞不会折叠；重复 `order_ack` 回调现在保留首条 canonical ack ID，并用 deterministic attempt suffix 保存后续回调；wrapper 重建后仅可从同 broker 的 recorded `order_ack` 事件恢复 broker-order ID 并关联 replayed fill/cancel callbacks，即使可选外层 lookup seam 暂时返回 `None` 或 blank/whitespace 值也会回退到 same-broker recorded ack，blank/whitespace `OrderTicket.broker_order_id` 也会先按 missing 处理而不是进入缓存，recorded-ack recovery 会跳过历史/外部写入的 blank/whitespace 顶层/payload broker-order ID 继续寻找有效 ack，且非 ack broker events 或同 run/order 的其他 broker ack 上的 broker-order link 不会污染恢复；重复 fill replay 可通过 order-scoped、cumulative/leaves-progress-aware 且 economics/link-revision-aware 的稳定 fill event ID 幂等落库，既不会因为不同订单复用同一个 broker fill ID 而互相覆盖，也不会丢失同一 fill ID 的后续累计进度或同一进度下的价格/费用/滑点或 broker-order link 修正证据；cancel/reject/fill_query_error response 使用 collision-safe attempt-scoped ID 保留重复响应，且 cancel/reject transport exceptions 会先记录 failed broker event 再向调用方重抛；提交后的立即 fill 查询失败会记录 `fill_query_error` 并保留已成功提交的 `OrderTicket` 语义；直接 `query_fills(...)` 失败也会记录 `fill_query_error` 后继续向调用方抛出异常；broker-order ID 也可由外层 lookup seam 注入
- mutating handlers 已通过端口隔离上下文解析与本地写入，避免 reconciliation 层猜测 `FillRecord` 身份字段
- `TradeService.replace_fill()` / SQLite `FillWriter.replace()` 使用显式 UPDATE，不会在 amendment 场景误插入缺失 fill
- `TradeService.get_order_status()` / `update_order_status()` 让当前本地 order status 修复落到 `trade_intents.status`，同时保留 transition guard
- 调用方仍拥有完全的处理自主权

**负面**：
- 写操作仍依赖调用方提供已复核的 source 数据和合适的 store/broker 端口，reconciliation 包不会自行判断业务真相
- 人工干预场景下，操作员仍需要理解 action 的影响范围

**权衡**：当前阶段以检测准确性、审批安全和可审计恢复编排为优先，只让 broker-fill import、local-fill amendment 和 order-status review 在外层端口解析出完整、已复核的业务事实后执行本地写入；repair execution 已有持久化审计记录，operating timeline 已覆盖 audit rows / order_events / run-scoped actual_positions / account_snapshots / broker_events，broker-event recording 已有 protocol-preserving wrapper、broker-order ID lookup seam、duplicate order_ack attempt evidence、same-broker recorded-ack-only broker-order ID recovery、lookup-miss fallback、recorded-ack blank-link skipping、cross-broker ack contamination guard、dirty non-ack link isolation、blank ticket-ack fallback、distinct connect/reconnect lifecycle IDs、event-time collision-safe lifecycle/response attempt IDs、attempt-scoped cancel/reject/error response IDs、direct fill-query error recording、cancel/reject exception failed-attempt recording、order-scoped/progress-aware/economics/link-revision-aware replay-idempotent fill event ID、submit-time fill-query error recording、duplicate-event late null/blank link-key backfill 和 late-replay event-time timeline ordering，但更长 Protocol 级 callback ordering/replay matrix 仍需继续扩展。真实券商 adapter 实现不在当前范围。

## 参考

- `packages/execution/src/ditto_execution/reconciliation/reconciler.py` — 对账核心逻辑
- `packages/execution/src/ditto_execution/reconciliation/repair.py` — 无副作用 repair planning
- `packages/execution/src/ditto_execution/reconciliation/executor.py` — repair action executor / handler / audit sink 端口
- `packages/execution/src/ditto_execution/reconciliation/types.py` — `ReconciliationReport` / `ReconciliationDiff` / `RepairPlan` / `RepairActionRecord` / `RepairExecutionResult` 类型定义
- `packages/execution/src/ditto_execution/storage/sqlite/reconciliation.py` — repair workflow SQLite 持久化
- `packages/execution/src/ditto_execution/storage/sqlite/trade/broker_events.py` — 标准化 broker event SQLite 存储
- `packages/execution/src/ditto_execution/broker/recording.py` — `BrokerGateway` 标准化事件记录 wrapper
- `packages/execution/src/ditto_execution/audit/repair_execution_sink.py` — repair execution 持久化审计 sink
- `packages/execution/src/ditto_execution/audit/execution_audit_service.py` — 共享 execution audit 表写入服务
