# Ditto 当前完整项目再审计报告

> 日期：2026-04-24
> 分支：`feat/v1-sprint`
> 基线：`docs/plans/2026-04-17-full-architecture-audit.md` 与 `docs/reviews/audit/2026-04-17-*.md`
> 目的：复核 2026-04-17 全架构审计后的修复闭环，重新评估当前完整项目的架构、正确性、可维护性与交付风险。

---

## 1. 执行摘要

当前项目相比 2026-04-17 审计基线已经有实质性改善：异常体系 P0 风险已闭环，`DataSource` God Interface 已被域级 Fetcher Protocol 替代，Kernel 已按子域重组，`import-linter` 合约从旧审计时的薄弱状态扩展到 33 条并全部通过，快速质量门禁也全部通过。

本次复核没有发现新的 P0。项目当前主要风险集中在 3 类：

1. 配置体系存在“已实现但未接入”的断点：`ConfigValidationProvider` 未注册，`DQSettings` 已加载但未注入 `QualityEngine`，`ENVIRONMENT` 仍未迁到 `DITTO_ENV`。
2. Engine 仍有少量运行时正确性债务：订单/事件默认时间硬编码到 `2026-01-01`，回测 flush 阶段吞掉 `Exception` 后只记 warning，Brokerage 使用 `AssertionError` 做运行时合约错误。
3. Data/App/Interfaces 的复杂度仍偏高：Data 仍是最大包，Reader/Writer 参数化只完成了基础设施层，薄包装文件仍大量存在；Interfaces 若干路由仍承载业务计算或 source 调试逻辑；Analytics 内部依赖方向仍未完全收敛。

总体判断：项目已从“架构风险明显”进入“架构骨架基本可靠、局部债务影响演进速度”的阶段。建议下一轮不要再做大面积重构，而是用 2-3 个短冲刺清掉配置断点、Engine 正确性债务和 Interfaces/App 边界泄漏。

---

## 2. 验证证据

本次审计运行了以下命令：

| 命令 | 结果 |
|---|---|
| `pixi run -e dev arch-check` | 33 条 import-linter 合约全部 KEPT，0 broken |
| `pixi run -e dev lint` | All checks passed |
| `pixi run -e dev type` | 0 errors, 0 warnings, 0 notes |
| `pixi run -e dev test --fast` | 5849 passed, 25 skipped in 55.00s |

跳过项说明：25 个 skipped 均来自 `interfaces/tests/e2e/test_reporter_unit.py`，原因是 TDX 样本数据不完整，不是当前代码失败。

源码规模快照：

| 包 | 源码文件数 | 源码行数 |
|---|---:|---:|
| `interfaces` | 109 | 11,878 |
| `packages/analytics` | 48 | 8,225 |
| `packages/app` | 97 | 17,732 |
| `packages/data` | 340 | 42,343 |
| `packages/engine` | 79 | 12,264 |
| `packages/infra` | 49 | 4,438 |
| `packages/kernel` | 12 | 857 |
| 合计 | 734 | 97,737 |

静态扫描摘要：

| 扫描项 | 源码命中数 | 解读 |
|---|---:|---|
| `import pandas` / `from pandas` | 0 | 符合项目禁用 pandas 规则 |
| `import json` / `from json` | 0 | 源码未直接使用标准库 json |
| `TYPE_CHECKING` | 18 | 仍有少量延迟类型导入，需按语义逐个判断 |
| `# noqa` | 49 | 大多为 SQL 白名单、延迟导入、已知 lint 豁免 |
| `except Exception` | 73 | 多数是边界降级/日志，但 Engine/App 有需收敛点 |
| `except BaseException` | 1 | 位于 artifact 写入路径，需确认是否必须吞中断类异常 |
| `NotImplementedError` | 23 | 多为协议/未支持能力，Tushare commodity 仍有显式不支持 |
| `TODO/FIXME/HACK` | 1 | TDX exchange 映射仍是 TODO |

---

## 3. 旧审计闭环状态

### 3.1 已闭环或基本闭环

| 旧问题 | 当前状态 | 证据 |
|---|---|---|
| X-P0-1 / X-P0-2：`DataSourceError`、`SourceFetchError` 双重定义 | 已闭环 | `sources/base.py` 只做异常 re-export，权威定义在 `data/errors.py` |
| X-P1-3：裸继承 `Exception` 的业务异常散落 | 基本闭环 | 源码中业务异常根已归入 `DittoError` / `DataError` / 包级异常 |
| DataSource God Interface | 已大幅改善 | `sources/protocols.py` 定义 `MetadataFetcher`、`MarketFetcher`、`FundamentalFetcher`、`CapitalFetcher`、`MacroFetcher`、`CommodityFetcher` |
| import-linter 覆盖不足 | 已大幅改善 | 当前 33 条合约全部通过，覆盖分层、Kernel/Infra/Data/Analytics/Engine/App/Interfaces 与 Data 子域隔离 |
| Kernel 文件按技术类型堆叠 | 已闭环 | 当前 Kernel 12 个文件，按 `instrument.py` / `market.py` / `strategy.py` / `order.py` 等子域拆分 |
| `obv_ma20` 缺少 `obv` 依赖 | 已闭环 | `technical.py` 中 `obv_ma20.dependencies=("obv",)` |
| Command DTO 缺失 | 已改善 | `CancelRunCommand`、`RetryRunCommand` 已存在并被 re-export |
| Kernel 测试缺失 | 已改善 | `packages/kernel/tests/unit` 已覆盖 order、market、strategy、quality、exceptions 等 |

### 3.2 部分闭环但仍有尾部风险

| 旧问题 | 当前状态 | 残余风险 |
|---|---|---|
| Reader/Writer 机械拆分过多 | 部分闭环 | 已有 `ParquetDatasetReader/Writer` 和 `SqliteTableReader/Writer`，但 storage 下仍有 109 个 `*reader.py` / `*writer.py` 文件，很多是薄包装 |
| Ports dataclass 非 Protocol | 部分闭环 | 外部 source 已 Protocol 化，但 `services/deps.py` 仍用多个 dataclass 聚合依赖，属于 DI 参数治理而非真正 Port |
| DI 注册遗漏 | 部分闭环 | App/Data 多个服务已注册，但 `ConfigValidationProvider` 仍未注册 |
| DQSettings 未被消费 | 部分闭环 | `QualityEngine` 已支持 `dq_settings`，但 DI provider 未传入 |
| Interface 层业务泄漏 | 部分闭环 | 多数路由走 App facade，但 `trade.deviation`、`source`、`backtest` 仍有业务/编排逻辑 |
| App 直接读环境变量 | 仍存在 | `get_trading_calendar_range()` 在 App Provider 中读 `os.environ` |

### 3.3 未闭环或仍建议保留为债务

| 旧问题 | 当前状态 | 建议 |
|---|---|---|
| `ENVIRONMENT` 未迁到 `DITTO_ENV` | 未闭环 | 做兼容迁移：优先 `DITTO_ENV`，兼容读取旧 `ENVIRONMENT`，加 deprecation 日志 |
| `DQSettings.environment` 是 `str` | 未闭环 | 改为 `Environment` 枚举或独立 DQ 环境枚举 |
| `tdx_path` 默认 Windows 路径 | 未闭环 | 改为可选配置，并在实际启用 TDX 时校验 |
| Analytics expression 反向依赖 materialization contracts | 未闭环 | 将 `Analysis` / `AnalysisWarning` 移到 `expression/contracts.py` |
| Engine 硬编码默认时间 | 未闭环 | 改为显式传入或由 `Clock` 注入 |
| Engine `AssertionError` 运行时校验 | 未闭环 | 替换为 `EngineError` 子类或 `ValueError` |

---

## 4. 当前分层评价

### 4.1 Kernel

评分：8.5 / 10

Kernel 已经很接近项目目标：文件数只有 12 个、857 行，边界清晰，import-linter 验证 Kernel 不依赖其他层。`DittoError`、`DataError`、`InstrumentId`、`AssetClass`、`OrderSide`、`DecisionFrame` 等共享原语集中管理，整体比旧审计时更健康。

保留风险：

- `CALENDAR_TO_TIMEZONE` / `GRAIN_TO_TIME_KEYS` 仍从顶层 `__init__.py` re-export，旧审计认为内部常量不应导出。若外部确有消费者，应保留；否则可降为模块内常量。
- `DQResult` 的多个计数 property 每次遍历 issues，规模大时有重复计算成本，但目前不是正确性风险。
- `MacroCategory` / `MacroFrequency` / `RiskScope` 仍在 Kernel。旧计划曾建议迁出，但当前修复计划说明其多包消费会触发 importlinter 问题，因此保留是合理折中。

### 4.2 Infra

评分：8.0 / 10

Infra 方向正确：`foundation` 与 `services` 分层明确，数据目录结构已经从 Infra 硬编码迁到 `DataStoreSettings.all_directories()`，这修复了旧报告的 I-P1-1 类问题。

主要问题是配置初始化链断裂：

- `ConfigValidationProvider` 已实现，但 `ConfigProvider.init_coordinator()` 只注册了 `DataRootInitProvider`、`DataSourceValidationProvider`、`MetadataDbInitProvider`，没有注册 `ConfigValidationProvider`。
- `ConfigValidationProvider` 只校验 `DATA_DIR`，而 `DataRootInitProvider` 本身会创建目录。它的定位需要重新定义：如果它负责“启动前必须存在”，就不应和自动创建目录的 provider 混在同一个 startup 链；如果负责“初始化后验证”，则应在 DataRootInitProvider 之后运行。

### 4.3 Data

评分：7.6 / 10

Data 层改善很明显，但仍是项目复杂度核心。当前 340 个源码文件、42,343 行，占源码总量约 43%。相比旧报告的 60% 已下降，但仍是最大包。

积极变化：

- `DataSource` ABC 已退场，`sources/base.py` 只 re-export 异常。
- `sources/protocols.py` 将数据源能力拆成多个 Fetcher Protocol，符合 ISP。
- `ParquetDatasetReader` / `ParquetDatasetWriter` 与 `SqliteTableReader` / `SqliteTableWriter` 已承担通用读写逻辑。
- `DataSourceError` / `SourceFetchError` 权威定义统一到 `data/errors.py`。

残余问题：

- Reader/Writer 参数化还没有转化为文件数量下降。storage 下仍有 109 个 reader/writer 文件，多数薄包装仍带来导入、DI、测试和维护成本。
- `DataProvider` 仍只有 `get_bars`、`get_instruments`、`get_schedule`、`get_factor` 4 个方法，能满足 Engine 现阶段回测，但不足以作为通用 DataPortal。
- `.importlinter` 中 `data-storage-no-model-import` 对 `ditto_data.models.*` 仍有较宽 ignore。当前合约是“有文档的豁免”，不是强隔离。
- `Dataset` 枚举仍包含 `asset_class`、`date_schedule`、`get_asset_class()` 等业务映射逻辑。作为短期唯一真源很实用，但长期应提炼为 dataset registry/metadata。
- `RuntimeProvider` 仍有 474 行，职责覆盖 SQLite、运行时 stores、服务注册、SQL engine，是 Data DI 的最大聚合点。
- `TdxSource._get_exchange_mapping()` 仍有 TODO，当前靠代码前缀推断 exchange，不适合长期质量对账。

### 4.4 Analytics

评分：7.3 / 10

Analytics 的表达式引擎在 PIT 语义上做得比较扎实：rolling 类时序算子通过 `shift(1)` 避免当前行泄漏，测试中也有 golden data 覆盖。`validate_factor_specs()` 已去掉旧报告提到的 bare Exception 式最终吞没，当前会收集错误并返回。

主要问题是内部依赖方向：

- `expression/analyzer.py` 导入 `ditto_analytics.materialization.contracts.Analysis` / `AnalysisWarning`。
- `materialization/contracts.py` 同时定义 materialization 请求/结果、编译产物、`Analysis`，并直接引入 `polars`。

这意味着 expression 这个更底层、更基础的编译阶段依赖 materialization 这个更外层的执行阶段。虽然包级 import-linter 全绿，但 Analytics 内部仍缺少“expression → materialization 禁止反向依赖”的子域合约。

因子分类重叠也仍存在：`alpha.py` 中混合了 momentum/value/quality/volatility/liquidity 等 composite factors，`fundamental.py` 中仍有 `earnings_growth`。这不是交付阻塞，但会影响因子库扩展治理。

### 4.5 Engine

评分：8.0 / 10

Engine 仍是架构质量较高的包：Pipeline + Step Chain 清晰，`EngineLoop` 已实现 `TradingLoop` Protocol，事件总线、规则提供者、DataProvider 都通过 Protocol 或窄接口接入。

需要尽快修复的运行时债务：

- `Order.created_at` 与 `OrderEvent.timestamp` 默认值仍是 `datetime(2026, 1, 1)`。这会污染审计记录和测试外的真实运行。
- `BacktestBrokerage._build_fill_event()` 用 `AssertionError` 表达 fill model 合约错误。生产运行中应抛 `EngineError` 子类或 `ValueError`。
- `EngineLoop._execute_delayed_signal()` 捕获 `Exception` 后只 warning 并 return，会让 flush 失败变成“静默少交易”。这是正确性风险，建议纳入 P1。
- `OrderCanceled` / `PositionChanged` 事件仍标注为预留且未在生产流程发布。可以保留，但应从公共事件表中标记 experimental，避免使用方误判事件完整性。

### 4.6 App

评分：7.4 / 10

App 内部 R8 import-linter 合约全部通过，Command/Query/Process/Builders 的边界比旧审计时更可靠。Command DTO 也已经补齐。当前问题主要是 provider 与 process 复杂度：

- `providers.py` 528 行，仍是 App DI 的高耦合聚合点。
- `process/ingestion/coordinator.py` 753 行，`process/materialization/orchestrator.py` 581 行，`helpers.py` 503 行，仍是变更热点。
- `get_trading_calendar_range()` 在 App 层直接读环境变量，和“配置只在 Interfaces/Port 层加载”的规则冲突。
- `QualityEngine` 的 `DQSettings` 没有从 DI 注入，导致配置开关实际上不会生效。

建议先处理配置/DQ 断点，再考虑拆 coordinator 或 helpers。前者是行为正确性，后者是维护性。

### 4.7 Interfaces

评分：7.0 / 10

Interfaces 层整体能通过 import-linter，但还有几个旧问题仍在：

- `api/routes/trade.py:get_deviation()` 在路由层计算 fill 聚合、填充状态、偏差项。该逻辑应下沉到 App Query Facade。
- `api/routes/source.py` 内联 Request/Response 模型，并通过 `type(exc).__name__` 字符串匹配错误类型。它还用 `TYPE_CHECKING` 延迟导入 `TushareSource`，这与项目“禁止用 TYPE_CHECKING 规避边界”的原则存在张力。
- `jobs/tasks/dq_batch.py` 仍维护 `_DEFAULT_DATASETS` 字符串列表，虽然 CLI/API 已从 `Dataset.all_datasets()` 派生，但 job 侧仍有重复真源。
- `api/routes/backtest.py` 仍包含 CostConfig 映射、flow 参数构造、进程内 flow 执行与失败回调。V1 可以接受，但如果进入长任务/分布式 worker，需要把 orchestration 从 route 里继续下沉。

---

## 5. 新发现清单

### P0

本次未发现 P0。

### P1：建议优先修复

| ID | 问题 | 影响 | 位置 |
|---|---|---|---|
| N-P1-1 | `ConfigValidationProvider` 已实现但未注册 | 启动通用配置校验不会执行，旧 X-P1-4 变体仍存在 | `interfaces/src/ditto_interfaces/registry/infra/config.py:108-119` |
| N-P1-2 | `DQSettings` 已加载但未注入 `QualityEngine` | `l1_enabled/l2_enabled/l3_enabled` 开关不会生效 | `packages/data/src/ditto_data/di/quality.py:101-114` |
| N-P1-3 | Engine 默认时间硬编码为 `2026-01-01` | 审计记录、订单事件默认时间不可信 | `packages/engine/src/ditto_engine/accounting/order_book.py:91,121` |
| N-P1-4 | 延迟信号 flush 阶段吞掉 `Exception` | 可能静默漏执行尾部交易 | `packages/engine/src/ditto_engine/backtest/engine.py:429-433` |
| N-P1-5 | Brokerage 用 `AssertionError` 表达运行时合约错误 | 生产错误语义不清，异常映射不稳定 | `packages/engine/src/ditto_engine/execution/brokerage.py:358-364` |
| N-P1-6 | `ENVIRONMENT` 仍未迁到 `DITTO_ENV` | 与旧审计要求不一致，通用变量名易冲突 | `packages/infra/src/ditto_infra/foundation/config/environment.py:53-67` |

### P2：计划修复

| ID | 问题 | 影响 | 位置 |
|---|---|---|---|
| N-P2-1 | `DQSettings.environment` 仍是 `str` | 类型安全不足，和 `Environment` 枚举断裂 | `packages/data/src/ditto_data/quality/config.py:13-16` |
| N-P2-2 | `tdx_path` 默认 Windows 路径 | Linux/macOS 默认配置不跨平台 | `packages/data/src/ditto_data/config/data_source.py:32-33` |
| N-P2-3 | Analytics expression 依赖 materialization contracts | 内部层级反向，后续拆分/缓存演进成本高 | `packages/analytics/src/ditto_analytics/expression/analyzer.py:19` |
| N-P2-4 | `DataProvider` 仍偏窄 | 只够回测与因子，无法承担更完整 DataPortal 角色 | `packages/data/src/ditto_data/provider.py:76-100` |
| N-P2-5 | storage reader/writer 文件数仍高 | 参数化基础已有，但维护面仍大 | `packages/data/src/ditto_data/storage/**` |
| N-P2-6 | `Dataset` enum 承担业务映射 | 作为唯一真源实用，但模型层仍有服务知识 | `packages/data/src/ditto_data/models/common.py:100-170` |
| N-P2-7 | `.importlinter` storage-model 合约豁免过宽 | 合约通过但隔离强度有限 | `.importlinter:312-327` |
| N-P2-8 | App 直接读环境变量 | 配置入口分散 | `packages/app/src/ditto_app/providers.py:134-147` |
| N-P2-9 | Interfaces trade route 承载偏差计算 | route 层业务逻辑泄漏 | `interfaces/src/ditto_interfaces/api/routes/trade.py:329-385` |
| N-P2-10 | DQ batch 默认数据集重复维护 | Dataset 真源未完全统一 | `interfaces/src/ditto_interfaces/jobs/tasks/dq_batch.py:18-35` |

### P3：整理型债务

| ID | 问题 | 建议 |
|---|---|---|
| N-P3-1 | `source.py` 路由内联模型与字符串异常匹配 | 模型迁到 `interfaces.models.source`，异常改用明确类型 |
| N-P3-2 | `OrderCanceled` / `PositionChanged` 公共导出但未发布 | 标记 experimental 或补发布路径 |
| N-P3-3 | `RuntimeProvider` 474 行 | 按 SQLite infra、runtime stores、runtime services、SQL engine 拆分 |
| N-P3-4 | TDX exchange 映射 TODO | 接入 InstrumentStore 批量查询 |
| N-P3-5 | 因子分类仍交叉 | 建立 factor registry metadata，而不是按文件名承载 taxonomy |

---

## 6. 建议修复顺序

### Sprint A：配置与质量开关闭环

目标：清掉最容易引发“配置看似存在但运行不生效”的问题。

1. 在 `ConfigProvider.init_coordinator()` 注册 `ConfigValidationProvider`，并确认它与 `DataRootInitProvider` 的执行语义。
2. `QualityProvider.dq_engine()` 注入 `DQSettings`，补测试覆盖 `l1/l2/l3_enabled=False` 的实际跳过行为。
3. `get_environment()` 改为优先读 `DITTO_ENV`，兼容旧 `ENVIRONMENT`，对旧变量发 deprecation warning。
4. `DQSettings.environment` 改为枚举或接收 `Environment` 后序列化使用。
5. `tdx_path` 改为无平台默认值，只有启用 TDX 时才强校验。

### Sprint B：Engine 正确性债务

目标：避免审计记录和回测尾部交易出现静默偏差。

1. `Order.created_at` / `OrderEvent.timestamp` 去掉 `2026-01-01` 默认值，要求调用方显式传入，或由 Engine/Clock 统一创建。
2. `_execute_delayed_signal()` 捕获异常时返回失败状态并写入 `EngineResult.skipped_dates` / errors，而不是只 warning。
3. `_build_fill_event()` 的 `AssertionError` 改为 `EngineError` 子类，例如 `FillContractError`。
4. 对 `OrderCanceled` / `PositionChanged` 做二选一：补发布路径，或从公共 API 标注预留。

### Sprint C：边界与复杂度收敛

目标：降低下一轮功能迭代成本。

1. Analytics：把 `Analysis` / `AnalysisWarning` 移到 `expression/contracts.py`，新增 analytics 内部 import-linter 合约。
2. Interfaces：把 `trade.deviation` 下沉到 App Query；`source.py` 的模型和异常类型显式化。
3. Data：选择一批最薄的 reader/writer wrapper 删除或自动生成，优先从 Parquet market wrappers 开始。
4. Dataset：把 `asset_class` / `date_schedule` 映射迁入 dataset registry metadata，保留 enum 只做稳定 id。
5. DQ batch：默认数据集从 Dataset/registry 派生，删除硬编码列表。

---

## 7. 结论

2026-04-17 审计指出的最大 P0 风险已经修掉，项目当前的机器门禁也很强：lint、type、arch、fast test 全部通过。当前不建议再做“全项目大重构”，因为架构骨架已可用，真正影响交付的是少数配置断点和 Engine 正确性尾巴。

下一步最有性价比的是先做 Sprint A + Sprint B。完成后，项目可从“架构合格但有明显尾债”进入“V1 可持续迭代”的状态；Sprint C 再逐步降低长期维护成本。
