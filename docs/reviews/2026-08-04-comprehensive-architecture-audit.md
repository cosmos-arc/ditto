# Ditto 全库首席架构师审计报告

> **日期**：2026-08-04
> **视角**：业界顶尖量化平台首席架构师
> **范围**：`packages/` 全部 12 包（kernel / platform / data / features / strategy / portfolio / risk / execution / backtest / analysis / application / apps）+ 对应 tests + 架构门禁
> **方法**：机器门禁实跑 + 全包 LOC/文件测绘 + 风险信号全量 Grep + 核心文件逐行深读（kernel 全量 16 文件、各包核心文件 head-to-tail）+ 业界横向对标
> **对照基线**：[boundaries-and-abstraction-standards.md](../architecture/boundaries-and-abstraction-standards.md)、各包 `CLAUDE.md`、`.importlinter`、`pyproject.toml`、CI workflows；并校准既有 [2026-06-16-quality-eval.md](2026-06-16-quality-eval.md)（工程 4.56★）与 [2026-07-10-capability-benchmark](../plans/2026-07-10-capability-benchmark-design.md)（功能 2.9★）

> ⚠️ **定位校准（2026-08-04 用户纠偏）**：本项目并非「A 股 ETF 日频」——当下覆盖 **A 股 ETF + 个股 + 选股**，目标是 **全资产标的 + AI/Agent 现代化平台**。本报告初稿曾以窄定位校准能力缺口，多处"日频可接受"的判定（实时风控/算法执行/tick/AI runtime）按正确北极星应**升级**；功能完整度据此从 3.0★ 下调至 **~2.5★**（AI/Agent 支柱 0★ + 资产覆盖窄 + 主动/执行薄）。下方 §0/§4 的窄定位表述为初稿原文，请以本校准与另行成文的「AI/Agent 能力平面设计」为准。好消息：缺口多为"加法"而非"重构"——R3 治理门禁与 features DSL 天然是 AI 安全接入的护栏与靶点。

---

## 0. Executive Summary

### 一句话裁决

> 这是一个**工程纪律处于业界上游、架构边界被机器门禁真实固化**的现代化量化平台（当下 A 股 ETF + 个股 + 选股，目标全资产标的 + AI/Agent）。它的主要矛盾**不在"边界是否清晰"**（37 条 forbidden 契约全 KEPT、pandas 0、TYPE_CHECKING 2、type:ignore 11、TODO 2），而在**"编排层的结构可伸缩性"**（application 97K LOC 占全仓 54% + 800 行硬上限诱发"贴线切分"）与**"组合优化/实时风控的能力完整度"**（凸求解器家族缺位，但 Protocol 注入点已就位）。

### 关键统计（实测）

| 指标 | 结果 | 评价 |
|------|------|------|
| 源码总规模 | 245K LOC / 1,325 文件 | application 占 40%（编排层过重） |
| 测试总规模 | 323K LOC / 921 文件 | test/src ≈ 1.32，密度健康 |
| **arch-check** | **37 contracts kept, 0 broken** | 优秀 |
| **arch-smells** | **0 issues** | 优秀 |
| **basedpyright (strict)** | **0 errors / 0 warnings / 0 notes** | 优秀 |
| **ruff lint** | **All checks passed** | 优秀 |
| **unit test --fast** | **12,177 passed, 1 xfailed**（documented） | 优秀 |
| 禁止库 pandas | **0 处** | polars mandate 落地 |
| `TYPE_CHECKING` | **2 处**（仅 analysis） | 反循环依赖 stance 真实 |
| `# type: ignore` | **11 处**（9 集中在 strategy 1 文件） | 极低、局部化、可消除 |
| `TODO/FIXME/HACK` | **2 处** | 极整洁 |
| 命名一致性 | `bar` 统一（无 kline/candle） | 优秀 |

### 双轨评分（校准既有基线）

| 维度 | 评分 | 说明 |
|------|:---:|------|
| **工程质量 / 架构纪律** | **★ 4.4 / 5.0** | 门禁真实有效、边界清晰、测试密度高；与既有 4.56★ 基本一致，本审计因发现 god-layer 与若干正确性瑕疵微调下调 |
| **功能能力完整度**（对标"全资产 + AI/Agent"北极星） | **★ ~2.5 / 5.0** | 较初稿 3.0★ 下调：AI/Agent 支柱 0★ + 资产覆盖窄 + 主动/执行薄；强项仍在数据治理/研究治理 |

> 两套分数不矛盾：**前者衡量"建得好不好"，后者衡量"建得全不全"**。对 A 股 ETF 日频这一产品定位，工程质量是决定性优势，能力缺口多属路线图（R3/R4）而非缺陷。

### Top 6 高优先级问题（按 ROI 排序）

1. **[ARCH-001] application 编排层 97K LOC 单体化**（Blocker · 结构性）— `processes/experiments/` 下 ~10 个 ~800 行文件疑似一个超大研究流程被机械切片。
2. **[ARCH-002] 800 行硬上限诱发"贴线切分"**（High · 设计）— 31 个文件落在 750–800 带、0 个超限，分布异常。
3. **[CORR-001] backtest 指标正确性瑕疵**（High · 正确性）— Sortino 混用自由度、turnover 双向计 2×、`engine_runtime.py` 零测试。
4. **[CORR-002] kernel 时间/精度原语缺陷**（Medium · 正确性）— `RealtimeClock` naive datetime；`FeeSchedule` 全 float；`FeeModel.order: Any` Port 错置。
5. **[CAP-001] 组合优化能力薄弱**（Medium · 能力）— 无真实凸求解器/风险平价/BL/HRP，但 `CovarianceProvider` Protocol 已就位。
6. **[ENG-001] execution 对账复杂度 + 文档塌陷**（Medium · 可维护性）— `executor.py` 777 行 5 层嵌套；CLAUDE.md 缺口段 1500 字 run-on 句。

---

## 1. 架构总览与依赖纪律

### 1.1 实测依赖图

```
                         apps  (32K, 传输适配 + DI composition root)
                          │
                       application  (97K, CQRS 编排 — 全仓最大)
                          │
   ┌──────────────── capability planes（并列，非线性上下游）─────────────────┐
   │  data(38K)  features(18K)  strategy(13K)  portfolio(1.8K)              │
   │  risk(1.6K)  execution(9.3K)  backtest(8.8K)  analysis(19K, 研究隔离)   │
   └──────────────────────────────┬───────────────────────────────────────┘
                                  │
            kernel(1.1K, 共享类型/Protocol)  +  platform(5.8K, 横切基础设施)
```

**平面互斥由 ~20 条 explicit forbidden contracts 固化**（实测全 KEPT）：
- `strategy` 禁依赖 data/features/portfolio/risk/execution（市场输入由 application 注入）
- `risk` 窄依赖 portfolio（仅账户/订单视图），禁依赖 execution
- `execution` 禁依赖 risk/strategy/backtest；`backtest` 禁导入真实券商网关
- 生产包禁依赖 `analysis`（研究隔离）；`analysis` 用独立 `sqlite3` 连接（`research/research.sqlite`），**零 `ditto_data` import**（实测）

**调用链**（`EngineLoop` 核实，`backtest/engine.py`）：`Synchronizer(kernel)` 驱动 7-step：`DataFetch → RiskScan → Strategy → Planning → PreTrade → Execution → Audit`。backtest 是唯一允许横向编排多能力包的平面。

### 1.2 架构纪律结论

门禁体系**真实且有效**，不是纸面规则：
- **R8 互斥**（queries↔commands↔builders）：6 条 forbidden 契约 KEPT，源码 grep 零违规。
- **Provider 整洁**：`providers*.py` 零 `os.environ`/`os.getenv`/`import os`，零 `ditto_platform.config` 访问；settings 以类型化 dataclass 经 dishka 注入；每个 `@provide` 是纯构造 `return Foo(ports=...)`。
- **Command 精简**：22 个 command handler 全部是"验证→DTO→委托 port/process→映射 typed error"的协调器，**零核心策略计算**。
- **无 god-process**：`ExperimentExecutionCoordinator` 是 mixin 组合（`ExperimentControlCoordinatorMixin` + `WorkerLeaseAuthorityCoordinator`）+ 8 个专注 leaf 协作模块，非上帝类。

---

## 2. 逐模块深审（12 包）

### 2.1 kernel — ★ 4.0（1151 行 / 16 文件）

**裁决**：质量显著高于平均的 shared kernel——零运行时依赖（`pyproject.toml` 无 `dependencies`）、1151 行零 TODO、边界守卫测试可执行、RuntimeLifecycle FSM 对标 NautilusTrader。但**未完全守住自定规矩**：文档与代码漂移、`FeeModel.order: Any` 是 Port 错置、量化平台最关键的 Money/Decimal 原语缺失。

| 维度 | ★ | 理由 |
|------|:--:|------|
| 架构/分层 | 4.0 | 零依赖守住，但 FeeModel Port 归属错、RunStatus 单消费者 |
| 代码质量 | 4.3 | 极整洁，但 RealtimeClock naive datetime 是真实 bug 隐患 |
| 测试质量 | 4.6 | test/src≈2.27，356 测试 + 边界守卫 + FSM 全转换 |
| 内聚/SRP | 3.9 | trading.py 182 行混常量+5 值对象+2 Protocol |
| 能力完整度 | 3.4 | 缺 Money/Decimal、OrderStatus、Symbol 强类型 |

**优势**：① 零运行时依赖实至名归（pyproject 实测无 dependencies）；② 边界守卫固化为测试（`test_kernel_import_boundary_unit.py:10-33` sys.modules 差集断言）；③ FSM 设计严谨（`runtime.py:61-134`，15 态表驱动，对标 NautilusTrader `ComponentState`）。

**问题**：
- **[Critical] `FeeModel.order: Any`**（`trading.py:112-137`）— kernel 定义端口却语义依赖 `ditto_portfolio.Order`，违反自定 boundaries §6.2"Port 由消费者拥有"。修复：下沉到 execution/portfolio。
- **[Major] `RunStatus` 单消费者**（`strategy.py:30-37`）— 全仓 grep 唯一消费者是 `ditto_strategy`，CLAUDE.md 标注的"Data"不存在；违反 kernel "≥2 包消费"准入标准。修复：下沉到 `ditto_strategy.runs`。
- **[Major] 值对象用裸 str**（`trading.py:74-82,96-97`）— `InstrumentDefinition.asset_class: str` 而非自有 `AssetClass` 枚举；违反 boundaries §6.3。
- **[Major] naive datetime**（`clock.py:67,71` vs `runtime.py:181` aware）— live 场景比较会抛 TypeError。修复：`datetime.now(UTC)`。
- **[Major] 文档漂移** — CLAUDE.md 虚假声明 strategy→market 依赖、`__all__` 33 个超 ≤30 上限、`time_semantics.py` 未登记。
- **[Minor] `validate_transition` 抛裸 `RuntimeError`**（`runtime.py:134`）非 `DittoError` 根。

**能力差距**：① 缺 **Money/Decimal/Price**（`FeeSchedule` 全 float，佣金/印花税精度风险——业界 NautilusTrader 全 Decimal）；② 缺 `OrderStatus` 枚举；③ 缺 `Symbol = NewType`；④ Clock 无时区绑定。

---

### 2.2 platform — ★ 4.1（6297 行 / 63 文件）

**裁决**：横切定位纯粹、OTel 三件套是真正的薄封装、零技术债信号（无 type:ignore/TYPE_CHECKING/TODO）。但**能力广度有明显缺口**：CLAUDE.md 允许的 tenacity/limits/httpx 三库中，httpx 仅散落两处裸用、tenacity/limits 完全未封装。

| 维度 | ★ | 理由 |
|------|:--:|------|
| 架构/分层 | 4.5 | platform→kernel 仅异常继承，业务零泄漏；但 foundation/__init__ 65 符号 facade 弱化子域 |
| 代码质量 | 4.5 | 零技术债信号；但 count() 全量加载、_evict_count 死指标 |
| 测试质量 | 4.5 | test/src 1.48 + 集成测试 |
| 内聚/SRP | 4.0 | ParquetStore leaf 拆分好；cache 双路径、config 双模型拖累 |
| 能力完整度 | 3.0 | 缺统一 http client、缺 tenacity/limits 封装、缺熔断/动态配置 |

**优势**：① OTel 三件套三环境 preset 精确分流（`tracing.py:103-144`，dev=1.0/testing=0.0/prod=0.1）；② 零技术债信号（63 文件 0 type:ignore）；③ 数据耐久性（atomic_write tmp+fsync+replace）+ SQLite WAL + SQL 注入白名单防护。

**问题**：
- **[High] `ParquetStore.count()` 全量加载**（`parquet_store.py:335`）— `len(self.read(...))` 读整个分区再数行，年度 parquet 严重内存反模式。修复：`scan_parquet().select(pl.len())`。
- **[High] `_evict_count` 死指标**（`cache/core.py:103`）— 初始化为 0 全路径无写入，`get_stats()` 返回误导监控。修复：移除或周期性推算。
- **[Medium] `SafeGauge.inc/dec` 并发竞争**（`_types.py:170-180`）— 无锁 RMW 跨多字节码丢更新。修复：加 `threading.Lock`。
- **[Medium] 无统一 HTTP client**（`webhook.py:60`、`telegram.py:53` 各自裸 `httpx.Client`，无连接池/重试/trace 传播）。
- **[Medium] `ObservabilitySettings` vs `ObservabilityConfig` 双模型**（字段重叠无继承关系）。

---

### 2.3 data — ★ 4.2（39071 行 / 311 文件）

**裁决**：具备**机构级 PIT 纪律**、明显高于行业均值的数据平台，被迁移债务（Dataset 枚举尸体）与若干重复拖低。PIT 正确性避开了量化头号杀手"前瞻偏差"。

| 维度 | ★ | 理由 |
|------|:--:|------|
| 架构/分层 | 4.5 | 禁止方向导入实测全 0；CQRS + Protocol 契约清晰 |
| 代码质量 | 4.0 | polars 优先、0 type:ignore；但 tushare 双 API 重复 ~220 行 |
| 测试质量 | 4.5 | test/src 1.2x + pit/integration + golden e2e |
| 内聚/SRP | 4.0 | 子域干净；InstrumentService 22 方法 |
| 能力完整度 | 4.0 | 三源 + PIT 版本化 + freeze + promotion 治理 + L1-L4 质量；缺 tick/实时/另类 |

**优势**：① **PIT 达机构级**——财报显式区分 `knowledge_date=ann_date`（PIT 过滤）与 `report_date=end_date`（仅留存），日行情 `knowledge_date=trade_date+1d`，`trade_date` 兜底 **fail-closed**（`policy.py:86-103`，`is_trade_date_fallback_allowed(None)→False`）；② 层级边界零穿透；③ **客观、不可"自造通过"的晋级治理**（`catalog/promotion.py` 按 criteria 精确匹配 + 端口持久化 + append-only 历史 + 撤销端口）。

**问题**：
- **[High] `Dataset` 枚举尸体**（`models/common.py:46-196`）— 20 成员常量外部零访问、2 helper 已 DeprecationWarning 无人调用，被 `DatasetMetadata` 取代却未清理。修复：改 `Literal` 别名或整体移除。
- **[Medium] tushare 双 API 重复**（`tushare_source.py:509-735`）— 每个域方法出现两次（facade + 扁平委托），~220 行纯重复。
- **[Medium] PIT 不变量散落 7 处**（`_pit_base` + `PitHelper` + 5 个 SQLite reader 各自手写 `effective_from <= ? AND ...`）— 边界语义改动须同步 7 处。
- **[Low] 财报映射错置**（`capital.py:161-279` 三大财报映射定义在"资金"文件）。

**能力差距**：无 tick/L2/order-book/实时；无另类数据；单一区域（A 股 ETF）；**SQLite 写锁是全历史回填天花板**（`--parallel` 无法突破，需迁 DuckDB/Parquet 写路径）。

---

### 2.4 features — ★ 4.5（18564 行 / 129 文件）

**裁决**：本仓**设计最优雅的包**——完整的因子表达式 DSL + governed 因子契约 + 丰富评估套件，风险信号极洁（0 type:ignore/0 TODO/0 TYPE_CHECKING）。

| 维度 | ★ | 理由 |
|------|:--:|------|
| 架构/分层 | 5.0 | expression↔materialization 单向；纯计算与 storage 清晰分离 |
| 代码质量 | 4.5 | 极洁；2 个文件偏大（786/729） |
| 测试质量 | 4.5 | DSL 全链路 + 算子 golden + 评估 regime/attribution |
| 内聚/SRP | 4.5 | 子域边界清晰 |
| 能力完整度 | 4.5 | DSL + 因子目录 + 物化计划 + IC/Fama-MacBeth/归因 |

**优势**：① **完整表达式语言**（lexer→parser→ast→analyzer→compiler→codegen，含 scalar/ts/cs 算子，`expression/codegen/_cs_operators.py`/`_ts_operators.py`）——对标 WorldQuant/DalphaLens 风格的 alpha 表达式；② **governed R3 因子契约**（`core_daily_contracts.py` 全 StrEnum：AssetLane/PitRequirement/PreprocessingStep/WinsorizationMethod MAD_3/StandardizationMethod zscore，hash 锁定不可变）；③ 评估套件齐全（IC/ICIR/Fama-MacBeth/归因/暴露/正交化/尾部风险）。

**问题**（少）：`core_daily_contracts.py`(786) + `evaluation/report.py`(729) 偏大；唯一 xfail（`cs_rank` polars `.over()` 嵌套限制）附完整根因——负责任的已知缺陷披露。

---

### 2.5 strategy — ★ 4.2（13610 行 / 74 文件）

**裁决**：契约驱动的策略框架设计扎实（DecisionFrame schema + 每边界校验 + canonical identity fail-closed），唯一代码瑕疵是 sqlite row mapper 的类型逃逸集中点。

| 维度 | ★ | 理由 |
|------|:--:|------|
| 架构/分层 | 4.5 | 纯策略定义，信号存储 Protocol 注入，禁依赖全部下游 |
| 代码质量 | 4.0 | governance_store 9 处 type:ignore |
| 测试质量 | 4.5 | 417 单元 + 端到端集成 |
| 内聚/SRP | 4.0 | alpha/ 41 文件较大子域 |
| 能力完整度 | 4.0 | Pipeline+Stage+模板成熟度分级 |

**优势**：① `DecisionFrame` schema 契约（`pipeline.py`，instrument_id/signal_value/score/weight/reason_codes 列约定）+ 输入/join/stage 输出/组合边界四点 `validate_frame`；② canonical identity 映射 fail-closed（实验模板字符串 ID → 晋级前必须证明已解析为 `InstrumentId`）；③ Stage 组合（Signal→Scoring→Allocation→Constraint）+ SelectionEvidence 子系统；④ 模板成熟度分级（initial-focus vs experimental，golden snapshot 签名门禁）。

**问题**：
- **[Medium] governance_store 9 处 type:ignore**（`strategy_governance_store.py:199-246`）— 全是 `int(d["version"]) # type: ignore[arg-type]`，sqlite Row→dict[str,object] 无法窄化。修复：引入 `StrategyVersionRow` dataclass + `from_row()` 类方法，单点集中。**全仓唯一可低成本归零的 type:ignore 簇**。
- **[Low]** alpha/ 子域 41 文件，parameters(782)/selection_evidence(778)/pipeline(713)/node_registry(641) 多个 700+ 行文件。

---

### 2.6 portfolio — ★ 4.5（1984 行 / 22 文件）

**裁决**：小而精——Protocol 驱动 + 原子会计状态机。历史"组合优化 2.5★"评价**部分过时**：已具 4 分配器 + 7 约束，真实短板仅剩凸求解器家族，且注入点就位。应上调至 3.5★（能力）。

**优势**：① `Account.apply_fill`（`accounting/account.py:139-190`）"先纯计算、后原子赋值" + frozen `Position` + `MappingProxyType` 只读视图；② Protocol 全消费者侧（WeightAllocator/CovarianceProvider/Constraint/FillProjector）；③ 已有 4 分配器（等权/逆波动率/score 加权/对角最小方差）+ 7 约束（MaxWeight/MinWeight/MaxPositions/IndustryMaxWeight/Liquidity/Tradability/MaxTurnover）。

**问题**：
- **[CAP-001] 无真实凸求解器**（`optimization.py:48-92`）— `MeanVarianceAllocator` 用对角协方差近似（`DiagonalVolCovariance` 仅 `diag(vol²)`）求逆方差，明确注释"deliberately avoids a solver dependency"。无 cvxpy/风险平价/BL/HRP。**但 `CovarianceProvider` Protocol 已就位**（`optimization.py:24-29`），R4 接入不改边界。

---

### 2.7 risk — ★ 4.5（1718 行 / 19 文件）

**裁决**：pre-trade 规则集完整正确、fail-closed，A 股手数规整的 resize-recheck 是正确工程化。短板在运行时抽象统一与实时/统计风控能力。

**优势**：① 6 PreTradeCheck（NoShortSell/PriceValidity 涨跌停/LotSize/BuyingPower/Concentration/DailyTurnover）+ `CompositePreTradeCheck` resize-recheck 循环（`constraints/checks.py:264-310`，MAX 3 次迭代防死循环）；② Decision ACCEPT/REJECT/RESIZE 返回值规范；③ fail-closed 默认。

**问题**：
- **[CAP-002] 缺统一 `RiskGate` 运行时 Protocol**（CLAUDE.md RISK-P1-01）— backtest 与 paper 各自内嵌门控，可能漂移。修复：抽象 `RiskGate`（pre+post+snapshot/restore）共用。
- **能力差距**：无 VaR/CVaR/Expected Shortfall、无压力测试/情景分析、无实时 pre-trade 流（日频定位可接受，但 T1 全栈目标需补）。

---

### 2.8 execution — ★ 4.0（9510 行 / 66 文件）

**裁决**：**最大亮点是 Order/Fill 模型跨回测/实盘完全统一**（回测→实盘迁移无模型阻抗）；主要债在对账子域的复杂度集中。

**优势**：① 回测与实盘共享同一 `FillEvent`（`ditto_portfolio.accounting`）与同一 `Order`（`ditto_execution.orders.model`），`BacktestBrokerage` 与 `PaperBrokerGateway` 产出类型一致；② 双 Brokerage 抽象分工清晰（`Brokerage` 运行时 vs `BrokerGateway` 低层）；③ 滑点职责正确切分（回测模拟/实盘取真实成交价）。

**问题**：
- **[High] `executor.py` 复杂度**（`reconciliation/executor.py:537-640`）— `execute_report_actions` 104 行 5 层嵌套，4 个 set/dict 手工追踪 same-fill 状态。修复：抽 `RepairReportMutationTracker` 状态机。
- **[Medium] 鸭子类型探测能力**（`executor.py:226-233,290-302`）— `getattr(resolved_port,"append_projected-fill",None)` + `cast()` 运行时探测。修复：显式 Protocol 组合。
- **[Medium] `recording.py` 652 行 SRP 过载**（BrokerEventRecordingGateway 承担全生命周期 + ID 恢复 + duplicate 折叠）。
- **[Low] `trade_builder.py` 死参数**（`on_fill(fill, account_view)` 的 account_view 在两 impl 均未引用，:137,198,414）+ `get_open_trades()` 读方法调用 `_next_id()` 自增（非确定性，:464,559）。
- **[Low] 无 `FeeModel` Protocol**（`SimpleFeeModel`/`AShareFeeModel` 鸭子类型，与回测侧 Fill/Slippage Protocol 不对称）。
- **[ENG-001] reconciliation CLAUDE.md 缺口段 1500 字 run-on 句**，不可读。

---

### 2.9 backtest — ★ 4.2（8909 行 / 49 文件）

**裁决**：PIT 单源设计严谨、零导入真实券商网关；但发现**指标正确性瑕疵**（本审计最重要的一类发现）。

**优势**：① PIT 单源——`TimeSlice.bars`/`benchmark_close` 是每步唯一 PIT 可见输入（`engine.py:662-684`），`execution_delay` 尾部 flush 复用最后 TimeSlice；② 零导入真实券商网关（`from ditto_execution.broker\b` 词边界 grep = 0）；③ EngineLoop 7-step 清晰。

**问题**：
- **[CORR-001 · High] Sortino 公式混用自由度**（`statistics_returns.py:159`）— 仅对 downside returns 求平方和，却除以 `(n-1)`（n 为总样本数）。混合"下行样本"与"全样本自由度"两种约定，偏离教科书 Sortino。
- **[CORR-001 · High] turnover 双向计 2× + 分母不一致**（`statistics_trades.py:200,202,211`）— `total_turnover` 对买卖双向求和（往返计 2× 名义额）；`:202` 用 `avg_nav` 而 `:211` `cost_drag` 用 `initial_nav`。
- **[High] `engine_runtime.py`（202 行）完全无测试**（grep 整个 backtest/tests 零引用）。
- **[Medium] FillModel 哨兵 FillEvent**（`simulation/fill.py:272-292`）— 返回 `Filled` 内夹带占位 `FillEvent`（fill_id=""/fee=0），brokerage 必须"知道"丢弃重建。修复：FillModel 改返回 `(fill_price, filled_qty)` 二元组。
- **[Medium] engine getattr 探测可选方法**（`engine.py:484,512,516,690`）+ legacy 兼容路径 58 行 + 8 cast（`:742-799`）。

---

### 2.10 analysis — ★ 4.0（19159 行 / 72 文件）

**裁决**：研究 control-plane 设计严谨（存储真隔离、experiments 是真实运行时、6 类硬门禁），但**测试质量有结构性问题**（关键文件无专属单测 + 测试质量长尾）。

**优势**：① **研究存储真隔离**——独立 `sqlite3` 连接（`storage/sqlite/experiments/database.py:5,12`），路径 `research/research.sqlite`（vs 生产 `metadata/metadata.sqlite`），**零 `ditto_data` import**；② **experiments 是真实运行时**（非 reserved 命名空间——~50 生产 import 跨 `ditto_application`），但调度循环在 application（analysis 只提供契约 + 存储/lease 持久化层）；③ 6 类硬门禁 + opaque identity + immutable launch spec + 状态机 + typed persistence。

**问题**：
- **[High] 关键文件无专属单测**：`preflight_authority.py`（792 行，authority decoder 零直接测试，仅上游集成覆盖）；experiments sqlite `writer.py`(800)/`reader.py`(792)/`_holdout.py`(796) 仅 `test_sqlite_store_unit.py` 间接覆盖；`persistence.py` codec 无隔离测试。
- **[Medium] 测试质量长尾**——3 文件（scheduler_lease 4354 + sqlite_store 3063 + trial_ledger 1009）占全部测试 LOC 的 53%；多个契约测试 <30 行。
- **[Low] 无 property-based / mutation testing**（canonical hashing、identity decoding、holdout replay 这类不变量表面本可受益于生成式输入）。
- **[Medium] 6 个 ~800 行贴线文件**（writer/reader/_holdout/_dispatch/_indexed_artifacts 同属一存储子域）。

---

### 2.11 application — ★ 3.8（96964 行 / 338 文件）

**裁决**：全仓**最大结构性风险**所在。R8 互斥、command 精简、provider 整洁都经得起审查；但 97K LOC 占全仓 40%、`processes/experiments/` 的 ~800 行碎片强烈暗示一个超大研究流程被机械切片。

| 维度 | ★ | 理由 |
|------|:--:|------|
| 架构/分层 | 3.5 | CQRS 形式成立 + R8 真实强制；但 god-layer + 贴线碎片 |
| 代码质量 | 4.0 | authority_source cast("object") 类型逃逸等少量 smell |
| 测试质量 | 4.5 | 4 golden 集成 + R3 闭环 golden |
| 内聚/SRP | 3.0 | experiments/processes 内聚失败（门禁通过但切片） |
| 能力完整度 | 4.0 | 编排能力齐全 |

**优势**：① R8 互斥真实强制（6 forbidden contracts KEPT）；② 无 god-process（coordinator 是 mixin 组合 + 8 leaf）；③ providers 纯接线（零 os.environ、零 platform.config 访问）。

**问题**：
- **[ARCH-001 · Blocker] god-layer**（97K LOC / 40%）— `processes/experiments/` 下 worker(781)/coordinator(777)/comparison(779)/execution_bundle(747)/research_data_feed(749)/_walk_forward_evidence_collection(785)/_coordinator_recovery(794)/_launch_material(761)/_comparison_evidence(799) 等 ~10 个 ~800 行文件，疑似一个超长研究流程被切成 ~800 行碎片贴门禁，而非按业务子域分解。修复：按 launch/planning/walk-forward/comparison/recovery/evidence 重组为子包；评估拆出独立 `research_runtime` 包。
- **[ARCH-003] `strategy_spec_deserialization.py`（792 行）放置包根**——导入 strategy.alpha 20+ 符号，更像 builders 子域。修复：迁入 `application/builders/strategy_spec/`。
- **[ENG-002] `cast("object", self._artifacts)` 类型逃逸**（`builders/research_validation_authority_source.py:444`）。

---

### 2.12 apps — ★ 4.1（32103 行 / 166 文件）

**裁决**：成熟的 composition root + maturity-gated API + 极详尽的边界纪律。主债是 `registry/live/` 一簇 ~800 行认证 driver 的过程式 bulk。

**优势**：① dishka composition root（`registry/container.py` + `contexts/` + `infra/` @provide）；② **maturity-gated API**（`x-ditto-maturity` + `ROUTE_MATURITY_BY_PREFIX` 架构测试防漂移）；③ 边界纪律极严（registry-only 豁免表 + `APPS_HOST_COMPOSITION_ALLOWANCES` enforcement + fail-closed promotion gate + "apps 不得 infer/duplicate/create real adapters"）；④ EOD flow 清晰 docstring 编排图（`jobs/flows/eod.py`）。

**问题**：
- **[Medium] `registry/live/` 认证 driver 簇**（r3_live_acceptance_driver 779/snapshot_builder 745/research_backup 741/r2_certification 719）——过程式 bulk，导入 25+ application/analysis 符号组装 golden/governance/recovery lane。可接受（认证 driver 本质过程式），但偏大。
- **[Low] `r3_live_acceptance_driver.py:220` `**payload` type:ignore**（未类型化 payload 解包）。

---

## 3. 跨切面发现

### 3.1 [ARCH-002] 800 行硬上限诱发"贴线切分"

全仓文件行数分布：`>800` = **0**；`750–800` = **31**；`700–749` = 33；`600–699` = 34。750–800 带聚集（31）显著高于相邻带且 0 超限——典型"凑门禁"分布，集中在 application(15)/analysis(6)/apps(5)。

**诊断**：800 行护栏本身是好的，但当单一职责模块被切成 A/B/C 三段（如 analysis 的 writer(800)+reader(792)+_holdout(796) 同属一存储子域），就把**内聚度换成了门禁通过**。

**修复**：补一条**语义门禁**——同目录 ≥3 文件且两两强耦合（互引高频 + 共享私有 helper）时警告；或改"文件 ≤800 且模块（目录）≤3000"双层约束。

### 3.2 类型纪律

`type:ignore` 11 处分类：strategy 9 处（sqlite row mapper，可一次性消除）+ application 1（cast("object") 逃逸）+ apps 1（**payload）。`noqa` 86 处经核实基本合理（data 28 个 S608 sqlite 标识符误报 + 正则二次防注入；3 个 PLC0415 错误路径懒加载）。**无 Any 滥用掩盖**。

### 3.3 命名一致性

`bar` 统一（无 kline/candle）；`instrument_id` 规范（1792 处）vs `ticker`（318，字符串符号次级）；`qty`(29)/`quantity`(235) 多为局部简写；仅 3 处合理技术术语 adapter 命名。**整体优秀**。

### 3.4 测试质量

test/src ≈ 1.32 健康；kernel/execution >2.0；12,177 单测 189s 全绿；唯一 xfail 附完整根因（负责任披露）。**结构性缺口**：analysis 多个 800 行关键文件无专属单测（仅间接覆盖）；全仓无 property-based/mutation testing。

---

## 4. 业界横向对标

### 4.1 能力矩阵（vs QuantConnect LEAN / NautilusTrader / Zipline / kdb+）

| 能力 | 业界顶尖 | Ditto 现状 | 差距 |
|------|---------|-----------|------|
| **架构边界纪律** | LEAN contracts（较弱） | 37 forbidden 契约 + arch-smell + strict pyright | **Ditto 更强** |
| **PIT 正确性** | kdb+/Databento 版本化 | knowledge_date 版本化 + freeze + fail-closed | **机构级，优于多数** |
| **研究→生产治理** | LEAN Alpha Streams 审核 | R3 hard-gate（11 gate + evidence hash + promotion 三层 identity） | **Ditto 更严** |
| **Money/Decimal 精度** | NautilusTrader 全 Decimal | FeeSchedule 全 float | **弱**（kernel 缺原语） |
| **凸优化（MVO QP）** | cvxpy/cvxopt | 对角协方差近似（Protocol 就位） | Medium |
| **风险平价/BL/HRP** | 旋转投资/HRP | 无 | Medium |
| **算法执行（TWAP/VWAP/POV）** | LEAN 标配 | 无（仅 MARKET/LIMIT） | Medium |
| **向量化回测快通道** | Zipline/event 双路 | 仅 event-driven | Low（日频可接受） |
| **tick/L2/实时数据** | kdb+/Databento | 仅日频 bar | Low（定位） |
| **实时 pre-trade 风控** | 流式风控引擎 | 逐单 PreTradeCheck + 日级 PostTrade | Low（日频可接受） |
| **VaR/压力测试** | RiskMetrics/BARRA | 无 | Medium（T1 需补） |
| **归因分析** | Brinson/Fama-French | Fama-MacBeth + 归因 + 暴露 已有 | **已覆盖** |
| **AI / Agent runtime** | LLM Copilot / Agentic 发现 / 决策 Agent | 0★（情绪因子桥接曾撤回） | **战略级头号缺口**（定位支柱，非推迟项） |

### 4.2 对标结论

- **vs LEAN**：Ditto 架构纪律与 PIT 治理**更强**，但能力广度（凸优化/算法执行/多账户）更窄。LEAN 更成熟全面，Ditto 更 disciplined 但 narrower。
- **vs NautilusTrader**：不同 tier——Nautilus 面向 HFT/live（Money/Decimal 一等公民、超低延迟事件循环），Ditto 面向日频 EOD。但 Ditto 的 kernel 应借鉴 Money/Decimal 原语。
- **vs Zipline**：Zipline 更简单、纪律弱；Ditto 的 R3 研究治理远超 Zipline。
- **vs kdb+/Databento（数据）**：Ditto 的 PIT 版本化 + promotion 治理达机构级，但 SQLite 写锁是规模化天花板。

**定位判断（按正确北极星）**：对标「A 股 ETF + 个股 + 选股 → 全资产 + AI/Agent」这一真实定位，Ditto 的**工程地基强**（门禁/PIT/研究治理/DSL 均为 AI 接入的优质接缝），但**能力完整度仍有实质缺口**：AI/Agent 支柱 0★、多资产微结构抽象待建、个股 universe 规模化与主动/算法执行能力偏薄。缺口多为"加法"而非"重构"——R3 治理门禁与 features DSL 天然是 AI 安全接入的护栏与靶点。

---

## 5. 优先修复路线图（ROI 排序）

### P0（正确性，立即）
1. **修 backtest 指标瑕疵**（CORR-001）：Sortino 自由度统一（`statistics_returns.py:159`）+ turnover 单向口径 + 分母统一（`statistics_trades.py:200-211`）。**风险**：错误的绩效指标会误导策略选择。
2. **补 `engine_runtime.py` 测试**：202 行运行时组装零覆盖。
3. **修 `RealtimeClock` naive datetime**（`clock.py:67`）：5 分钟修复，避免 live TypeError。

### P1（结构性，本季度）
4. **重构 `application/processes/experiments`**（ARCH-001/002）：按业务子域重组为子包，消除 ~800 行碎片；评估拆出 `research_runtime` 独立包收缩 application 体积。**最高 ROI 结构性投资**。
5. **引入 typed row mapper 消除 strategy 9 处 type:ignore**（`strategy_governance_store.py`）：低成本高收益，全仓 type:ignore 从 11→2。
6. **补统一 HTTP client + tenacity/limits 封装**（platform）：兑现 CLAUDE.md 已允许的依赖承诺，消除 data 源网络调用重复。

### P2（能力，R3/R4 路线图）
7. **R4 凸优化器接入**（CAP-001）：`FullCovarianceProvider` + cvxpy `ConstrainedMVOSolver`（long-only + max_weight + sector + turnover），复用现有 Protocol，portfolio 边界零改动。
8. **统一 `RiskGate` Protocol + VaR/压力测试**（CAP-002）：backtest/paper 共用运行时风控抽象。
9. **kernel 引入 Money/Decimal + OrderStatus + Symbol**：精度根基投资，对标 NautilusTrader。

### P3（债务清理，持续）
10. 删除 `Dataset` 枚举尸体；消除 tushare 双 API 重复；统一 PIT 不变量到单一真源；修 `_evict_count` 死指标 + `SafeGauge` 并发；清理 execution `trade_builder` 死参数/非确定性。

---

## 6. 验证命令（复现）

```bash
pixi run -e dev arch-check          # 37 contracts kept, 0 broken
pixi run -e dev type                # 0/0/0
pixi run -e dev lint                # All checks passed
pixi run -e dev test --unit --fast  # 12177 passed, 1 xfailed

# 风险信号复核
grep -rE "TYPE_CHECKING" packages/*/src --include='*.py' | wc -l   # 2
grep -rE "# *type: *ignore" packages/*/src --include='*.py' | wc -l  # 11
grep -rEn "^(import pandas|from pandas)" packages/*/src --include='*.py' | wc -l  # 0

# 800 行贴线检测
find packages/*/src -name '*.py' -exec wc -l {} + | awk '$1>=750 && $1<=800' | wc -l  # 31
```

---

## 附录 A：检查项清单

| 类别 | 项 | 结果 |
|------|-----|------|
| 架构约束 | 层级穿透 / 循环依赖 / R8 互斥 / 反向依赖 | ✅ 37 契约全 KEPT |
| 设计结构 | SRP / 文件规模 / 模块划分 / 命名 | ✅ 总体良好（experiments/processes 例外） |
| 依赖合规 | 禁止库 / 允许库 / 包管理 | ✅ pandas 0、polars/orjson/fastapi/prefect/pixi 合规 |
| 工程实践 | TYPE_CHECKING / type:ignore / 死代码 / Any 滥用 | ✅ 极低（2/11/2/0） |
| 测试质量 | 可运行性 / 覆盖率 / 密度 | ✅ 12177 pass、branch 强制、1.32x |
| 命名概念 | 同义多述 / 风格 / 术语泄漏 | ✅ bar 统一、轻微 qty/quantity |

## 附录 B：本审计深读的关键文件（证据基线）

kernel（全量 16 文件）· platform（observability/config/cache/storage/db 全子域）· data（PIT policy/财报映射/catalog metadata/tushare source/CQRS 基类/治理闭环）· features（core_daily_contracts/expression compiler+codegen/evaluation report）· strategy（pipeline/governance_store/node_registry）· portfolio（optimization/account/position/constraints）· risk（checks/pre_trade）· execution（executor/recording/trade_builder/target_diff）· backtest（engine/statistics/simulation fill/replay/runtime_state）· analysis（preflight_authority/gates/hard_gate_collector/persistence/storage 读写/holdout）· application（R8 配置/coordinator/commands/providers/strategy_spec_deserialization）· apps（r3_live drivers/eod flow/registry composition/routes）· 全仓（.importlinter/pyproject/CI）
