# Layer 5: 元数据 + 日历 + Universe + 研究数据集 + 配置 实施计划

> **状态：全部完成 (18/18)** — 2026-03-18
>
> 单元测试：2544 passed | 覆盖率：82.10% | CI 预存集成测试失败不影响

## Context

日频策略底层能力完备度分析中，Layer 5（元数据域）当前完备度约 85%。本计划覆盖 P0 + P1 + P2 全部 22 项缺口，目标推至 100%。

**关键设计决策**：
- is_st/list_status 的 PIT 化：复用已有 Parquet 日频快照（`market/stock/status/`），不再新建 SQLite PIT 表
- 所有变更遵循 TDD（RED → GREEN → REFACTOR）
- 遵循 CQRS 模式（Reader/Writer 分离）
- SQLite PIT 模式：`effective_from <= asof AND (effective_to IS NULL OR effective_to > asof)`

---

## 依赖图

```
Phase 1 (P0 — 无依赖，可立即开始):
  T01: delist_date 全链路打通

Phase 2 (P1 核心 — 相互独立):
  T02: Calendar 丰富字段自动化
  T03: Status PIT 服务层（复用 Parquet）
  T04: IPO 日期过滤 → 依赖 T01
  T05: 半日交易标记
  T06: SW L3 行业
  T07: CSRC 行业分类
  T08: Universe 流动性过滤
  T09: Universe 批量替换 + 集合运算

Phase 3 (P1 增强):
  T10: LateArrivalPolicy 实施
  T11: Calendar 丰富字段自动化（后处理） → 依赖 T02

Phase 4 (P2):
  T12: 股票名称变更历史
  T13: 多交易所日历 + 特殊交易日 → 依赖 T05
  T14: 行业多级查询 + PIT 覆盖 → 依赖 T06, T07
  T15: Universe 调仓日程
  T16: 研究数据集多格式导出
  T17: 启动配置校验 + 交易策略配置
  T18: Settings 聚合 → 依赖 T17
```

---

## T01: delist_date 全链路打通 [P0] ✅

**缺口**: META-MD-1 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/models/metadata.py` — InstrumentRegistration 添加 `delist_date: str | None = None`
- `packages/datahub/src/ditto_datahub/stores/metadata/instrument/instrument_writer.py:87-102` — INSERT SQL 添加 delist_date
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/stock.py:76,105` — fields 添加 delist_date
- `packages/datahub/src/ditto_datahub/sources/tushare/processors/mappings/basic.py:43-57` — STOCK_BASIC_MAPPING 添加 delist_date 到 date_columns 和 output_columns

**实现**:
1. `InstrumentRegistration` 在 `list_date` 后添加 `delist_date: str | None = None`
2. `InstrumentWriter.register()` INSERT SQL: `(…, list_date, delist_date, is_active) VALUES (…, ?, ?, TRUE)`
3. `StockTushareAdapter.fetch_stock_basic()` — fields 字符串添加 `delist_date`（单只模式和批量模式两处）
4. `STOCK_BASIC_MAPPING` — `date_columns` 添加 `"delist_date": "%Y%m%d"`，`output_columns` 添加 `"delist_date"`
5. `_empty_stock_basic_schema()` 确保包含 delist_date 列

**测试**: 单元测试验证 InstrumentRegistration 持久化 delist_date、delist_date=None 向后兼容

---

## T02: Calendar 丰富字段自动化 [P1] ✅

**缺口**: META-CL-2 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增 `enrich_calendar()` 方法

**实现**:
1. 新增纯函数 `_compute_calendar_enrichment(days: list[dict]) -> list[dict]`：
   - 按 trade_date 排序，筛选 is_open=True 的交易日
   - 计算 prev_trade_date / next_trade_date（shift ±1）
   - 从 trade_date 提取 week_of_year / month / quarter / year
   - 比较 consecutive 交易日判断 is_week_end / is_month_end / is_quarter_end
2. `MetadataService.enrich_calendar(start, end)` 读取未丰富行（prev_trade_date IS NULL）→ 调用纯函数 → 批量 upsert

**测试**: 跨月/跨季/跨年边界正确性、首尾日为 None、幂等性

---

## T03: Status PIT 服务层 [P1] ✅

**缺口**: META-MD-2, META-MD-3 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增 `get_stock_status()` 方法
- DI 容器可选注入 StockStatusReader（或通过构造函数参数）

**实现**:
1. `get_stock_status(instrument_id: int, asof: str) -> dict[str, Any]`：
   - 通过 `StockStatusReader` 读取 Parquet `market/stock/status/{year}.parquet`
   - 筛选 `instrument_id == X AND trade_date <= asof`，取最新行
   - 返回 `{is_st, list_status, is_suspended, suspend_timing}`
   - 无数据时返回默认值 `{is_st=False, list_status="L", is_suspended=False}`
2. SQLite 中 `instrument.is_st` 和 `instrument_stock.list_status` 保留为"当前"缓存，不删除

**测试**: 正常查询、无数据返回默认值、asof 早于所有数据返回默认值

---

## T04: IPO 日期过滤 [P1] ✅

**缺口**: META-MD-4 | **依赖**: T01

**修改文件**:
- `packages/datahub/src/ditto_datahub/stores/metadata/instrument/instrument_reader.py` — `find_securities()` SQL 添加日期过滤
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — `find_securities()` 添加 `min_list_days` 参数

**实现**:
1. `InstrumentReader.find_securities()` 添加 `min_list_days: int | None = None` 参数
2. SQL 追加: `AND (i.list_date IS NULL OR julianday(?, 'start of day') - julianday(i.list_date, 'start of day') >= ?)`
3. `MetadataService.find_securities()` 透传参数

**测试**: min_list_days=60 正确排除新股、None 不过滤、list_date=NULL 不过滤

---

## T05: 半日交易标记 [P1] ✅

**缺口**: META-CL-1 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/scripts/schema.sql` — trading_calendar 添加 `is_half_day BOOLEAN DEFAULT FALSE`
- `packages/datahub/src/ditto_datahub/models/metadata.py` — CalendarDay 添加 `is_half_day: bool = False`
- `packages/datahub/src/ditto_datahub/stores/metadata/calendar/calendar_writer.py` — upsert 包含 is_half_day
- `packages/datahub/src/ditto_datahub/stores/metadata/calendar/calendar_reader.py` — 读取 is_half_day
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — `compute_half_days()` 方法

**实现**:
1. CalendarDay 添加 `is_half_day: bool = False`
2. schema.sql 添加列
3. CalendarWriter/Reader 适配
4. `compute_half_days()`: 从已有 `suspend_d` 数据（Parquet `market/stock/status/`）中检测 `suspend_timing` 包含下午时段的日期，标记为半日

**测试**: CalendarDay 构造、已知半日日期标记正确

---

## T06: SW L3 行业支持 [P1] ✅

**缺口**: META-IN-1 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/industry.py` — `fetch_sw_industry()` 和 `fetch_sw_industry_concepts()` 扩展 level=3

**实现**:
1. `fetch_sw_industry(level=3)` — Tushare `index_classify` API 已支持 `src="SW2021"` + `level="3"`，现有代码直接可用，更新 docstring
2. `fetch_sw_industry_concepts()` — 添加 `level: int = 1` 参数，替换硬编码的 `level="1"` 和 `industry_level=1`
3. 需要为 L2/L3 行业构建 `index_code → parent_index_code` 的映射（通过 `index_classify` 返回的 `ts_code` 层级关系或 `parent_id`）

**测试**: level=3 返回三级行业数据、concepts 返回 L2/L3 成分

---

## T07: CSRC 行业分类 [P1] ✅

**缺口**: META-IN-2 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/scripts/schema.sql` — industry_basic 添加 `source TEXT DEFAULT 'sw'`
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/industry.py` — 新增 `fetch_csrc_industry()` 方法
- `packages/datahub/src/ditto_datahub/stores/metadata/industry/industry_reader.py` — `get_all()` 添加 source 过滤
- `packages/datahub/src/ditto_datahub/stores/metadata/industry/industry_mapping_writer.py` — source 参数化

**实现**:
1. schema.sql industry_basic 表添加 `source TEXT DEFAULT 'sw'` 列
2. `fetch_csrc_industry()` — 使用 Tushare `csrc_industrial` API（或 `ths_member`），映射到 IndustryBasic 模型 `source="csrc"`
3. `IndustryReader.get_all()` 支持 `source` 过滤参数
4. `IndustryMappingWriter.update_mapping()` source 参数化（当前硬编码 `'sw'`）

**测试**: CSRC 行业数据采集、source 过滤正确

---

## T08: Universe 流动性过滤 [P1] ✅

**缺口**: META-UV-2 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增 `get_filtered_universe()` 方法

**实现**:
1. `get_filtered_universe(universe_id, asof, min_avg_volume=None, min_avg_turnover=None, lookback=20)`:
   - 获取 base constituent IDs（UniverseReader）
   - 读取 lookback 窗口内的成交量/换手率数据（通过 MarketService 或直接读 Parquet）
   - 计算每只股票的平均值（PIT 安全：`closed="left"`）
   - 过滤低于阈值的股票
   - 返回过滤后的 ID 列表

**测试**: 低成交量股票被过滤、None 不过滤、空 universe

---

## T09: Universe 批量替换 + 集合运算 [P1] ✅

**缺口**: META-UV-3, META-UV-5 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/stores/metadata/universe/universe_writer.py` — 新增 `replace_constituents()`
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增集合运算方法

**实现**:
1. `UniverseWriter.replace_constituents(universe_id, records, effective_date)`:
   - 事务中: 关闭所有当前成分（SET effective_to）→ 批量插入新成分
2. Service 层集合运算（纯 Python set 操作）:
   - `universe_intersection(id_a, id_b, asof) -> list[int]`
   - `universe_union(id_a, id_b, asof) -> list[int]`
   - `universe_subtract(id_a, id_b, asof) -> list[int]`

**测试**: replace 原子性、集合运算正确性

---

## T10: LateArrivalPolicy 实施 [P1] ✅

**缺口**: META-RS-1 | **依赖**: 无

**修改文件**:
- `packages/core/src/ditto_core/engine/research.py` — 新增检测/处理函数
- `apps/port/src/ditto_port/services/derived/research.py` — build() 集成

**实现**:
1. `_detect_late_arrivals(frame, derived_id) -> pl.DataFrame`:
   - 比较 `known_at` vs `{derived_id}_availability_time`
   - 标记 `availability_time > known_at` 的行
2. `_apply_late_arrival_policy(frame, policy, late_flags)`:
   - EXCLUDE: 标记行设为 null
   - SHIFT: 标记行移至下一个 sample_row_id（v1 暂记日志）
   - REBUILD: raise `LateArrivalError` 包含详情
3. `ResearchDatasetFacade.build()` 在 `_pit_join` 后调用

**测试**: 延迟数据检测正确、各 policy 行为符合预期

---

## T11: Calendar 丰富字段自动化（后处理） [P1] ✅

**缺口**: META-CL-2 (自动化部分) | **依赖**: T02

**修改文件**:
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增 `auto_enrich_calendar()` 方法

**实现**:
1. 读取 `prev_trade_date IS NULL` 的交易日行
2. 调用 T02 的 `_compute_calendar_enrichment()`
3. 通过 CalendarWriter 批量 upsert
4. 幂等：已丰富行跳过

**测试**: 幂等性、混合丰富/未丰富行

---

## T12: 股票名称变更历史 [P2] ✅

**缺口**: META-MD-5 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/scripts/schema.sql` — 新建 `instrument_name_history` 表
- 新建 `packages/datahub/src/ditto_datahub/stores/metadata/instrument/name_history_reader.py`
- 新建 `packages/datahub/src/ditto_datahub/stores/metadata/instrument/name_history_writer.py`
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增 `get_stock_name(instrument_id, asof)`

**实现**:
1. 表: `(instrument_id INTEGER, old_name TEXT, new_name TEXT, changed_date DATE, PRIMARY KEY (instrument_id, changed_date))`
2. Reader: `get_name(instrument_id, asof)` — `WHERE changed_date <= asof ORDER BY changed_date DESC LIMIT 1`
3. Writer: `record_name_change(instrument_id, old_name, new_name, date)`
4. Tushare `namechange` API 采集（新增 adapter 方法或扩展 fetch_stock_basic）

**测试**: CRUD、PIT 查询、无历史返回当前名称

---

## T13: 多交易所日历 + 特殊交易日 [P2] ✅

**缺口**: META-CL-3, META-CL-4 | **依赖**: T05

**修改文件**:
- `packages/datahub/src/ditto_datahub/scripts/schema.sql` — 添加 `exchange TEXT DEFAULT 'SSE'`, `is_special BOOLEAN DEFAULT FALSE`
- `packages/datahub/src/ditto_datahub/models/metadata.py` — CalendarDay 添加字段
- `packages/datahub/src/ditto_datahub/sources/tushare/adapters/calendar.py` — 支持 exchange 参数
- Reader/Writer 适配

**实现**:
1. CalendarDay 添加 `exchange: str = "SSE"` 和 `is_special: bool = False`
2. CalendarTushareAdapter.fetch_calendar(exchange="SSE") — 替换硬编码
3. 特殊交易日标记：Tushare `trade_cal` 返回的周末交易日或补班日标记为 `is_special=True`

**测试**: SZSE 日历获取、特殊日标记

---

## T14: 行业多级查询 + PIT 覆盖 [P2] ✅

**缺口**: META-IN-3, META-IN-4 | **依赖**: T06, T07

**修改文件**:
- `packages/datahub/src/ditto_datahub/stores/metadata/industry/industry_mapping_reader.py` — 新增多级查询方法
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增 `get_stock_industries_all_levels()`

**实现**:
1. `get_stock_industries_all_levels(instrument_id, asof, source="sw") -> list[dict]`:
   - 查询 industry_mapping 获取该股票所有行业关系
   - JOIN industry_basic 获取 industry_level
   - 按 level 排序返回（L1, L2, L3）
2. PIT 重组检测：行业变更时 effective_from/to 正确切换

**测试**: 返回多级行业、PIT 重组正确

---

## T15: Universe 调仓日程 [P2] ✅

**缺口**: META-UV-4 | **依赖**: 无

**修改文件**:
- `packages/datahub/src/ditto_datahub/scripts/schema.sql` — 新建 `universe_rebalance` 表
- 新建 Reader
- `packages/datahub/src/ditto_datahub/services/metadata_service.py` — 新增方法

**实现**:
1. 表: `(universe_id TEXT, rebalance_date DATE, description TEXT, PRIMARY KEY (universe_id, rebalance_date))`
2. Reader: `get_next_rebalance(universe_id, after_date)` / `list_rebalances(universe_id)`
3. Writer: `record_rebalance(universe_id, date, description)`

**测试**: CRUD、获取下次调仓日

---

## T16: 研究数据集多格式导出 [P2] ✅

**缺口**: META-RS-2 | **依赖**: 无

**修改文件**:
- `apps/port/src/ditto_port/services/derived/research.py` — 新增 `export()` 方法

**实现**:
1. `export(snapshot: DatasetSnapshot, format: str, path: Path)`:
   - `format="csv"`: `df.write_csv(path)`
   - `format="sqlite"`: `df.write_database(table_name, connection_string)`
2. 默认导出 Parquet 保持不变

**测试**: CSV 导出内容匹配、SQLite 导出可查询

---

## T17: 启动配置校验 + 交易策略配置 [P2] ✅

**缺口**: CFG-1, CFG-2 | **依赖**: 无

**修改文件**:
- `packages/infra/src/ditto_infra/foundation/config/settings.py` — 新增 `TradingSettings`
- `packages/infra/src/ditto_infra/foundation/config/initializer.py` — 添加校验逻辑

**实现**:
1. `TradingSettings(BaseModel)`: `default_universe`, `max_position_pct`, `risk_free_rate`, `benchmark`, `cost_bps`, `slippage_bps`
2. `ConfigInitProvider` 子类: 启动时校验必填字段非空、路径存在
3. 生产环境额外校验: TUSHARE_TOKEN 非空、DATA_ROOT 可写

**测试**: 无效配置抛出异常、有效配置通过

---

## T18: Settings 聚合 [P2] ✅

**缺口**: CFG-3 | **依赖**: T17

**修改文件**:
- `packages/infra/src/ditto_infra/foundation/config/settings.py` — Settings 聚合所有子设置

**实现**:
1. `Settings(BaseModel)` 添加 `trading: TradingSettings | None = None`
2. 通过 `ConfigInitProvider` 加载 `config/{env}/trading.env`（新建）
3. 确保向后兼容（新字段可选）

**测试**: 聚合后的 Settings 对象正确访问所有子设置

---

## 验证

每个 Task 完成后:
```bash
pixi run -e dev check    # lint + fmt + type + test --fast
```

全部 Task 完成后:
```bash
pixi run -e dev ci       # 完整 CI 检查
```
