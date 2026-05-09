# 全模块逐文件深度审查计划

> 日期：2026-05-08
> 目标：逐模块、逐文件审查全部 827 个源码文件，在扩展性、理解性、可读性、一致性、整洁架构划分及优雅代码实现上追求卓越
> 方法：自底向上，6 维度评估，3 档优先级
> 基准：`docs/reviews/audit/2026-05-07-comprehensive-architecture-evaluation.md` + 业界最佳实践对标

---

## 1. 审计框架

### 1.1 六维度评估（每维度 1-5 分）

| 维度 | 评估内容 | 5 分标准 |
|------|---------|---------|
| 命名精确性 | 类/函数/变量命名是否唯一表达意图，后缀是否与职责匹配 | 同一概念在包内只有一种叫法；后缀稳定表达层级 |
| 职责单一性 | 文件/类/函数是否只做一件事，放置是否在正确归属 | 每个文件表达一个职责，无错放概念 |
| 抽象边界 | Protocol 归属是否正确，依赖方向是否干净，port 是否消费者拥有 | 跨包对话全部通过消费者 port，无实现侧语言泄漏 |
| 代码优雅度 | 无死代码/冗余分支/过度抽象，数据流清晰，pattern 一致 | 每行代码都有存在理由，控制流直觉可读 |
| 可扩展性 | 新增能力是否只需改一处，是否支持多 adapter，是否留有 seam | 开放扩展关闭修改，新增市场/资产类/数据源改动 ≤ 3 处 |
| 测试覆盖 | 测试是否验证行为而非实现，是否覆盖边界和异常路径 | 每个公共行为有对应测试，mock 最小化 |

### 1.2 三档优先级

| 级别 | 含义 | 处理要求 |
|------|------|---------|
| **P0** | 概念错放、命名混淆、职责越界 | 必须修复 |
| **P1** | 抽象可优化、代码可精简、可读性可提升 | 应当修复 |
| **P2** | 命名微调、注释补充、风格统一 | 建议修复 |

### 1.3 审查路线图

```
Phase 1: 基础层（2 模块，28 文件，~7.2K LOC）
  kernel      → 16 文件,  1,507 行
  platform    → 51 文件,  5,661 行

Phase 2: 领域能力层（5 模块，111 文件，~12.5K LOC）
  portfolio   → 21 文件,  1,717 行
  risk        → 18 文件,  1,372 行
  execution   → 35 文件,  2,981 行
  strategy    → 48 文件,  5,321 行
  analysis    → 19 文件,  1,116 行

Phase 3: 数据与计算层（3 模块，406 文件，~50K LOC）
  features    → 105 文件, 14,625 行
  backtest    → 31 文件,  4,686 行
  data        → 270 文件, 30,690 行

Phase 4: 编排与入口层（2 模块，213 文件，~30K LOC）
  application → 104 文件, 18,315 行
  apps        → 109 文件, 12,094 行
```

---

## 2. Kernel 审计报告（Phase 1 第 1 模块）

### 2.1 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 16 |
| 源码行数 | 1,507 |
| 测试文件 | 17 |
| Protocol 数 | 6 |
| Service 数 | 0 |
| `__all__` 导出 | 30 |
| 外部依赖 | 0（纯标准库） |
| 被引用次数 | 432（11 个包全部依赖） |

### 2.2 根因分析：为什么领域概念会泄漏进 kernel

**根因 1：准入门槛是"2+ 包需要"而非"全系统通用原语"**

隐性规则变成了"如果有两个以上包需要某个类型，就放 kernel"。publication_safety（features+application 需要）和 quality（data+application+apps 需要）因此被错误准入。

正确标准：不是"多少人用"，而是"这个类型是否表达了超越任何单一领域的系统级原语"。InstrumentId 是系统级原语；DQIssue 是 data 领域的业务类型。

**根因 2："共享内核"被误解为"公共抽屉"**

DDD 的 Shared Kernel 原意是"两个 bounded context 显式协议共享的一小部分模型"。实践中 kernel 变成了"谁都不想拥有的类型的默认归宿"。DerivedSpec 没有明确领域所有者，于是被放进 kernel。

**根因 3：跨包依赖被 kernel 绕过**

当 features 需要被 application 引用 publication_safety 类型时，正确做法是 features 暴露公共 API。但直接放 kernel 更"方便"——不需要处理跨包 API 设计和 import-linter 豁免。

**根因 4：命名相似性导致归属误判**

- `DerivedSpec` 听起来像"策略衍生品"，实际是"特征物化规格"
- `DerivedRole.FEATURE/FACTOR/SIGNAL/LABEL` 的枚举值已明确指向 features 领域
- `MaterializationProfile` 听起来通用，实际是 features 独有概念

**根因 5：缺少自动化准入门禁**

smell checker 覆盖了 17 类语义 smell，但不包含"kernel 只能包含以下类别"的白名单检查。

### 2.3 优化后的 Kernel 准入规则

#### 只允许包含的 5 类符号

| 类别 | 定义 | 合格示例 | 不合格示例 |
|------|------|---------|-----------|
| 身份标识 | NewType / 纯标识符，零行为 | InstrumentId | — |
| 通用枚举 | 跨 3+ 领域的通用分类，不含领域逻辑 | OrderSide, AssetClass | DerivedRole, MacroFrequency |
| 基础设施 Protocol | 运行时基础设施接口，非业务行为 | Clock, EventBus | MacroDataProvider, DecisionFrame |
| 通用异常层级 | 仅根异常 + 第一层子域异常 | DittoError → DataError | DerivedError 层级 |
| 零行为值对象 | frozen dataclass，纯数据载体，无领域方法 | MarketSnapshot | Publication safety records |

#### 三条硬性准入测试

1. **"去掉它"测试**：删除后是否有 3+ 个不同领域能力包（非 application/apps）同时需要定义它？
2. **"换名字"测试**：去掉领域前缀（Derived/DQ/Research/Publication）后是否仍有意义？
3. **"零依赖"测试**：是否不依赖 kernel 之外的任何业务概念？

#### 建议新增的自动化门禁

- kernel 文件白名单守卫（新增文件必须显式注册）
- barrel 导出数 ≤ 20
- 禁止包含 `to_json_dict`/`from_json_dict` 方法的 dataclass（领域行为标志）
- 禁止包含运行时校验函数（require_*/validate_*）

### 2.4 P0 级发现（3 项，必须修复）

| ID | 文件 | 行数 | 问题 | 目标归属 |
|----|------|------|------|---------|
| K-P0-1 | `publication_safety.py` | 233 | features 领域的"影子发布安全"记录类型，20 次外部引用中 features 占 14 次 | `ditto_features.publication_safety` |
| K-P0-2 | `quality.py` | 105 | data 领域的数据质量类型（DQIssue/DQResult/DQLevel/DQSeverity），13 次引用中 data 占 7 次 | `ditto_data.quality`（已有子包） |
| K-P0-3 | `research.py` | 79 | analysis 领域的研究数据集记录类型，5 次引用中 analysis 占 4 次 | `ditto_analysis.domain` |

**迁移后影响**：kernel 从 1,507 行降至 ~1,090 行（-28%），3 个领域泄漏文件彻底清除。

### 2.5 P1 级发现（5 项，应当修复）

| ID | 文件 | 问题 | 动作 | 目标归属 |
|----|------|------|------|---------|
| K-P1-1 | `strategy.py` | DerivedSpec/DerivedRole 是 features 领域概念；MaterializationProfile→MaterializationMode, ExecutionPolicy→PitPolicy | 拆分迁出 + 重命名两个 | `ditto_features` |
| K-P1-2 | `trading.py` | DEFAULT_COMMISSION_RATE 等常量和 default_price_limit_pct() 是 A 股业务逻辑 | 迁出常量和函数 | `ditto_execution` 或 `ditto_backtest` |
| K-P1-3 | `json_types.py` | 整体（类型别名 + require_* 函数）属于横向技术基础设施 | 整体迁移 | `platform.foundation` |
| K-P1-4 | `exceptions.py` | DerivedError → DerivedNotFoundError/VersionError/NotImplementedError/ValidationError 是 features 领域专用异常 | 拆分迁出 | `ditto_features.exceptions` |
| K-P1-5 | `market.py` | MacroDataProvider Protocol 只被 data.macro 实现和使用 | 迁出 | `ditto_data.macro` 或消费者 port |

### 2.6 架构级发现（3 项）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-kernel-review.md`
> 以下发现超越代码级清理，涉及 kernel 在运行时架构中的角色定位

| ID | 问题 | 说明 | 建议 | 时机 |
|----|------|------|------|------|
| K-ARCH-1 | 事件载荷无类型安全 | `DomainEvent(event_type: str, payload: dict[str, Any])`，backtest 发布 `order_submitted`/`order_filled`/`risk_guard_triggered` 等字符串事件。schema drift 无法被类型检查捕获 | 领域包拥有类型化事件记录 + event-name catalog；kernel EventBus 保持纯传输 | Runtime Spine 设计启动时 |
| K-ARCH-2 | 市场规则默认值散落 | `trading.py` 含 A 股默认值（`DEFAULT_COMMISSION_RATE`、`default_price_limit_pct`），跨 execution/backtest/risk 使用。kernel 不应成为市场规则包 | 冻结当前 DTO 为过渡共享语言，市场规则语义向 reference provider 迁移 | Execution OMS/rules provider 定义时 |
| K-ARCH-3 | Derived* 异常归属模糊 | `DerivedError` 层级在 kernel 但仅 data/features 使用，package type table 未列出。未来 agent 可能在 kernel 添加更多领域异常 | 文档化为 deliberate shared boundary 或随 K-P1-4 迁出 | K-P1-4 执行时 |

### 2.7 P2 级发现（3 项，建议修复）

| ID | 文件 | 问题 | 建议 |
|----|------|------|------|
| K-P2-1 | `__init__.py` | barrel 导出 30 个符号偏多 | P0+P1 迁移后精简至 ~15 个，其余引导从叶模块导入 |
| K-P2-2 | `instrument.py` | InstrumentIngestParams 属于 data 摄取流程概念 | 迁至 `ditto_data`（影响面小，可延后） |
| K-P2-3 | 各文件 | 准入依据注释需统一更新 | 迁移完成后统一更新每个保留文件的注释 |

### 2.8 迁移后 kernel 理想状态

```
ditto_kernel/
├── __init__.py          # barrel, ~15 个核心符号
├── identity.py          # InstrumentId (不变)
├── instrument.py        # AssetClass, Exchange (不变)
├── order.py             # OrderSide, OrderType (不变)
├── market.py            # CalendarId, GrainId, TimeSpec, 枚举 (去掉 MacroDataProvider)
├── strategy.py          # RiskScope, RunStatus, ImpactModel, DecisionFrame (精简后)
├── trading.py           # 值对象 + Protocol (去掉常量和默认值函数)
├── clock.py             # Clock Protocol + 实现 (不变)
├── events.py            # DomainEvent + EventBus (不变)
├── exceptions.py        # DittoError → DataError → IdentifierError (去掉 DerivedError)
├── tracing.py           # traced 装饰器 (不变)
└── math.py              # pearson_correlation (不变)
```

16 文件 / 1,507 行 → 12 文件 / ~900 行

---

## 3. Platform 审计报告（Phase 1 第 2 模块）

### 3.1 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 38 |
| 源码行数 | ~5,500 |
| 测试文件 | 41 |
| Protocol 数 | 4 (DatasetReader/Writer, SqliteReader/Writer) |
| Service 数 | 0 |
| 外部依赖 | 13 个（loguru, polars, pydantic, opentelemetry 等） |
| 被引用次数 | 293（7 个包，data 占 62%） |
| 领域泄漏 | **零**（smell guard 已验证） |

### 3.2 P1 级发现（5 项）

| ID | 问题 | 说明 |
|----|------|------|
| PL-1 | 直接引用内部子模块 | 62 处 `foundation.storage.sqlite_client`、9 处 `foundation.storage.types`、8 处 `foundation.config.*` 深层、7 处 `services.notification.*` 深层。应统一走 `__init__.py` 公共 API |
| PL-2 | SQL 标识符注入风险 | `SQLiteClient.count(table, where)` 直接插值 table/where 字符串，安全依赖调用方约定。平台提供可复用的安全漏洞入口：一个未校验的调用方可将共享 helper 变为 SQL 注入向量。应增加标识符校验/值对象或受约束的 query builder |
| PL-3 | parquet_store.py 769 行 | 全库第二大文件。如果继续增长，可拆分元数据操作到 `ParquetMetadata` |
| PL-4 | paths.py 废弃函数 | `get_paths()`/`reload_paths()`/`reset_paths_for_testing()` 已废弃但仍存在，应删除 |
| PL-5 | application scope 违规 | `forward_return_service.py` 引用 `foundation.config.get_environment`，违反 "application 禁止 config" 规则 |

### 3.3 架构级发现（2 项）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-platform-review.md`

| ID | 问题 | 说明 | 建议 | 时机 |
|----|------|------|------|------|
| PL-ARCH-1 | 通用存储使用领域术语 | `ParquetStore` 文档/示例使用 `data_root/dataset/YYYY.parquet`、`instrument_column`、daily market datasets 等数据领域词汇 | 平台 API/文档重定向到 `namespace`/`collection`/`key_column`；市场示例留在 data 文档 | data storage 审查时 |
| PL-ARCH-2 | SQL/noqa 分散 | 多个 storage/runtime helper 使用插值 table/where 字符串，安全依赖大量本地 `S608` allowlist 注释 | 维护 SQL/noqa budget，将标识符校验提取到共享 helper | PL-2 修复时 |

### 3.4 P2 级发现（4 项）

| ID | 问题 | 建议 |
|----|------|------|
| PL-6 | NotificationSender 使用 ABC 非 Protocol | 改为 Protocol 保持全库一致性 |
| PL-7 | 残留 `.pyc` 缓存 | `foundation/util/__pycache__/ticker_utils.cpython-313.pyc` 应清理 |
| PL-8 | 空 templates 目录 | `services/notification/templates/` 清理或标注 reserved |
| PL-9 | metrics.py 535 行复杂度 | 预定义指标和注册 API 可拆到独立文件 |

### 3.4 CLAUDE.md 规则优化

**文档与代码不一致（需修正）**：

| 位置 | 文档写法 | 实际代码 | 应改为 |
|------|---------|---------|--------|
| 导入规范 | `from ditto_platform.foundation import get_logger` | 导出是 `logger`（loguru 实例） | `from ditto_platform.foundation import logger` |
| 导入规范 | `from ditto_platform.services.notification import NotificationManager` | 类名是 `AlertManager` | `from ditto_platform.services.notification import AlertManager` |
| 目录结构 | `util/ # 通用工具（日期、IO、校验和、Ticker）` | `ticker_utils.py` 已删除 | 删除 "Ticker"，改为"日期、IO、校验和" |
| L86-87 | 多余的闭合围栏 ` ``` ` + `└─────┘` | 格式错误 | 删除多余行 |

**缺失规则（需新增）**：

1. **公共 API 导入纪律**——禁止绕过 `__init__.py` 的深层引用：
   ```python
   # ❌ 错误：绕过公共 API
   from ditto_platform.foundation.storage.sqlite_client import SQLiteClient
   from ditto_platform.foundation.storage.types import OnDuplicate
   # ✅ 正确：通过子模块公共入口
   from ditto_platform.foundation.storage import SQLiteClient, OnDuplicate
   ```

2. **services.notification scope**——notification 仅限 apps（注册装配）和 application（流程编排）使用。

3. **application config 禁止范围精确化**——禁止 `foundation.config.*` 的所有导入（包括 `get_environment`、`Settings`、`find_project_root`），环境信息通过参数或 DI 传入。

4. **foundation.storage 公共 API 边界**——所有 storage 消费者必须通过 `from ditto_platform.foundation.storage import ...` 导入。

---

## 4. Portfolio 审计报告（Phase 2 第 1 模块）

### 4.1 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 21 |
| 源码行数 | 1,717 |
| 测试文件 | 15 |
| Protocol 数 | 11 |
| Service 数 | 0 |
| 外部依赖 | kernel + polars |
| 被引用次数 | 34（backtest 15, risk 7, execution 7, application 4, apps 1） |
| frozen dataclass 率 | ~95%（仅 Account/OrderBook 可变） |

### 4.2 P0 级发现（1 项）

| ID | 问题 | 说明 | 修复方案 |
|----|------|------|---------|
| PF-0 | RebalanceTarget.positions vs TargetPortfolio.weights | Protocol 要求 `positions` 属性，DTO 定义 `weights` 属性。**TargetPortfolio 不满足 RebalanceTarget Protocol** | 统一为 `weights`（更精确描述 0-1 权重百分比） |

### 4.3 P1 级发现（5 项）

| ID | 问题 | 建议 |
|----|------|------|
| PF-1 | Account.positions 缺防御性保护 | 内部改 `_positions` + property 返回只读视图 |
| PF-2 | Account.apply_fill() 非原子操作 | 先计算新状态再统一赋值，或文档声明异常恢复责任 |
| PF-3 | 公共 API 零使用 | 34 条 import 全用深层路径。建议新增 import-linter contract 强制走公共 API |
| PF-4 | contracts.py Protocol 零外部消费 | PortfolioStateReader/RebalanceTarget 无消费者。是过度设计或尚未采纳 |
| PF-5 | StateTransitionError 双重暴露 | 在 errors.py 和 accounting/__init__.py 两处导出。建议只在 errors.py 暴露 |

### 4.3.1 架构级发现（3 项）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-portfolio-review.md`

| ID | 问题 | 说明 | 建议 | 时机 |
|----|------|------|------|------|
| PF-ARCH-1 | 缺少状态快照/恢复契约 | Account 可在内存中 apply_fill，但无 portfolio 拥有的 snapshot/journal restore contract。execution 也没有 OMS journal。崩溃恢复无法独立重建 portfolio/accounting 状态 | 定义 portfolio state snapshot/projection contract，消费 execution journal/fill events | OMS Lite 完成后 |
| PF-ARCH-2 | positions/holdings/target_portfolios 仅为 DTO/Protocol | 无 runtime/store 实现，文档和包名暗示了更丰富的状态管理能力 | 标注 experimental/reserved 直到有最小 runtime path，或实现最小 store/projection | Runtime Spine 设计时 |
| PF-ARCH-3 | PositionChanged 事件未发射 | 显式标注为 reserved，`Account.apply_fill` 不发射事件。事件流无法证明账户持仓转换 | 从 accounting transitions 发布类型化事件，或保持 reserved 标注于成熟度文档 | K-ARCH-1 event catalog 完成后 |

### 4.4 P2 级发现（4 项）

| ID | 问题 | 建议 |
|----|------|------|
| PF-6 | SELL 路径未检查 available_quantity >= qty | 增加边界检查，防负值 |
| PF-7 | ScoreWeightAllocator.min_weight 权重可能超标 | min_weight 应用后需重新归一化 |
| PF-8 | sentinel 时间戳 datetime(2026,1,1) | 改为 None + 必填约束 |
| PF-9 | metrics.py instrument_name → metric_name | 字段名不精确 |

### 4.5 CLAUDE.md 规则优化

**文档与代码不一致（需修正）**：

| 位置 | 文档写法 | 实际代码 | 应改为 |
|------|---------|---------|--------|
| 典型导入 L90 | `from ditto_portfolio.rebalancing.constraints import check_constraints` | 无此函数；实际 API 是 `ConstraintChecker` | `from ditto_portfolio.rebalancing import ConstraintChecker` |
| 典型导入 L94 | `from ditto_portfolio.events import PortfolioEvent` | 类名是 `PositionChanged`，且标注为"预留" | `from ditto_portfolio.events import PositionChanged` |
| 典型导入 L86-87 | 鼓励深层路径 `accounting.account import Account` | 34 处全部用深层路径 | 改为推荐 `__init__.py` 公共 API |

**缺失规则（需新增）**：

1. **公共 API 导入纪律**——推荐通过子包 `__init__.py` 导入：
   ```python
   # ✅ 推荐：通过子包公共入口
   from ditto_portfolio.accounting import Account, AccountView, Order
   from ditto_portfolio.rebalancing import EqualWeightAllocator, ConstraintChecker
   # ⚠️ 允许但非推荐：直接引用内部文件
   from ditto_portfolio.accounting.account import Account
   ```

2. **Account 可变性契约**——`Account` 是有状态容器，仅限 Brokerage/StateOwner 持有并修改。`Account.positions` 为内部可变 dict，外部不应直接修改。`AccountView` 是不可变快照，所有字段只读。

3. **contracts.py Protocol 消费指导**——`PortfolioStateReader`（execution/risk 读取账户状态）和 `RebalanceTarget`（strategy 传递调仓目标）是面向消费者的契约。当前消费者直接使用具体类，Protocol 是 live/paper runtime 的 seam。

4. **持仓子包职责区分**——
   - `accounting.position.Position`：交易生命周期持仓（average_cost, quantity, available_quantity）
   - `holdings.HoldingSnapshot`：估值视角快照（market_value, weight）
   - `positions.PositionSnapshot`：管理视角持仓（status, average_cost）
   - `target_portfolios.TargetPortfolio`：策略产出的目标权重配置

---

## 5. Risk 审计报告（Phase 2 第 2 模块）

### 5.1 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 18 |
| 源码行数 | 1,372 |
| 测试文件 | 22 |
| Protocol 数 | 5（其中 2 个零消费） |
| Service 数 | 0 |
| 外部依赖 | kernel + portfolio（+ polars/orjson 声明但未使用） |
| 被引用次数 | ~30（仅 backtest/application/apps） |
| frozen dataclass 率 | ~90% |

### 5.2 P1 级发现（5 项）

| ID | 问题 | 说明 | 建议 |
|----|------|------|------|
| RK-1 | contracts.py Protocol 冗余 | RiskSlice/PostTradeGuard 与 post_trade.py 的 SliceView/PostTradeRiskGuard 功能完全相同，零消费者 | 删除 contracts.py 冗余 Protocol，统一到 post_trade.py |
| RK-2 | checks.py 319 行三层混合 | 1 Protocol + 5 规则 + 1 组合器 + 1 helper | 提取 Protocol 到 context.py，提取组合器到 composite.py |
| RK-3 | models.py 三个模型完全未使用 | RiskMetrics/ExposureData/DrawdownStats 无消费者 | 删除或标注 reserved |
| RK-4 | _accept() helper 重复定义 | constraints/checks.py 和 exposure/checks.py 各一个 | 提取到 _validation.py |
| RK-5 | 虚假依赖 | pyproject.toml 声明 polars/orjson 但源码从未导入 | 移除未使用依赖 |

### 5.3 P2 级发现（4 项）

| ID | 问题 | 建议 |
|----|------|------|
| RK-6 | 空 post_trade/ 目录残留 | 删除 |
| RK-7 | CLAUDE.md 列出不存在的顶层 rules.py | 更新文档 |
| RK-8 | RiskAction.target_quantity 从未被填充 | 评估 seam 或删除 |
| RK-9 | MaxDrawdownRule 硬编码中文字符串 | 评估国际化或提取常量 |

### 5.4 架构级发现（3 项）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-risk-review.md`

| ID | 问题 | 说明 | 建议 | 时机 |
|----|------|------|------|------|
| RK-ARCH-1 | 缺少统一 Risk Gate 契约 | Pre-trade/post-trade API 存在，但可执行的 gate 被嵌入 backtest steps 和 application wiring，无共享 runtime contract。Paper runtime 可能绕过或复制风控序列 | 定义一等 `RiskGate`/decision event contract，backtest 和 paper 共用 | Runtime Spine 设计时 |
| RK-ARCH-2 | 有状态风控无快照/恢复 | `MaxDrawdownRule` 存储 `_peak_nav`；strategy locks/cooldowns 在 `StrategyContext`。均无持久化快照/恢复契约 | 为有状态规则增加状态快照/恢复测试 | OMS Lite + Runtime Spine 后 |
| RK-ARCH-3 | 风控事件载荷无类型 | `RiskGuardTriggered` 含 `details: dict[str, Any]`；审计记录在其他地方组装 | 引入类型化 risk decision/audit payloads，映射到 event-name catalog | K-ARCH-1 event catalog 完成后 |

### 5.5 CLAUDE.md 规则优化

**文档与代码不一致（需修正）**：

| 位置 | 问题 | 应改为 |
|------|------|--------|
| 目录结构 | 列出顶层 `rules.py`，实际不存在 | 规则分布在 constraints/exposure/drawdown 子包 |
| 目录结构 | 未提及 `_validation.py` | 补充"内部参数校验工具" |

**缺失规则（需新增）**：

1. **Protocol 归属明确化**——`PreTradeRiskCheck` 和 `PostTradeRiskGuard` 是 risk 核心接口，由 risk 定义、消费者依赖。`contracts.py` 的冗余版本应在清理后删除。
2. **风控不是 runtime 组件**——当前只是 pre-trade 逐单校验 + post-trade 日终扫描。未来向 continuous risk 演进时，risk gate 应嵌入 order submit/modify/fill path。
3. **规则覆盖度标注**——当前 PreTrade 覆盖 6 条、PostTrade 覆盖 4 条。缺失项（停牌校验、行业暴露度 PreTrade、波动率监控等）应标注为 P2/P3 roadmap。

---

## 6. Execution 审计报告（Phase 2 第 3 模块）

### 6.1 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 35 |
| 源码行数 | 2,981 |
| 测试文件 | 23 |
| Protocol 数 | 10（其中 3 个零消费） |
| Service 数 | 2（ExecutionAuditService, TradeService） |
| 外部依赖 | kernel + portfolio + platform + dishka + orjson |
| 被引用次数 | ~43（application 20, backtest 22, apps 1） |

### 6.2 P1 级发现——代码级（5 项）

| ID | 问题 | 说明 | 建议 |
|----|------|------|------|
| EX-1 | TradeAuditor Protocol 不完整 | contracts.py 只有 2 方法，实现有 4 方法 | 重命名为 ExecutionAuditor 并补全方法 |
| EX-2 | planner.py 530 行 9 种职责 | diff/预检/T+1/100+1/订单创建混在一起 | 规则应用拆为独立模块，planner 只做 diff-to-plan |
| EX-3 | TradeService 跨层穿透 | application 6 处直接引用 SQLite 实现类 | 通过消费者 port 访问 |
| EX-4 | FillStore 与 FillReceiver 重叠 | 两个 Protocol 表达同一概念 | 合并为 FillStore，删除 FillReceiver |
| EX-5 | CLAUDE.md 严重过时 | 列出不存在的 6 个 reality 子模块 | 更新为实际目录结构 |

### 6.2.1 P1 级发现——架构级（4 项，OMS Lite 核心）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-execution-review.md`
> 以下发现是 paper/live 交易的硬阻塞，优先级高于代码级清理

| ID | 问题 | 说明 | 建议 | 前置条件 |
|----|------|------|------|---------|
| EX-ARCH-1 | OMS 身份与 journal 缺失 | 有 `OrderStore` Protocol 和 `OrderRecord`，但无 `ClientOrderId`/`BrokerOrderId`/`OrderJournal`/状态转换表/幂等键。Paper/live 订单恢复无法证明提交、确认、部分成交、取消、拒绝、重放 | 定义 OMS Lite：身份类型、状态转换表、append-only journal、幂等键，向 portfolio/risk 暴露窄视图 | 无 |
| EX-ARCH-2 | 填充/审计/对账表互不关联 | `execution_fills`/`trade_intents`/`actual_positions`/`execution_audit` 有 CRUD/audit 路径，但无 broker order id、client id、fill id、journal sequence、reconciliation result 的关联 | 以 OMS journal 为 spine，fill/audit/reconciliation 引用 journal/client/broker ids | EX-ARCH-1 |
| EX-ARCH-3 | BrokerGateway 无可执行适配器 | `BrokerGateway` 是 Protocol，`broker/gateways` 仅有占位符。唯一具体 brokerage 实现是 backtest 拥有的模拟撮合 | 添加确定性 paper/mock gateway harness（不改 backtest brokerage） | EX-ARCH-1 |
| EX-ARCH-4 | 市场规则语义散落 | A 股规则行为分散在 execution planner/reality/rules 和 backtest default rules，kernel 仍含共享交易默认值 | 与 K-ARCH-2 协调：venue/reference 语义统一向 reference provider 迁移 | K-ARCH-2 |

**Execution 整改策略调整**：代码级清理（EX-1~5）作为 OMS Lite 的准备工作，先清理再建设。OMS Lite 是 execution 模块的核心交付物。

### 6.3 P2 级发现（4 项）

| ID | 问题 | 建议 |
|----|------|------|
| EX-6 | OrderRecord 在 orders/store.py 而非 models.py | 移至 models.py |
| EX-7 | ExecutionAuditService save 方法 DRY 违反 | 提取通用 save 模板 |
| EX-8 | di/storage.py 两套 schema 初始化模式 | 统一为 dishka 依赖参数 |
| EX-9 | ReconciliationError 定义但从未使用 | 对齐 reconciliation 占位阶段 |

### 6.4 CLAUDE.md 规则优化

**文档与代码不一致（需修正）**：

| 位置 | 问题 | 应改为 |
|------|------|--------|
| reality/ 目录 | 列出 slippage/settlement/fill/market/brokerage/constants 6 个模块 | 实际只有 fee.py |
| broker/ 目录 | 未说明 BrokerGateway 零实现状态 | 标注为"adapter-facing port，待真实券商适配器" |
| OMS 成熟度 | 未标注 | orders/ 是占位符，成熟度 ~5% |
| reconciliation 成熟度 | 未标注 | 仅占位 dataclass，成熟度 ~2% |

**缺失规则（需新增）**：

1. **Protocol 与实现一致性要求**——每个 Protocol 必须覆盖其已知实现的所有公开方法。
2. **跨层引用纪律**——application 禁止直接引用 execution 的 storage/sqlite 实现类，应通过 execution 定义的 Protocol 或 Facade 访问。
3. **planner 职责边界**——执行计划器只做 diff-to-plan 转换，规则应用（T+1、100+1、涨跌停）应是可插拔的规则模块。

---

## 7. Strategy 审计报告（Phase 2 第 4 模块）

### 7.1 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 48 |
| 源码行数 | 5,321 |
| 测试文件 | 29 |
| Protocol 数 | 13（6 storage pairs + 3 contracts + 4 其他） |
| Service 数 | 4（Catalog/Run/Artifact/BacktestReader） |
| 外部依赖 | kernel + platform + dishka + polars + orjson |
| 被引用次数 | 61（application 48, backtest 8, apps 5） |

### 7.2 P1 级发现（5 项）

| ID | 问题 | 说明 | 建议 |
|----|------|------|------|
| ST-1 | 存储层跨层穿透 | application 21 处直接引用 SQLite Service 实现 | 统一 Protocol 接口，application 只依赖 Protocol |
| ST-2 | stock_sector_rotation.py 640 行 | 5 Stage + Config + validate + builder | 拆为 stages.py + config_and_builder.py |
| ST-3 | Benchmark 白名单硬编码 A 股 | 封闭集合，仅 SH/SZ 格式 | 改为可配置/可注册机制 |
| ST-4 | contracts.py Protocol 方法名与 Service 不匹配 | list_specs vs list_all | 统一方法名，使 Service 满足 Protocol |
| ST-5 | 辅助函数重复 | _raise_config_error 在两个模板中重复 | 提取到共享位置 |

### 7.3 P2 级发现（3 项）

| ID | 问题 | 建议 |
|----|------|------|
| ST-6 | traced() span 名称遗留 "engine." 前缀 | 改为 "strategy.pipeline.process" |
| ST-7 | observability/metrics.py 仅 1 个 counter | runtime 化时补全 |
| ST-8 | signals/ 子包极简（45 行） | 标注成熟度 |

### 7.4 架构级发现（3 项）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-strategy-review.md`

| ID | 问题 | 说明 | 建议 | 时机 |
|----|------|------|------|------|
| ST-ARCH-1 | Stage 缺少 schema 契约 | `DecisionStage.process(frame, context) -> frame` 不声明 required/produced columns。schema 检查依赖局部 `validate_frame` 调用。Pipeline 变更可破坏下游 stage 而无机器可读契约 | 增加 stage metadata（`requires`、`produces`、maturity）和 pipeline contract tests | Strategy 模板迭代时 |
| ST-ARCH-2 | StrategyContext 无状态恢复 | 存储 risk locks/cooldowns 和跨日期 positions，无持久化快照/恢复契约。Backtest replay 或 paper restart 可能在锁定/上下文上分叉 | 定义 context snapshot/restore 或将有状态 risk locks 移入共享 risk/runtime state model | RK-ARCH-2 风控状态恢复时 |
| ST-ARCH-3 | 模板成熟度差异未标注 | ETF/stock selection/stock sector 模板共享包 surface，但成熟度差异大。全球全市场能力可能被误判为当前已支持 | 按市场成熟度分级：A股 ETF 已可用、A股个股进行中、全球市场规划中。在成熟度文档/public API 标注 | CLAUDE.md 更新时 |

### 7.5 CLAUDE.md 规则优化

**缺失规则（需新增）**：

1. **存储层消费者隔离**——application 禁止直接引用 `storage.sqlite.services.*` 的具体类，应通过 `contracts.py` 的 Protocol 访问。当前 Protocol 方法名需与 Service 统一。
2. **Benchmark 可扩展性**——新增市场/基准不应修改 `StrategySpec` 源码。白名单应从配置或注册机制加载。
3. **模板拆分标准**——超过 500 行的模板文件应拆分为 stages.py + config_and_builder.py。

---

## 8. Analysis 审计报告（Phase 2 第 5 模块）

### 8.1 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 19 |
| 源码行数 | 1,116 |
| 测试文件 | 10 |
| Protocol 数 | — |
| Service 数 | 2（CatalogService, ArtifactService） |
| 外部依赖 | kernel + platform |
| 被引用次数 | application(4), apps(1) |
| 领域泄漏 | **零**（production-to-analysis imports 和 reserved namespace honesty 由 smell test 守卫） |

### 8.2 P1 级发现（2 项，代码级）

| ID | 问题 | 建议 |
|----|------|------|
| AN-1 | Reserved namespace guard 部分硬编码 | 架构脚本路径/短语硬编码。新增 reserved namespace 可能绕过守卫 |
| AN-2 | Public API 极窄 | `__all__` 仅导出 `AnalysisError`/`ResearchDatasetError`/`ResearchDatasetSpec` |

### 8.3 架构级发现（3 项）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-analysis-review.md`

| ID | 问题 | 说明 | 建议 | 时机 |
|----|------|------|------|------|
| AN-ARCH-1 | Research facade 在 application 层 | `ResearchDatasetFacade` 在 application 中直接 import analysis services/domain。唯一运行时 research 用例被上层拥有，analysis port 可复用性和守卫性降低 | 增加 application-owned research ports 或在 analysis 定义中立 facade contract，application 只做编排 | Application 审查时 |
| AN-ARCH-2 | SHIFT late-arrival policy 语义不诚实 | `SHIFT_TO_NEXT_SNAPSHOT` 当前仅 warn 并返回 unchanged。命名暗示实现了 shift，实际未实现 | 标注 SHIFT policy 为 reserved/unsupported，或实现真实 shift 语义后再暴露 | Research v2 扩展时 |
| AN-ARCH-3 | Research v1 能力边界未标注 | v1 验证 `cn_stock`/`1d`/derived-only inputs，但产品路线图语言暗示全球/全市场支持 | Research control-plane 按市场成熟度分级：A股 daily derived datasets 为当前可用，全球/全频段为规划中 | CLAUDE.md 更新时 |

---

## 9. Phase 3 数据与计算层审计计划

### 9.1 Features 审计报告（105 文件, 14,625 行）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-features-review.md`

#### 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 105 |
| 源码行数 | 14,625 |
| 测试文件 | 33 |
| 外部依赖 | kernel + platform |
| 被引用次数 | ~80（application 主导） |
| 领域泄漏 | **零** |

#### P1 级发现——架构级（3 项）

| ID | 问题 | 说明 | 建议 |
|----|------|------|------|
| FEAT-ARCH-1 | 制品溯源不完整 | Artifacts 记录 `source_snapshot_id`，manifest 记录 `time_semantics_version`，但不使用 DataCatalog asset refs 或共享 `TimeContext`。本地可复现但跨 data/backtest/research 无法统一追踪 | 链接 derived inputs/outputs 到 DataCatalog/Lineage（runtime store 就绪后）；对齐查询截止时间到 `TimeContext` |
| FEAT-ARCH-2 | Time semantics 硬编码 | `time_semantics_version="time-v1"` 硬编码在 application manifest builder；本地 readers 用 `as_of`/effective-time 约定。Time semantics 可在物化/制品读取/research build/runtime query 之间漂移 | 在 ADR 中定义 time semantics；manifest builder 消费版本化共享 constant/config |
| FEAT-ARCH-3 | 表达式前瞻泄漏无标准测试模板 | Expression/operator tests 覆盖 PIT 行为，但无跨 shift/rolling/join/publication cutoff 的标准泄漏测试模板。未来 operator/join 可能意外引入前瞻 | 增加可复用的 PIT leak test harness 用于表达式和 artifact publication reads |

#### P2 级发现（2 项）

| ID | 问题 | 建议 |
|----|------|------|
| FEAT-2 | codegen/evaluator/IC/materialization 大文件多职责 | 用 golden tests 锁定行为后，按关注点拆分 emitters/evaluator |
| FEAT-3 | `features.services` 是宽泛公共命名空间 | 增加 features public API 表或按关注点拆子包 service namespace |

#### CLAUDE.md 规则优化

**缺失规则（需新增）**：
1. **Time semantics 一致性**——所有 PIT 读取（factor/derived/artifact/research）必须使用统一的 time semantics version，禁止本地硬编码
2. **PIT leak test 标准化**——新增 operator/expression 必须通过标准 PIT leak test template

### 9.2 Backtest 审计报告（31 文件, 4,686 行）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-backtest-review.md`

#### 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 31 |
| 源码行数 | 4,686 |
| 测试文件 | 40 |
| 外部依赖 | kernel + data + strategy + portfolio + risk + execution |
| 被引用次数 | ~30（application 22, apps 1） |

#### P1 级发现——架构级（3 项）

| ID | 问题 | 说明 | 建议 |
|----|------|------|------|
| BT-ARCH-1 | Runtime step chain 为 backtest 独有 | `EngineLoop` 内存循环，paper/live seam 不是一等契约。Paper runtime 可能复制 backtest loop 或在 order/risk/fill 序列上分叉 | 提取/文档化共享 backtest/paper runtime seam：data slice → strategy decision → risk → planning → brokerage/gateway → fills → audit |
| BT-ARCH-2 | 直接依赖 data 层 Provider | `ProviderBackedDataFeed` 直接 import `ditto_data.provider.DataProvider` 和 `BarQuery`。消费者绑定数据层接口而非消费者 port | 引入 backtest-owned `HistoricalDataPortal` Protocol（Consumer-Owned Port），在 application boundary 适配 DataProvider |
| BT-ARCH-3 | Replay 覆盖不完整 | Replay 比较 manifest/NAV，但不比较 OMS journal、risk state snapshots、account restore、fill idempotency。确定性 NAV 可隐藏状态恢复缺陷 | OMS Lite 后扩展 replay proof：order journal、fills、risk state、account state projections |

#### P2 级发现（2 项）

| ID | 问题 | 建议 |
|----|------|------|
| BT-2 | statistics/engine/manifest/brokerage/data_feed 大文件多职责 | 按 runtime/simulation/manifest/reporting 拆分（behavior-preserving tests 先行） |
| BT-3 | `RunMode` 含 live 词汇但 live adapter 为 reserved | manifest mode 语言保持关联 maturity manifest，live mode 标注为规划中 |

#### CLAUDE.md 规则优化

**缺失规则（需新增）**：
1. **Consumer-Owned Port**——backtest 核心循环不 import data 层类型，通过 `HistoricalDataPortal` Protocol 访问历史数据
2. **Runtime seam 契约**——backtest/paper 共享统一的 lifecycle 接口或 orchestrator
3. **Replay 完整性**——replay proof 应覆盖所有状态投影，不仅是 NAV

### 9.3 Data 审计报告（270 文件, 30,690 行）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-data-review.md`

#### 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 270 |
| 源码行数 | 30,690 |
| 测试文件 | 191 |
| 外部依赖 | kernel + platform |
| 被引用次数 | ~200（backtest/application/features/apps） |
| 最大文件 | `tushare_source.py` 777, `market_service.py` 752, `capital.py` 725 |

#### P1 级发现——架构级（4 项）

| ID | 问题 | 说明 | 建议 |
|----|------|------|------|
| DATA-ARCH-1 | DataCatalog/Lineage 仅为 contract | `DataCatalogReader/Writer` 和 `DataLineageRecorder/Reader` 只有 Protocol 和 dataclass，无 runtime store/integration path。治理词汇可被误认为已执行的 lineage/catalog | 实现最小 runtime store，或标注 DataCatalog runtime 为 experimental 并附明确 reopen 条件 |
| DATA-ARCH-2 | Dataset enum 仍是实际路由 spine | `Dataset` enum + `application.config.INGESTION_SPECS` 仍是数据集路由真相。新增市场/数据集需在多处编辑 enum/config，推迟 DataCatalog 迁移 | 定义 Dataset budget 和迁移路径：enum 用于当前固定 ingestion，catalog 用于可扩展 assets |
| DATA-ARCH-3 | DataProvider 被消费者直接 import | `DataProvider` 是 data-owned 但被 backtest/application runtime builders 直接消费。消费者绑定数据层接口 | backtest/application-owned portal ports + composition boundary adapter（Consumer-Owned Port 模式） |
| DATA-ARCH-4 | 市场参考数据归属分散 | 交易日历、参考元数据、状态历史、规则式 PIT 参考数据在 data storage/services 中，kernel/execution/backtest 也持有市场规则默认值 | 在 ADR 中分离 "data storage" 和 "market reference provider" 决策 |

#### P2 级发现（2 项）

| ID | 问题 | 建议 |
|----|------|------|
| DATA-2 | 多个 source/service/storage 文件超 600 行 | Dataset/DataCatalog 方向确定后按关注点拆分 |
| DATA-3 | SQL 插值有大量本地 S608 allowlist | 维护 SQL/noqa budget，将标识符校验提取到共享 helper |

#### CLAUDE.md 规则优化

**缺失规则（需新增）**：
1. **Dataset budget**——新增 `Dataset` enum 条目需附带成熟度标签，extensible assets 走 DataCatalog
2. **Consumer-Owned Port**——backtest/application 不直接 import data provider，通过 portal port + application adapter
3. **参考数据归属**——market reference provider 需独立 ADR，当前散落在 data/kernel/execution/backtest

---

## 10. Phase 4 编排与入口层审计计划

### 10.1 Application 审计报告（104 文件, 18,315 行）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-application-review.md`

#### 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 104 |
| 源码行数 | 18,315 |
| 测试文件 | 107 |
| 外部依赖 | 所有能力包 + data + platform |
| 被引用次数 | apps (~109) |
| 最大文件 | `coordinator.py` 764, `runtime_builder.py` 626, `config.py` 614, `queries/research.py` 595 |

#### P1 级发现——架构级（4 项）

| ID | 问题 | 说明 | 建议 |
|----|------|------|------|
| APP-CORE-1 | Provider fan-in 成为隐藏 composition root | `providers.py` import data services/sources/stores, execution audit/trade, features services/stores, strategy stores 等。application 可成为隐藏的 composition root 而非纯 use-case 编排 | 将具体基础设施选择移至 apps registry，或用更窄的 application-owned ports 包装 |
| APP-CORE-2 | Runtime builder 定义生命周期默认值 | `BacktestRuntimeBuilder` 构造 backtest simulation、data provider adapter、portfolio account、risk checks、execution planner、fee/slippage 默认值。Runtime mode 语义变成 builder 行为而非被 review 的包契约 | 提取 backtest/paper runtime factory contract，application 编排 port 而非定义 lifecycle 默认值 |
| APP-CORE-3 | Dataset 路由真相重复 | `INGESTION_SPECS` 镜像 data `Dataset` enum，含 task names/dependencies/schedules/critical fields/availability times。事实可在 data/application/apps 间分叉 | DataCatalog/Dataset budget 作为真相源；application config 标注为当前固定 ingestion config |
| APP-CORE-4 | Research 路径直接依赖 analysis/data/features | `queries/research.py` 直接 import analysis domain/services + data metadata + features artifact reader。路径意图正确但未隔离在 application-owned ports 之后 | 增加 research reader/builder ports 或文档化为 ADR allowance + owner/reopen condition |

#### P2 级发现（2 项）

| ID | 问题 | 建议 |
|----|------|------|
| APP-2 | 多个编排文件超 500 行 | 按 command/query/runtime concern 拆分 coordinators/builders（behavior tests 先行） |
| APP-3 | Position/trade/signal/dataset/research DTO 命名与能力包重叠 | 增加 public DTO naming table，限定跨包 model names |

#### CLAUDE.md 规则优化

**缺失规则（需新增）**：
1. **Composition 边界**——application 只依赖 port/Protocol，具体实现选择在 apps registry
2. **Runtime factory 契约**——backtest/paper runtime 使用共享 lifecycle contract，builder 只做端口适配
3. **Dataset 路由真相**——DataCatalog 为唯一真相源，application config 为固定映射

### 10.2 Apps 审计报告（109 文件, 12,094 行）

> 来源：独立审计 `docs/reviews/audit/modules/2026-05-08-apps-review.md`

#### 模块概览

| 指标 | 值 |
|------|-----|
| 源码文件 | 109 |
| 源码行数 | 12,094 |
| 测试文件 | 136 |
| 外部依赖 | application + platform + composition root wiring |
| 最大文件 | `api/routes/backtest.py` 526, `api/routes/trade.py` 412 |

#### P1 级发现——架构级（3 项）

| ID | 问题 | 说明 | 建议 |
|----|------|------|------|
| APPS-ARCH-1 | E2E 测试跳过机制掩盖核心路径 | E2E fixtures 依赖本地 TDX samples 和 PIT snapshots，缺失时 skip。Full check 可在跳过最重要端到端路径的情况下通过 | 添加小型 committed synthetic golden dataset 或 CI artifact path，确保一条完整 E2E lane 始终可执行 |
| APPS-ARCH-2 | API/CLI 成熟度未感知 | API surface 覆盖广泛市场域，但 maturity manifest 标记多项为 experimental/reserved。用户可从 endpoint/model 存在推断生产就绪度 | 增加 maturity-aware docs/route metadata；禁止 reserved capability 措辞出现在 API/CLI help |
| APPS-ARCH-3 | Registry composition 可能积累业务事实 | `registry/infra/config.py` 和 registry contexts 拥有广泛 infra/capability composition。正确但可积累业务事实，难审计 | 保持 registry 为纯 composition；dataset/maturity/runtime 事实移至 architecture manifests 或 application/data configs |

#### P2 级发现（2 项）

| ID | 问题 | 建议 |
|----|------|------|
| APPS-2 | 大 route/job 文件混合请求解析/facade 调用/response 塑形 | 按 subresource 或 response mapping 拆分（behavior snapshots 先行） |
| APPS-3 | 单一 DQ host-composition allowance 在 `jobs/context.py` | 保持精确 allowance 为 enforcement source，新增例外需 owner/reason |

#### CLAUDE.md 规则优化

**缺失规则（需新增）**：
1. **Golden E2E lane**——至少一条 E2E 路径使用 committed synthetic fixtures，不依赖外部数据源
2. **Maturity-aware API**——route/help 文本不宣称 reserved/experimental capability 为 production-ready
3. **Registry budget**——新增 registry capability import 需附 exact allowance owner/reason

---

## 11. 跨模块统一治理项

### 11.1 代码级治理（原有）

以下问题需在所有模块审查完成后统一处理：

| 治理项 | 影响范围 | 优先级 |
|--------|---------|--------|
| Service 后缀语义收敛（~44% 实为 Store/Repository） | data/application/features/execution/strategy | P1 |
| 异常文件命名统一（errors.py vs exceptions.py） | 全部 12 包 | P1 |
| `__all__` 公共 API 收敛（8/12 包无 `__all__`） | 除 kernel/risk/features/analysis 外全部 | P1 |
| 深/浅导入统一（消费者绕过 __init__.py 公共 API） | platform(86处) + portfolio(34处) | P1 |
| 空 namespace 清理（analysis 2、features 2、strategy 1） | 3 包 | P2 |
| 跨包同名词消歧（PositionReader/TargetPortfolio/TradeRecord） | portfolio/execution/application | P1 |
| 命名词典机器化（suffix guard / canonical glossary） | 全库 | P2 |

### 11.2 架构级治理（新增）

> 以下跨模块主题来自独立审计，涉及 runtime 架构的根本性缺口

| 治理项 | 来源 | 影响范围 | 优先级 | 前置条件 |
|--------|------|---------|--------|---------|
| **Runtime Spine** | BT-ARCH-1, EX-ARCH-1, RK-ARCH-1 | backtest/execution/risk/application | **P0** | 无 |
| **OMS Lite** | EX-ARCH-1~4 | execution/portfolio/application | **P0** | 无 |
| **Consumer-Owned Ports** | BT-ARCH-2, DATA-ARCH-3, APP-CORE-1 | backtest/data/application | P1 | Runtime Spine 设计 |
| **状态快照/恢复** | PF-ARCH-1, RK-ARCH-2, ST-ARCH-2 | portfolio/risk/strategy | P1 | OMS Lite |
| **事件类型化** | K-ARCH-1, RK-ARCH-3 | kernel/risk/execution/backtest | P1 | Runtime Spine |
| **DataCatalog Runtime** | DATA-ARCH-1, DATA-ARCH-2, FEAT-ARCH-1 | data/features/application | P1 | Consumer-Owned Ports |
| **市场参考 Provider** | DATA-ARCH-4, K-ARCH-2, EX-ARCH-4 | data/kernel/execution/backtest | P1 | OMS Lite |
| **成熟度分级** | ST-ARCH-3, AN-ARCH-3, APPS-ARCH-2, BT-3 | strategy/analysis/apps/backtest | P2 | 无 |

### 11.3 治理依赖图

```
Runtime Spine ─────────┬─────────────────────────────────────
  │                    │
  ├─→ OMS Lite ────┬───┤
  │                │   │
  │                ├──→ 状态快照/恢复
  │                │
  │                └──→ 市场参考 Provider
  │
  ├─→ 事件类型化
  │
  └─→ Consumer-Owned Ports ──→ DataCatalog Runtime

成熟度分级（独立，可并行）
```

---

## 12. 审计进度

| 阶段 | 模块 | 状态 | P0 | 代码 P1 | 架构 P1 | P2 |
|------|------|------|----|---------|---------|-----|
| Phase 1 | kernel | ✅ 已完成 | 3 | 5 | 3 | 3 |
| Phase 1 | platform | ✅ 已完成 | 0 | 5 | 2 | 4 |
| Phase 2 | portfolio | ✅ 已完成 | 1 | 5 | 3 | 4 |
| Phase 2 | risk | ✅ 已完成 | 0 | 5 | 3 | 4 |
| Phase 2 | execution | ✅ 已完成 | 0 | 5 | 4 | 4 |
| Phase 2 | strategy | ✅ 已完成 | 0 | 5 | 3 | 3 |
| Phase 2 | analysis | ✅ 已完成 | 0 | 2 | 3 | 2 |
| Phase 3 | features | ✅ 已完成 | 0 | 0 | 3 | 2 |
| Phase 3 | backtest | ✅ 已完成 | 0 | 0 | 3 | 2 |
| Phase 3 | data | ✅ 已完成 | 0 | 0 | 4 | 2 |
| Phase 4 | application | ✅ 已完成 | 0 | 0 | 4 | 2 |
| Phase 4 | apps | ✅ 已完成 | 0 | 0 | 3 | 2 |

**统计**：P0 共 4 项 | 代码级 P1 共 32 项 | 架构级 P1 共 38 项 | P2 共 34 项

---

## 13. 执行流程

### 13.1 单模块审查流程

每个模块的审查流程：

1. **全量扫描**：建立文件清单，统计基础指标
2. **逐文件审查**：6 维度评估，标注 P0/P1/P2
3. **模块总结**：产出审计报告 + 改进优先级清单
4. **确认后执行**：按优先级实施改进
5. **验证**：`pixi run -e dev check` 确认无回归

### 13.2 跨模块治理执行顺序

```
第一批（无前置，可并行）：
  └─ Runtime Spine 设计（ADR + 核心契约定义）
  └─ OMS Lite 设计（ADR + identity/journal 契约）
  └─ 成熟度分级（全模块 CLAUDE.md 标注）

第二批（依赖第一批）：
  └─ 代码级 P0/P1 清理（所有模块并行）
  └─ 事件类型化（kernel event catalog）
  └─ Consumer-Owned Ports（backtest/data/application）
  └─ OMS Lite 实现（execution identity/journal/gateway harness）

第三批（依赖第二批）：
  └─ 状态快照/恢复（portfolio/risk/strategy）
  └─ DataCatalog Runtime（data/features）
  └─ 市场参考 Provider ADR（data/kernel/execution/backtest）

第四批（持续改进）：
  └─ P2 级代码清理（全模块）
  └─ 大文件拆分
  └─ 命名/导入统一
```
