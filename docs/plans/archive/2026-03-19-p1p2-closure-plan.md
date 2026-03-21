# 日频策略完备度 P1+P2 收尾计划

**日期**: 2026-03-19
**基准**: 基于 2026-03-18 差距分析报告二次审计
**状态**: 已完成 (2026-03-19)

---

## Context

基于 2026-03-18 差距分析报告的二次审计，P0 已全部关闭（15/15）。本计划覆盖剩余 P1（6 个，ENG-E-11 已在未提交代码中实现）和有价值的 P2 项。经审计，34 个原始 P2 中 **13 个已关闭**，剩余中 **9 个建议 DEFER**（v1 无需），**8 个有实际价值**（NICE）。

---

## P1 收尾（6 个）

### P1-A: META-UV-1 — CSI 300/500/1000 指数 Universe 自动创建

**问题**: Universe 基础设施完整，但缺少从 index_composition 到 named universe 的桥接。策略无标准指数可用。

**方案**: 在 `MetadataService` 新增 `sync_index_universe(index_code, asof_date)` 方法：
1. 从 `IndexCompositionReader` 查询成分
2. 调用 `UniverseWriter.replace_constituents()` 原子写入
3. 对 CSI 300/500/1000 三个指数批量执行

**文件**:
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增 `sync_index_universe()`
- `packages/datahub/tests/unit/services/test_metadata_service_universe.py` — 测试

**复杂度**: S

### P1-B: ING-A-1 — 复权因子按 ticker 回填

**问题**: 复权因子数据存在空洞（停牌期间无数据），无自动回填机制。

**方案**: 在 IngestionCoordinator 新增 `backfill_adj_factor(instrument_id, start, end)`：
1. 查询当前已有数据的最后日期
2. 从 Tushare 拉取缺失区间
3. DQ 校验后写入
4. 暴露为 CLI 命令 `pixi run ingest backfill-adj --ticker 000001.SZ`

**文件**:
- `apps/port/src/ditto_port/services/ingestion/coordinator.py` — 新增回填方法
- `apps/port/src/ditto_port/cli/commands/ingest/` — 新增 CLI 命令
- `packages/datahub/src/ditto_datahub/services/market_service.py` — 新增 `backfill_adj_factor()`

**复杂度**: M

### P1-C: ING-F-1 — ROE 直接采集

**问题**: 估值指标已覆盖 PE/PB/PS/股息率，但 ROE 需要从财报推导，未直接采集。

**方案**: Tushare `daily_basic` API 已包含 `roe` 字段，在 `VALUATION_METRICS_MAPPING` 中增加映射。

**文件**:
- `packages/datahub/src/ditto_datahub/sources/tushare/processors/mappings/capital.py` — VALUATION_METRICS_MAPPING 加 `roe`
- `packages/datahub/src/ditto_datahub/models/metadata.py` — StockExtension 加 `roe` 字段（如需要）

**复杂度**: S

### P1-D: ING-ST-1 / META-MD-2 — ST 状态变更显式记录

**问题**: ST 有日快照但无 `effective_from/to` 变更记录。当前日快照可查历史，但不是最优形态。

**方案**: 在 `StockStatusWriter` 新增 `record_st_change()` 方法，参考 `NameHistoryWriter` 模式：
1. 对比前后两日 `is_st` 状态
2. 变化时写入 `st_change_history` 表（instrument_id, effective_from, is_st, st_type, effective_to）
3. 提供 `get_st_status(instrument_id, asof_date)` PIT 查询

**文件**:
- `packages/datahub/src/ditto_datahub/stores/market/stock/status/status_writer.py` — 新增方法
- `packages/datahub/src/ditto_datahub/stores/market/stock/status/status_reader.py` — PIT 查询
- `packages/datahub/scripts/schema.sql` — 新表

**复杂度**: M

### P1-E: META-RS-1 — LateArrivalPolicy

**问题**: 数据延迟到达（如财报晚发）无处理策略。

**方案**: 在数据写入层增加 `knowledge_date` 概念：
1. 每条写入记录标记 `knowledge_date`（数据可知的日期）
2. `LateArrivalPolicy` 枚举：`REJECT`（拒绝迟到的数据）、`ACCEPT`（直接写入）、`REBUILD`（重算受影响的因子）
3. 在 `MarketService` 写入路径中检查策略

**文件**:
- `packages/datahub/src/ditto_datahub/models/derived.py` 或新建 policy model — LateArrivalPolicy 定义
- `packages/datahub/src/ditto_datahub/services/market_service.py` — 写入检查
- 测试文件

**复杂度**: M

### P1-F: MAT-M-4 — 大数据集内存管理

**问题**: 全量加载 OOM 风险。

**方案**: 在 `ArtifactReader` 的 scan 路径中增加流式读取选项：
1. 使用 Polars `scan_parquet` + `lazy().collect(streaming=True)` 替代 `read_parquet`
2. 对大查询增加 `row_limit` 参数，返回迭代器
3. `QueryService` 暴露 `query_streaming()` 方法

**文件**:
- `packages/datahub/src/ditto_datahub/services/derived/artifact_reader.py` — lazy streaming
- `packages/datahub/src/ditto_datahub/services/derived/query_service.py` — 流式查询 API

**复杂度**: M

---

## P2 — 有价值项（8 个，其余 DEFER 或 DROP）

### DROP（13 个，已关闭无需处理）

| ID | 缺口 | 原因 |
|----|------|------|
| ING-SS-2 | IPO 日期过滤 | `min_list_days` 已实现 |
| ING-X-1 | 摄入调度器 | Prefect flows 已实现 |
| ING-X-2 | 并发写入竞态 | FileLockManager 已实现 |
| ENG-E-12 | L1 缓存无上限 | LRU maxsize=256 |
| ENG-E-15 | 窗口参数校验 | `_require_positive()` 已实现 |
| ENG-E-16 | L2 双重解析 | AST 预解析已实现 |
| ENG-E-17 | 缺失标量算子 | log10/log2/floor/ceil/round 已实现 |
| ENG-E-18 | 无算子 golden 测试 | 49KB 测试文件已实现 |
| META-MD-5 | 名称变更历史 | NameHistoryReader/Writer 已实现 |
| META-IN-4 | 多级行业单条查询 | `get_stock_industries_all_levels()` 已实现 |
| META-UV-4 | 调仓日程跟踪 | RebalanceReader/Writer 已实现 |
| CFG-2 | 策略配置段 | `TradingSettings` 已实现 |
| CFG-3 | Settings 聚合 | `Settings` model 已实现 |

### DEFER（9 个，v1 无需）

| ID | 缺口 | 推理 |
|----|------|------|
| ING-C-1 | 股本变动数据 | 日频因子策略不需要股本变动细节，PE/PB 已基于市值 |
| MAT-M-9 | 可配置压缩 | Snappy 是分析型最优默认值，存储成本非当前瓶颈 |
| MAT-M-10 | Query→Eval 适配器 | 评估模块输入契约清晰，消费者可直接处理 |
| MAT-M-11 | Catalog 统一查询 | 开发体验便利，非正确性问题 |
| INVAL-IC-5 | 分布式锁 | 当前单进程运行，Kvrocks 已在栈中可后续接入 |
| META-MD-6 | 股份类型区分 | 仅 A 股策略，B/H 股无需求 |
| META-MD-7 | board 枚举化 | 字符串匹配在 v1 足够 |
| META-CL-3 | 北交所日历 | 北交所标的不适合日频因子策略 |
| META-IN-3 | PIT 重组分类 edge case | PIT 框架完整，重组导致的行业变更为极小众场景 |

### NICE — 建议实现（8 个）

#### P2-A: ENG-E-14 — 表达式类型检查

**价值**: 编译期拦截 `cs_rank("string")` 等类型错误，而非运行时 Polars 报错。

**方案**: 在 analyzer 阶段新增轻量类型推断（Column→Float, String→String, Number→Float），在 codegen 分发前校验。

**文件**: `packages/core/src/ditto_core/engine/expression/analyzer.py`

**复杂度**: M

#### P2-B: ENG-E-13 — cs_winsorize 支持分位数模式

**价值**: 当前只支持 sigma 模式。分位数 winsorize（5th/95th percentile）是学术界标准做法。

**方案**: 扩展 `cs_winsorize(x, n)` 为 `cs_winsorize(x, method="sigma", n=3)` 或 `cs_winsorize(x, method="quantile", lower=0.05, upper=0.95)`。

**文件**: `packages/core/src/ditto_core/engine/expression/codegen.py`, `registry.py`

**复杂度**: S

#### P2-C: CFG-1 — 启动配置校验

**价值**: 防止 TOKEN 为空、数据目录不存在等导致运行时困惑。

**方案**: 在 `ConfigInitCoordinator.check()` 中增加关键字段非空校验（TUSHARE_TOKEN、DATA_DIR）。

**文件**: `packages/infra/src/ditto_infra/foundation/config/initializer.py`

**复杂度**: S

#### P2-D: META-CL-4 — 特殊交易日消费

**价值**: `is_special` 字段已存在于 schema，只需在因子计算中感知（如 IPO 首日涨跌幅限制不同）。

**方案**: 在 CalendarReader 查询结果中包含 `is_special`，在因子定义的 context 中可获取。

**文件**: `packages/core/src/ditto_core/engine/factors/` — 因子 context 扩展

**复杂度**: S

#### P2-E: META-UV-5 — Universe 集合运算

**价值**: 方便组合选股池（如 CSI 300 ∩ 低波动率）。

**方案**: 在 MetadataService 新增 `universe_intersection()`, `universe_union()`, `universe_subtract()`。

**文件**: `packages/datahub/src/ditto_datahub/services/metadata_service.py`

**复杂度**: S

#### P2-F: META-RS-2 — 研究数据集多格式导出

**价值**: 人类查看方便。

**方案**: 在研究数据集导出方法中增加 `format="parquet|csv|feather"` 参数。

**文件**: `packages/datahub/src/ditto_datahub/services/research_artifact_service.py`

**复杂度**: S

#### P2-G: MAT-M-8 — Parquet 写入原子性

**价值**: 防止写入中断导致损坏文件。

**方案**: 写入临时文件后 `os.replace()` 原子重命名。

**文件**: `packages/datahub/src/ditto_datahub/stores/runtime/derived_artifact_writer.py`

**复杂度**: S

#### P2-H: ING-C-2 — 公司行动增强

**价值**: 回购/配股数据已有基础设施，仅需在 adapter 中扩展采集字段。

**方案**: 在 CapitalTushareAdapter 中增加 `fetch_share_buyback()` 和 `fetch_rights_issue()` 方法。

**文件**: `packages/datahub/src/ditto_datahub/sources/tushare/adapters/capital.py`

**复杂度**: S

---

## 实施顺序

```
Phase 1 — 策略阻塞项（P1-A/B/C）
  ├── P1-A: CSI Universe 自动创建     [S]
  ├── P1-B: 复权因子回填              [M]
  └── P1-C: ROE 采集                 [S]

Phase 2 — 数据完整性（P1-D/E）
  ├── P1-D: ST 变更记录              [M]
  └── P1-E: LateArrivalPolicy        [M]

Phase 3 — 工程健壮性（P1-F + 高价值 P2）
  ├── P1-F: 内存管理                [M]
  ├── P2-A: 表达式类型检查           [M]
  └── P2-B: winsorize 分位数        [S]

Phase 4 — 收尾打磨（低价值 P2）
  ├── P2-C: 启动校验                [S]
  ├── P2-D: 特殊交易日              [S]
  ├── P2-E: 集合运算                [S]
  ├── P2-F: 多格式导出              [S]
  ├── P2-G: 写入原子性              [S]
  └── P2-H: 公司行动增强            [S]
```

## 验证

每个 Phase 完成后：
```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # 分层依赖检查
```

全部完成后：
```bash
pixi run -e dev ci             # CI 完整检查
```
