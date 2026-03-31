# Hybrid 平面架构 v2 — 批判性审查

**日期**: 2026-03-31
**审查对象**: `docs/plans/2026-03-30-architecture-hybrid-plane-design.md`
**审查范围**: 设计文档 + Phase 0/1 实际落地状态 + 与旧设计（03-26）的差异

---

## 0. Phase 0/1 落地审计

### 已完成

| 项目 | 状态 | 说明 |
|------|------|------|
| Phase -1a: Kernel CLAUDE.md 准入标准扩展 | ✅ 完成 | Protocol/薄实现标准已写入 |
| Phase -1b: architecture.md Server→Port 术语修正 | ✅ 完成 |
| Phase 0: Kernel 扩展（4 模块 17 符号） | ✅ 完成 | clock/provider/pipeline/events + 单元测试 |
| Phase 1a: datahub/query/ 子模块 | ✅ 完成 | MetadataQuerist + MarketQuerist |
| Phase 1b: BacktestProvider | ✅ 完成 | 组合 MarketService + MetadataService + DerivedQueryService |

### 未完成 / 偏差

| 项目 | 计划 | 实际 | 严重程度 |
|------|------|------|---------|
| Phase 1c: DataFeed 改造 | 改 ParquetDataFeed 消费 DataProvider | 新增 ProviderBackedDataFeed 并存，旧路径未清理 | 中 |
| Phase 1d: LiveProvider | 提取公共基类/mixin + 缓存层 | 与 BacktestProvider **逐行复制**，零差异 | 中 |
| Core 依赖收敛 | Phase 1 后 `core → kernel only` | CLAUDE.md 仍声明 `core → kernel, datahub, infra` | 高 |
| DI 注册 | port/registry/ 新增 Provider 注册 | 未验证是否完成 | 低 |
| Golden test | 回测流程行为不变验证 | 无 golden test 证据 | 中 |
| architecture.md 同步 | 反映 Protocol 模式变更 | 未更新 | 低 |

---

## 1. [Blocker] Kernel Protocol 层类型安全为零

**现状**: 四大 Protocol 在 Kernel 层全部退化为 `Any`

| Protocol | 类型安全状况 |
|----------|-------------|
| `DataProvider` | 返回 `AnyFrame = Any` |
| `Stage` | `process(data: Any) -> Any` |
| `Pipeline` | 内部 `Any` 中转 |
| `EventBus` | `payload: dict[str, Any]` |
| `Context.metadata` | `dict[str, Any]` |

**根因**: Kernel 零外部依赖红线禁止引入 polars，导致 DataProvider 无法返回 `pl.DataFrame`。为绕过此限制引入 `AnyFrame = Any`，但这是最差折中 — 两边好处都没捞到。

**Pipeline 变成无类型函数调用链**: `Stage.process(data: Any) -> Any` 与直接调用 `f(result)` 在类型系统层面无区别。Pipeline 的核心价值（类型安全的 Stage 间契约）完全丧失。

**决定**: Pipeline 抽象从 Kernel 移出，归属到实际使用模块（engine/analytics），在那里可以直接用 `pl.DataFrame` 强类型。Kernel 只保留 Clock、DataProvider（Protocol 定义）、EventBus 这类真正跨层共享的抽象。Pipeline 作为引擎内部编排模式，无需跨层复用。

**待办**:
- [ ] 将 `pipeline.py`（Context、Stage、Pipeline）从 `ditto_kernel` 移至 `ditto_core`（或 Phase 2 后的 `ditto_engine`）
- [ ] Context/Stage/Pipeline 可以直接引用 `pl.DataFrame`
- [ ] Stage 间数据契约（AlphaOutput、PortfolioOutput 等）用 frozen dataclass + pl.DataFrame 字段强类型化
- [ ] Kernel public symbols 从 17 降至 14

---

## 2. [Blocker] Engine Pipeline 无法表达交易引擎控制流

**现状**: `Pipeline.execute()` 是线性 `for stage in stages: result = stage.process(result, ctx)`

**交易引擎实际需求**:
- **条件分支**: 风控 gate 可以阻断后续 Stage
- **状态突变**: accounting（position、cash、order book）是可变状态，不是 input→output 纯函数
- **反馈回路**: fill → 更新 position → 重新检查风控
- **重试/补偿**: 订单提交失败后的重试逻辑

**结论**: TradingPipeline 不应该是 `Pipeline` 的实例。它需要一个**编排器**（Orchestrator），内部使用 Stage 但有自己的控制流逻辑。Kernel 中的线性 `Pipeline` 更适合 Analytics 的纯函数计算链。

**待办**:
- [ ] 设计 `TradingOrchestrator`（Phase 2），替代线性 Pipeline
- [ ] 明确 Stage 在 Orchestrator 中的角色（可被 gate 拦截、可访问共享状态）
- [ ] 考虑状态管理模型（见 Issue #6）

---

## 3. [Blocker] 五大支柱缺少"状态管理"

**现状**: 五大支柱 = Clock + DataProvider + Stage/Pipeline + DomainEvent + 双通道数据流

**分析结论**（2026-03-31）: **不需要新增顶层"状态管理支柱"抽象。**

现有代码已有清晰且工作良好的状态管理模式：

```
Brokerage (state owner)
    ├── Account (可变: positions dict + CashBook 引用替换)
    │       └── get_view() → AccountView (frozen 只读快照)
    ├── place_order(order) → OrderBook 变更
    └── process_pending(input) → Account.apply_fill() → 新 AccountView
```

**模式特征**:
1. **状态所有者单一** — Brokerage 拥有 Account，其他组件只拿 AccountView
2. **读写分离彻底** — AccountView frozen + MappingProxyType 包装 positions
3. **变更路径唯一** — 只通过 Brokerage.place_order() + process_pending()
4. **每日循环是命令式** — "读状态快照 → 决策 → 变更状态 → 读新快照"

**结论**: 状态管理是 Engine 平面的**内部关注点**，不是跨层共享抽象。
现有 Brokerage + Account/AccountView 模式直接映射到 TradingOrchestrator：
Orchestrator 持有 Brokerage，每日生成 AccountView 注入各 Stage。

**但需要补充**:
1. Brokerage Protocol — Engine 内部定义，回测/实盘各有实现（Phase 2）
2. 状态持久化 — Account 序列化/反序列化，用于回测中断恢复和实盘重启（Phase 3+）

**待办**:
- [x] 分析现有状态管理模式（已完成 — Brokerage owner 模式成立）
- [ ] Phase 2 中定义 Brokerage Protocol（Engine 内部）
- [ ] Phase 3+ 中设计状态持久化

---

## 4. [Major] BacktestProvider / LiveProvider 代码完全重复

**现状**: `datahub/query/provider.py` 中两个类 80 行 × 2，逐行复制，零差异。

**根因**: 缓存不是 Provider 层的职责。回测/实盘差异不在数据获取，在编排行为（Clock、Pipeline 控制流）。

**决定**: 现阶段只需要一个 `DataProviderAdapter`。回测/实盘差异通过构造参数（是否启用缓存）而非类继承表达。

**待办**:
- [ ] 合并为单一 `DataProviderAdapter` 类
- [ ] 如需缓存，用装饰器或 composition，不继承

---

## 5. [Major] Data 平面 ≈ datahub 改名？子域归属未审计

**现状**: datahub 有 477 个 .py 文件，设计文档只说"直接迁移"，未讨论：

| datahub 中的模块 | 应归属的平面 | 设计文档是否覆盖 |
|-----------------|------------|----------------|
| `runtime/`（SQL engine, freeze manager） | data? infra? | 未提及 |
| `helpers/`（adjustment, PIT） | data? | 未提及 |
| `services/strategy_service.py` | engine | 未提及 |
| `services/trading_service.py` | engine | 未提及 |
| `models/portfolio.py` | engine | 未提及 |
| `models/strategy*.py` | engine | 未提及 |

**待办**:
- [ ] Phase 2 前对 datahub 做子域归属审计 — 逐模块标记目标平面
- [ ] 文档化迁移清单

---

## 6. [Major] Phase 2 "core → engine 改名"风险被低估

**现状**: 标为"中风险 + 纯机械操作 + 1 PR"

**实际影响范围**:
- `ditto_core` 被 `ditto_port`、`ditto_datahub` 广泛引用
- 改名 = 全库 import 路径变更
- 改名后 quality → datahub、expression → analytics 还要迁走 = **改两次名**

**决定**: 先完成 core 内部子域迁移（quality → datahub、expression → analytics），等 core 只剩交易引擎代码时再改名 engine。

**待办**:
- [ ] 调整 Phase 2 顺序：先迁子域，后改名
- [ ] Phase 2 拆为 2a（子域迁出）和 2b（改名 engine）

---

## 7. [Major] 实时流 / 实盘流程的抽象预留不足

**现状**: 设计以回测为主要场景，Pipeline 是批量处理模型。对以下场景缺乏抽象：

| 场景 | 当前设计 | 缺失 |
|------|---------|------|
| 实时行情推送 | DataProvider.get_bars() 是 pull 模型 | 缺少 push/streaming 模型 |
| 实时因子计算 | Analytics 是批量 DataFrame | 缺少增量/流式计算抽象 |
| 实盘事件驱动 | Pipeline.execute() 是同步单次 | 缺少事件循环/长驻进程模型 |
| 订单状态异步回调 | DomainEvent 同步分发 | 缺少异步事件处理（券商回报） |
| 心跳/健康检查 | 无 | 实盘基础设施 |

**虽然当前不实现，但抽象层需要预留扩展点**：
- `Clock` 需要支持 `RealtimeClock` 的高精度模式（毫秒级）
- `DataProvider` 需要考虑 `subscribe(stream)` 模式
- `EventBus` 需要考虑异步 handler 支持
- Stage 需要考虑有状态/长驻 Stage（如实时风控监控）

**待办**:
- [ ] 讨论并设计实时流的抽象扩展点
- [ ] 在 Clock、DataProvider、EventBus 协议中预留可选的 streaming 方法
- [ ] 考虑 Engine 平面是否需要 `LiveOrchestrator` 作为 `TradingOrchestrator` 的变体

---

## 8. [Minor] 其他设计细节

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 8a | `BarQuery` 用 `str` 而非 `date` | 格式验证推迟到实现侧 | 改为 `date`（标准库，不违反 Kernel 约束） |
| 8b | `Stage.name` 是 `@property` | 展示逻辑混入行为协议 | 移除，用 `__class__.__name__` 或独立元数据 |
| 8c | `SimpleEventBus.publish()` handler 异常传播 | 一个 handler 失败阻断后续 handler | 至少提供隔离模式配置 |
| 8d | Pipeline 错误处理策略 | Stage 失败时 abort/skip/retry 未定义 | 需明确策略 |
| 8e | Pipeline 执行监控 | 无 trace/debug 机制 | 考虑 Context 中注入 tracer |
| 8f | DataProvider 无 PIT 支持 | BarQuery 缺 `as_of_date` | 回测场景必需，需补充 |
| 8g | 状态持久化与恢复 | 回测中断/实盘重启无恢复机制 | 需设计 checkpoint 抽象 |

---

## 9. 总结与优先级

### 必须在 Phase 2 之前解决

1. **Pipeline 从 Kernel 移出** → 强类型化（Issue #1）
2. **合并 BacktestProvider/LiveProvider**（Issue #4）
3. **TradingOrchestrator 设计**（Issue #2）— 状态管理已分析，Brokerage owner 模式成立
4. **状态管理** — 无需新增顶层抽象，补充 Brokerage Protocol 即可（Issue #3）
5. **datahub 子域归属审计**（Issue #5）

### 已决策

6. **实时流抽象预留**（Issue #7）— **不改现有协议，通过 Protocol 继承 + 实现扩展演进**

**扩展策略**（2026-03-31 决策）：

| 协议 | 当前 | 未来扩展方式 | 时机 |
|------|------|-------------|------|
| `DataProvider` | pull-only `get_*()` | 新建 `StreamableDataProvider(Protocol)` 继承 + 扩展 | broker 对接开始时 |
| `Clock` | 秒级 `RealtimeClock` | `now()` 改用 `datetime.now(tz=UTC)` 提高精度 | Phase 2 改名时顺手修 |
| `EventBus` | 同步 `SimpleEventBus` | 新增 `AsyncEventBus` 并存 | 异步事件需求出现时 |
| `Stage` | 引擎自定义（移出 Kernel 后） | 有状态长驻 Stage 作为 Engine 内部概念 | 实盘编排器设计时 |

**原则**：Python Protocol 支持结构子类型，实现类比 Protocol 多方法不违规。Kernel 只冻结回测所需最小协议，实盘通过"Protocol 继承 + 实现扩展"演进，不回头改已冻结接口。

### 需要讨论后决策

7. **Phase 2 顺序调整**（Issue #6）

### 可以在后续 Phase 处理

8. Minor 细节（Issue #8）

---

## 10. 与旧设计（03-26）的演进对比

| 维度 | 03-26 纯 DDD | 03-30 Hybrid v2 | 本次审查建议 |
|------|-------------|----------------|-------------|
| Kernel 范围 | 极小类型仓库 | 类型 + Protocol + 薄实现 | **Pipeline 移出**，只留跨层真正的抽象 |
| Pipeline 归属 | 无 | Kernel（跨层复用） | **引擎内部**（强类型） |
| Engine 编排 | Pipeline 链 | Pipeline 链 | **Orchestrator**（支持条件分支和状态突变） |
| 状态管理 | 未涉及 | 未涉及 | **Engine 内部 Brokerage owner 模式**，无需顶层抽象 |
| 实时流 | 未涉及 | 未涉及 | **协议预留扩展点** |
| DataProvider | Kernel 禁止 | Kernel Protocol + AnyFrame | 保留在 Kernel，但 AnyFrame 需要重新审视 |
