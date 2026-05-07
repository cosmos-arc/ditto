> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-006: 增量计算策略

**状态**: 已决策（2026-03-04）

---

## 子问题 1：Watermark 管理策略

### 决策：混合方案 - 核心因子单一 Watermark，非核心因子 Gap 容忍

```python
@dataclass
class WatermarkState:
    """Watermark 状态"""
    entity_type: str           # "feature" | "factor"
    entity_id: str             # "rsi_14"
    version: int               # 1

    watermark: date            # 最新成功日期
    coverage_start: date       # 最早覆盖日期

    # 仅非核心因子使用
    coverage_gaps: list[str] | None  # ["2026-01-15", "2026-02-20:2026-02-22"]

    # 元信息
    last_run_id: str
    updated_at: datetime


@dataclass
class EntityConfig:
    """实体配置"""
    entity_id: str
    is_critical: bool          # True = 核心因子，不允许 gap

    @property
    def allow_gaps(self) -> bool:
        return not self.is_critical
```

### 分类标准

| 类型 | is_critical | Watermark 策略 | 失败处理 |
|------|-------------|---------------|---------|
| 核心 Alpha 因子 | `True` | 单一，无 gap | 立即重试，阻塞下游 |
| 技术指标特征 | `False` | gap 容忍 | 记录 gap，继续推进 |
| 基本面特征 | `False` | gap 容忍 | 记录 gap，继续推进 |
| 非核心因子 | `False` | gap 容忍 | 记录 gap，继续推进 |

---

## 子问题 2：Lookback 预热数据加载

### 决策：混合策略 - 有交易日历用精确回退，无日历用保守估计

```python
@dataclass
class LookbackConfig:
    """Lookback 计算配置"""
    safety_factor: float = 1.5      # 无日历时：lookback * 1.5
    max_warmup_days: int = 365      # 最大预热天数（防止异常）


def compute_compute_start(
    target: date,
    lookback: int,
    calendar: TradingCalendar | None = None,
    config: LookbackConfig = LookbackConfig(),
) -> date:
    """
    计算预热开始日期
    """
    if calendar is not None:
        # 有日历：精确回退
        start = calendar.lookback(target, lookback)
    else:
        # 无日历：保守估计
        start = target - timedelta(days=int(lookback * config.safety_factor))

    # 边界保护
    return max(start, target - timedelta(days=config.max_warmup_days))
```

---

## 子问题 3：Invalidation 扩展规则

### 决策：分级回补 - 核心因子立即重算，非核心延迟处理

```python
@dataclass
class InvalidationConfig:
    """失效处理配置"""
    critical_immediate: bool = True          # 核心因子立即重算
    non_critical_delay_hours: int = 24       # 非核心延迟 24 小时
    ts_lookback_extend: bool = True          # TS 因子向后扩展
    cs_full_day: bool = True                 # CS 因子整日失效


def compute_affected_range(
    change_date: date,
    lookback: int,
    requires_full_day: bool,
    watermark: date,
    config: InvalidationConfig = InvalidationConfig(),
) -> AffectedRange:
    """计算受影响的日期范围"""
    if requires_full_day:
        # CS 因子：整日失效（所有标的）
        return AffectedRange(
            start=change_date,
            end=change_date,
            scope="full_day"
        )
    else:
        # TS 因子：向后扩展 lookback 天
        end_date = min(change_date + timedelta(days=lookback), watermark)
        return AffectedRange(
            start=change_date,
            end=end_date,
            scope="instrument_only"
        )
```

---

## 子问题 4：原子性与失败恢复

### 决策：幂等覆写 + 分区级 Checkpoint 混合方案

```python
def materialize_partition(
    entity_id: str,
    partition_key: str,
    force: bool = False,
) -> MaterializeResult:
    """单分区物化（幂等）"""
    # 1. 检查 checkpoint
    if not force:
        checkpoint = load_checkpoint(entity_id, partition_key)
        if checkpoint and checkpoint.status == "done":
            return MaterializeResult(skipped=True, reason="already_done")

    # 2. 获取锁
    with acquire_lock(f"derived/{entity_id}/{partition_key}"):
        # 3. 计算
        df = compute_partition(entity_id, partition_key)

        if df.is_empty():
            return MaterializeResult(skipped=True, reason="no_data")

        # 4. 写临时目录
        temp_path = write_temp(df, entity_id, partition_key)

        # 5. 校验
        validate(df)

        # 6. 原子替换
        target_path = get_target_path(entity_id, partition_key)
        atomic_replace(temp_path, target_path)

        # 7. 更新 Catalog（SQLite 事务）
        with catalog.transaction():
            catalog.upsert_partition(
                entity_id=entity_id,
                partition_key=partition_key,
                rows=len(df),
                checksum=compute_checksum(df),
            )
            catalog.update_checkpoint(
                entity_id=entity_id,
                partition_key=partition_key,
                status="done",
            )

        return MaterializeResult(
            entity_id=entity_id,
            partition_key=partition_key,
            rows_written=len(df),
        )
```
