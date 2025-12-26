# Ditto 数据质量设计

**版本：v1.0**

**日期：2025-12-25**

---

## 1. 设计原则

### 1.1 核心理念

参考业界最佳实践（Great Expectations / dbt / Data Contract）：

1. **规则定义收敛**：所有 DQ 规则定义在 DataHub 的 YAML 配置中
2. **执行时机分离**：写入时同步执行 vs 定时批量执行
3. **分层校验**：技术校验 → 业务规则 → 统计异常

### 1.2 不做双源校验

Phase 0-1 阶段**不实现双源校验**（Tushare vs AkShare），原因：

| 维度 | 分析 |
|------|------|
| 复杂度 | 需维护两套适配器，增加 50% 工作量 |
| 收益 | ETF 数据来自交易所，错误概率极低 |
| 替代方案 | 时序异常检测 + Golden Dataset 人工核验更实用 |

AkShare 保留作为**降级备选**，而非校验对比源。

---

## 2. 规则分层

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DQ 规则分层                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ L1: 技术校验（Technical）                                            │   │
│  │                                                                      │   │
│  │ - 非空检查：sid, trade_date, close 必填                              │   │
│  │ - 主键唯一：(sid, trade_date) 不重复                                 │   │
│  │ - 类型检查：数值字段为数值类型                                        │   │
│  │ - 外键存在：sid 存在于 security 表                                   │   │
│  │                                                                      │   │
│  │ 执行时机：写入时同步                                                  │   │
│  │ 失败处理：硬失败，阻断写入，数据进隔离区                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ L2: 业务规则（Business）                                             │   │
│  │                                                                      │   │
│  │ - OHLC 一致性：high >= low, high >= max(open, close)                │   │
│  │ - 正数检查：open, high, low, close, volume >= 0                     │   │
│  │ - 涨跌幅限制：|pct_change| <= 11%（含 ST/新股容差）                  │   │
│  │ - 量额匹配：volume > 0 时 amount > 0                                 │   │
│  │                                                                      │   │
│  │ 执行时机：写入时同步                                                  │   │
│  │ 失败处理：软失败，记录警告，允许写入                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ L3: 统计异常（Statistical）                                          │   │
│  │                                                                      │   │
│  │ - 成交量 Z-score：60 日滚动窗口，|zscore| > 5 告警                   │   │
│  │ - 完整性检查：Universe 标的数据完整率 >= 95%                         │   │
│  │ - 时序断点：检测连续缺失 > 3 天的标的                                │   │
│  │ - 趋势异常：数据量较上周同期下降 > 10%                               │   │
│  │                                                                      │   │
│  │ 执行时机：定时批量（每日收盘后）                                      │   │
│  │ 失败处理：生成报告，发送告警，不阻断                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 统一规则定义

### 3.1 配置文件结构

```yaml
# packages/ditto-data-hub/config/dq_rules.yaml

version: "1.0"

# ============================================================
# 全局默认配置
# ============================================================
defaults:
  on_l1_failure: reject      # L1 失败：拒绝写入
  on_l2_failure: warn        # L2 失败：警告但允许
  on_l3_failure: alert       # L3 失败：发送告警

# ============================================================
# 按数据集定义规则
# ============================================================
datasets:

  # ---------- ETF 日线 ----------
  etf_daily:
    description: "ETF 日 K 线数据"

    # L1: 技术校验（写入时强制）
    l1_technical:
      - rule: not_null
        columns: [sid, trade_date, open, high, low, close]
        message: "必填字段不能为空"

      - rule: unique
        columns: [sid, trade_date]
        message: "主键重复"

      - rule: foreign_key
        column: sid
        reference: security.sid
        message: "SID 不存在于证券主表"

    # L2: 业务规则（写入时警告）
    l2_business:
      - rule: positive
        columns: [open, high, low, close]
        message: "价格必须为正"

      - rule: non_negative
        columns: [volume, amount]
        message: "成交量/额不能为负"

      - rule: expression
        name: ohlc_consistency
        expr: "high >= low AND high >= open AND high >= close AND low <= open AND low <= close"
        message: "OHLC 关系不一致"

      - rule: expression
        name: price_change_limit
        expr: "pct_change IS NULL OR abs(pct_change) <= 0.11"
        message: "涨跌幅超过 11%"

      - rule: expression
        name: volume_amount_match
        expr: "volume = 0 OR amount > 0"
        message: "有成交量但无成交额"

    # L3: 统计异常（定时批量）
    l3_statistical:
      - rule: zscore
        name: volume_spike
        column: volume
        window: 60
        threshold: 5
        message: "成交量异常波动"

      - rule: completeness
        name: universe_coverage
        universe: etf_core
        threshold: 0.95
        message: "Universe 覆盖率不足 95%"

      - rule: continuity
        name: no_long_gap
        max_gap_days: 3
        message: "数据连续缺失超过 3 天"

  # ---------- 指数日线 ----------
  index_daily:
    description: "指数日 K 线数据"

    l1_technical:
      - rule: not_null
        columns: [sid, trade_date, close]

      - rule: unique
        columns: [sid, trade_date]

    l2_business:
      - rule: positive
        columns: [open, high, low, close]

      - rule: expression
        name: ohlc_consistency
        expr: "high >= low"

  # ---------- 复权因子 ----------
  adj_factor:
    description: "复权因子"

    l1_technical:
      - rule: not_null
        columns: [sid, trade_date, adj_factor]

      - rule: unique
        columns: [sid, trade_date]

    l2_business:
      - rule: expression
        name: adj_factor_positive
        expr: "adj_factor > 0"
        message: "复权因子必须为正"

      - rule: expression
        name: adj_factor_range
        expr: "adj_factor >= 0.1 AND adj_factor <= 100"
        message: "复权因子超出合理范围"

  # ---------- 交易日历 ----------
  trading_calendar:
    description: "交易日历"

    l1_technical:
      - rule: not_null
        columns: [cal_date, is_open]

      - rule: unique
        columns: [cal_date]
```

### 3.2 规则类型说明

| 规则类型 | 参数 | 说明 |
|----------|------|------|
| `not_null` | columns | 指定列不能为空 |
| `unique` | columns | 指定列组合唯一 |
| `foreign_key` | column, reference | 外键存在性检查 |
| `positive` | columns | 值必须 > 0 |
| `non_negative` | columns | 值必须 >= 0 |
| `expression` | expr | 自定义 SQL 表达式 |
| `zscore` | column, window, threshold | 滚动 Z-score 异常检测 |
| `completeness` | universe, threshold | Universe 覆盖率检查 |
| `continuity` | max_gap_days | 时序连续性检查 |

---

## 4. 执行引擎（DataHub）

### 4.1 目录结构

```
packages/
  ditto-data-hub/
    config/
      dq_rules.yaml              # 规则定义（唯一来源）

    src/
      ditto_data_hub/
        dq/                      # DQ 模块
          __init__.py
          engine.py              # DQ 执行引擎
          rules.py               # 规则加载与解析
          checkers/              # 规则检查器实现
            __init__.py
            technical.py         # L1 技术校验
            business.py          # L2 业务规则
            statistical.py       # L3 统计异常
          result.py              # 校验结果模型
```

### 4.2 引擎实现

```python
# src/ditto_data_hub/dq/engine.py
"""
DQ 执行引擎

统一的数据质量检查引擎，根据配置执行不同层级的规则
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal
from pathlib import Path
import polars as pl
import yaml

from .checkers import TechnicalChecker, BusinessChecker, StatisticalChecker


class DQLevel(Enum):
    """DQ 层级"""
    L1_TECHNICAL = "l1_technical"
    L2_BUSINESS = "l2_business"
    L3_STATISTICAL = "l3_statistical"


class DQSeverity(Enum):
    """问题严重程度"""
    ERROR = "error"      # L1 失败
    WARNING = "warning"  # L2 失败
    ALERT = "alert"      # L3 失败


@dataclass
class DQIssue:
    """单个 DQ 问题"""
    level: DQLevel
    severity: DQSeverity
    rule_name: str
    message: str
    affected_rows: int = 0
    sample_data: list[dict] = field(default_factory=list)


@dataclass
class DQResult:
    """DQ 检查结果"""
    dataset: str
    passed: bool                    # 是否通过（L1 无失败）
    issues: list[DQIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """是否有 L1 错误"""
        return any(i.severity == DQSeverity.ERROR for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """是否有 L2 警告"""
        return any(i.severity == DQSeverity.WARNING for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == DQSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == DQSeverity.WARNING)


class DQEngine:
    """
    DQ 执行引擎

    使用示例：
        engine = DQEngine()

        # 写入时校验（L1 + L2）
        result = engine.check(df, dataset="etf_daily", levels=["l1", "l2"])
        if not result.passed:
            raise DQValidationError(result)

        # 批量校验（L3）
        result = engine.check_statistical(dataset="etf_daily", trade_date="2024-12-20")
    """

    def __init__(self, config_path: str | Path | None = None):
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "dq_rules.yaml"

        self.config = self._load_config(config_path)
        self.technical_checker = TechnicalChecker()
        self.business_checker = BusinessChecker()
        self.statistical_checker = StatisticalChecker()

    def _load_config(self, path: Path) -> dict:
        """加载规则配置"""
        with open(path) as f:
            return yaml.safe_load(f)

    def get_rules(
        self,
        dataset: str,
        level: DQLevel | None = None,
    ) -> list[dict]:
        """获取指定数据集的规则"""
        dataset_config = self.config.get("datasets", {}).get(dataset, {})

        if level is None:
            rules = []
            for lvl in DQLevel:
                rules.extend(dataset_config.get(lvl.value, []))
            return rules

        return dataset_config.get(level.value, [])

    def check(
        self,
        df: pl.DataFrame,
        dataset: str,
        levels: list[Literal["l1", "l2"]] = ["l1", "l2"],
        context: dict | None = None,
    ) -> DQResult:
        """
        执行 DQ 检查（写入时调用）

        Args:
            df: 待检查的数据
            dataset: 数据集名称
            levels: 要执行的层级
            context: 额外上下文（如 hub 实例）
        """
        issues = []

        if "l1" in levels:
            l1_rules = self.get_rules(dataset, DQLevel.L1_TECHNICAL)
            l1_issues = self.technical_checker.check(df, l1_rules, context)
            issues.extend(l1_issues)

        if "l2" in levels:
            l2_rules = self.get_rules(dataset, DQLevel.L2_BUSINESS)
            l2_issues = self.business_checker.check(df, l2_rules, context)
            issues.extend(l2_issues)

        passed = not any(i.severity == DQSeverity.ERROR for i in issues)

        return DQResult(dataset=dataset, passed=passed, issues=issues)

    def check_statistical(
        self,
        dataset: str,
        trade_date: str,
        hub: "DataHub",
    ) -> DQResult:
        """
        执行 L3 统计异常检查（定时批量调用）
        """
        l3_rules = self.get_rules(dataset, DQLevel.L3_STATISTICAL)
        issues = self.statistical_checker.check(
            dataset=dataset,
            trade_date=trade_date,
            rules=l3_rules,
            hub=hub,
        )

        return DQResult(dataset=dataset, passed=True, issues=issues)


# 单例
_engine: DQEngine | None = None

def get_dq_engine() -> DQEngine:
    """获取 DQ 引擎单例"""
    global _engine
    if _engine is None:
        _engine = DQEngine()
    return _engine
```

### 4.3 L1 技术校验检查器

```python
# src/ditto_data_hub/dq/checkers/technical.py
"""
L1 技术校验检查器
"""

import polars as pl
from ..result import DQIssue, DQLevel, DQSeverity


class TechnicalChecker:
    """L1 技术校验"""

    def check(
        self,
        df: pl.DataFrame,
        rules: list[dict],
        context: dict | None = None,
    ) -> list[DQIssue]:
        """执行 L1 规则检查"""
        issues = []

        for rule in rules:
            rule_type = rule["rule"]

            if rule_type == "not_null":
                issue = self._check_not_null(df, rule)
            elif rule_type == "unique":
                issue = self._check_unique(df, rule)
            elif rule_type == "foreign_key":
                issue = self._check_foreign_key(df, rule, context)
            else:
                continue

            if issue:
                issues.append(issue)

        return issues

    def _check_not_null(self, df: pl.DataFrame, rule: dict) -> DQIssue | None:
        """非空检查"""
        columns = rule["columns"]

        null_counts = {}
        for col in columns:
            if col in df.columns:
                null_count = df.filter(pl.col(col).is_null()).height
                if null_count > 0:
                    null_counts[col] = null_count

        if null_counts:
            return DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="not_null",
                message=rule.get("message", f"字段存在空值: {null_counts}"),
                affected_rows=sum(null_counts.values()),
            )
        return None

    def _check_unique(self, df: pl.DataFrame, rule: dict) -> DQIssue | None:
        """唯一性检查"""
        columns = rule["columns"]
        duplicate_count = df.height - df.unique(subset=columns).height

        if duplicate_count > 0:
            duplicates = (
                df.group_by(columns)
                .agg(pl.count().alias("cnt"))
                .filter(pl.col("cnt") > 1)
                .head(5)
            )

            return DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="unique",
                message=rule.get("message", f"主键重复: {duplicate_count} 条"),
                affected_rows=duplicate_count,
                sample_data=duplicates.to_dicts(),
            )
        return None

    def _check_foreign_key(
        self,
        df: pl.DataFrame,
        rule: dict,
        context: dict | None,
    ) -> DQIssue | None:
        """外键存在性检查"""
        if context is None or "hub" not in context:
            return None

        hub = context["hub"]
        column = rule["column"]

        valid_sids = set(hub.security_store.get_all_sids())
        df_sids = set(df[column].unique().to_list())
        invalid_sids = df_sids - valid_sids

        if invalid_sids:
            return DQIssue(
                level=DQLevel.L1_TECHNICAL,
                severity=DQSeverity.ERROR,
                rule_name="foreign_key",
                message=rule.get("message", f"无效的 SID: {len(invalid_sids)} 个"),
                affected_rows=df.filter(pl.col(column).is_in(list(invalid_sids))).height,
                sample_data=[{"invalid_sids": list(invalid_sids)[:10]}],
            )
        return None
```

### 4.4 L3 统计异常检查器

```python
# src/ditto_data_hub/dq/checkers/statistical.py
"""
L3 统计异常检查器
"""

import polars as pl
from ..result import DQIssue, DQLevel, DQSeverity


class StatisticalChecker:
    """L3 统计异常（定时批量执行）"""

    def check(
        self,
        dataset: str,
        trade_date: str,
        rules: list[dict],
        hub: "DataHub",
    ) -> list[DQIssue]:
        """执行 L3 统计异常检查"""
        issues = []

        for rule in rules:
            rule_type = rule["rule"]

            if rule_type == "zscore":
                issue = self._check_zscore(dataset, trade_date, rule, hub)
            elif rule_type == "completeness":
                issue = self._check_completeness(dataset, trade_date, rule, hub)
            elif rule_type == "continuity":
                issue = self._check_continuity(dataset, trade_date, rule, hub)
            else:
                continue

            if issue:
                issues.append(issue)

        return issues

    def _check_zscore(
        self,
        dataset: str,
        trade_date: str,
        rule: dict,
        hub: "DataHub",
    ) -> DQIssue | None:
        """Z-score 异常检测"""
        column = rule["column"]
        window = rule.get("window", 60)
        threshold = rule.get("threshold", 5)
        name = rule.get("name", f"zscore_{column}")

        start_date = hub.calendar.offset(trade_date, -window)
        df = hub.bars.get(start=start_date, end=trade_date)

        if df.is_empty():
            return None

        # 计算滚动 Z-score
        stats = df.group_by("sid").agg([
            pl.col(column).mean().alias("mean"),
            pl.col(column).std().alias("std"),
        ])

        current = df.filter(pl.col("trade_date") == trade_date)
        current = current.join(stats, on="sid")
        current = current.with_columns([
            ((pl.col(column) - pl.col("mean")) / pl.col("std")).alias("zscore")
        ])

        anomalies = current.filter(pl.col("zscore").abs() > threshold)

        if anomalies.height > 0:
            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name=name,
                message=rule.get("message", f"{column} 异常: {anomalies.height} 只"),
                affected_rows=anomalies.height,
                sample_data=anomalies.head(10).to_dicts(),
            )
        return None

    def _check_completeness(
        self,
        dataset: str,
        trade_date: str,
        rule: dict,
        hub: "DataHub",
    ) -> DQIssue | None:
        """完整性检查"""
        universe = rule.get("universe", "etf_core")
        threshold = rule.get("threshold", 0.95)
        name = rule.get("name", "completeness")

        expected_sids = hub.universe.get_constituents(universe)
        expected_count = len(expected_sids)

        if expected_count == 0:
            return None

        df = hub.bars.get(sids=expected_sids, start=trade_date, end=trade_date)
        actual_count = df["sid"].n_unique()
        coverage = actual_count / expected_count

        if coverage < threshold:
            missing_sids = set(expected_sids) - set(df["sid"].unique().to_list())

            return DQIssue(
                level=DQLevel.L3_STATISTICAL,
                severity=DQSeverity.ALERT,
                rule_name=name,
                message=rule.get("message", f"覆盖率 {coverage:.1%} < {threshold:.1%}"),
                affected_rows=len(missing_sids),
                sample_data=[{
                    "expected": expected_count,
                    "actual": actual_count,
                    "missing_sample": list(missing_sids)[:10],
                }],
            )
        return None
```

---

## 5. Repository 集成

```python
# src/ditto_data_hub/repositories/bars.py

from ..dq import get_dq_engine
from ..exceptions import DQValidationError


class BarsRepository:
    """行情数据 Repository"""

    def write(
        self,
        df: pl.DataFrame,
        dataset: str,
        source: str,
        skip_dq: bool = False,
    ) -> WriteResult:
        """写入行情数据"""

        # DQ 检查（L1 + L2）
        if not skip_dq:
            dq_engine = get_dq_engine()
            dq_result = dq_engine.check(
                df=df,
                dataset=dataset,
                levels=["l1", "l2"],
                context={"hub": self._hub},
            )

            # L1 失败：阻断写入
            if not dq_result.passed:
                self._quarantine(df, dataset, dq_result)
                raise DQValidationError("DQ check failed", dq_result=dq_result)

            # L2 警告：记录但继续
            if dq_result.has_warnings:
                logger.warning("dq_warnings", count=dq_result.warning_count)

        # 写入存储
        # ...
```

---

## 6. Server 批量检查任务

```python
# apps/server/src/ditto_server/ingestion/tasks/dq_batch.py
"""
L3 批量 DQ 检查 Task

定时执行统计异常检测，规则定义在 DataHub
"""

from prefect import task, get_run_logger
from ditto_data_hub import DataHub
from ditto_data_hub.dq import get_dq_engine


@task(
    name="dq-batch-check",
    description="批量数据质量检查（L3 统计异常）",
    tags=["dq", "batch"],
)
def dq_batch_check(
    trade_date: str | None = None,
    datasets: list[str] | None = None,
) -> dict:
    """
    执行 L3 批量检查

    规则定义在 DataHub 的 dq_rules.yaml
    此 Task 只负责触发执行和处理结果
    """
    logger = get_run_logger()
    hub = DataHub()
    engine = get_dq_engine()

    if trade_date is None:
        trade_date = hub.calendar.get_last_trading_day()

    if datasets is None:
        datasets = ["etf_daily", "index_daily", "adj_factor"]

    logger.info(f"开始 L3 批量检查: {trade_date}")

    all_issues = []
    for dataset in datasets:
        result = engine.check_statistical(
            dataset=dataset,
            trade_date=trade_date,
            hub=hub,
        )
        all_issues.extend(result.issues)

    summary = {
        "trade_date": trade_date,
        "total_issues": len(all_issues),
        "alerts": sum(1 for i in all_issues if i.severity.value == "alert"),
    }

    if all_issues:
        send_dq_alert(trade_date, all_issues)

    return summary
```

---

## 7. 总结

### 设计对比

| 维度 | 原方案 | 新方案 |
|------|--------|--------|
| 规则定义 | DataHub DQ + Server Validator | **统一在 DataHub `dq_rules.yaml`** |
| 执行引擎 | 两套独立实现 | **统一 `DQEngine`** |
| 双源校验 | 实现 | **不实现**（复杂度高、收益低） |
| Server 职责 | 独立 Validator | **仅触发 L3 检查** |

### 三层规则

| 层级 | 检测内容 | 执行时机 | 失败处理 |
|------|----------|----------|----------|
| L1 | 非空、唯一、外键 | 写入时 | **阻断写入** |
| L2 | OHLC、涨跌幅 | 写入时 | **警告记录** |
| L3 | Z-score、完整性 | 定时批量 | **告警通知** |

### 最终目录结构

```
DataHub                              Server
├── config/                          ├── ingestion/
│   └── dq_rules.yaml  ←─────────────│   tasks/
├── dq/                               │     └── dq_batch.py
│   ├── engine.py                    │         （仅触发 L3）
│   ├── result.py                    │
│   └── checkers/                    │
│       ├── technical.py             │
│       ├── business.py              └── 不再有独立 validators/
│       └── statistical.py
```

**核心原则**：规则定义收敛在 DataHub，Server 只负责编排触发。
