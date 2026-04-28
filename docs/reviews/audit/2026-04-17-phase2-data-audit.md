# Phase 2: Data 层审计报告

> **日期**: 2026-04-17
> **范围**: packages/data (325 文件, 46,991 行 — 占总量 60%)
> **架构检查**: 24 条契约全部通过

---

## 总览

Data 是最大的包，分为 6 个子层：models / services / storage / sources / quality / di。整体架构分层清晰，CQRS 在 market/fundamental/capital 三个域执行良好，但存在多处不一致和违规。

---

## P0 — 无

---

## P1 — 架构违规 / 职责错位（10 项）

### 架构分层违规

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| D-P1-1 | ExecutionAuditService 绕过 storage 层 | `services/audit/execution_audit_service.py:33-276` | 直接包含 DDL/SQL，使用 SQLitePool 执行读写，不通过 Reader/Writer 分离 |
| D-P1-2 | Trade Writer 混合读写（CQRS 违规） | `services/trade/{intents,fills,positions}.py` | 3 个 "Writer" 类均包含 get/list/find 读取方法 |
| D-P1-3 | DataSourceError 重复定义，继承链冲突 | `sources/base.py:11` + `errors.py:279` | 同名但继承链完全不同（Exception vs DataError），上层 `except` 可能捕获错误类型 |
| D-P1-4 | SourceFetchError 同名重复定义 | `sources/base.py:109` + `errors.py:426` | 同上，继承链冲突 |
| D-P1-5 | TdxSource 未继承 DataSource 基类 | `sources/tdx/source.py:24` | 架构不一致，缺少统一错误处理和接口约束 |
| D-P1-6 | importlinter 规则形同虚设 | `.importlinter:312-320` | `data-storage-no-model-import` 的 ignore_imports 豁免了几乎所有 models 子模块，storage 实际 57 处导入 models |

### DI 注册遗漏

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| D-P1-7 | ArtifactPersistenceService 未注册 | `services/derived/artifact_persistence_service.py` | DI 容器无法获取该 Service |
| D-P1-8 | BacktestArtifactReader 未注册 | `services/strategy/backtest_artifact_reader.py` | 同上 |
| D-P1-9 | InstrumentRuleProvider 未注册 | `services/strategy/instrument_rule_provider.py` | 同上 |

### 数据源健壮性

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| D-P1-10 | 缺少跨数据源 fallback/降级机制 | sources/ 全局 | Tushare 失败后无自动切换 TDX 的机制，无健康检查/熔断器 |

---

## P2 — 命名不一致 / 抽象不当（10 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| D-P2-1 | Dataset 枚举包含 6 个业务方法 | `models/common.py:100-226` | `asset_class`/`date_schedule` 等方法应属于 service 层 |
| D-P2-2 | InstrumentIdRange.detect_asset_class 含 ~70 行业务逻辑 | `models/common.py:310-402` | 不属于 models 层 |
| D-P2-3 | RuntimeProvider 过于庞大（475 行） | `di/runtime.py` | 注册 15+ Service 和 30+ Reader/Writer，应拆分 |
| D-P2-4 | Ports 模式使用不一致 | services/ 全局 | Market/Fundamental/Capital 使用 Ports；Metadata/Macro/Trade 及 runtime Service 使用裸参数/Protocol/SQLiteClient |
| D-P2-5 | MetadataService Universe 方法绕过子服务 | `services/metadata_service.py:386-436` | 直接操作 _universe_reader/_universe_writer，与委托模式不一致 |
| D-P2-6 | DataProvider Protocol 方法不完整 | `provider.py` | 缺少 Fundamental/Macro/Capital/Trade/Metadata 域的访问方法 |
| D-P2-7 | ParquetStore 与 SQLiteStore merge 代码重复 | `storage/base/parquet_store.py:306-370` + `sqlite_store.py:341-410` | ~50 行重复的 _merge_with_existing 逻辑 |
| D-P2-8 | SQLiteStore 与 SQLiteClient 职责重叠 | `storage/base/sqlite_store.py` + `storage/sqlite_client.py` | 都提供 execute/fetchone/fetchall，使用不够统一 |
| D-P2-9 | FredSource 约 20 个方法为 NotImplementedError | `sources/fred/fred_source.py:138-317` | DataSource 基类过于宽泛 |
| D-P2-10 | Query 模型定义位置分散 | 多处 | `BarQuery` 在 provider.py，`MarketBarsQuery` 在 Service 内，`DerivedLatestQuery` 在独立 queries.py |

---

## P3 — 可改进（9 项）

| # | 问题 | 位置 | 说明 |
|---|------|------|------|
| D-P3-1 | strategy_run.py status 字段类型不精确 | `models/strategy_run.py:36` | 声明为 `str` 而非 `RunStatus` |
| D-P3-2 | _CatalogReader Protocol 重复定义 3 次 | `derived/{artifact_reader,query_service,garbage_collector}.py` | 同名不同接口，容易混淆 |
| D-P3-3 | query_service.py 过多私有函数 | `services/derived/query_service.py:358-466` | 5 个 DataFrame shaping 函数可提取到独立模块 |
| D-P3-4 | JsonDict/JsonValue 重复导出 | `models/derived.py` + `publication_safety.py` | 定义在 common.py，两处重复 __all__ |
| D-P3-5 | CrossSourceChecker 硬编码创建 | `quality/engine.py:47` | 未通过 Protocol 注入 |
| D-P3-6 | 未识别的 rule_type 被静默忽略 | `quality/checkers/technical.py:71`, `business.py:71` | 返回 None 而非报错 |
| D-P3-7 | InstrumentRuleProvider 混合读写 | `services/strategy/instrument_rule_provider.py` | "V1 内存实现"但仍应保持接口分离 |
| D-P3-8 | Checker 使用字符串分发 | `quality/checkers/technical.py:58-71` | 扩展需修改代码，无注册机制 |
| D-P3-9 | __init__.py 缺少显式文档 | `ditto_data/__init__.py` | 未说明 storage/sources 不可直接访问 |

---

## 子层评分

| 子层 | 架构 | 抽象 | 依赖 | 实践 | 说明 |
|------|------|------|------|------|------|
| **models/** | 7/10 | 7/10 | 10/10 | 8/10 | Dataset 枚举和 InstrumentIdRange 含业务逻辑 |
| **services/** | 6/10 | 7/10 | 9/10 | 8/10 | ExecutionAuditService 绕过 CQRS，Trade Writer 混合读写，Ports 不一致 |
| **storage/** | 8/10 | 8/10 | 8/10 | 9/10 | CQRS 分离高度一致，base 类抽象得当，有重复代码 |
| **sources/** | 7/10 | 7/10 | 10/10 | 8/10 | TdxSource 架构不一致，DataSourceError 重复，缺 fallback |
| **quality/** | 9/10 | 8/10 | 10/10 | 8/10 | 设计良好，Protocol 使用合理，checker 扩展方式可改进 |
| **di/** | 7/10 | 7/10 | 9/10 | 7/10 | RuntimeProvider 过大，3 个 Service 未注册 |

---

## 业界对标总结

### Data 层对标

| 维度 | Ditto 现状 | 业界最佳实践 | 差距 |
|------|-----------|-------------|------|
| **TET 管线** (OpenBB) | sources/ → services/ → storage/ 三层 | Transform-Extract-Transform | 基本对标，缺跨源 fallback |
| **统一 Schema** (Databento) | SourceSchema + StoreSchema 分离 | batch/stream 同 schema | batch/stream 未统一（规划中） |
| **DataPortal** (Zipline) | DataProvider Protocol（4 方法） | 统一读取门面 | 方法不完整，缺 5 个域 |
| **DataHandler** (Qlib) | 无 Processor chain | 表达式缓存 + Processor pipeline | 无管线化数据处理 |
| **多源 Fallback** (daily_stock_analysis) | 无 | 多源适配器 + 优先级 fallback | P1 级差距 |

### 积极发现
- **CQRS 分离高度一致**：market/fundamental/capital 三个域严格 Reader/Writer，优于大多数开源项目
- **Polars 100% 覆盖**：零 pandas 依赖
- **quality 零业务依赖**：仅依赖 kernel，设计纯粹
- **base 类抽象得当**：ParquetStore/SQLiteStore 的 Template Method 模式可扩展
