# DQ - 数据质量模块

## 功能概述

实现三层（L1/L2/L3）数据质量检查机制，确保数据摄入、存储和使用过程中的数据可靠性。支持配置驱动的规则定义、灵活的检查器和完善的报告机制。

## 三层检查机制

```
┌─────────────────────────────────────────────────┐
│                   L1: 技术检查                    │
│  非空、唯一、外键、类型校验                        │
│  时机: 写入时 | 阻断: 是                          │
├─────────────────────────────────────────────────┤
│                   L2: 业务检查                    │
│  OHLC 一致性、价格合理性、成交量                   │
│  时机: 写入时 | 阻断: 否 (警告)                    │
├─────────────────────────────────────────────────┤
│                   L3: 统计检查                    │
│  Z-Score 异常、数据完整性                         │
│  时机: 定时批量 | 阻断: 否 (告警)                  │
└─────────────────────────────────────────────────┘
```

## 核心组件

| 组件 | 描述 | 路径 |
|------|------|------|
| `DQEngine` | 检查执行引擎，协调三层检查 | `engine.py` |
| `TechnicalChecker` | L1 技术检查器 | `checkers/technical.py` |
| `BusinessChecker` | L2 业务检查器 | `checkers/business.py` |
| `StatisticalChecker` | L3 统计检查器 | `checkers/statistical.py` |
| `DQConfig` | 规则配置模型 | `models.py` |
| `DQResult` | 检查结果模型 | `models.py` |
| `DQReportGenerator` | 报告生成器 | `report.py` |

## DQ 处理流程

```python
# 1. Check: 执行检查
result = DQEngine.check(df, dataset="stock_daily")

# 2. Result: 获取结果
if result.has_errors:
    # L1 失败 -> 阻断写入
    return WriteResult(blocked=True, dq_result=result)

# 3. Handle: 处理问题数据
if result.has_warnings:
    # L2 失败 -> 记录并继续
    logger.warning("DQ warnings found")

# 4. Report: 生成报告
generator = DQReportGenerator()
generator.save_report(result, report_path)
```

## DQEngine - 检查引擎

### 初始化

```python
from ditto_datahub.dq import DQEngine, DQConfig
from pathlib import Path

# 方式 1: 从配置目录加载
engine = DQEngine(
    config_path=Path("config/dq"),
)

# 方式 2: 使用预加载配置
config = DQConfig.from_yaml_dir(Path("config/dq"))
engine = DQEngine(config=config)

# 方式 3: 默认配置
engine = DQEngine()
```

### 写入时检查 (L1 + L2)

```python
from ditto_datahub.dq import DQEngine
import polars as pl

# 准备数据
df = pl.DataFrame({
    "sid": [1000001, 1000002],
    "trade_date": ["2024-01-02", "2024-01-02"],
    "open": [10.5, 20.3],
    "high": [11.0, 20.8],
    "low": [10.2, 20.0],
    "close": [10.8, 20.5],
    "volume": [1000000, 2000000],
})

# 执行检查
result = engine.check(
    df=df,
    dataset="stock_daily",
    levels=["l1", "l2"],  # 默认
    context={"hub": hub},  # 用于外键检查
)

# 判断结果
if result.passed:
    print("DQ 检查通过")
else:
    print(f"DQ 检查失败: {result.error_count} 个错误")

if result.has_warnings:
    print(f"DQ 警告: {result.warn_count} 个")

# 遍历问题
for issue in result.issues:
    print(f"[{issue.severity.value}] {issue.rule_name}: {issue.message}")
    print(f"  影响行数: {issue.affected_rows}")
```

### 批量统计检查 (L3)

```python
# 执行 L3 统计异常检查
result = engine.check_statistical(
    dataset="stock_daily",
    trade_date="2024-01-02",
    hub=hub,  # DataHub 实例，用于查询历史数据
    asset_class="stock",
    market_wide=True,  # 全市场查询模式
)

# L3 检查总是 passed=True (仅告警)
for issue in result.issues:
    print(f"[ALERT] {issue.rule_name}: {issue.message}")
```

## 规则配置

### 配置文件结构

```yaml
# config/dq/stock_daily.yml
dataset: stock_daily
description: 股票日线数据质量检查规则

# L1: 技术检查 (阻断)
l1_technical:
  - rule: not_null
    columns: [sid, trade_date, open, high, low, close, volume]
    message: "关键字段不能为空"

  - rule: unique
    columns: [sid, trade_date]
    message: "SID 和交易日期组合必须唯一"

  - rule: foreign_key
    column: sid
    reference: "security.sid"
    message: "SID 必须在 security 表中存在"

  - rule: type_check
    types:
      sid: Int64
      trade_date: Date
      open: Float64
      high: Float64
      low: Float64
      close: Float64
      volume: Int64
    message: "数据类型不匹配"

# L2: 业务检查 (警告)
l2_business:
  - rule: positive
    columns: [open, high, low, close, volume]
    message: "价格和成交量必须为正数"

  - rule: expression
    name: ohlc_consistency
    message: "OHLC 关系不正确: high >= max(open, close), low <= min(open, close)"

  - rule: range_check
    column: close
    min: 0.01
    max: 10000.0
    message: "收盘价格超出合理范围"

  - rule: no_zero_volume
    column: volume
    message: "成交量不应为零"

# L3: 统计检查 (告警)
l3_statistical:
  - rule: zscore
    name: price_anomaly_detection
    column: close
    window: 60
    threshold: 3.0
    group_by: sid
    message: "收盘价 Z-Score 异常"

  - rule: completeness
    name: daily_data_completeness
    lookback_days: 5
    message: "最近 5 个交易日数据缺失"
```

### 规则类型

| 规则 | 层级 | 参数 | 说明 |
|------|------|------|------|
| `not_null` | L1 | `columns` | 字段不能为空 |
| `unique` | L1 | `columns` | 组合必须唯一 |
| `foreign_key` | L1 | `column`, `reference` | 外键引用 |
| `type_check` | L1 | `types` | 类型校验 |
| `positive` | L2 | `columns` | 值必须为正 |
| `expression` | L2 | `name`, `expr` | 表达式校验 |
| `range_check` | L2 | `column`, `min`, `max` | 范围校验 |
| `no_zero_volume` | L2 | `column` | 非零校验 |
| `zscore` | L3 | `column`, `window`, `threshold` | Z-Score 异常检测 |
| `completeness` | L3 | `lookback_days` | 完整性检查 |

## 检查结果

### DQResult 结构

```python
@dataclass
class DQResult:
    dataset: str           # 数据集名称
    passed: bool           # 是否通过 (L1 无错误)
    issues: list[DQIssue]  # 问题列表

    # 便捷属性
    @property
    def has_errors(self) -> bool:
        """是否有 L1 错误"""

    @property
    def has_warnings(self) -> bool:
        """是否有 L2 警告"""

    @property
    def has_alerts(self) -> bool:
        """是否有 L3 告警"""

    @property
    def error_count(self) -> int:
        """L1 错误数量"""

    @property
    def warn_count(self) -> int:
        """L2 警告数量"""

    @property
    def alert_count(self) -> int:
        """L3 告警数量"""
```

### DQIssue 结构

```python
@dataclass
class DQIssue:
    level: DQLevel              # 检查层级
    severity: DQSeverity        # 严重程度
    rule_name: str              # 规则名称
    message: str                # 问题描述
    affected_rows: int          # 影响行数
    sample_data: list[dict]     # 样本数据
```

### 严重程度

| 严重程度 | 层级 | 处理方式 | 示例 |
|----------|------|----------|------|
| `ERROR` | L1 | 阻断写入，数据进入隔离区 | 空值、重复键 |
| `WARNING` | L2 | 记录日志，继续写入 | OHLC 不一致 |
| `ALERT` | L3 | 发送告警，不阻断 | Z-Score 异常 |

## 与 Ingestion 集成

### 写入流程

```python
# 在 Repository 写入时自动触发 DQ 检查
class BarsRepository:
    def write(self, df, year, dataset, run_dq_check=True):
        # 1. DQ 检查
        if run_dq_check:
            dq_result = self._dq_engine.check(df, dataset)

            # 2. L1 错误阻断
            if dq_result.has_errors:
                # 保存失败数据到隔离区
                for issue in dq_result.issues:
                    if issue.severity == DQSeverity.ERROR:
                        self._save_to_quarantine(df, issue, dataset)

                return WriteResult(
                    blocked=True,
                    dq_result=dq_result,
                )

            # 3. L2 警告记录
            if dq_result.has_warnings:
                logger.warning(f"DQ warnings: {dq_result.warn_count}")

        # 4. 写入数据
        file_path, checksum = self._bars_store.write(...)

        # 5. 生成 DQ 报告
        if dq_result and not dq_result.passed:
            self._generate_dq_report(dq_result, dataset)

        return WriteResult(...)
```

### 定时批量检查

```python
# 在 T3 任务中执行 L3 检查
from datetime import datetime

trade_date = datetime.now().strftime("%Y-%m-%d")

# 执行统计检查
result = engine.check_statistical(
    dataset="stock_daily",
    trade_date=trade_date,
    hub=hub,
    asset_class="stock",
    market_wide=True,
)

# 发送告警
if result.has_alerts:
    alert_manager.alert_dq_failure(
        dataset="stock_daily",
        trade_date=trade_date,
        failed_rules=[i.rule_name for i in result.issues],
        error_count=0,  # L3 无错误，只有告警
    )
```

## 报告生成

### Markdown 报告

```python
from ditto_datahub.dq.report import DQReportGenerator
from pathlib import Path

# 创建报告生成器
generator = DQReportGenerator()

# 生成 Markdown 报告
report_path = Path("reports/dq/stock_daily_20240102.md")
generator.save_report(
    result=result,
    output_path=report_path,
    report_format="markdown",
)
```

### 报告内容

```markdown
# 数据质量检查报告 - stock_daily

## 检查概要

- 数据集: stock_daily
- 检查时间: 2024-01-02 10:30:00
- 检查结果: FAILED
- 错误数: 2
- 警告数: 5
- 告警数: 0

## L1 技术检查 (阻断)

### ❌ not_null: volume has null values
- 严重程度: ERROR
- 影响行数: 15
- 样本数据:
  - sid: 1000001, trade_date: 2024-01-02
  - sid: 1000003, trade_date: 2024-01-02

### ❌ unique: Duplicate key: ['sid', 'trade_date']
- 严重程度: ERROR
- 影响行数: 3
- 样本数据:
  - sid: 1000005, trade_date: 2024-01-02

## L2 业务检查 (警告)

### ⚠️ positive: volume has non-positive values
- 严重程度: WARNING
- 影响行数: 8

### ⚠️ ohlc_consistency: OHLC relationship violated
- 严重程度: WARNING
- 影响行数: 2

## 建议

1. 检查数据源，修复空值问题
2. 排查重复数据来源
3. 验证价格数据合理性
```

## 配置驱动设计

### 规则加载

```python
# 从目录加载所有 YAML 配置
config = DQConfig.from_yaml_dir(Path("config/dq"))

# 加载结果
config.datasets = {
    "stock_daily": DatasetRules(...),
    "etf_daily": DatasetRules(...),
    "adj_factor": DatasetRules(...),
}

# 获取特定数据集规则
rules = config.get_rules("stock_daily")
```

### 规则验证

```python
# 检查数据集是否有规则配置
if config.has_dataset("stock_daily"):
    rules = config.get_rules("stock_daily")

    # L1 规则
    l1_rules = rules.l1_technical

    # L2 规则
    l2_rules = rules.l2_business

    # L3 规则
    l3_rules = rules.l3_statistical
```

## 安全机制

### SQL 注入防护

```python
# 外键检查时的 SQL 注入防护
class TechnicalChecker:
    # 1. 数据集白名单
    _ALLOWED_REF_DATASETS = frozenset({
        "security", "stock_daily", "etf_daily", ...
    })

    # 2. 列名格式验证
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", ref_column):
        return None

    # 3. 参数化查询
    query = f"SELECT DISTINCT {ref_column} FROM {ref_dataset}"
    result_df = hub.sql(query)  # 白名单保护
```

## 扩展检查器

### 自定义规则

```python
# 1. 在 YAML 中定义表达式规则
l2_business:
  - rule: expression
    name: custom_price_check
    expr: "close > open * 0.9 and close < open * 1.1"
    message: "收盘价异常波动"

# 2. 扩展 Checker 类
class CustomBusinessChecker(BusinessChecker):
    def _check_rule(self, df, rule, context):
        if rule.get("rule") == "custom_check":
            return self._custom_check(df, rule)
        return super()._check_rule(df, rule, context)

    def _custom_check(self, df, rule):
        # 自定义检查逻辑
        pass
```

## 相关文档

- [检查器实现](checkers/README.md)
- [配置文件示例](../../../../../config/dq/)
- [数据质量设计](../../../../../docs/design/09_data_quality_design.md)
- [隔离区处理](../stores/quarantine_store.py)
