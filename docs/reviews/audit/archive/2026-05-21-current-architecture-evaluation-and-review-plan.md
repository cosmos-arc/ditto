# Ditto 当前架构综合评估、业界对标与分模块 Review 计划

> 日期：2026-05-21
> 基线：对 `docs/reviews/audit/2026-05-14-comprehensive-architecture-evaluation-and-review-plan.md` 的当前源码复评
> 范围：12 个包、当前工作区未提交变更、架构守卫、产品能力成熟度、业界最佳实践对标、全局与分模块 review 计划
> 目标：一个模块一个模块攻克，追求扩展性、理解性、可读性、一致性、整洁架构划分和优雅实现

---

## 0. 执行摘要

Ditto 当前已经越过“架构是否清晰”的阶段，进入“静态架构纪律很强，但运行时和产品闭环仍需补齐”的阶段。

本次复核和 2026-05-14 报告相比，最大的变化是：

1. **架构守卫更强**：`pixi run -e dev arch-check` 当前为 **37/37 kept, 0 broken**，新增了 application 禁止直接导入具体 storage/source/infra 的合约。
2. **Execution 明显前进**：OMS Lite、`PaperBrokerGateway`、`BrokerGateway` conformance test、`ExecutionReconciler` typed diff 已经落地，不再是纯 placeholder。
3. **Paper runtime 仍只是冒烟闭环**：`PaperTradingRuntime.execute_order()` 已可走 gateway -> fill -> account，但没有共享 runtime kernel、事件中枢、RiskGate、审计关联键、重启恢复。
4. **Dataset 静态目录债务有改善但未结束**：`Dataset.supports_instrument_ingestion()` 已迁移走，`date_schedule` 也在向 registry 迁移，但 Dataset/INGESTION_SPECS/查询配置仍是运行时事实中心。
5. **内部认知负载仍高**：没有超过 800 行的文件，但 `check_code_size.py` 仍失败在 3 个大类：`MetadataService`、`TushareSource`、`DataStoreSettings`。
6. **质量红线出现一个回归信号**：当前生产源码/scripts 中出现 1 个 `# type: ignore`，位于 `packages/platform/src/ditto_platform/foundation/observability/_registry.py`。

一句话判断：

> Ditto 的包边界治理已经是开源量化项目中偏优秀的一档；下一阶段要把评分继续推高，核心不是再写更多边界文档，而是把 runtime、DataCatalog、交易审计、产品成熟度和端到端可证明性补成体系。

---

## 1. 本次证据

### 1.1 本地验证

| 检查 | 结果 | 解释 |
|---|---:|---|
| `pixi run -e dev arch-check` | 37 kept, 0 broken | import-linter + architecture smell 全绿 |
| `pixi run -e dev python scripts/check_code_size.py` | failed | 3 个类超过 20 个 public methods |
| import-linter analyzed files | 892 | 工具实际分析文件数 |
| 源码 Python 文件 | 909 | `packages/*/src/**/*.py` 简单计数 |
| 源码 LOC | 104,602 | `wc -l` 简单计数 |
| 测试 Python 文件 | 693 | `packages/*/tests/**/*.py` 简单计数 |
| Protocol class definitions | 128 | 端口抽象使用成熟 |
| frozen dataclass | 359 | 不可变数据模型文化强 |
| all dataclass | 378 | 大部分 dataclass 为 frozen |
| ABC usage | 0 | 当前源码已接近 Protocol-only |
| `TYPE_CHECKING` in src/scripts | 0 | 符合架构铁律 |
| pandas import in src/scripts | 0 | 符合 polars-first 约束 |
| `# type: ignore` in src/scripts | 1 | 需要修复到 0 |
| `# noqa` in src/scripts | 74 | 可接受但要预算治理 |

### 1.2 当前逐包规模

| 包 | src 文件 | LOC | tests | Protocol | frozen dataclass | 评估 |
|---|---:|---:|---:|---:|---:|---|
| kernel | 14 | 919 | 16 | 5 | 9 | 小而稳，适合继续严控准入 |
| platform | 59 | 5,917 | 43 | 8 | 14 | 基础设施清晰，observability/config 需收口 |
| data | 285 | 31,440 | 192 | 20 | 50 | 最大包，仍是扩展摩擦核心 |
| features | 112 | 15,232 | 34 | 23 | 87 | 表达式/评估能力强，服务面偏宽 |
| strategy | 57 | 5,898 | 30 | 14 | 51 | 隔离优秀，模板成熟度需分层 |
| portfolio | 21 | 1,485 | 16 | 10 | 18 | 会计核心简洁，状态投影需强化 |
| risk | 18 | 1,434 | 23 | 7 | 5 | 规则清楚，runtime gate 仍需一等化 |
| execution | 52 | 3,920 | 37 | 13 | 23 | 近期进步最大，仍缺持久化闭环 |
| backtest | 39 | 5,279 | 43 | 6 | 27 | 当前最成熟 runtime 模块 |
| analysis | 20 | 1,299 | 12 | 2 | 8 | research control-plane 有雏形，产品面仍薄 |
| application | 118 | 19,416 | 111 | 17 | 60 | CQRS 清楚，但仍是第二 composition hotspot |
| apps | 114 | 12,363 | 136 | 3 | 7 | registry/entrypoint 强，E2E 与 maturity 文案需补 |

### 1.3 当前维护热点

| 行数 | 文件 | Review 风险 |
|---:|---|---|
| 697 | `packages/data/src/ditto_data/services/metadata/instrument.py` | instrument 查询/富化过宽 |
| 672 | `packages/data/src/ditto_data/storage/metadata/instrument/instrument_reader.py` | SQL 查询构造和行转换集中 |
| 629 | `packages/data/src/ditto_data/storage/base/sqlite_store.py` | 泛型 SQLite 基类职责偏多 |
| 629 | `packages/data/src/ditto_data/sources/tushare/adapters/stock.py` | 单 adapter 承载过多 dataset |
| 622 | `packages/features/src/ditto_features/evaluation/metrics/ic.py` | IC/decay/统计路径集中 |
| 583 | `packages/application/src/ditto_application/processes/materialization/orchestrator.py` | 物化编排复杂 |
| 583 | `packages/application/src/ditto_application/processes/execution/backtest_process.py` | 回测 process 仍偏胖 |
| 577 | `packages/features/src/ditto_features/services/derived_catalog_service.py` | catalog service 表面过宽 |
| 577 | `packages/features/src/ditto_features/expression/codegen/_builders.py` | codegen 已拆，但 builder 仍大 |
| 569 | `packages/application/src/ditto_application/processes/ingestion/data_writer.py` | dataset 写入路由集中 |

`check_code_size.py` 的类级失败更重要：

| 类 | public methods | 文件 |
|---|---:|---|
| `MetadataService` | 43 | `packages/data/src/ditto_data/services/metadata_service.py` |
| `TushareSource` | 27 | `packages/data/src/ditto_data/sources/tushare/tushare_source.py` |
| `DataStoreSettings` | 26 | `packages/data/src/ditto_data/config/data_store.py` |

---

## 2. 和 2026-05-14 报告的差异

| 维度 | 2026-05-14 判断 | 2026-05-21 当前判断 |
|---|---|---|
| 架构合约 | 36 kept | 37 kept，新增 application concrete infra guard |
| Execution | BrokerGateway/Paper/Reconciliation 未闭环 | PaperBrokerGateway + conformance + typed reconciliation 已落地，但仍是实验级 |
| ABC | 2 个 | 0 个，Protocol-only 更一致 |
| Dataset | Dataset enum 承担运行时目录 | 部分职责迁移到 registry，但 Dataset/config/application 事实仍分散 |
| 大文件 | 多个 700 行文件 | 无 800+ 文件，但 500-700 行热点仍多 |
| 类型纪律 | `type: ignore` 为 0 | 当前出现 1 个 `type: ignore`，需要回归修复 |
| 能力成熟度文档 | Paper/Broker/Reconciliation 标为 reserved/不完整 | `capability-maturity.md` 对 execution/paper 的描述已经滞后，需要同步 |

新版主线应从“实现第一批 runtime spine 缺口”改为：

> 把已出现的 paper/execution 小闭环升级为可复用、可审计、可恢复、可接入真实券商的 runtime spine。

---

## 3. 总体评分

### 3.1 工程架构评分

| 维度 | 当前分 | 目标分 | 主要依据 |
|---|---:|---:|---|
| 包边界与依赖方向 | **9.0 / 10** | 9.4 | 37/37 合约全绿，生产包不依赖 analysis，application concrete infra 已守卫 |
| 整洁架构划分 | **8.7 / 10** | 9.3 | Protocol、CQRS、composition root 思路清楚；application 仍承担偏多 wiring |
| 可读性/理解性 | **8.1 / 10** | 9.0 | 无 800+ 文件，但 500+ 文件和大类仍拉高认知成本 |
| 一致性/命名治理 | **8.0 / 10** | 9.0 | Store/Service/Accessor 已有规范；maturity manifest 和 CLAUDE 局部滞后 |
| 类型与测试纪律 | **8.8 / 10** | 9.4 | 测试资产充足、Protocol 多、dataclass frozen 多；1 个 `type: ignore` 是回归 |
| 数据平台扩展性 | **7.4 / 10** | 8.8 | PIT/storage/source 强；DataCatalog runtime 和 dataset 插件化仍弱 |
| Runtime/交易闭环 | **6.9 / 10** | 8.8 | PaperBrokerGateway 已有，但缺共享 kernel、event journal、RiskGate、recovery |
| 产品架构完整度 | **6.0 / 10** | 8.5 | A 股 ETF research/backtest 有基础；global/live/product workflow 缺口明显 |

综合判断：

| 口径 | 当前分 |
|---|---:|
| 静态工程架构质量 | **8.7 / 10** |
| 作为研究/回测平台 | **8.3 / 10** |
| 作为 paper-ready 交易平台 | **6.8 / 10** |
| 作为 global live-ready T1 平台 | **6.0 / 10** |
| 当前整体 T1 演进成熟度 | **7.8 / 10** |

这不是贬低，而是区分两个不同现实：Ditto 的代码边界已经很强；产品闭环和 live-ready 仍在早中期。

---

## 4. 业界最佳实践对标

本次只采纳能改变 Ditto 下一阶段决策的实践，不做框架照抄。

### 4.1 LEAN / QuantConnect

QuantConnect 文档把 LEAN 描述为用于 strategy research、backtesting、live trading 的开源引擎，并且集成数据提供商和 brokerages。LEAN 的算法引擎会同步数据、处理订单、更新算法状态，并提供 portfolio、transactions、schedule、universe 等管理器。

对 Ditto 的结论：

- Ditto 的 `strategy -> portfolio -> risk -> execution -> backtest` 领域拆分方向正确。
- 主要差距在 runtime 编排：LEAN 将数据、订单、portfolio、reality modeling 放在统一引擎路径里；Ditto 当前 backtest 成熟，paper 还只是 `execute_order()` 冒烟路径。
- 下一步不应只继续打磨 `backtest`，而要做共享 runtime seam：同一订单/风控/账户/事件语义，被 backtest 和 paper 复用。

参考：[QuantConnect Algorithm Engine](https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/algorithm-engine)

### 4.2 NautilusTrader

NautilusTrader 的核心启发是 backtest-live parity。其架构文档强调 event-driven、MessageBus、单线程 kernel 消息消费，以获得确定性事件顺序并维护 backtest-live 一致性。

对 Ditto 的结论：

- Ditto 的 `Clock`、`EventBus`、`Synchronizer`、OMS Lite、Protocol 已经具备 runtime spine 的原料。
- 当前缺的是“把这些原料组装成一条路径”：Paper runtime 没有统一 Clock/EventBus/RiskGate/StateStore。
- 应设计最小 `TradingRuntimeKernel`，先支撑 backtest/paper，不急于 live。

参考：[NautilusTrader Architecture](https://nautilustrader.io/docs/latest/concepts/architecture/)

### 4.3 OpenBB Platform

OpenBB 的 extension/provider 体系把 core、router extension、provider extension 分开。ProviderInterface 管理 provider 参数和 fetcher 映射；安装/卸载扩展后覆盖能力随之变化。

对 Ditto 的结论：

- Ditto 不需要复制 OpenBB 的打包机制，但需要吸收“runtime catalog + provider capability”的思想。
- 当前 `Dataset` enum、`INGESTION_SPECS`、应用层查询配置共同承担 dataset 事实，扩展新数据集仍要改多处。
- 应把 DataCatalog 从 Protocol-only 推进到最小可运行 registry/store，承载 dataset metadata、maturity、fetch/write/query capability、DQ profile、schedule。

参考：[OpenBB Architecture Overview](https://docs.openbb.co/platform/developer_guide/architecture_overview)、[OpenBB Extensions Overview](https://docs.openbb.co/platform/usage/extensions/overview)

### 4.4 Microsoft Qlib

Qlib 官方 README 强调从 data processing、model training、back-testing 到 alpha seeking、risk modeling、portfolio optimization、order execution 的完整链条，并且组件 loose-coupled、可独立使用。

对 Ditto 的结论：

- Ditto 当前在 clean architecture 和边界守卫上更严，但 AI/ML workflow、模型训练、自动研究、在线滚动还不是一等能力。
- `analysis` 不应长期只做 research dataset control-plane。中期需要 experiment/run registry、parameter sweep、result cube、model artifacts。
- 这部分应该在 `analysis/application` 边界推进，不应污染 `execution`。

参考：[Microsoft Qlib](https://github.com/microsoft/qlib)

### 4.5 Backtrader

Backtrader live data/live trading 文档强调保持同一套 interface，实现“backtest once, trade many times”，并引入 Store 概念衔接 data feed 和 broker。

对 Ditto 的结论：

- Ditto 的 `BrokerGateway` 和 `DataFeed/Synchronizer` 应该有对称关系：数据输入和执行输出都通过 adapter 替换。
- Paper/live 不应复制一套 backtest 逻辑，而应替换 adapter，复用 runtime kernel。
- `PaperBrokerGateway` 现在是好开始，但它需要从即时成交 toy gateway 升级为可配置、可审计、可重放的 test adapter。

参考：[Backtrader Live Data/Live Trading](https://www.backtrader.com/blog/posts/2016-06-21-livedata-feed/live-data-feed/)

### 4.6 FinRL / FinRL-X

FinRL 传统架构强调 market environment、DRL agents、applications 三层；FinRL-X 进一步提出统一 data processing、strategy construction、backtesting、broker execution，并以 weight-centric interface 维持部署一致性。

对 Ditto 的结论：

- Ditto 的 `TargetPortfolio`/权重式策略输出方向是对的，适合接规则策略、ML/RL allocator、风险 overlay。
- 不应让 AI/RL 直接侵入 broker/execution。AI 组件应作为 strategy/allocator plugin，输出权重或目标组合。
- 产品层要补“策略构建 -> 回测 -> paper -> broker execution”的一致协议。

参考：[FinRL 三层架构](https://finrl.readthedocs.io/en/latest/start/three_layer.html)、[FinRL-X arXiv](https://arxiv.org/abs/2603.21330)

### 4.7 VectorBT

VectorBT 的价值在高性能批量参数扫描、向量化/事件驱动 portfolio simulation、研究体验和快速策略探索。

对 Ditto 的结论：

- Ditto 不应引入 pandas 依赖，但应做 Polars-first 的 parameter sweep 和 result cube。
- `features + backtest + analysis` 的产品差距不是“又一个指标函数”，而是可比较、可复现、可导航的研究体验。

参考：[VectorBT Features](https://vectorbt.dev/getting-started/features/)

---

## 5. 当前最重要的系统性结论

### 5.1 Ditto 的强项

1. **边界机器化治理优秀**：37 个 import-linter 合约全绿，且新增 concrete infra guard。
2. **领域拆分方向正确**：strategy 纯粹、portfolio/risk/execution/backtest 能力包边界清楚。
3. **类型文化强**：128 个 Protocol、359 个 frozen dataclass、0 ABC、0 pandas、0 TYPE_CHECKING。
4. **Backtest 是当前标杆模块**：step chain、manifest、replay、simulation、risk/pretrade 集成已经成熟。
5. **Execution 开始形成真实骨架**：OMS Lite、PaperBrokerGateway、reconciliation typed diff 已经把 5/14 的最大短板向前推了一截。

### 5.2 Ditto 的核心短板

1. **Runtime spine 还没成为一等架构**：Clock/EventBus/StateStore/RiskGate/OMS/Account/Reconciliation 没有统一内核。
2. **DataCatalog 还是“名词”多于“运行事实”**：Dataset、application specs、maturity manifest、DQ config 仍分散事实。
3. **application 仍有第二 composition root 倾向**：虽然 concrete infra guard 已加，但 providers/builders/processes 仍是 review 热点。
4. **产品成熟度文档和源码现实不同步**：`capability-maturity.md` 对 execution/paper 的描述已落后于最新源码。
5. **内部可读性风险集中在 data/features/application**：行数不是罪，但大类和大编排器会拖慢每次 review。
6. **端到端证明不足**：缺 committed synthetic golden E2E lane，fixture skip 仍可能让系统“看起来通过”。

---

## 6. 全局 Review 攻坚路线

### Wave 0：评分和事实源校准

目标：先让文档、源码和守卫一致，避免后续 review 追逐过期事实。

| ID | 任务 | 产物 | 验收 |
|---|---|---|---|
| W0-1 | 同步 `capability-maturity.md` | execution/paper/reconciliation 成熟度改为 experimental | 文档不再声称 paper gateway 不存在 |
| W0-2 | 修复 1 个生产 `type: ignore` | `_registry.py` 类型窄化 | `rg "type: ignore" packages/*/src scripts` 为 0 |
| W0-3 | 建立 scorecard 模板 | 每轮模块 review 使用统一评分 | 分数可横向比较 |
| W0-4 | 更新 module-review-ledger | 标记已修复和仍 open 的 findings | ledger 反映 5/18 后事实 |

### Wave 1：Runtime Spine

目标：用最小共享 runtime kernel 连接 backtest 和 paper。

| ID | 任务 | 覆盖模块 | 验收 |
|---|---|---|---|
| W1-1 | 定义 `TradingRuntimeKernel` | kernel/application/backtest/execution | Clock + EventBus + state handle + lifecycle |
| W1-2 | Paper runtime 从 `execute_order()` 升级为 time-slice driver | application/execution/portfolio | 可处理多个订单、fills、account update、events |
| W1-3 | RiskGate 嵌入 submit/fill/daily 路径 | risk/execution/backtest | paper/backtest 使用同一 gate contract |
| W1-4 | SQLite/append-only OrderEventJournal | execution/platform | journal 可重放订单生命周期 |
| W1-5 | Reconciliation 关联 OMS journal/fills/account snapshot | execution/portfolio | diff 可追溯到 client order id、broker order id、fill id |

### Wave 2：DataCatalog 和时间语义

目标：把 Dataset 静态目录迁移为 runtime catalog，统一 PIT/time/provenance。

| ID | 任务 | 覆盖模块 | 验收 |
|---|---|---|---|
| W2-1 | 最小 DataCatalog store/registry | data/application/apps | dataset metadata、maturity、capability 可查询 |
| W2-2 | Dataset/INGESTION_SPECS 事实收敛 | data/application | 新增 dataset 不再改 4+ 个事实源 |
| W2-3 | shared TimeContext policy | kernel/data/features/backtest/analysis | PIT、publication cutoff、snapshot 语言一致 |
| W2-4 | Data lineage 最小实现 | data/features/analysis | derived artifact 记录输入 dataset/catalog refs |
| W2-5 | PIT leak reusable test harness | data/features/backtest | rolling/join/shift/publication cutoff 可复用测试 |

### Wave 3：Application 和 Apps 边界瘦身

目标：让 application 编排 use case，让 apps/registry 承担 host composition。

| ID | 任务 | 覆盖模块 | 验收 |
|---|---|---|---|
| W3-1 | application providers/builders concrete import audit | application/apps | concrete wiring 移到 registry 或 app-owned ports |
| W3-2 | research/query facade ports | application/analysis/features/data | research facade 不直接拉多包 service |
| W3-3 | API route maturity metadata | apps/application | OpenAPI/CLI help 标注 initial-focus/experimental/reserved |
| W3-4 | committed synthetic golden E2E lane | apps/data/backtest | `check` 不依赖本地样本也能证明主路径 |

### Wave 4：可读性和一致性

目标：降低长期维护成本，不追求机械拆文件。

| ID | 任务 | 覆盖模块 | 验收 |
|---|---|---|---|
| W4-1 | `MetadataService` 分解 | data | public methods 降到 20 以下 |
| W4-2 | `TushareSource` 分解为 capability facade | data | public methods 降到 20 以下 |
| W4-3 | `DataStoreSettings` API 收敛 | data/platform | public methods 降到 20 以下 |
| W4-4 | feature evaluation/codegen 大文件拆分 | features | IC/codegen 每个关注点独立测试 |
| W4-5 | application process 大编排器分层 | application | backtest/materialization/ingestion 主文件降认知负载 |

### Wave 5：产品架构补齐

目标：从“工程平台”推进到“可操作产品”。

| ID | 任务 | 价值 | 验收 |
|---|---|---|---|
| W5-1 | Paper trading dashboard/API 主路径 | 用户可用性 | submit/query/account/reconcile 可串联 |
| W5-2 | QMT/XTP/IBKR adapter contract design | A 股和全球扩展 | adapter conformance suite 先行 |
| W5-3 | kill switch + realtime risk alerts | 实盘安全 | 分级风控动作可审计 |
| W5-4 | research parameter sweep/result cube | 研究体验 | Polars-first 批量回测和结果比较 |
| W5-5 | multi-market/multi-currency reference plan | 全球市场 | calendar/currency/rules 不再散落 |

---

## 7. 分模块 Review 计划

### 7.1 kernel：8.7 -> 9.2

核心判断：kernel 小而稳，应继续只承载共享语言，不吸收市场业务逻辑。

Review 清单：

- 检查 `trading.py` 中 A 股默认规则是否继续下沉为 reference provider。
- 明确 `Clock`、`EventBus`、`TimeContext` 在 runtime spine 中的最小职责。
- 梳理 root `__init__.py` 的公共 API，区分 stable API 和 leaf-only API。
- 为事件类型建立 typed event catalog，减少 stringly-typed payload。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | Runtime kernel ADR 中明确 kernel 只提供 primitives | 不新增 broker/data/reference 逻辑到 kernel |
| P1 | Typed event catalog v1 | backtest/paper/risk/execution 事件名统一 |
| P2 | kernel public API 表 | root `__all__` 不再无意扩张 |

### 7.2 platform：8.5 -> 9.1

核心判断：platform 是干净的横切基础设施，但 observability/config/storage helper 需要更可审计。

Review 清单：

- 修复 `_registry.py` 唯一 `type: ignore`。
- 复核 ContextVar observability state 是否满足测试隔离和并发语义。
- 检查 SQL helper/identifier validation，避免共享层成为注入风险入口。
- 将 platform 文档中的 domain 词改成 collection/key 语言。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | `# type: ignore` 清零 | src/scripts 为 0 |
| P1 | SQLite helper identifier validation | 无新增本地 S608 例外 |
| P1 | observability correlation guidance | execution journal id/order id 可贯穿 logs/metrics |

### 7.3 data：7.5 -> 8.8

核心判断：data 是当前最大包，也是新增资产类别/数据集时摩擦最大的包。

Review 清单：

- Dataset enum、DatasetRegistration、DataCatalog、DQ rules、storage schema 之间谁是事实源。
- `MetadataService`、`TushareSource`、`DataStoreSettings` 三个大类拆分路径。
- sources/storage/services 的命名是否继续保持 Store/Service/Accessor 规范。
- PIT、calendar、instrument、reference rule 是否有统一 TimeContext 和 reference-domain 边界。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | DataCatalog runtime MVP | 能查询 dataset maturity/capability/schedule |
| P0 | Dataset routing budget | 新增 dataset 修改点有上限和测试 |
| P1 | `MetadataService` 分解 | public methods < 20 |
| P1 | Tushare source facade 分解 | provider capability 可发现 |

### 7.4 features：8.2 -> 9.0

核心判断：表达式、因子、评估能力强，但 provenance/time 和服务公共面需要治理。

Review 清单：

- Derived artifacts 是否记录 DataCatalog refs、snapshot、time semantics version。
- `ic.py`、`derived_catalog_service.py`、codegen builders 是否按职责拆分。
- Evaluation metrics 是否有 golden tests 和 property tests。
- `features.services` 哪些是 public API，哪些是内部服务。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | derived artifact provenance 接 DataCatalog | materialization/report 可追输入 |
| P1 | PIT leak harness | rolling/join/shift 统一防泄漏 |
| P1 | IC/evaluator 拆分 | 每个指标族有独立测试 |

### 7.5 strategy：8.5 -> 9.1

核心判断：strategy 依赖隔离是全仓亮点，下一步是模板和 stage contract 产品化。

Review 清单：

- `DecisionStage` 是否有 machine-readable requires/produces。
- ETF templates 和 stock/sector templates 的 maturity 是否在 API/docs 中分层呈现。
- `StrategyContext` 中 locks/cooldowns 是否应该转入 runtime/risk state。
- `TargetPortfolio` 与 portfolio target naming 是否有清晰 glossary。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P1 | Stage schema v1 | pipeline 可静态验证输入/输出 |
| P1 | template maturity catalog | experimental template 不被 API 过度宣传 |
| P2 | 策略输出 glossary | signal/target/position 语言不混淆 |

### 7.6 portfolio：7.8 -> 8.8

核心判断：会计模型清楚，但需要成为 runtime state projection 的可靠一环。

Review 清单：

- `Account.apply_fill` 是否能从 execution journal 确定性重建。
- `PositionChanged` 等事件是否继续 reserved，还是正式发布。
- positions/holdings/target_portfolios reserved namespace 是否和 maturity manifest 一致。
- 多币种 cash book、settlement、market value 语义是否有全球扩展路径。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | Account projection contract | journal/fills -> account view 可重放 |
| P1 | portfolio event policy | 事件发布或 reserved 状态明确 |
| P2 | multi-currency accounting ADR | 全球市场前置设计完成 |

### 7.7 risk：7.8 -> 8.9

核心判断：规则实现不差，但 RiskGate 应成为 runtime submit/fill/daily 的强制路径。

Review 清单：

- `RiskGate` Protocol 是否足够覆盖 pre-submit、cancel、post-fill、daily drawdown。
- 风控状态快照/恢复是否可重启一致。
- 风控事件 payload 是否 typed，能否进入 audit/reconciliation。
- kill switch 分级动作是否和 execution account state 关联。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | RiskGate runtime contract | backtest/paper 共享 |
| P1 | typed risk decision event | audit 不再依赖 `dict[str, Any]` |
| P1 | state snapshot/replay tests | 风控锁定和回撤状态可恢复 |

### 7.8 execution：7.4 -> 8.9

核心判断：execution 近期进步最大，但仍要从“有对象”变成“有可恢复运行时事实”。

Review 清单：

- `PaperBrokerGateway` 即时成交是否应引入 price source、partial fill、reject、cancel path。
- `OrderEventJournal` 是否需要 SQLite durable implementation。
- `ReconciliationReport` 如何关联 client id、broker id、fill id、journal sequence。
- `Audit Spine` 如何变成 execution 的主线，而不是旁路记录。
- 真实 broker adapter conformance suite 需要哪些测试。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | Durable OMS journal | 订单生命周期可重放 |
| P0 | Paper gateway 行为矩阵 | submit/fill/cancel/reject/partial/conformance |
| P1 | Reconciliation store + audit links | diff 可追到 order/fill/journal |
| P1 | Broker adapter contract v2 | QMT/XTP/IBKR 可按同一测试接入 |

### 7.9 backtest：8.7 -> 9.2

核心判断：backtest 是当前成熟模块，但不能成为 isolated kingdom，应与 paper 共享 runtime seam。

Review 清单：

- Engine step chain 哪些可抽象为 backtest/paper 共享 lifecycle。
- replay 是否覆盖 OMS journal、risk state、account restore，而不仅是 NAV/manifest。
- DataFeed 是否应换成 backtest-owned historical data portal。
- statistics/reporting 大文件是否可按指标族拆分。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | backtest/paper shared lifecycle contract | paper 不复制 step chain |
| P1 | replay 扩展到 OMS/risk/account | NAV 一致之外证明状态一致 |
| P2 | historical data portal | backtest 不直接消费 data-owned runtime 语言 |

### 7.10 analysis：7.2 -> 8.6

核心判断：analysis 目前更像 research control-plane，还不是完整研究产品层。

Review 清单：

- Research dataset policy 和 `SHIFT_TO_NEXT_SNAPSHOT` reserved 状态是否诚实。
- reports/diagnostics/experiments/screeners reserved namespace 是否由 manifest 驱动。
- `application.queries.research` 是否应通过 app-owned ports 访问 analysis/features/data。
- 研究体验是否需要 parameter sweep、result cube、experiment registry。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | reserved policy 事实源统一 | script/docs/API 一致 |
| P1 | research ports | application 不直接混拉三包 service |
| P1 | experiment/result cube 设计 | Polars-first 研究体验进入计划 |

### 7.11 application：7.8 -> 8.8

核心判断：CQRS 分层清楚，但 application 仍容易变成第二 composition root。

Review 清单：

- providers/builders 是否只装配 app-owned ports，而不选择具体 source/storage。
- ingestion/materialization/backtest/execution process 是否可按 use case + adapters 拆分。
- query facade 是否隐藏了过多 capability package 具体类型。
- R8 合约之外，是否需要 process/builders/providers 更细门禁。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | providers/builders concrete import audit | 新 guard 无漂移 |
| P1 | runtime factory contract | backtest/paper 创建路径一致 |
| P1 | process 大文件分解 | ingestion/backtest/materialization 主路径更薄 |

### 7.12 apps：7.7 -> 8.8

核心判断：apps 作为 composition root 方向正确，但要承担成熟度呈现和 E2E 证明。

Review 清单：

- registry 是否只做 composition，不存储业务事实。
- API/CLI 是否为 experimental/reserved 能力标注 maturity。
- E2E 是否有 committed synthetic golden lane，避免依赖本地 TDX 样本。
- route/job 大文件是否拆分 request parsing、facade call、response mapping、error mapping。

第一批行动：

| 优先级 | 行动 | 验收 |
|---|---|---|
| P0 | synthetic golden E2E | CI 能证明 A 股 ETF 主路径 |
| P1 | maturity-aware OpenAPI/CLI docs | endpoint presence 不暗示 production-ready |
| P1 | registry fact extraction | facts 来自 manifest/catalog/config |

---

## 8. 产品架构差距

### 8.1 当前已接近可产品化的能力

| 能力 | 成熟度 | 说明 |
|---|---|---|
| A 股 ETF 日频数据/研究/回测 | initial-focus | 当前最可信主路径 |
| 因子表达式和物化 | initial-focus | 需要 provenance/time 加固 |
| 策略模板 | ETF initial-focus，股票/行业 experimental | 需要 maturity catalog |
| Backtest engine | initial-focus | 需要 paper/live parity |
| Research dataset control-plane | initial-focus | 需要产品体验增强 |

### 8.2 和 T1/global/live-ready 的缺口

| 产品能力 | 当前状态 | 缺口 |
|---|---|---|
| Paper trading | experimental | 只有最小 runtime，缺 risk/event/audit/recovery |
| Live trading | reserved | 无真实 broker adapter |
| Broker ecosystem | early | 需要 QMT/XTP/IBKR adapter contract 和 conformance |
| 多市场 | experimental | calendar/rules/currency/security master 还未统一 |
| 多币种 | missing | cash book、FX conversion、base currency accounting 缺失 |
| 实时风控 | partial | 缺 kill switch、分级告警、实时风险状态 |
| 数据目录/血缘 | protocol-only | DataCatalog/Lineage 没有 runtime store |
| 研究产品体验 | weak | 缺 parameter sweep、experiment registry、result cube |
| E2E 证明 | weak | 需要 committed synthetic golden lane |
| 运维恢复 | weak | 缺断线重连、状态恢复、broker truth reconciliation workflow |

产品架构建议：

1. 先把 A 股 ETF daily path 做到可证明、可回放、可 paper。
2. 再接 A 股真实券商 mock/QMT/XTP contract，不急于全球 broker。
3. global market 能力以 reference-domain/multi-currency/calendar/rules 为前置，不从 API endpoint 扩张开始。
4. AI/RL/LLM 作为 strategy/analysis plugin，不进入 execution。

---

## 9. 推荐攻坚顺序

如果按“一次只攻一个模块或一个主题”推进，推荐顺序如下：

| 顺序 | 攻坚主题 | 为什么先做 |
|---:|---|---|
| 1 | W0 事实源校准 | 先修文档/评分/type-ignore，否则 review 基线不稳 |
| 2 | execution | 当前已有新骨架，最适合趁热补 durable OMS/reconciliation |
| 3 | portfolio + risk | 与 execution 共同形成 runtime state 和 safety |
| 4 | backtest + kernel | 抽 shared lifecycle，不让 paper 复制 backtest |
| 5 | data | DataCatalog/事实源收敛会影响后续所有数据扩展 |
| 6 | application + apps | composition root 和 E2E 证明收口 |
| 7 | features + strategy | provenance、stage contract、template maturity |
| 8 | analysis | 研究产品体验和 result cube |
| 9 | platform | observability/correlation/SQL guard 深化 |

第一个实际模块建议从 **execution** 开始，但前置必须先做 W0：

- 修复 `# type: ignore` 回归。
- 同步 `capability-maturity.md`。
- 更新 module-review-ledger 中 EXEC 已完成/仍 open 状态。
- 为 execution review 建立最新 scorecard。

---

## 10. Definition of Done

每个模块 review 完成必须满足：

1. 有源码证据：关键文件、当前实现、测试覆盖、架构合约影响。
2. 有业界对标：只引用会影响该模块设计的实践。
3. 有评分：当前分、目标分、扣分原因。
4. 有 findings：P0/P1/P2，必须可复现、可验证。
5. 有 remediation plan：每项包含文件、测试、验收命令。
6. 有 maturity 更新：涉及产品能力时同步 `capability-maturity.md`。
7. 有验证：至少 `pixi run -e dev arch-check`；涉及源码则 `pixi run -e dev check`。

每个模块修复完成必须满足：

```bash
pixi run -e dev check
```

并且：

- `pixi run -e dev arch-check` 保持 37/37 kept。
- `rg "type: ignore" packages/*/src scripts -g "*.py"` 回到 0。
- 新增能力有单元测试；跨包行为有集成或 E2E 测试。
- 文档、maturity manifest、ledger 与源码同步。

---

## 11. 结论

Ditto 当前不是“需要重构一切”的项目。它的核心骨架是对的，边界守卫也足够硬。真正要追求卓越，下一阶段应少做宽泛清理，多做可证明闭环：

1. **先修正事实源**：maturity、ledger、scorecard、type-ignore 清零。
2. **以 execution 为第一攻坚模块**：把 OMS journal、paper gateway、reconciliation、audit spine 串起来。
3. **把 runtime spine 做成共享内核**：backtest 和 paper 共享，不分裂。
4. **把 DataCatalog 做成运行事实**：dataset 扩展从 enum/config 多点修改，走向 capability catalog。
5. **用 E2E 和 replay 证明产品能力**：不能只靠单元测试和静态边界证明 T1 就绪。

当前分数约 **7.8/10**。如果 Wave 0-3 落地，Ditto 能稳定进入 **8.6-8.9**；如果 runtime spine、DataCatalog、paper trading、golden E2E 都闭环，才真正有资格冲击 **9.2+**。
