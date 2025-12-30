# PR #19 代码修复计划

## 当前进度

**完成时间**: 2025-12-30
**完成阶段**: Phase 1 (P0 正确性修复) + Phase 2 (P1 可观测性修复) + Phase 3 (P2 配置/文档) + Phase 4 (P0 致命问题修复) + Phase 5 (P1 代码重构)

### ✅ 已完成任务 (16/16)

| 任务 | 状态 | 完成时间 |
|------|------|----------|
| A.1: PitHelper SQL 注入风险修复 | ✅ 完成 | 2025-12-29 |
| A.2: PitHelper SQL 语法问题修复 | ✅ 完成 | 2025-12-29 |
| A.3: SecurityStore 负缓存失效问题修复 | ✅ 完成 | 2025-12-29 |
| A.4: DataCache.get_stats() 指标读取修复 | ✅ 完成 | 2025-12-29 |
| A.5: CalendarStore.get_range() 返回不可变副本 | ✅ 完成 | 2025-12-29 |
| A.6: SqlEngine 慢查询指标重复记录修复 | ✅ 完成 | 2025-12-29 |
| A.7: pixi.toml server 命令修复 | ✅ 完成 | 2025-12-29 |
| A.8: PitHelper.add_pit_join() 支持 effective_from | ✅ 完成 | 2025-12-29 |
| A.9: 创建 packages/datahub/README.md | ✅ 完成 | 2025-12-29 |
| B.1: BarsRepository 复权计算 PIT 安全隐患 | ✅ 完成 | 2025-12-29 |
| B.2: BarsStore Last-Write-Wins 数据覆盖风险 | ✅ 完成 | 2025-12-29 |
| B.1.1: 统一 asof/pit_asof 语义（删除 pit_asof） | ✅ 完成 | 2025-12-29 |
| B.3: 风控字段缺失（涨跌停价、停牌状态） | ✅ 完成 | 2025-12-30 |
| B.4: 抽取 ParquetStoreBase 基类 | ✅ 完成 | 2025-12-30 |
| B.5: 统一 DQSeverity 类型定义 | ✅ 完成 | 2025-12-30 |
| B.6: pre_close 复权计算（无需修改） | ✅ 完成 | 2025-12-30 |

### 🔧 后续修复

| 任务 | 状态 | 完成时间 |
|------|------|----------|
| 测试修复: Schema validator 测试数据更新 | ✅ 完成 | 2025-12-30 |

**说明**: B.1 和 B.3 添加了新的 schema 字段（knowledge_date, up_limit, down_limit），schema validator 测试需要更新测试数据以匹配新 schema。

### 📋 待完成任务 (0/16)

---

## 概述

基于 PR #19 的评审建议，修复代码质量问题。本计划分为三个部分：
- **Part A**: 本次PR范围内的修改（必须修复）
- **Part B**: 本次PR范围外的核心问题（高优先级）
- **Part C**: 文档和配置优化（低优先级）

**总工作量预估**: Part A (12-16h) + Part B (23-34h) = **35-50 小时**

**用户选择**: 全部修复（Part A + Part B）

---

## Part A: 本次PR范围内的修改

### 🔴 P0 - 必须修复（正确性问题）

#### Task A.1: PitHelper SQL 注入风险修复
**优先级**: P0 - 必须修复
**复杂度**: M
**预估工时**: 2-3h
**相关文件**: `packages/datahub/src/ditto_datahub/runtime/pit_helper.py`

**问题位置**:
- Line 55: `f"{query} AND {date_column} <= '{knowledge_date}'"`
- Line 108: `f"{right_alias}.trade_date <= '{asof_date}'"`
- Line 150: `f" WHERE trade_date <= '{asof_date}'"`
- Line 188: `f"{base_column} <= '{knowledge_date}'"`

**修复方案**:
```python
def _validate_date_string(date_str: str) -> None:
    """验证日期字符串格式，防止 SQL 注入."""
    import re
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        raise ValueError(f"Invalid date format: {date_str}")

# 在所有方法中调用
def add_pit_filter(..., knowledge_date: str):
    self._validate_date_string(knowledge_date)
    ...
```

**验收标准**:
- [x] 所有 PitHelper 方法添加日期验证
- [x] 新增 11 个测试用例（SQL注入防护测试）
- [x] bandit 安全扫描通过

---

#### Task A.2: PitHelper.add_pit_filter() SQL 语法问题修复
**优先级**: P0 - 必须修复
**复杂度**: M
**预估工时**: 2-3h
**相关文件**: `packages/datahub/src/ditto_datahub/runtime/pit_helper.py`

**问题**: 直接拼接 WHERE/AND，遇到 ORDER BY/LIMIT 会生成非法SQL

**修复方案**:
```python
def add_pit_filter(query: str, knowledge_date: str, date_column: str = "knowledge_date") -> str:
    query = query.strip()

    # 检测 ORDER BY / LIMIT / GROUP BY / HAVING
    if re.search(r'\b(ORDER BY|LIMIT|GROUP BY|HAVING)\b', query, re.IGNORECASE):
        # 使用 CTE 包装
        wrapped = f"WITH _pit_original AS ({query}) SELECT * FROM _pit_original WHERE {date_column} <= '{knowledge_date}'"
        return wrapped

    # 原有逻辑
    if " where " in query.lower():
        return f"{query} AND {date_column} <= '{knowledge_date}'"
    else:
        return f"{query} WHERE {date_column} <= '{knowledge_date}'"
```

**验收标准**:
- [x] 检测 ORDER BY/LIMIT/GROUP BY/HAVING 子句
- [x] 自动使用 CTE 包装
- [x] 新增 6 个测试用例（ORDER BY、LIMIT、GROUP BY、HAVING）

**依赖**: A.1

---

#### Task A.3: SecurityStore 负缓存失效问题修复
**优先级**: P0 - 必须修复
**复杂度**: S
**预估工时**: 1-2h
**相关文件**: `packages/datahub/src/ditto_datahub/stores/security_store.py`

**问题**: `register()` 新增标的后，负缓存(-1)未失效

**修复方案**:
```python
def register(self, sid: int, source: str, src_code: str, ...):
    # ... 现有插入逻辑 ...

    # 失效相关缓存
    if self._data_cache:
        self._data_cache.invalidate(f"sid:{src_code}:{source}:current")
        self._data_cache.invalidate_pattern("sid_symbol_map:*")
```

**验收标准**:
- [x] `register()` 失效相关缓存
- [x] 新增 2 个测试用例

---

### 🟡 P1 - 应该修复（可观测性）

#### Task A.4: DataCache.get_stats() 指标读取修复
**优先级**: P1
**复杂度**: M
**预估工时**: 2-3h
**相关文件**: `packages/datahub/src/ditto_datahub/runtime/cache.py`

**问题**: `enable_metrics=True` 时返回全0

**修复方案**: 同步维护本地计数器
```python
def get(self, key: str, default: Any = None) -> Any:
    try:
        value = self._cache[key]
        M.cache_hit.add(1, {"type": "data_cache"})
        self._hit_count += 1  # 同步维护
        return value
    except KeyError:
        M.cache_miss.add(1, {"type": "data_cache"})
        self._miss_count += 1  # 同步维护
        return default
```

**验收标准**:
- [x] metrics 模式下同步维护计数器
- [x] 新增 2 个测试用例

---

#### Task A.5: CalendarStore.get_range() 返回不可变副本
**优先级**: P1
**复杂度**: S
**预估工时**: 1h
**相关文件**: `packages/datahub/src/ditto_datahub/stores/calendar_store.py`

**问题**: 返回内部 list 引用，调用方修改会污染缓存

**修复方案**: 返回副本
```python
def get_range(self, start: str, end: str) -> list[str]:
    # ...
    return result.copy()
```

**验收标准**:
- [x] 返回 list 副本
- [x] 新增 1 个测试用例

---

#### Task A.6: SqlEngine 慢查询指标重复记录修复
**优先级**: P1
**复杂度**: S
**预估工时**: 0.5-1h
**相关文件**: `packages/datahub/src/ditto_datahub/runtime/sql_engine.py`

**问题**: duration 指标被记录两次（line 273, 351）

**修复方案**: 删除 `_log_slow_query()` 中的重复记录

**验收标准**:
- [x] 删除重复的 `M.sql_query_duration.record()`
- [x] 新增 1 个测试用例

---

### 🟢 P2 - 配置/文档

#### Task A.7: pixi.toml server 命令修复
**优先级**: P2
**复杂度**: S
**预估工时**: 0.5h
**相关文件**: `pixi.toml`

**修复**:
```toml
server = "granian apps.server.src.ditto_server.main:app --interface asgi --reload --host 0.0.0.0 --port 8000"
server-prod = "granian apps.server.src.ditto_server.main:app --interface asgi --host 0.0.0.0 --port 8000 --workers 4"
```

**验收标准**:
- [x] 将 uvicorn 替换为 granian
- [x] 添加 `--interface asgi` 参数

---

#### Task A.8: PitHelper.add_pit_join() 支持 effective_from
**优先级**: P2
**复杂度**: S
**预估工时**: 1h
**相关文件**: `packages/datahub/src/ditto_datahub/runtime/pit_helper.py`

**修复**: 添加 `date_column` 参数（默认 "trade_date"）

**验收标准**:
- [x] 添加 `date_column` 参数（默认 "trade_date"）
- [x] 添加列名验证防止 SQL 注入
- [x] 新增 3 个测试用例（effective_from、knowledge_date、默认值）

---

#### Task A.9: 创建 packages/datahub/README.md
**优先级**: P2
**复杂度**: M
**预估工时**: 2-3h
**相关文件**: `packages/datahub/README.md` (新建)

**验收标准**:
- [x] 创建 packages/datahub/README.md
- [x] 包含架构说明、快速开始、PIT 安全规则
- [x] 包含代码示例和数据目录结构

---

## Part B: 本次PR范围外的核心问题

### 🔴 P0 - 致命问题

#### Task B.1: BarsRepository 复权计算 PIT 安全隐患
**优先级**: P0 - 致命
**复杂度**: L
**预估工时**: 8-12h
**相关文件**: `packages/datahub/src/ditto_datahub/repositories/bars.py:517`

**问题**:
```python
# 当前: 使用 trade_date（错误！）
baseline_df = adj_df.filter(pl.col("trade_date") <= asof_date)

# 应该: 使用 knowledge_date
baseline_df = adj_df.filter(pl.col("knowledge_date") <= asof_date)
```

**风险**: 复权因子通常T+1日才公布，使用trade_date构成未来函数，回测收益虚高

**修复方案**:
1. Schema: `ADJ_FACTOR_SCHEMA` 添加 `knowledge_date` 字段
2. Ingestion: `knowledge_date = trade_date + 1 day`
3. 计算: 修改为使用 `knowledge_date` 过滤

---

#### Task B.2: BarsStore Last-Write-Wins 数据覆盖风险
**优先级**: P0 - 高风险
**复杂度**: L
**预估工时**: 6-8h
**相关文件**: `packages/datahub/src/ditto_datahub/stores/bars_store.py`

**问题**: `unique(subset=["sid", "trade_date"], keep="last")` 导致高质量数据被低质量爬虫数据覆盖

**修复方案**: 增加 `on_duplicate` 参数（默认 ERROR 或 SAFE_MERGE）

---

#### Task B.3: 风控字段缺失（涨跌停价、停牌状态）
**优先级**: P0 - 高风险
**复杂度**: L
**预估工时**: 4-6h
**相关文件**:
- `packages/datahub/src/ditto_datahub/meta/schemas.py`
- `packages/datahub/src/ditto_datahub/sources/tushare/source.py`
- `packages/datahub/src/ditto_datahub/stores/stock_status_store.py` (新建)
- `packages/datahub/src/ditto_datahub/repositories/bars.py`

**问题**: 缺少 `up_limit/down_limit` 和 `trade_status`，无法模拟一字板买不进、停牌卖不出

**数据来源**:
| 数据 | 接口 | 字段 |
|------|------|------|
| 涨跌停价格 | `stk_limit` | up_limit, down_limit |
| 停复牌 | `suspend_d` | suspend_timing, suspend_type |
| ST 状态 | `stock_st` | type, type_name |
| list_status | `stock_basic` | list_status (L/D/P) |

**修复方案**:

1. **更新 STOCK_DAILY_SCHEMA** - 添加涨跌停价格
```python
STOCK_DAILY_SCHEMA: dict[str, type[pl.DataType]] = {
    # ... 现有字段 ...
    "up_limit": pl.Float64,      # 涨停价
    "down_limit": pl.Float64,    # 跌停价
}
```

2. **新增 STOCK_STATUS_SCHEMA** - 独立存储状态信息
```python
STOCK_STATUS_SCHEMA: dict[str, type[pl.DataType]] = {
    "sid": pl.Int64,
    "trade_date": pl.Date,
    "is_suspended": pl.Boolean,     # 是否停牌
    "suspend_timing": pl.Utf8,      # 停牌时间段 "09:30-10:00"
    "is_st": pl.Boolean,            # 是否ST
    "st_type": pl.Utf8,             # ST/*ST 类型名称
    "list_status": pl.Utf8,         # L正常/D退市/P暂停
    "source": pl.Utf8,
    "src_code": pl.Utf8,
}
```

3. **存储策略**:
   - 涨跌停价: 存入 `stock_daily` (与行情同表，查询高效)
   - 状态信息: 存入独立的 `stock_status` 表 (按年分区)

4. **查询支持**:
```python
bars = hub.bars.get(
    sids=[1],
    start="2024-01-01",
    end="2024-01-15",
    asof="2024-01-15",      # PIT 查询
    with_status=True,       # 返回状态信息
)
```

**验收标准**:
- [x] 更新 STOCK_DAILY_SCHEMA 添加 up_limit/down_limit
- [x] 新增 STOCK_STATUS_SCHEMA
- [x] 新增 StockStatusStore 类（按年分区）
- [x] TushareSource.fetch_stock_limit() 方法
- [x] TushareSource.fetch_stock_status() 方法
- [x] BarsRepository.get() 支持 with_status 参数
- [x] 新增测试用例（涨跌停、停牌、ST）

**完成时间**: 2025-12-30

---

### 🟡 P1 - 代码重构

#### Task B.4: 抽取 ParquetStoreBase 基类
**优先级**: P1
**复杂度**: M
**预估工时**: 4-6h
**相关文件**: `stores/bars_store.py`, `stores/adj_factor_store.py`

**问题**: 两个 Store 类 90% 代码重复

**修复方案**: 抽取 `ParquetStoreBase` 基类

---

#### Task B.5: 统一 DQSeverity 类型定义
**优先级**: P1
**复杂度**: S
**预估工时**: 1-2h
**相关文件**: `types.py`, `dq/models.py`

**问题**: 两处定义不一致
- `types.py`: FAIL/WARN
- `dq/models.py`: ERROR/WARNING/ALERT

**修复方案**: 统一使用三级定义

---

#### Task B.6: pre_close 复权计算（已完成）
**优先级**: P1
**复杂度**: S
**预估工时**: 0h
**相关文件**: `packages/datahub/src/ditto_datahub/repositories/bars.py`

**说明**: Tushare `daily` 接口返回的 `pre_close` 已经是除权参考价，**不需要进行复权处理**。

**当前实现**（已正确）:
- 只对 `open/high/low/close` 进行复权（原始价格）
- `pre_close` 保持不变（已经是除权参考价）

**文档更新**（已完成）:
- ✅ 在 `_apply_qfq_adj` 和 `_apply_hfq_adj` 方法中添加了注释说明
- ✅ 在 `packages/datahub/README.md` 中添加了"复权数据说明"章节

**验证标准**: ✅ 当前实现正确，无需修改

---

## Part C: 低优先级优化

#### Task C.1: SidRange 定义补全
**优先级**: P2
**相关文件**: `types.py`
**缺失**: bond (400M-499M), future (500M-599M)

---

## 执行计划（用户选择：全部修复）

**总工作量**: 约 35-50 小时（Part A: 12-16h + Part B: 23-34h）

### Phase 1: Part A - P0 正确性修复 (5-7h)
1. A.1: PitHelper SQL 注入修复 (2-3h)
2. A.2: PitHelper SQL 语法修复 (2-3h, 依赖 A.1)
3. A.3: SecurityStore 负缓存失效 (1-2h)

### Phase 2: Part A - P1 可观测性修复 (4-5h)
4. A.4: DataCache.get_stats() (2-3h)
5. A.5: CalendarStore 返回副本 (1h)
6. A.6: SqlEngine 慢查询指标 (0.5-1h)

### Phase 3: Part A - P2 配置/文档 (4-5h)
7. A.7: pixi.toml (0.5h)
8. A.8: PitHelper effective_from (1h)
9. A.9: datahub README (2-3h)

### Phase 4: Part B - P0 致命问题修复 (18-26h)
10. B.1: PIT 复权逻辑修复 (8-12h) - **最关键**
11. B.2: Last-Write-Wins 覆盖风险 (6-8h)
12. B.3: 风控字段缺失 (4-6h)

### Phase 5: Part B - P1 代码重构 (7-11h)
13. B.4: ParquetStoreBase 抽取 (4-6h)
14. B.5: DQSeverity 统一 (1-2h)
15. B.6: pre_close 复权 (2-3h)

---

## 依赖关系

```
Phase 1-2-3 (Part A):
  A.1 (SQL注入)
    │
    └─→ A.2 (SQL语法) ──┐
    │                  │
  A.3 (负缓存)         │
    │                  │
    └──────────────────┴──→ A.4, A.5, A.6 (并行)
                              │
                              └──→ A.7, A.8, A.9 (并行)
                                    │
                                    └──→ Phase 4-5 (Part B)
                                            │
                          ┌─────────────────┼─────────────────┐
                          │                 │                 │
                     B.1 (PIT复权)      B.2 (LWW)         B.3 (风控字段)
                          │                 │                 │
                          └─────────────────┴─────────────────┘
                                        │
                                   B.4, B.5, B.6 (并行)
```

**关键路径**: A.1 → A.2 → A.4-A.9 → B.1 (PIT复权，最关键)

---

## 测试策略

### Part A 新增测试
- A.1: 4 个（日期验证、SQL注入）
- A.2: 4 个（ORDER BY, LIMIT, GROUP BY, HAVING）
- A.3: 2 个（注册后解析）
- A.4: 2 个（metrics stats）
- A.5: 1 个（返回副本）
- A.6: 1 个（慢查询指标）
- A.8: 2 个（effective_from）

**总计**: 约 16-20 个测试用例

### Part B 新增测试
- B.1: 6-8 个（PIT复权逻辑）
- B.2: 4 个（数据覆盖）
- B.3: 3 个（风控字段）
- B.4: 4 个（基类抽取）
- B.5: 2 个（类型统一）
- B.6: 3 个（pre_close复权）

**总计**: 约 22-27 个测试用例

---

## Critical Files

### Part A - 必须修改
1. `packages/datahub/src/ditto_datahub/runtime/pit_helper.py` - A.1, A.2, A.8
2. `packages/datahub/src/ditto_datahub/stores/security_store.py` - A.3
3. `packages/datahub/src/ditto_datahub/runtime/cache.py` - A.4
4. `packages/datahub/src/ditto_datahub/stores/calendar_store.py` - A.5
5. `packages/datahub/src/ditto_datahub/runtime/sql_engine.py` - A.6
6. `pixi.toml` - A.7
7. `packages/datahub/README.md` - A.9 (新建)

### Part B - 需要修复
1. `packages/datahub/src/ditto_datahub/repositories/bars.py` - B.1, B.6
2. `packages/datahub/src/ditto_datahub/stores/bars_store.py` - B.2
3. `packages/datahub/src/ditto_datahub/sources/tushare/source.py` - B.3
4. `packages/datahub/src/ditto_datahub/stores/adj_factor_store.py` - B.4
5. `packages/datahub/src/ditto_datahub/types.py` - B.5, C.1
