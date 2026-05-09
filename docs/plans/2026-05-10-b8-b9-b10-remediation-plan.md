# B8/B9/B10 代码级整改计划

> 创建：2026-05-10
> 基线：`docs/reviews/audit/2026-05-10-full-re-audit-report.md`
> 前置：B1-B7 已全部完成并合入 `remediation/cross-module-b1-b7`
> 分支：从 `remediation/cross-module-b1-b7` 拉取新分支
> 策略：严格顺序执行，每批次通过 `pixi run -e dev check` 后进入下一批次
> 复核：V2 补入审计报告 §2.1-§2.12 全部 P1+P2 未修复项（36 项遗漏）

---

## 概述

- **目标**：修复重审报告中的 **2 个 P0** + **31 个 P1** + **34 个 P2** = **67 个原子任务**
- **范围**：仅代码级修复，不涉及 Runtime Spine / OMS Lite / Consumer-Owned Ports 等架构级工作
- **验收**：每批次 `pixi run -e dev check` 通过（lint + fmt + type + test + arch-check + arch-smells）

### 批次-模块覆盖矩阵

| 批次 | kernel | platform | portfolio | risk | execution | strategy | analysis | features | backtest | data | application | apps |
|------|--------|----------|-----------|------|-----------|----------|----------|----------|----------|------|-------------|------|
| B8 | ●●● | | | | | | | | | | ● | |
| B9-K | ●●●●●●● | | | | | | | | | | | |
| B9-P | | ● | | | | | | | | | | |
| B9-PF | | | ●●●●●● | | | | | | | | | |
| B9-RK | | | | ●●●● | | | | | | | | |
| B9-EX | | | | | ●●●● | | | | | | | |
| B9-ST | | | | | | ●●●●●● | | | | | | |
| B9-AN | | | | | | | ●● | | | | | |
| B9-FEAT | | | | | | | | ●●● | | | | |
| B9-BT | | | | | | | | | ● | | | |
| B9-DATA | | | | | | | | | | ●●●● | | |
| B9-APP | | | | | | | | | | | ●●●●● | |
| B9-APPS | | | | | | | | | | | | ● |
| B10 | | ● | ● | ● | ● | ● | | | | | | ● |

---

## 技术方案

### 关键决策

1. **Kernel 迁移策略**：B8 先迁 3 个 P0 文件，B9 再迁 5 个 P1 文件 + 清理 2 个 P2 死 Protocol
2. **跨层穿透收敛**：先提升 Protocol 到包级 contracts.py，再逐个更新 import
3. **Portfolio 原子性**：PF-2 `apply_fill()` 先计算新状态再统一赋值（不引入事务框架）
4. **Golden E2E**：使用 committed synthetic Parquet 数据集，不依赖外部数据源

### 依赖关系

```
B8 (P0 紧急修复，2 项)
  │
  └─→ B9 (P1+P2 代码级清理，按模块分 13 个子批次)
       │
       └─→ B10 (文档/E2E，6 项)
```

---

## B8：P0 紧急修复（2 项）

### B8.1：Kernel 领域泄漏 3 文件迁移 `[XL]`

**问题**：3 个文件不属于 kernel 但一直留在 kernel，违反准入规则。

| 源文件 | 目标位置 | 外部引用数 | 复杂度 |
|--------|---------|-----------|--------|
| `kernel/publication_safety.py` (233 LOC) | `ditto_features.publication_safety` | ~20 | L |
| `kernel/quality.py` (105 LOC) | `ditto_data.quality`（已有子包） | ~13 | L |
| `kernel/research.py` (79 LOC) | `ditto_analysis.research.domain`（合并） | ~5 | M |

**执行步骤（每个文件）**：

1. `[M]` 确认目标包已有对应测试，补充迁移测试
2. `[S]` 将源文件移动到目标包目录
3. `[M]` 更新目标包 `__init__.py` barrel 导出
4. `[L]` 全库搜索旧 import 路径并逐一更新
5. `[S]` 更新 kernel `__init__.py` 从 `__all__` 移除迁移符号
6. `[S]` 删除 kernel 原文件
7. `[S]` `pixi run -e dev check`

**验收**：
- `rg "from ditto_kernel.publication_safety" packages/` → 0
- `rg "from ditto_kernel.quality import" packages/` → 0
- `rg "from ditto_kernel.research import" packages/` → 0
- kernel `__all__` 从 30 降至 ~20

### B8.2：`_DEFAULT_SLIPPAGE_BPS` 不一致修复 `[S → M]`

**问题**：`runtime_builder.py` 中值为 5.0，全项目其他位置为 1.0。

1. `[S]` 全库搜索确认统一值应为 `1.0`
2. `[S]` 修改 `runtime_builder.py`：`_DEFAULT_SLIPPAGE_BPS = 5.0` → `1.0`
3. `[S]` 添加测试验证默认滑点 = 1.0
4. `[S]` `pixi run -e dev check`

**验收**：`rg "slippage_bps.*=.*5" packages/` → 0

---

## B9：P1+P2 代码级清理（按模块分 13 个子批次）

### B9-K：Kernel 模块修复（5 P1 + 2 P2 = 7 项）

> 前置：B8.1 kernel P0 迁移完成

#### B9-K.1：`strategy.py` DerivedSpec/DerivedRole 迁移 `[M]` — P1

**问题**：`DerivedSpec`/`DerivedRole`/`MaterializationProfile` 是 features 领域概念。

1. `[S]` 迁移 `DerivedSpec`, `DerivedRole` 及其枚举值到 `ditto_features` 合适位置
2. `[M]` 更新全库 import（features 14 次引用 + application/backtest 引用）
3. `[S]` 更新 kernel barrel

**验收**：`rg "from ditto_kernel.strategy import.*Derived" packages/` → 0

#### B9-K.2：`trading.py` A 股业务常量迁移 `[M]` — P1

**问题**：`DEFAULT_COMMISSION_RATE` 和 `default_price_limit_pct()` 是 A 股业务逻辑。

1. `[S]` 迁移常量和函数到 `ditto_execution` 或 `ditto_backtest`
2. `[M]` 更新全库 import
3. `[S]` 更新 kernel barrel

**验收**：kernel `trading.py` 不再包含 A 股默认值

#### B9-K.3：`json_types.py` 迁移到 platform `[M]` — P1

**问题**：类型别名 + `require_*` 函数属于横向技术基础设施。

1. `[S]` 迁移到 `ditto_platform.foundation.json_types`（新文件）
2. `[M]` 更新全库 import
3. `[S]` 更新 kernel/platform barrel

**验收**：`rg "from ditto_kernel.json_types" packages/` → 0

#### B9-K.4：`exceptions.py` DerivedError 层级迁移 `[M]` — P1

**问题**：`DerivedError` → `DerivedNotFoundError`/`VersionError`/`NotImplementedError`/`ValidationError` 仅 features 使用。

1. `[S]` 迁移 Derived* 异常到 `ditto_features.exceptions`
2. `[M]` 更新全库 import（features/data/application 7 处引用）
3. `[S]` 更新 kernel barrel

**验收**：`rg "from ditto_kernel.exceptions import.*Derived" packages/` → 0

#### B9-K.5：`market.py` MacroDataProvider 迁移 `[S]` — P1

**问题**：MacroDataProvider Protocol 只被 data.macro 实现和使用。

1. `[S]` 迁移到 `ditto_data.macro` 或消费者 port
2. `[S]` 更新全库 import
3. `[S]` 更新 kernel barrel

**验收**：kernel `market.py` 不再包含 MacroDataProvider

#### B9-K.6：DecisionFrame Protocol schema 校验 `[S]` — P2

**问题**：DecisionFrame 是 `pl.DataFrame` 类型别名，无运行时列名校验。

1. `[S]` 添加 `validate_decision_frame()` 函数到 strategy，在 pipeline 入口调用
2. `[S]` kernel 只保留类型别名定义

#### B9-K.7：BrokerProtocol 零消费者清理 `[S]` — P2

**问题**：`trading.py` BrokerProtocol 无任何外部消费者。

1. `[S]` 确认零消费后删除死 Protocol
2. `[S]` 更新 kernel barrel

---

### B9-P：Platform 模块修复（1 P1 = 1 项）

#### B9-P.1：PL-1 深层引用 3 处残留修复 `[S]` — P1

**问题**：`apps/registry/infra/observability.py` 3 处可简化为 barrel 导入。

1. `[S]` 将 `from ditto_platform.foundation.config.settings import Settings` → `from ditto_platform.foundation import Settings`
2. `[S]` 将 `from ditto_platform.foundation.observability.config import ObservabilityConfig` → barrel 导入
3. `[S]` 将 `from ditto_platform.foundation.observability.tracing import traced` → barrel 导入
4. `[S]` `pixi run -e dev check`

**验收**：`rg "from ditto_platform\..*\..*\..*import" packages/apps/` → 0

---

### B9-PF：Portfolio 模块修复（4 P1 + 2 P2 = 6 项）

#### B9-PF.1：`Account.positions` 防御性保护 `[M]` — P1

**问题**：`Account.positions` 是裸 `dict[InstrumentId, Position]`，外部可直接篡改。

1. `[S]` 内部改 `_positions: dict` + `@property` 返回 `MappingProxyType` 只读视图
2. `[S]` `apply_fill` 内部通过 `_positions` 直接操作
3. `[S]` 更新测试（如有直接 `account.positions[x] =` 的用法需改用 API）
4. `[S]` `pixi run -e dev check`

**验收**：外部无法通过 `account.positions[key] = value` 篡改持仓

#### B9-PF.2：`apply_fill()` 原子性保障 `[M]` — P1

**问题**：`_update_position_from_fill` + `_update_cash_from_fill` 两步操作，异常可致不一致。

1. `[M]` 重构为：先计算新 position + 新 cash，再统一赋值
2. `[S]` 添加测试：模拟第二步异常后验证状态一致性
3. `[S]` `pixi run -e dev check`

**验收**：`apply_fill()` 在任意异常下不产生部分更新

#### B9-PF.3：`PortfolioStateReader` 零消费清理 `[S]` — P1

**问题**：Protocol 无生产消费者。

1. `[S]` 标注 reserved 或删除
2. `[S]` 更新 `__init__.py` barrel

#### B9-PF.4：`StateTransitionError` 双路径导出统一 `[S]` — P1

**问题**：在 `errors.py` 定义，在 `accounting/__init__.py` re-export，消费者全走 accounting 路径。

1. `[S]` `accounting/__init__.py` 停止 re-export `StateTransitionError`
2. `[S]` 更新所有消费端改为 `from ditto_portfolio.errors import StateTransitionError`
3. `[S]` `pixi run -e dev check`

**验收**：`StateTransitionError` 只从 `errors.py` 一个路径导出

#### B9-PF.5：`Constraint` Protocol 移除 `priority` property `[S]` — P2

**问题**：`priority` 是排序策略细节，不应入 Protocol。

1. `[S]` Protocol 移除 `priority` property
2. `[S]` `ConstraintChecker` 改用内部排序策略
3. `[S]` 更新所有 Check 实现

#### B9-PF.6：`report_views.py` Protocol 实现者标注 `[S]` — P2

**问题**：`AlphaStatsView`/`AggregatedTradeStatsView`/`BacktestReportView` 无显式实现者。

1. `[S]` 在 docstring 标注 "duck typing 隐式满足"
2. `[S]` 添加 `@runtime_checkable`

---

### B9-RK：Risk 模块修复（3 P1 + 1 P2 = 4 项）

> 注：severity 类型化在原计划 B9-C.3，保留

#### B9-RK.1：死代码清理 `[S]` — P1

**问题**：`models.py` 中 `RiskMetrics`/`ExposureData`/`DrawdownStats` 无生产消费者。

1. `[S]` 删除三个 frozen dataclass
2. `[S]` 更新 `__init__.py` barrel
3. `[S]` 更新引用测试

**验收**：`rg "RiskMetrics|ExposureData|DrawdownStats" packages/risk/src/` → 0

#### B9-RK.2：`checks.py` 拆分 `[L]` — P1

**问题**：319 行混合 Protocol + 6 Check + Composite + 默认配置。

1. `[M]` Protocol + `_accept` helper → `constraints/context.py`
2. `[M]` 6 个 Check 类按功能分组
3. `[S]` CompositePreTradeCheck + DEFAULT_CHECK_ORDER → `constraints/composite.py`
4. `[S]` `checks.py` 保留为 facade（re-export）
5. `[S]` `pixi run -e dev check`

**验收**：每个文件 < 150 LOC，公共 API 不变

#### B9-RK.3：severity 类型化 `[S]` — P2（从原 B9-C.3 保留）

**问题**：`RiskGuardTriggered.severity` 为 `str` 而非 `RiskSeverity` enum。

1. `[S]` `events.py` `severity: str` → `severity: RiskSeverity`
2. `[S]` 更新构造端（backtest risk_scan.py）

#### B9-RK.4：`RiskAction.target_quantity` 未填充字段清理 `[S]` — P2

**问题**：`target_quantity` 和 `cooldown_until_date` 从未被填充。

1. `[S]` 评估是否需要保留（有 future seam 价值则标注 reserved）
2. `[S]` 若删除则更新 Protocol 和构造端

---

### B9-EX：Execution 模块修复（3 P1 + 1 P2 = 4 项）

#### B9-EX.1：三重 `save_fill` 合并 `[M]` — P1

**问题**：`FillReceiver`/`FillStore`/`TradeService.save_fill` 三处签名相同。

1. `[S]` 将 `FillReceiver`（contracts.py）合并到 `FillStore`（fills/store.py），删除 `FillReceiver`
2. `[S]` 更新 contracts.py barrel 导出
3. `[S]` 更新消费端（backtest brokerage 等）
4. `[S]` `pixi run -e dev check`

**验收**：`rg "FillReceiver" packages/` → 0

#### B9-EX.2：TradeAuditor 签名统一 `[S]` — P1

**问题**：Protocol 用 `Sequence[T]`，实现用 `tuple[T, ...]`。

1. `[S]` `contracts.py` TradeAuditor 3 方法 `records: Sequence[T]` → `tuple[T, ...]`
2. `[S]` `pixi run -e dev check`

#### B9-EX.3：TradeService 跨层穿透收敛 `[M]` — P1

**问题**：application 6 处直接 import SQLite 实现类。

1. `[M]` `contracts.py` 新增 `TradeDataPort` Protocol（提炼 TradeService 公共方法）
2. `[M]` application 6 处改为 Protocol 引用
3. `[S]` `pixi run -e dev check`

**验收**：`rg "from ditto_execution.storage.sqlite" packages/application/` → 0

#### B9-EX.4：`compute_diff` 参数过多优化 `[M]` — P2

**问题**：10 个参数，需引入参数对象。

1. `[M]` 提取 `DiffContext` frozen dataclass 封装 10 个参数
2. `[S]` 更新 `compute_diff` 签名
3. `[S]` 更新调用端

---

### B9-ST：Strategy 模块修复（4 P1 + 2 P2 = 6 项）

#### B9-ST.1：Protocol 方法名对齐 `[S]` — P1

**问题**：`StrategySpecReaderProtocol`（services 内）方法名与 `StrategyCatalogReader`（包级 contracts）不一致。

1. `[S]` 统一方法名为 `get_spec/list_specs/list_versions`
2. `[S]` 更新 `StrategyCatalogService` 注入类型

#### B9-ST.2：跨层穿透收敛 `[L]` — P1

**问题**：application 24 处直接 `from ditto_strategy.storage.sqlite.services.*`。

1. `[M]` 将 services 内 Protocol 提升到 `contracts.py`
2. `[L]` 24 处 import 替换为 Protocol 引用
3. `[S]` DI Provider 注册为 Protocol 类型
4. `[S]` `pixi run -e dev check`

**验收**：`rg "from ditto_strategy.storage.sqlite" packages/application/` → 0

#### B9-ST.3：Benchmark 白名单可配置化 `[M]` — P1

**问题**：`specs.py` 硬编码 9 个 A 股指数白名单，非 A 股基准无法使用。

1. `[M]` 改为格式校验（保留 `dddd.SS` 正则）+ 可配置基准映射
2. `[S]` 默认行为不变，新增市场可注册自定义基准
3. `[S]` `pixi run -e dev check`

#### B9-ST.4：辅助函数去重 `[S]` — P1

1. `[S]` `_utc_now()` 提取到 `ditto_strategy/_internal.py`
2. `[S]` `_raise_config_error()` 提取到 `ditto_strategy/alpha/templates/_common.py`
3. `[S]` 更新调用处 import

#### B9-ST.5：`stock_selection_trend.py` 拆分 `[M]` — P1

1. `[S]` 拆为 stages.py + config.py + 入口文件
2. `[S]` 确保行为测试通过
3. `[S]` `pixi run -e dev check`

#### B9-ST.6：ETF 模板补充 `validate_config` + `get_param_constraints` `[M]` — P2

**问题**：只有 stock 模板有三件套，ETF 模板缺失。

1. `[M]` 为 `etf_rotation.py` 和 `etf_trend_swing.py` 添加参数校验元数据
2. `[S]` 添加 validate 测试

---

### B9-AN：Analysis 模块修复（2 P2 = 2 项）

#### B9-AN.1：contracts.py Protocol 添加 `@runtime_checkable` `[S]` — P2

**问题**：`ResearchCatalogReaderProtocol`/`ResearchCatalogWriterProtocol` 缺少装饰器。

1. `[S]` 添加 `@runtime_checkable` 装饰器
2. `[S]` 与 strategy 包保持一致

#### B9-AN.2：root barrel 扩展 `[S]` — P2

**问题**：只导出 3 符号，常用类型需深层导入。

1. `[S]` 在 `__init__.py` 添加 `SpineSpec`、`SpineSnapshot`、`DatasetSnapshot` 等常用类型
2. `[S]` 保持 `__all__` budget guard 通过

---

### B9-FEAT：Features 模块修复（1 P1 + 2 P2 = 3 项）

#### B9-FEAT.1：evaluator Protocol 提取 `[M]` — P1

**问题**：`evaluator.py`（746 LOC）混合 Protocol 定义与编排逻辑。

1. `[S]` Protocol 定义提取到 `evaluation/contracts.py`
2. `[S]` `evaluator.py` 从 contracts 导入
3. `[S]` `pixi run -e dev check`

#### B9-FEAT.2：`codegen.py` 关注点分区优化 `[M]` — P2

**问题**：749 LOC 虽职责分区良好但单文件仍大。

1. `[M]` 评估是否需拆分（当前分区注释清晰，优先级低于其他项）
2. `[S]` 若拆分则按 ts_special/cross_section/grouped 分离

#### B9-FEAT.3：services 命名空间收敛 `[M]` — P2

**问题**：`__init__.py` re-export 44 符号，宽泛命名空间。

1. `[M]` 按能力域分组注释（catalog / publication_safety / query / derived）
2. `[S]` 或拆为 `services/catalog.py`、`services/publication_safety.py` 入口

---

### B9-BT：Backtest 模块修复（1 P2 = 1 项）

#### B9-BT.1：`EngineMode.LIVE` 死代码清理 `[S]` — P2

**问题**：枚举值未被任何代码路径使用。

1. `[S]` 删除 `EngineMode.LIVE` 或标注 reserved
2. `[S]` 更新 docstring 说明 live 模式为规划中

---

### B9-DATA：Data 模块修复（1 P1 + 3 P2 = 4 项）

#### B9-DATA.1：Catalog/Lineage Protocol Mock 验证 `[M]` — P1

**问题**：Protocol 无实现，接口设计可能在实现时发现不匹配。

1. `[M]` 为 `DataCatalogReader`/`DataCatalogWriter` 创建 Mock 实现
2. `[S]` 为 `DataLineageRecorder`/`DataLineageReader` 创建 Mock 实现
3. `[S]` 添加基础契约测试验证接口可行性
4. `[S]` `pixi run -e dev check`

#### B9-DATA.2：`errors.py` 按域拆分 `[M]` — P2

**问题**：606 LOC 混合 Calendar/Instrument/Trading/Persistence/Auth/Network 错误。

1. `[M]` 拆为 `errors/calendar.py`、`errors/instrument.py`、`errors/persistence.py` 等
2. `[S]` `errors.py` 保留为 facade（re-export）
3. `[S]` `pixi run -e dev check`

#### B9-DATA.3：apps 层直接导入 data 服务类收敛 `[L]` — P2

**问题**：apps 层直接 `from ditto_data.services.xxx import XxxService`（12 处）。

1. `[M]` 通过 DI 容器注入服务实例（apps 已有 dishka Container）
2. `[L]` 逐个替换硬编码具体类导入
3. `[S]` `pixi run -e dev check`

#### B9-DATA.4：关键大文件拆分 `[L]` — P2

**问题**：3 个文件超 700 LOC（tushare_source.py 777、market_service.py 752、capital.py 725）。

1. `[M]` `tushare_source.py` 按适配器域拆分（已有 adapters/ 子目录）
2. `[M]` `market_service.py` 按资产类别拆分
3. `[M]` `capital.py` 按数据类型拆分
4. `[S]` `pixi run -e dev check`

---

### B9-APP：Application 模块修复（4 P1 + 1 P2 = 5 项）

#### B9-APP.1：Runtime builder 生命周期默认值收敛 `[M]` — P1

**问题**：`BacktestRuntimeBuilder` 定义了 fee/slippage/commission 默认值，runtime 语义变成 builder 行为。

1. `[M]` 将默认值提取到 backtest 包的配置常量
2. `[S]` runtime_builder 只做 port 适配，不定义默认值
3. `[S]` `pixi run -e dev check`

#### B9-APP.2：INGESTION_SPECS 双源事实标注 `[S]` — P1

**问题**：`application.config.INGESTION_SPECS` 与 data `Dataset` enum 双源。

1. `[S]` 在 INGESTION_SPECS 添加 docstring："当前固定摄取配置，DataCatalog 为未来真相源"
2. `[S]` 在 CLAUDE.md 记录此决策和迁移条件

#### B9-APP.3：Research 路径隔离 `[M]` — P1

**问题**：`queries/research.py` 直接 import analysis domain/services + data metadata + features artifact reader。

1. `[M]` 添加 application-owned `ResearchCatalogPort` 和 `ResearchArtifactPort` Protocol
2. `[M]` research query 层通过 port 访问，或写 ADR 记录当前直接依赖为 narrow allowance
3. `[S]` `pixi run -e dev check`

#### B9-APP.4：异常入口统一 `[L]` — P1

**问题**：部分 process 用 `DittoError` 子类，部分用裸 `ValueError`/`RuntimeError`。

1. `[M]` 审计所有 application process 的异常抛出点
2. `[M]` 统一为 `DittoError` 子类层级
3. `[S]` `pixi run -e dev check`

#### B9-APP.5：大文件拆分 `[L]` — P2

**问题**：8 个文件超 500 行（coordinator 764、runtime_builder 626、config 614、research 595 等）。

1. `[M]` coordinator.py 按用例阶段拆分（ingestion start/monitor/complete）
2. `[M]` config.py 按配置域拆分
3. `[S]` 拆分前先有 behavior snapshot 测试

---

### B9-APPS：Apps 模块修复（1 P1 = 1 项）

#### B9-APPS.1：Registry composition 事实积累治理 `[S]` — P1

**问题**：`registry/infra/config.py` 可能积累业务事实。

1. `[S]` 审计 config.py 确认无业务事实泄漏
2. `[S]` 添加 guard 注释：新增 registry capability import 需附 owner/reason
3. `[S]` 更新 CLAUDE.md

---

## B10：文档/E2E 同步（6 项）

### B10.1：Platform 死代码清理 `[S]`

**问题**：`paths.py` 3 个废弃函数体（24 行）。

1. `[S]` 删除 `get_paths()`/`reload_paths()`/`reset_paths_for_testing()` 函数体
2. `[S]` 确认无调用者

### B10.2：barrel/`__all__` 统一 `[M]`

1. `[S]` `execution/__init__.py` 添加核心公共 API
2. `[S]` `portfolio/__init__.py` 填充顶层 barrel
3. `[S]` `risk/observability/__init__.py` 连接 METRIC_DEFINITIONS

### B10.3：CLAUDE.md 同步 `[M]`

1. `[M]` execution：planner 描述更新（530→164 LOC）+ 目录树补充
2. `[S]` strategy：目录结构更新
3. `[S]` platform：导入示例确认

### B10.4：Committed Synthetic Golden E2E `[XL]`

1. `[M]` 设计合成数据集（5 只 ETF、20 交易日）
2. `[L]` 创建 golden E2E 测试（数据→因子→策略→回测→报告→replay）
3. `[M]` CI 配置 golden E2E 不可 skip
4. `[S]` `pixi run -e dev check`

### B10.5：Data `errors.py` facade re-export 验证 `[S]`

1. `[S]` 验证 B9-DATA.2 拆分后 facade re-export 完整
2. `[S]` 确认全库 import 无破坏

### B10.6：Data services DI 注入端到端验证 `[S]`

1. `[S]` 验证 B9-DATA.3 DI 注入后 apps 层正常工作
2. `[S]` 确认所有 12 个服务均可通过 DI 获取

---

## 验收总清单

每个批次完成后必须通过：

- [ ] `pixi run -e dev lint` — 零错误
- [ ] `pixi run -e dev fmt` — 格式一致
- [ ] `pixi run -e dev type` — 零 type error
- [ ] `pixi run -e dev test` — 全部通过
- [ ] `pixi run -e dev arch-check` — 36/36 contracts kept
- [ ] `pixi run -e dev arch-smells` — passed
- [ ] 相关 CLAUDE.md 已同步更新

---

## 风险评估

| 风险 | 批次 | 缓解措施 |
|------|------|---------|
| kernel 迁移大量 import 更新遗漏 | B8.1, B9-K | `rg` 搜索验证 + `arch-check` 门禁 |
| slippage 修改影响已有回测结果 | B8.2 | golden E2E 验证 + 测试断言 |
| 跨层穿透收敛破坏 DI 装配 | B9-ST.2, B9-EX.3 | 逐个 import 更新 + 每步 `check` |
| checks.py 拆分破坏 backtest 风控 | B9-RK.2 | 行为快照测试先行 |
| `apply_fill()` 原子性重构 | B9-PF.2 | 先测试（RED）再重构（GREEN） |
| Golden E2E 合成数据不够真实 | B10.4 | 使用真实 ETF 代码和合理价格区间 |
| data 大文件拆分 | B9-DATA.4 | 行为测试先行，facade re-export 保证公共 API 不变 |
| application 异常统一 | B9-APP.4 | 按模块逐步替换，不一次改完 |

---

## 未覆盖项（延后至架构级整改）

| 项 | 原因 | 触发条件 |
|----|------|---------|
| Runtime Spine（事件/时间/状态统一） | 需要独立 ADR | B8-B10 完成后启动 |
| OMS Lite（身份/journal/状态机） | 需要独立实施计划 | Runtime Spine 设计后 |
| Consumer-Owned Ports | 依赖 Runtime Spine | OMS Lite 方向后 |
| DataCatalog Runtime Store | 依赖 Consumer-Owned Ports | Ports 完成后 |
| 市场参考 Provider ADR | 依赖 OMS Lite | OMS Lite 方向后 |
| Portfolio PositionChanged 事件发射 | 依赖 OMS journal | 状态快照完整化后 |
| DataProvider 跨包导入 | 依赖 Consumer-Owned Ports | Ports 完成后 |
| Dataset enum 降权 | 依赖 DataCatalog Runtime | Catalog 实现后 |
| backtest/paper 共享 runtime seam | 依赖 Runtime Spine + OMS | Runtime Spine 设计后 |

---

## 任务统计

| 批次 | P0 | P1 | P2 | 合计 |
|------|----|----|-----|------|
| B8 | 2 | 0 | 0 | 2 |
| B9-K kernel | 0 | 5 | 2 | 7 |
| B9-P platform | 0 | 1 | 0 | 1 |
| B9-PF portfolio | 0 | 4 | 2 | 6 |
| B9-RK risk | 0 | 2 | 2 | 4 |
| B9-EX execution | 0 | 3 | 1 | 4 |
| B9-ST strategy | 0 | 4 | 2 | 6 |
| B9-AN analysis | 0 | 0 | 2 | 2 |
| B9-FEAT features | 0 | 1 | 2 | 3 |
| B9-BT backtest | 0 | 0 | 1 | 1 |
| B9-DATA data | 0 | 1 | 3 | 4 |
| B9-APP application | 0 | 4 | 1 | 5 |
| B9-APPS apps | 0 | 1 | 0 | 1 |
| B10 文档/E2E | 0 | 0 | 6 | 6 |
| **合计** | **2** | **26** | **24** | **52** |
