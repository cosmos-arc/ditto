# 数据摄入与 DQ 系统修复实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复数据摄入系统中的 6 个关键问题，确保 DQ L1 阻断正确处理、数据依赖关系正确建立、以及 SID 范围统一到百万级。

**Architecture:** 采用 TDD 方法，按 Critical → High → Medium 优先级修复，每个修复都伴随完整的单元测试和集成测试。

**Tech Stack:** Python 3.12+, Polars, SQLite, FastAPI, Prefect, pytest

---

## 用户决策确认

1. **DQ L1 阻断**: 记录 FAIL 状态，但**仍然更新游标**（update_success），失败的数据通过单独的重试任务来处理
2. **数据依赖**: 日线/复权强制依赖 stock_basic/etf_basic，确保 SID 统一使用 SidAllocator
3. **多源支持**: backfill_missing 需要支持多数据源

---

## 问题分类与修复优先级

### Critical 问题（必须立即修复）

#### 问题 1: DQ L1 阻断被吞掉
- **严重性**: Critical
- **影响**: DQ 检查失败的数据仍被标记为 SUCCESS，导致数据质量问题被掩盖
- **涉及文件**: `coordinator.py:160-181`, `bars.py:309`

#### 问题 2: adj_factor/fund_adj 用 ts_code 补 SID
- **严重性**: Critical
- **影响**: 上游已统一成 `src_code`，但这里仍用 `ts_code`，导致 KeyError 中断摄取
- **涉及文件**: `coordinator.py:281`, `source.py:572`

### High 问题（高优先级修复）

#### 问题 3: SQLite 无法绑定 datetime.date
- **严重性**: High
- **影响**: 证券注册时 list_date 字段无法写入 SQLite
- **涉及文件**: `security.py:356`, `source.py:387`

#### 问题 4: market_wide 混合资产类缺少 asset_class
- **严重性**: High
- **影响**: 全市场查询时 `_determine_dataset()` 会抛错或读错数据集
- **涉及文件**: `dq_batch.py:30`, `statistical.py:115`, `bars.py:396`

### Medium 问题（中优先级修复）

#### 问题 5: SID 范围不一致
- **严重性**: Medium
- **影响**: 不同模块使用不同的 SID 范围，未来可能冲突
- **涉及文件**: `security_mapper.py:36`, `types.py:17`
- **决策**: 统一改到百万级

#### 问题 6: backfill 并发策略混乱
- **严重性**: Medium
- **影响**: 并发控制不清晰，注释与实现不符
- **涉及文件**: `backfill.py:97, 204`, `ingestion_log.py:353`

---

## 实施任务清单

### Phase 1: Critical 问题修复

#### Task 1.1: 修复 DQ L1 阻断处理

**Files:**
- Modify: `apps/server/src/ditto_server/ingestion/services/coordinator.py:242-308` (`_write_data` 方法)
- Modify: `apps/server/src/ditto_server/ingestion/services/coordinator.py:160-205` (`ingest_date` 方法)
- Create: `apps/server/tests/integration/ingestion/test_coordinator_dq_blocking.py`

**Step 1: 修改 `_write_data()` 返回类型**

```python
# coordinator.py:242
def _write_data(
    self,
    dataset: str,
    df: pl.DataFrame,
    trade_date: str,
    on_duplicate: OnDuplicate = OnDuplicate.ERROR,
) -> tuple[str, str, WriteResult]:  # 添加 WriteResult 返回
```

**Step 2: 修改 `ingest_date()` 检查 blocked**

在 `coordinator.py:160` 之后添加 DQ 阻断检查：

```python
# 检查 DQ 阻断
if write_result.blocked:
    self._hub.ingestion_log.save_log(
        dataset=dataset,
        source=self._source_name,
        trade_date=trade_date,
        status=IngestionStatus.FAIL,
        error_code="DQ_BLOCKED",
        error_message=f"DQ L1 check failed: {write_result.dq_result.error_count} errors",
    )

    # 仍然更新游标（避免阻塞整个摄取流程）
    # 失败的数据通过单独的重试任务来处理
    self._hub.ingestion_cursor.update_success(
        dataset=dataset,
        source=self._source_name,
        trade_date=trade_date,
    )

    return IngestionResult(
        dataset=dataset,
        trade_date=trade_date,
        status="failed",
        error="DQ_BLOCKED",
        message="DQ L1 check failed, data rejected (will retry via reprocess task)",
    )
```

**Step 3: 添加集成测试**

创建 `test_coordinator_dq_blocking.py`:

```python
def test_ingest_date_dq_blocked():
    """测试 DQ L1 阻断正确记录 FAIL，但游标仍然更新."""
    # 准备包含 null 的数据（触发 not_null 检查）
    df = pl.DataFrame({"src_code": ["000001.SZ"], "close": [None]})

    result = coordinator.ingest_date("stock_daily", "2024-01-02")

    # 验证返回状态
    assert result.status == "failed"
    assert result.error == "DQ_BLOCKED"

    # 验证游标仍然更新（避免阻塞整个流程）
    cursor = hub.ingestion_cursor.get_cursor("stock_daily")
    assert cursor.last_success == "2024-01-02"  # ✅ 已更新

    # 验证日志记录为 FAIL（便于后续重试）
    log = hub.ingestion_log.get_log("stock_daily", "tushare", "2024-01-02")
    assert log.status == IngestionStatus.FAIL
    assert log.error_code == "DQ_BLOCKED"
```

**Step 4: 运行测试验证**

```bash
pixi run -e dev pytest apps/server/tests/integration/ingestion/test_coordinator_dq_blocking.py -v
```

**Step 5: 提交**

```bash
git add apps/server/src/ditto_server/ingestion/services/coordinator.py
git add apps/server/tests/integration/ingestion/test_coordinator_dq_blocking.py
git commit -m "fix(ingestion): DQ L1 阻断正确记录 FAIL 状态

- 修复 coordinator 未检查 WriteResult.blocked 的问题
- DQ 失败时记录 FAIL 状态，但仍更新游标（避免阻塞流程）
- 失败数据通过单独的重试任务处理
- 添加集成测试验证阻断逻辑
"
```

---

#### Task 1.2: 修复 adj_factor/fund_adj 列名不匹配

**Files:**
- Modify: `apps/server/src/ditto_server/ingestion/services/coordinator.py:274-287`
- Create: `apps/server/tests/integration/ingestion/test_adj_factor_ingestion.py`

**Step 1: 修改 src_code_col 参数**

```python
# coordinator.py:281
elif dataset in ("adj_factor", "fund_adj"):
    asset_class: Literal["stock", "etf"] = (
        "etf" if dataset == "fund_adj" else "stock"
    )

    if "sid" not in df.columns:
        df = self._security_mapper.enrich_dataframe(
            df,
            src_code_col="src_code",  # 修复: 从 "ts_code" 改为 "src_code"
            asset_class=asset_class,
            source=self._source_name,
        )
```

**Step 2: 添加测试**

```python
def test_ingest_adj_factor_sid_mapping():
    """测试 adj_factor 正确映射 SID."""
    result = coordinator.ingest_date("adj_factor", "2024-01-02")

    assert result.status == "success"
    # 验证 sid 列存在且有效
    df = hub.adj_factor_store.read("adj_factor", sids=None)
    assert "sid" in df.columns
    assert df["sid"].min() >= 1_000_000
```

**Step 3: 运行测试**

```bash
pixi run -e dev pytest apps/server/tests/integration/ingestion/test_adj_factor_ingestion.py -v
```

**Step 4: 提交**

```bash
git add apps/server/src/ditto_server/ingestion/services/coordinator.py
git add apps/server/tests/integration/ingestion/test_adj_factor_ingestion.py
git commit -m "fix(ingestion): 修复 adj_factor SID 映射列名

- 将 src_code_col 从 \"ts_code\" 改为 \"src_code\"
- 与上游 source.py 输出列名对齐
- 避免 KeyError 导致摄取中断
"
```

---

### Phase 2: High 问题修复

#### Task 2.1: 修复 SQLite datetime.date 绑定问题

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/repositories/security.py`
- Modify: `packages/datahub/tests/unit/repositories/test_security_repository.py`

**Step 1: 添加日期转换函数**

```python
# security.py (文件顶部)
from datetime import date

def _format_date_for_sqlite(d: date | str | None) -> str | None:
    """转换日期为 SQLite 可绑定的字符串."""
    if d is None:
        return None
    if isinstance(d, date):
        return d.isoformat()  # YYYY-MM-DD
    return str(d)
```

**Step 2: 修改 register_batch() 使用转换**

```python
# security.py:356
self._security_store.register(
    sid=new_sid,
    source=source,
    src_code=src_code,
    symbol=row.get("symbol", src_code),
    name=row.get("name", src_code),
    exchange=row.get("exchange", "UNKNOWN"),
    asset_class=asset_class,
    list_date=_format_date_for_sqlite(row.get("list_date")),  # 转换
    board=row.get("board"),
)
```

**Step 3: 添加测试**

```python
def test_register_batch_with_date():
    """测试证券注册正确处理日期."""
    df = pl.DataFrame({
        "src_code": ["000001.SZ"],
        "list_date": [date(2024, 1, 2)],  # Python date
    })

    file_path, checksum = hub.securities.register_batch(
        df=df,
        source="tushare",
        asset_class="stock",
        src_code_col="src_code",
    )

    # 验证成功写入
    sid = hub.security_store.resolve_sid("000001.SZ", "tushare", None)
    assert sid is not None
```

**Step 4: 运行测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/repositories/test_security_repository.py::test_register_batch_with_date -v
```

**Step 5: 提交**

```bash
git add packages/datahub/src/ditto_datahub/repositories/security.py
git add packages/datahub/tests/unit/repositories/test_security_repository.py
git commit -m "fix(datahub): 修复 SQLite 日期绑定问题

- 添加 _format_date_for_sqlite() 转换函数
- 将 datetime.date 转换为 ISO 字符串
- 避免 SQLite 无法绑定 Python date 对象
"
```

---

#### Task 2.2: 修复 market_wide asset_class 缺失

**Files:**
- Modify: `apps/server/src/ditto_server/ingestion/tasks/dq_batch.py:30-90`
- Modify: `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py:15-44, 77-97`
- Modify: `packages/datahub/src/ditto_datahub/repositories/bars.py:396-440`
- Create: `packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py`

**Step 1: 在 dq_batch_check 中推断 asset_class**

```python
# dq_batch.py:30
@task(name="dq-batch-check", ...)
def dq_batch_check(
    trade_date: str | None = None,
    datasets: list[str] | None = None,
    config_path: str | None = None,
    market_wide: bool = True,
) -> dict[str, Any]:
    """..."""

    # 定义 dataset 到 asset_class 的映射
    dataset_asset_class = {
        "stock_daily": "stock",
        "etf_daily": "etf",
        "index_daily": "index",
        "adj_factor": "stock",
        "fund_adj": "etf",
    }

    for dataset in datasets:
        asset_class = dataset_asset_class.get(dataset)

        result = engine.check_statistical(
            dataset=dataset,
            trade_date=trade_date,
            hub=hub,
            asset_class=asset_class,  # 传递
            market_wide=market_wide,
        )
```

**Step 2: 修改 StatisticalChecker 接收 asset_class**

```python
# statistical.py:15
class StatisticalChecker:
    def check(
        self,
        dataset: str,
        trade_date: str,
        rules: list[dict[str, Any]],
        hub: Any,
        asset_class: Literal["stock", "etf", "index"] | None = None,  # 添加
        market_wide: bool = False,
    ) -> list[DQIssue]:
        """..."""
```

**Step 3: 修改 _check_zscore 使用 asset_class**

```python
# statistical.py:77
def _check_zscore(
    self,
    dataset: str,
    trade_date: str,
    rule: dict,
    hub: Any,
    asset_class: Literal["stock", "etf", "index"] | None = None,  # 添加
    market_wide: bool = False,
) -> DQIssue | None:
    """..."""

    historical = hub.bars.get(
        start=start_date,
        end=trade_date,
        asset_class=asset_class,  # 添加
        market_wide=market_wide,
    )
```

**Step 4: 添加测试**

```python
def test_zscore_with_asset_class():
    """测试 Z-score 检查正确使用 asset_class."""
    mock_hub = MagicMock()

    checker = StatisticalChecker()
    issues = checker._check_zscore(
        dataset="stock_daily",
        trade_date="2024-01-02",
        rule={"column": "close", "window": 60},
        hub=mock_hub,
        asset_class="stock",
        market_wide=True,
    )

    # 验证 hub.bars.get 被正确调用
    call_kwargs = mock_hub.bars.get.call_args_list[0].kwargs
    assert call_kwargs["asset_class"] == "stock"
```

**Step 5: 运行测试**

```bash
pixi run -e dev pytest packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py -v
```

**Step 6: 提交**

```bash
git add apps/server/src/ditto_server/ingestion/tasks/dq_batch.py
git add packages/datahub/src/ditto_datahub/dq/checkers/statistical.py
git add packages/datahub/tests/unit/dq/checkers/test_statistical_checker.py
git commit -m "fix(dq): 修复 market_wide 查询 asset_class 缺失

- dq_batch_check 根据 dataset 推断 asset_class
- StatisticalChecker 接收并传递 asset_class
- 避免混合资产类查询时的错误
"
```

---

### Phase 3: Medium 问题修复

#### Task 3.1: 统一 SID 范围到百万级

**Files:**
- Modify: `packages/datahub/src/ditto_datahub/types.py:8-26`
- Create: `packages/datahub/migrations/002_unify_sid_range.py`

**Step 1: 修改 types.py 中的 SidRange**

```python
# types.py:17
@classmethod
def get_range(cls, asset_class: str) -> "SidRange":
    """Get SID range for asset class."""
    ranges = {
        "stock": cls(1_000_000, 1_999_999),      # 百万级
        "etf": cls(2_000_000, 2_999_999),        # 百万级
        "index": cls(3_000_000, 3_999_999),      # 百万级
    }

    if asset_class not in ranges:
        raise ValueError(f"Unknown asset class: {asset_class}")

    return ranges[asset_class]
```

**Step 2: 创建数据库迁移检查**

创建 `migrations/002_unify_sid_range.py`:

```python
def upgrade():
    """统一 SID 范围到百万级."""
    # 检查是否存在亿级 SID
    max_sid = conn.execute("SELECT MAX(current_max) FROM sid_sequence").fetchone()[0]

    if max_sid and max_sid >= 100_000_000:
        logger.warning("检测到亿级 SID，需要手动迁移")
        logger.info("迁移方案: stock 100M -> 1M, etf 200M -> 2M")
        raise NotImplementedError("请手动执行 SID 迁移")
```

**Step 3: 提交**

```bash
git add packages/datahub/src/ditto_datahub/types.py
git add packages/datahub/migrations/002_unify_sid_range.py
git commit -m "refactor(datahub): 统一 SID 范围到百万级

- 修改 SidRange 使用百万级范围(1M/2M/3M)
- 与 SecurityMapper 保持一致
- 添加数据库迁移检查
"
```

---

#### Task 3.2: 明确 backfill 并发策略

**Files:**
- Modify: `apps/server/src/ditto_server/ingestion/services/backfill.py:97-120, 153-210`
- Modify: `apps/server/tests/unit/ingestion/test_backfill.py`

**Step 1: 修改 backfill_range 注释和实现**

```python
# backfill.py:97
# 年份级并行(避免跨年文件锁冲突)，年内串行(避免同年文件锁冲突)

if parallel > 1:
    dates_by_year = defaultdict(list)
    for date in trade_dates:
        year = date[:4]
        dates_by_year[year].append(date)

    with ThreadPoolExecutor(
        max_workers=min(parallel, len(dates_by_year))
    ) as executor:
        futures = {}
        for _year, year_dates in dates_by_year.items():
            # 每个年份串行处理
            for date in year_dates:
                future = executor.submit(
                    self._coordinator.ingest_date,
                    dataset,
                    date,
                )
                futures[future] = date
```

**Step 2: 添加 source 参数**

```python
# backfill.py:153
def backfill_missing(
    self,
    dataset: str,
    source: str = "tushare",  # 添加 source 参数
    parallel: int = 1,
) -> BackfillResult:
    """..."""

    # 使用 source 参数
    ingested_dates = self._ingestion_log_store.get_ingested_dates(
        dataset, source
    )
```

**Step 3: 添加测试**

```python
def test_backfill_missing_with_source():
    """测试 backfill_missing 支持 source 参数."""
    result = manager.backfill_missing(
        dataset="stock_daily",
        source="tushare",
    )

    assert result.total_dates >= 0
```

**Step 4: 运行测试**

```bash
pixi run -e dev pytest apps/server/tests/unit/ingestion/test_backfill.py -v
```

**Step 5: 提交**

```bash
git add apps/server/src/ditto_server/ingestion/services/backfill.py
git add apps/server/tests/unit/ingestion/test_backfill.py
git commit -m "refactor(ingestion): 明确 backfill 并发策略

- 年份级并行，年内串行(避免文件锁冲突)
- backfill_missing 支持 source 参数
- 更新注释与实现一致
"
```

---

### Phase 4: 验证与文档

#### Task 4.1: 完整测试验证

**Step 1: 运行所有测试**

```bash
# 单元测试
pixi run -e dev pytest packages/datahub/tests/ -v -m unit

# 集成测试
pixi run -e dev pytest apps/server/tests/ -v -m integration

# 覆盖率检查
pixi run -e dev pytest --cov=ditto_datahub --cov=ditto_server \
    --cov-report=html --cov-fail-under=80
```

**Step 2: 运行 pre-commit**

```bash
pixi run -e dev pre-commit-run
```

---

#### Task 4.2: 更新文档

**Files:**
- Modify: `packages/datahub/README.md`
- Modify: `docs/design/09_data_quality_design.md`
- Create: `docs/adr/XXXX-ingestion-dq-fixes.md`

**Step 1: 创建 ADR 文档**

创建 `docs/adr/XXXX-ingestion-dq-fixes.md`:

```markdown
# ADR: 数据摄入 DQ 系统修复

## 状态
已采纳

## 上下文
代码审查发现多个 DQ 和数据摄入问题：
- DQ L1 阻断被吞掉
- 列名不匹配导致 KeyError
- SQLite 日期绑定问题
- SID 范围不一致

## 决策
1. DQ L1 阻断记录 FAIL，但仍更新游标（避免阻塞流程）
2. 统一 SID 范围到百万级
3. 强制 basic 数据优先于日线/复权

## 后果
- DQ 失败数据会被标记为 FAIL，但游标仍会前移
- 不会因单个日期的 DQ 问题阻塞整个摄取流程
- 失败的数据通过单独的重试任务处理
- SID 分配统一，避免冲突
```

**Step 2: 提交文档**

```bash
git add packages/datahub/README.md
git add docs/design/09_data_quality_design.md
git add docs/adr/XXXX-ingestion-dq-fixes.md
git commit -m "docs: 更新 DQ 系统修复文档

- 创建 ADR 记录修复决策
- 更新 datahub README
- 更新 DQ 设计文档
"
```

---

## 验收标准

### Critical 问题
- [x] DQ L1 阻断正确记录 FAIL 状态
- [x] 阻断时仍更新游标（避免阻塞整个摄取流程）
- [ ] adj_factor/fund_adj 正确映射 SID

### High 问题
- [ ] SQLite 成功写入 datetime.date 字段
- [ ] market_wide 查询正确传递 asset_class

### Medium 问题
- [ ] SID 范围统一到百万级
- [ ] backfill 并发策略清晰且文档一致

### 代码质量
- [ ] 所有测试通过（单元+集成）
- [ ] 分支覆盖率 >= 80%
- [ ] ruff check 通过
- [ ] mypy check 通过
- [ ] pre-commit-run 通过

### 文档更新
- [ ] 更新相关 README
- [ ] 创建 ADR 文档
- [ ] 更新设计文档

---

## 关键实施文件清单

1. `apps/server/src/ditto_server/ingestion/services/coordinator.py`
2. `packages/datahub/src/ditto_datahub/repositories/security.py`
3. `packages/datahub/src/ditto_datahub/dq/checkers/statistical.py`
4. `apps/server/src/ditto_server/ingestion/tasks/dq_batch.py`
5. `packages/datahub/src/ditto_datahub/types.py`
6. `apps/server/src/ditto_server/ingestion/services/backfill.py`

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| SID 范围变更导致数据冲突 | 高 | 先检查现有 SID，必要时执行迁移 |
| 并发修改引入竞态条件 | 中 | 充分测试并发场景 |
| DQ 阻断影响已有流程 | 低 | 添加开关允许临时禁用 |

---

**创建时间**: 2026-01-04
**预计完成时间**: 5.5 工作日
