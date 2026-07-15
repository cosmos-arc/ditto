# 综合架构评估报告的严格审视（第二部分：业界对标、专项复核与结论）

> 日期：2026-05-08
> 延续自：`2026-05-08-runtime-architecture-critique-part1.md`
> 审视对象：`docs/reviews/audit/2026-05-07-comprehensive-architecture-evaluation.md`

---

## 5. 业界对标详解（被审视报告遗漏的运行时维度）

### 5.1 NautilusTrader — 单线程事件循环内核

NautilusTrader 的核心不是包结构，而是运行时架构：

- **MessageBus** 是系统中枢，三种模式（Pub/Sub、Point-to-Point、Request/Response）
- **单线程消费**保证确定性事件排序——cache-then-publish 保证策略 handler 执行前数据已在 Cache 中
- **Actor 模型** + **Component FSM**（7 稳定态 + 7 过渡态）
- **BacktestNode / LiveNode 共享 NautilusKernel**——环境差异仅在 adapter 层
- **Crash-only 设计**：不可恢复故障立即终止，状态外部持久化，启动和恢复共享路径

**Ditto 对标差距**：EventBus 是空壳，无 FSM，无 crash-only，无共享运行时。报告引用了 NautilusTrader 但只对标了"模块化"和"backtest/live 统一"的文字描述，没有对标运行时架构。

来源：https://nautilustrader.io/docs/latest/concepts/architecture/

### 5.2 QuantConnect LEAN — 流式分析系统

LEAN 的关键不是 C# vs Python，而是它的核心设计：**流式分析系统（streaming analysis），不是批处理**。

- 回测以快速前进模式模拟实时的逐条数据推送
- 策略代码在回测和实盘间零修改
- 每个 timeslice 触发 26 步处理链，每步是 event-triggered
- Algorithm Framework 五层管道：Universe → Alpha → Portfolio → Risk → Execution
- 每个 Security 对象挂载独立 Reality Model（Fee/Fill/Slippage/BuyingPower/Settlement）

**Ditto 对标差距**：数据加载是全量批处理，step chain 是顺序方法调用不是事件触发，无 Reality Model 抽象（A 股规则硬编码在 planner 中）。

来源：https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine

### 5.3 ArcticDB (Man AHL) — 不可变版本化时序数据库

Man Group（$160B+ AUM）的核心数据架构决策：

- **放弃 ACID 中的 Isolation**——数据科学工作负载不需要 SERIALIZABLE
- **不可变数据结构 + 版本化**——新写入创建新版本，原子符号链接切换
- **时间旅行查询**：`read(symbol, as_of=timestamp)`
- **无服务器**——无 MongoDB、无 Kafka、无 job queue、无锁
- **性能**：从闪存存储读取 40 GB/s，数十亿行/秒

**Ditto 对标差距**：Ditto 的 PIT 是分散约定（shift(1)/knowledge_date/_find_pit），不是架构级版本化。没有时间旅行查询。没有不可变数据结构。

来源：https://www.infoq.com/presentations/arcticdb/

### 5.4 Databento — 微秒级市场数据

Databento 的设计哲学：**极简架构，零外部依赖**。

- 无 Kubernetes、无 Kafka、无 WebSocket、无 protocol buffers
- 裸金属服务器 + multicast + 二进制平面文件 + lock-free queues + BSD sockets
- FPGA SmartNIC 100G 线速无损捕获
- 从 venue handoff 到应用中位延迟 **6.1 微秒**
- PTP 纳秒时间戳嵌入每条消息

**Ditto 对标差距**：HTTP pull → 全量加载 → 内存过滤。延迟单位是秒级（网络请求），不是微秒级。

来源：https://databento.com/blog/worlds-fastest-cloud-ticker-plant

### 5.5 Chronon (Airbnb) — 声明式特征工程

Chronon 的核心突破：**定义一次，online-offline 自动生成**。

- 同一份 Python 定义 → Spark batch job（训练数据）+ Flink streaming job（实时服务）+ KV store serving endpoint
- **自动 PIT correctness**：内部维护 partial aggregates，组合产生不同时间点的特征值
- **10,000+ 特征**通过 Chronon 管理
- 服务层 sub-10ms p99 latency

**Ditto 对标差距**：只有 batch materialization。无 online serving。无声明式定义。无自动 PIT。

来源：https://medium.com/airbnb-engineering/chronon-a-declarative-feature-engineering-framework-b7b8ce796e04

### 5.6 Jane Street — 类型系统驱动的正确性

Jane Street 是全球最大 OCaml 商业用户（500+ 程序员，30M+ 行代码）。

- **类型系统替代测试**：一次大规模重构修改了几乎所有文件，首次在测试环境启动直接运行成功
- **统一语言**：交易系统、研究工具、系统基础设施、硬件设计（Hardcaml DSL）全部 OCaml
- **Crash-only**：编译器保证的正确性比运行时检查更可靠

**Ditto 对标差距**：Ditto 的 `# type: ignore` = 0 是好的，但 Python 的类型系统无法提供 OCaml 级别的编译时保证。`FeeModel` Protocol 用 `order: Any` 就是类型空洞。

来源：https://blog.janestreet.com/ocaml-the-ultimate-refactoring-tool/

---

## 6. 第 8 节专项审核复核

被审视报告的第 8 节（命名、抽象边界与领域划分）按 10/10 理想口径给了 7.4。这个分数比工程综合 8.6 更诚实，但仍有两个问题。

### 6.1 方向正确但不完整

报告正确识别了：

- ✅ Service 后缀过载（44% 实为 Repository）
- ✅ Dataset enum 是 #1 架构债务
- ✅ Reference domain 缺失
- ✅ Composition root 不纯
- ✅ Port 归属偏差
- ✅ 消费者应拥有 port

但遗漏了更基础的运行时缺失：

- ❌ 事件驱动核心（第 8 节完全未提及 EventBus 空壳问题）
- ❌ 统一时间模型（PIT 被放在"数据架构"子维度，不是独立架构维度）
- ❌ 状态恢复机制（crash recovery 完全未提及）
- ❌ 流式数据能力（实时 vs 批处理未作为架构维度评估）
- ❌ Continuous risk（风控是装饰还是架构未讨论）

### 6.2 8.8 过度设计复核：护栏方向对，但评判范围错

8.8 节对每项建议做了"是否过度设计"判定。这个方法论是对的。问题在于：它评判的是包结构层面的建议（reference domain、DataCatalog、port 归属），而不是运行时架构层面的缺失。

把"提炼 reference domain"评为"不过度"是对的。但没有把"补齐事件驱动核心"纳入评判范围——因为第 8 节根本没有识别这个需求。

### 6.3 对 8.4 领域划分的补充

报告提出了独立 reference/market_reference 能力边界。这个建议被审视报告自己质疑为"可能过度设计"，然后在 8.8 节又判定为"不过度"。

我的判断：**方向正确，但优先级应排在事件驱动核心之后。** 原因：

1. 没有事件驱动核心，reference domain 只是被方法调用链串起来的静态数据
2. 没有统一时间模型，reference 的 PIT 查询无法系统保证
3. 没有状态恢复，reference 的缓存状态在 crash 后丢失

正确优先级：事件驱动 → 时间模型 → 状态恢复 → reference domain → DataCatalog

---

## 7. 面 10/10 的真实差距清单

按重要性排序（不是按改造成本排序）：

| 优先级 | 差距 | 对标 | Ditto 现状 | 预估提升 |
|--------|------|------|-----------|---------|
| **P0** | 事件驱动核心 | NautilusTrader MessageBus | EventBus write-only 空壳，零 subscribe | +1.0 |
| **P0** | Backtest/Live 共享运行时 | NautilusTrader Node / LEAN streaming | 0% parity，无 live path | +1.0 |
| **P0** | 状态恢复与 crash-only | NautilusTrader crash-only + ArcticDB 不可变 | 全部 in-memory | +0.5 |
| **P1** | 统一时间模型 | NautilusTrader nanosecond + ArcticDB time-travel | Clock + 分散 PIT 约定 | +0.5 |
| **P1** | 流式数据能力 | Databento microsecond + LEAN streaming | 纯 HTTP batch pull | +0.5 |
| **P1** | Continuous risk | NautilusTrader RiskEngine in submit path | 仅 pre/post-trade | +0.3 |
| **P1** | DataCatalog runtime | ArcticDB 版本化 | Dataset enum + contract only | +0.3 |
| **P2** | Online feature store | Chronon PIT join + online serving | Batch materialization only | +0.3 |
| **P2** | Fill reconciliation | NautilusTrader ExecutionEngine | 不存在 | +0.2 |
| **P2** | Transaction Cost Analysis | LEAN reality modeling | 不存在 | +0.1 |
| **P2** | Reference domain | DDD bounded context | 分散在 kernel + data | +0.2 |
| **P2** | Composition root 纯化 | Hexagonal boundary | application 知道 SQLite | +0.1 |
| **P2** | 命名消歧 / suffix guard | DDD ubiquitous language | Service 44% 过载 | +0.1 |
| **P2** | 能力成熟度 manifest | Thinnest Viable Platform | 无 | +0.1 |

**完成全部 P0 + P1 后预估：6.8 → 8.5**
**完成全部后预估：6.8 → 9.2**

---

## 8. 对被审视报告的建议改进

如果未来重写这份评估，建议增加以下内容：

### 8.1 增加"运行时架构"审计维度

在评分卡中增加独立维度：

| 新增维度 | 权重建议 | 审计内容 |
|---------|---------|---------|
| 事件驱动与通信模式 | 10% | EventBus publish/subscribe 比率、reactive flow 覆盖、消息类型丰富度 |
| 状态管理与恢复 | 8% | crash recovery、snapshot/restore、WAL/journal、幂等操作 |
| 时间模型与 PIT 系统性 | 8% | 统一时间上下文、valid-time/transaction-time、架构级 PIT 保证 |
| 流式与实时能力 | 7% | streaming vs batch、增量更新、实时推送、延迟级别 |
| Backtest/Live parity | 10% | 共享运行时路径比例、adapter 实现完成度、replay 准确性 |

### 8.2 修正过度乐观的评分

| 维度 | 建议修正 | 理由 |
|------|---------|------|
| 依赖边界与架构清晰度 | 9.3 → 7.5 | 包边界 ≠ 架构边界 |
| 量化平台研究-回测-执行一致性 | 7.8 → 5.5 | BrokerGateway 零实现 |
| 工程质量与验证 | 9.2 → 7.5 | 无 crash recovery 测试、无 reconciliation 测试 |
| 可观测性与运维 | 8.3 → 6.0 | 4 包 @traced 为 0 |

### 8.3 业界对标应增加运行时层面

当前对标以架构理论和模式为主（Clean Architecture、Hexagonal、DDD）。建议增加：

- NautilusTrader 的 MessageBus + Actor + FSM 模型（运行时对标）
- ArcticDB 的不可变版本化 + 时间旅行（数据架构对标）
- Databento 的微秒级延迟架构（实时对标）
- Chronon 的 online-offline 一致性（特征工程对标）

---

## 9. 最终结论

### 9.1 被审视报告的真实水平

这是一份**8.0/10 的 Python 包结构审计报告**，但不是一份量化系统运行时架构审计。

它在包结构层面的发现是准确、深入、可执行的。Dataset enum、reference domain、composition root 纯化、Service 命名、Port 归属——这些发现都是对的。

但它用包结构的标准给交易系统架构打分，导致系统性地遗漏了五个更基础的运行时缺失：事件驱动核心、统一时间模型、状态恢复、流式数据、continuous risk。

### 9.2 一句话

> 包结构 8.0+，运行时架构 5.0-6.0。最急需的不是继续优化 import 边界，而是补齐事件驱动核心、统一时间模型、backtest/live 共享运行时路径、状态恢复机制这四块地基。

### 9.3 建议的优先执行路径

```
Phase 0（地基）：事件驱动核心 + 统一时间模型 + 状态恢复
    ↓
Phase 1（骨架）：Backtest/Live 共享运行时 + 流式数据 + Continuous risk
    ↓
Phase 2（填充）：DataCatalog runtime + Feature store + Reconciliation + TCA
    ↓
Phase 3（打磨）：Reference domain + Composition root 纯化 + 命名消歧 + Maturity manifest
```

Phase 0 完成后，Ditto 才能从"组织良好的回测框架"进化为"架构正确的量化交易系统"。

---

## 验证命令

本次审视基于以下源码验证：

```bash
# 事件驱动：零 subscribe
grep -r "event_bus.subscribe\|\.subscribe" packages/*/src --include="*.py" | grep -v test | wc -l
# 结果：0

# BrokerGateway 实现：零
find packages/execution/src -name "*.py" -exec grep -l "BrokerGateway" {} \; | grep -v test | grep -v contracts
# 结果：仅 contracts.py（定义处）

# 状态恢复：零
grep -r "restore\|rebuild\|snapshot_to\|recover" packages/*/src --include="*.py" | grep -v test | grep -v "# " | wc -l
# 结果：0（相关语义）

# 流式数据：零
grep -r "WebSocket\|kafka\|streaming\|pub.sub" packages/*/src --include="*.py" | grep -v test | grep -v "polars" | grep -v comment | wc -l
# 结果：0

# Crash recovery：零
grep -r "WAL\|journal\|checkpoint" packages/*/src --include="*.py" | grep -v test | wc -l
# 结果：0
```
