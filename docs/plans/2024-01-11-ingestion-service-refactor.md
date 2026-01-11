# 数据摄入服务重构与修复计划

**日期**: 2024-01-11
**状态**: 待审核
**版本**: v1.0

---

## 概述

本计划包含两个部分：
1. **架构重构**: 移除游标表，简化数据追踪
2. **问题修复**: 修复 code review 指出的关键问题

---

## 🏗️ 架构重构

### 重构决策

| 决策 | 方案 | 说明 |
|------|------|------|
| 游标表 | ✅ 移除 | 所有查询基于 ingestion_log + 索引 |
| 标的维度 | ⏸️ 暂缓 | 只记录 DQ 失败，后续统一设计 DQ 时重构 |
| 更新策略 | ✅ 统一处理 | 不区分增量/回补/重试场景 |

### ingestion_log 表（保持不变）

```sql
CREATE TABLE ingestion_log (
    dataset TEXT NOT NULL,
    source TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    status TEXT NOT NULL,              -- SUCCESS / FAIL
    rows INTEGER,                      -- 总行数（SUCCESS 时）
    checksum TEXT,
    error_code TEXT,
    error_message TEXT,
    attempts INTEGER DEFAULT 1,
    first_attempt_at TEXT,
    last_attempt_at TEXT,
    PRIMARY KEY (dataset, source, trade_date)
);

-- 索引优化查询
CREATE INDEX idx_ingestion_log_success
ON ingestion_log(dataset, source, trade_date)
WHERE status = 'SUCCESS';
```

### DQ 失败记录（新增表，简化设计）

```sql
CREATE TABLE dq_failure_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset TEXT NOT NULL,
    source TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    sid INTEGER NOT NULL,
    src_code TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dataset, source, trade_date)
        REFERENCES ingestion_log(dataset, source, trade_date)
);

CREATE INDEX idx_dq_failure_lookup
ON dq_failure_log(dataset, source, trade_date, sid);
```

**设计说明**:
- 只记录 DQ 检查失败的标的
- 成功的标的不记录（避免存储膨胀）
- 后续 DQ 重构时可扩展

### 更新规则（所有场景统一）

| 场景 | ingestion_log | DQ 失败记录 | 说明 |
|------|--------------|-----------|------|
| 非交易日 | ❌ 不记录 | ❌ 不记录 | 静默跳过 |
| 全部成功 | ✅ UPSERT SUCCESS | ❌ 不记录 | 正常流程 |
| 全部失败（非 DQ） | ✅ UPSERT FAIL | ❌ 不记录 | 网络错误等 |
| DQ 阻断 | ✅ UPSERT FAIL | ✅ 批量记录 | 部分成功 |

**关键点**:
- **不区分场景**: 增量/回补/重试都是"摄取"
- **UPSERT 语义**: 覆盖之前的记录
- **DQ 失败**: 单独记录到 dq_failure_log

### 查询起点（替代游标）

```python
# 获取最后成功日期
def get_last_success_date(dataset: str, source: str) -> str | None:
    sql = """
    SELECT MAX(trade_date) as last_success
    FROM ingestion_log
    WHERE dataset = ? AND source = ? AND status = 'SUCCESS'
    """
    row = self._client.fetchone(sql, [dataset, source])
    return row["last_success"] if row else None

# 获取需要摄取的日期范围
last_success = hub.ingestion_log.get_last_success_date(dataset, source)
trade_dates = hub.calendar_store.get_range(last_success, today)
```

---

## 📋 数据集分类

| 类型 | 数据集 | 交易日检查 | 空数据处理 |
|------|--------|-----------|-----------|
| **行情类** | `stock_daily`, `etf_daily` | ✅ 检查交易日历 | ❌ 异常 |
| **参考类** | `adj_factor`, `fund_adj` | ❌ 不检查 | 根据业务逻辑 |
| **基础类** | `calendar`, `stock_basic`, `etf_basic` | ❌ 不检查 | 根据业务逻辑 |

---

## 🔄 处理流程

### ingest_date 处理流程

```
                ingest_date(dataset, trade_date)
                                │
                                ▼
                ┌───────────────────────────────┐
                │ 行情类数据集?                  │
                │ (stock_daily, etf_daily)      │
                └───────────────────────────────┘
                         │
           ┌─────────────┴─────────────┐
           │ Yes                         │ No
           ▼                             ▼
     ┌───────────────┐          ┌───────────────┐
     │ 检查交易日历   │          │ 直接继续      │
     └───────────────┘          └───────────────┘
           │
   ┌───────┴───────┐
   │               │
非交易日          交易日
   │               │
   ▼               ▼
返回 skipped    继续处理
(不记录)            │
                   ▼
           ┌───────────────┐
           │ Fetch data    │
           └───────────────┘
                   │
   ┌───────────────┼───────────────┐
   │               │               │
FETCH_ERROR   df.is_empty()   DQ_BLOCKED / WRITE_ERROR
   │               │                   │
   ▼               ▼                   ▼
记录 FAIL      行情类?              根据状态处理
   │               │
   │          ┌────┴────┐
   │          │ Yes     │ No
   │          ▼         ▼
   │     记录 FAIL  业务逻辑
   │          │         处理
   │          ▼
   │     DQ 失败场景:
   │     - log: FAIL
   │     - dq_failure_log: 批量记录
```

---

## 🔴 问题修复清单

### P0-1: 移除游标表 ✅

**状态**: 已完成 (2024-01-11)

**问题**: 游标表可能导致倒退，增加复杂度

**文件**:
- 删除: `packages/datahub/src/ditto_datahub/stores/ingestion_cursor.py`
- 修改: `packages/datahub/src/ditto_datahub/hub.py`
- 修改: `apps/server/src/ditto_port/ingestion/services/coordinator.py`
- 修改: `apps/server/src/ditto_port/ingestion/services/backfill.py`

**修复**:

1. **删除 IngestionCursorStore**

2. **添加 get_last_success_date 到 IngestionLogStore**

```python
def get_last_success_date(
    self,
    dataset: str,
    source: str = "tushare",
) -> str | None:
    """获取最后成功的交易日期。"""
    sql = """
    SELECT MAX(trade_date) as last_success
    FROM ingestion_log
    WHERE dataset = ? AND source = ? AND status = 'SUCCESS'
    """
    row = self._client.fetchone(sql, [dataset, source])
    return row["last_success"] if row else None
```

3. **更新 coordinator.py** - 移除所有游标更新代码

4. **更新 backfill.py** - 使用 get_last_success_date 替代游标

---

### P0-2: 交易日检查 ✅

**状态**: 已完成 (2024-01-11)

**问题**: 行情类数据集未检查交易日，非交易日被错误记录

**文件**: `apps/server/src/ditto_port/ingestion/services/coordinator.py`

**修复**:

```python
def ingest_date(self, dataset: str, trade_date: str, force: bool = False):
    # 对于行情类数据集，检查是否为交易日
    if dataset in ("stock_daily", "etf_daily"):
        calendar_df = self._hub.calendar_store.get(trade_date, trade_date)
        if not calendar_df.is_empty() and not calendar_df.row(0, "is_open"):
            # 非交易日，静默跳过
            return IngestionResult(
                dataset=dataset,
                trade_date=trade_date,
                status="skipped",
                message="非交易日，跳过",
            )
```

---

### P0-3: 统一失败处理 ✅

**状态**: 已完成 (2024-01-11)

**问题**: 失败路径处理不一致

**文件**: `apps/server/src/ditto_port/ingestion/services/coordinator.py`

**修复**:

```python
# FETCH_ERROR
except SourceFetchError as e:
    self._hub.ingestion_log.save_log(
        dataset, source, trade_date,
        status=IngestionStatus.FAIL,
        error_code="FETCH_ERROR",
        error_message=str(e),
    )
    return IngestionResult(status="failed", error="FETCH_ERROR")

# EMPTY_DATA（行情类）
if df.is_empty():
    if dataset in ("stock_daily", "etf_daily"):
        self._hub.ingestion_log.save_log(
            dataset, source, trade_date,
            status=IngestionStatus.FAIL,
            error_code="EMPTY_DATA",
        )
        return IngestionResult(status="failed", error="EMPTY_DATA")

# DQ_BLOCKED
if write_result.blocked:
    self._hub.ingestion_log.save_log(
        dataset, source, trade_date,
        status=IngestionStatus.FAIL,
        error_code="DQ_BLOCKED",
    )
    # 记录 DQ 失败标的
    self._hub.dq_failure_log.save_failures(
        dataset, source, trade_date,
        write_result.dq_result.failures,
    )
    return IngestionResult(status="partial", ...)
```

---

### P0-4: PIT 日期格式统一

**问题**: `_format_date_for_sqlite` 输出 YYYYMMDD，但 `effective_from` 是 DATE 类型

**文件**: `apps/server/src/ditto_port/ingestion/services/security_mapper.py`

**修复**:

```python
def _format_date_for_sqlite(self, date_str: str) -> str:
    """直接返回 YYYY-MM-DD 格式，不转换。"""
    try:
        datetime.fromisoformat(date_str)
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}, expected YYYY-MM-DD")
    return date_str
```

---

### P0-5: Symbol-based 查询支持 asof

**问题**: `_resolve_sids` 不传递 asof，`resolve_by_symbol` 只查当前有效

**文件**:
- `packages/datahub/src/ditto_datahub/stores/security_store.py`
- `packages/datahub/src/ditto_datahub/repositories/bars.py`

**修复**:

1. `security_store.py` - 添加 asof 参数
2. `bars.py` - 传递 asof 参数

---

### P0-6: QFQ 基准因子显式排序

**问题**: `group_by().last()` 无显式顺序保证

**文件**: `packages/datahub/src/ditto_datahub/repositories/bars.py`

**修复**:

```python
baseline_df_sorted = baseline_df.sort("sid", "trade_date")
latest_factors = baseline_df_sorted.group_by("sid").agg(
    pl.col("adj_factor").last().alias("latest_factor")
)
```

---

## 📝 TODO（后续统一处理）

### DQ 系统重构

创建 issue 追踪以下任务：

1. **补齐缺失的 DQ 规则**:
   - `monotonic_decrease`: 检查单调递减（如 adj_factor）
   - `outlier`: 检查异常值（基于 IQR 或 Z-score）
   - `consistency`: 检查数据一致性

2. **修复 DQ L3 数据源路由**:
   - `statistical.py` 按数据集选择正确的 Store
   - `dq_completeness_check` 使用 dataset 参数

3. **统一 DQ 规则配置**:
   - 验证 YAML 配置与实现的一致性
   - 添加规则验证和测试

4. **DQ 失败记录优化**:
   - 扩展 dq_failure_log 表
   - 支持标的级别重试
   - DQ 报告生成

---

## 实施顺序

### Week 1: 架构重构
1. **Day 1**: 实现 dq_failure_log 表
2. **Day 2**: 删除游标表，更新依赖
3. **Day 3**: 交易日检查
4. **Day 4**: 统一失败处理

### Week 2: P0 问题修复
1. **Day 1**: PIT 日期格式 + Symbol-based asof
2. **Day 2**: QFQ 基准因子

### Week 3: 测试与文档
1. **Day 1-2**: 端到端测试
2. **Day 3**: 文档更新

---

## 关键文件清单

| 文件 | 变更类型 | 优先级 |
|------|---------|--------|
| `dq_failure_log.py` | 新增 | P0 |
| `ingestion_log.py` | 修改 | P0 |
| `ingestion_cursor.py` | 删除 | P0 |
| `coordinator.py` | 修改 | P0 |
| `backfill.py` | 修改 | P0 |
| `security_store.py` | 修改 | P0 |
| `bars.py` | 修改 | P0 |
| `security_mapper.py` | 修改 | P0 |
| `hub.py` | 修改 | P0 |

---

## 验证方案

### 单元测试
- dq_failure_log 测试
- coordinator 测试（交易日检查、失败处理）
- backfill 测试（无游标）

### 集成测试
- 端到端摄取流程
- DQ 阻断场景
- 非交易日跳过

### 验证命令
```bash
pixi run -e dev pytest --cov=apps/server --cov=packages/datahub --cov-fail-under=80
pixi run -e dev pre-commit-run
```
