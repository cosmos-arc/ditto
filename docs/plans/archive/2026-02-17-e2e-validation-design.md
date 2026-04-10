# Ditto E2E 验证测试框架设计

> 创建日期: 2026-02-17
> 状态: 已确认

## 1. 设计决策

| 决策项 | 选择 | 原因 |
|--------|------|------|
| 测试定位 | 完整验证型 | 全面覆盖（30+ 分钟），用于 nightly/daily 构建 |
| 数据来源 | 连接真实数据源 | 验证与真实 API 的兼容性 |
| CI 配置 | GitHub Secrets | 安全管理 Tushare token |
| TDX 文件 | 仓库内置样本 | 测试数据版本绑定，CI 配置简单 |
| 黄金数据集 | YAML 配置 + 预期快照 | 明确分离配置与预期 |
| 报告输出 | 自定义 Markdown | 符合验收报告模板，可在 GitHub 中查看 |
| 目录位置 | 顶层 `tests/e2e/` | 跨包测试，独立运行 |

## 2. 目录结构

```
tests/
├── e2e/                           # E2E 测试
│   ├── conftest.py                # 共享 fixtures
│   ├── test_ingestion.py          # 数据接入验证
│   ├── test_storage.py            # 数据存储验证
│   ├── test_query.py              # 数据查询验证
│   ├── test_quality.py            # 质量检查验证
│   ├── test_performance.py        # 性能验证
│   ├── test_readiness.py          # 生产就绪验证
│   └── reporter.py                # 报告生成器
│
├── fixtures/
│   └── golden_expected/           # 黄金数据集预期结果
│       ├── daily_snapshots/       # PIT 快照（parquet）
│       ├── reconciliation/        # 对账预期结果
│       └── quality_reports/       # 质量报告样本
│
├── tdx_samples/                   # TDX 本地文件样本
│   └── vipdoc/sz/lday/
│
└── reports/                       # 测试报告输出
    └── e2e_validation_YYYYMMDD.md
```

## 3. 核心 Fixtures

```python
# tests/e2e/conftest.py

import os
from pathlib import Path
from datetime import date

import pytest
import polars as pl
from ditto_core.quality import GoldenDatasetSpec
from ditto_data.sources import TushareSource, TDXSource, DataSourceSettings


# 黄金数据集
@pytest.fixture(scope="session")
def golden_spec() -> GoldenDatasetSpec:
    """加载黄金数据集配置（25 个标的）"""
    return GoldenDatasetSpec.from_yaml("config/default/golden_dataset.yml")


# 真实数据源
@pytest.fixture(scope="session")
def tushare_source() -> TushareSource:
    """连接真实 Tushare API（token 从环境变量读取）"""
    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        pytest.skip("TUSHARE_TOKEN 环境变量未设置")
    return TushareSource(settings=DataSourceSettings(), token=token)


@pytest.fixture(scope="session")
def tdx_source() -> TDXSource:
    """加载内置 TDX 样本文件"""
    return TDXSource(data_root=Path("tests/tdx_samples"))


# 预期结果
@pytest.fixture
def expected_snapshots(golden_spec: GoldenDatasetSpec) -> dict[str, pl.DataFrame]:
    """加载黄金数据集的预期快照"""
    return load_expected_snapshots("tests/fixtures/golden_expected/daily_snapshots/")


def load_expected_snapshots(path: str) -> dict[str, pl.DataFrame]:
    """加载预期快照文件"""
    snapshots = {}
    snapshot_dir = Path(path)
    if not snapshot_dir.exists():
        return snapshots
    for file in snapshot_dir.glob("*.parquet"):
        ticker = file.stem
        snapshots[ticker] = pl.read_parquet(file)
    return snapshots
```

## 4. 测试用例结构

```python
# tests/e2e/test_ingestion.py

class TestIngestion:
    """数据接入验证 - 验证 Tushare/TDX 源数据拉取、解析、校验"""

    def test_tushare_connection(self, tushare_source):
        """S1-01: Tushare 连接性"""
        df = tushare_source.fetch_stock_daily(trade_date="2024-01-02")
        assert df.height > 0, "应返回非空数据"

    def test_tdx_file_readable(self, tdx_source, golden_spec):
        """S1-02: TDX 文件可读性"""
        for ticker in golden_spec.tickers[:5]:  # 抽样验证
            df = tdx_source.read_daily(ticker)
            assert df is not None, f"{ticker} TDX 文件读取失败"

    def test_field_completeness(self, tushare_source):
        """S1-03: 字段完整性"""
        required_fields = ["instrument_id", "trade_date", "open", "high", "low", "close", "vol"]
        df = tushare_source.fetch_stock_daily(trade_date="2024-01-02")
        for field in required_fields:
            assert field in df.columns, f"缺少必需字段: {field}"

    def test_golden_tickers_daily(self, tushare_source, golden_spec):
        """黄金数据集日线数据接入"""
        for ticker in golden_spec.tickers:
            df = tushare_source.fetch_stock_daily(ticker=ticker, start="2023-01-01")
            assert df.height > 0, f"{ticker} 日线数据为空"
```

```python
# tests/e2e/test_storage.py

class TestStorage:
    """数据存储验证 - Writer/Reader CQRS 模式"""

    def test_write_read_consistency(self, market_service, golden_spec, tmp_path):
        """S2-01/02: 写入读取一致性"""
        for ticker in golden_spec.tickers[:5]:  # 抽样验证
            # 写入
            raw_df = fetch_data(ticker)
            rows_written = market_service.save_bars(raw_df)
            # 读取
            result_df = market_service.find_bars(ticker)
            assert result_df.height == rows_written, f"{ticker} 读写不一致"

    def test_upsert_idempotency(self, market_service):
        """S2-03: Upsert 幂等性"""
        df = create_sample_data()
        # 写入两次
        market_service.save_bars(df)
        rows_second = market_service.save_bars(df)
        assert rows_second == 0, "重复写入应返回 0（无新数据）"
```

```python
# tests/e2e/test_query.py

class TestQuery:
    """数据查询验证 - Services API、PIT 时点查询"""

    def test_pit_isolation(self, market_service, golden_spec):
        """S3-04: PIT 时点隔离 - 无未来数据泄漏"""
        as_of = date(2024, 6, 30)
        for ticker in golden_spec.tickers[:5]:
            df = market_service.find_bars(ticker, as_of=str(as_of))
            future_data = df.filter(pl.col("trade_date") > as_of)
            assert future_data.is_empty(), f"{ticker} 存在未来数据泄漏"

    def test_adj_factor_calculation(self, market_service):
        """S3-05: 复权计算正确性"""
        raw = market_service.find_bars(ticker, adj="none")
        qfq = market_service.find_bars(ticker, adj="qfq")
        # 验证复权后价格关系
        assert qfq["close"].mean() != raw["close"].mean(), "复权应有价格调整"
```

```python
# tests/e2e/test_quality.py

class TestQuality:
    """质量检查验证 - L1/L2/L3、跨源对账"""

    def test_l1_technical_check(self, quality_engine):
        """S4-01: L1 技术检查"""
        # 注入包含空值的数据
        df_with_nulls = create_data_with_nulls()
        result = quality_engine.check(df_with_nulls, levels=["l1"])
        assert result.has_errors, "应检出 L1 错误"

    def test_cross_source_reconciliation(self, reconciliation_service, golden_spec):
        """S4-04: 跨源对账 - Tushare vs TDX"""
        report = reconciliation_service.run(trade_date="2024-06-28")
        assert set(report.tickers) <= set(golden_spec.tickers), "仅对账黄金标的"
        assert report.discrepancy_rate < 0.0001, "偏差应 < 0.01%"
```

## 5. 报告生成机制

```python
# tests/e2e/reporter.py

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class StageResult:
    """单个验证阶段结果"""
    name: str
    passed: int
    failed: int
    skipped: int
    errors: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total * 100 if self.total > 0 else 0


class E2EReporter:
    """E2E 验收报告生成器"""

    def __init__(self, golden_spec) -> None:
        self.golden_spec = golden_spec
        self.results: dict[str, StageResult] = {}

    def record(self, stage: str, result: StageResult) -> None:
        """记录阶段结果"""
        self.results[stage] = result

    def generate_markdown(self, output_path: Path) -> None:
        """生成 Markdown 验收报告"""
        content = self._build_report()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

    def _all_passed(self) -> bool:
        return all(r.failed == 0 for r in self.results.values())

    def _build_report(self) -> str:
        lines = [
            f"# Ditto E2E 验收报告",
            f"",
            f"**日期**: {date.today():%Y-%m-%d}",
            f"**黄金数据集**: {len(self.golden_spec.tickers)} 标的",
            f"**整体状态**: {'✅ 通过' if self._all_passed() else '❌ 未通过'}",
            f"",
            f"## 阶段汇总",
            f"",
            f"| 阶段 | 状态 | 通过率 | 备注 |",
            f"|------|------|--------|------|",
        ]
        for name, result in self.results.items():
            status = "✅" if result.failed == 0 else "❌"
            lines.append(f"| {name} | {status} | {result.pass_rate:.0f}% | - |")

        lines.extend([
            f"",
            f"## 问题清单",
            f"",
            f"| 编号 | 严重度 | 描述 | 状态 |",
            f"|------|--------|------|------|",
        ])
        for name, result in self.results.items():
            for err in result.errors:
                lines.append(f"| {name} | ERROR | {err} | 待处理 |")

        if self._all_passed():
            lines.extend([
                f"",
                f"## 结论",
                f"",
                f"系统已通过端到端验证，具备上线条件。",
            ])

        return "\n".join(lines)
```

**使用方式**：

```python
# tests/e2e/conftest.py

@pytest.fixture(scope="session")
def reporter(golden_spec) -> E2EReporter:
    return E2EReporter(golden_spec)


@pytest.fixture(scope="session", autouse=True)
def generate_report(request, reporter: E2EReporter):
    yield
    # 所有测试结束后生成报告
    output_path = Path(f"tests/reports/e2e_validation_{date.today():%Y%m%d}.md")
    reporter.generate_markdown(output_path)
```

## 6. CI 配置

```yaml
# .github/workflows/e2e-validation.yml

name: E2E Validation

on:
  schedule:
    - cron: '0 2 * * *'  # 每日凌晨 2 点运行
  workflow_dispatch:      # 手动触发
  pull_request:
    paths:
      - 'packages/**'
      - 'apps/port/**'
    types: [labeled]     # 带有 e2e 标签时触发

jobs:
  e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - uses: actions/checkout@v4

      - name: Setup Pixi
        uses: prefix-dev/setup-pixi-action@v0.8.0

      - name: Run E2E Tests
        env:
          TUSHARE_TOKEN: ${{ secrets.TUSHARE_TOKEN }}
          ENVIRONMENT: testing
        run: |
          pixi run -e dev pytest tests/e2e/ \
            --tb=short \
            --junit-xml=tests/reports/e2e-junit.xml

      - name: Upload Reports
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: e2e-reports
          path: |
            tests/reports/*.md
            tests/reports/*.xml

      - name: Comment PR
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const glob = require('glob');
            const files = glob.sync('tests/reports/e2e_validation_*.md');
            if (files.length > 0) {
              const report = fs.readFileSync(files[0], 'utf8');
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: '```\n' + report + '\n```'
              });
            }
```

## 7. 实现计划

### Phase 1 - 基础设施（Day 1-2）

| 任务 | 产出 |
|------|------|
| 创建目录结构 | `tests/e2e/`, `tests/fixtures/`, `tests/tdx_samples/` |
| 核心fixtures | `conftest.py`（golden_spec, tushare_source, tdx_source） |
| TDX样本文件 | 25个标的的 `.day` 文件 |

### Phase 2 - 核心测试（Day 3-5）

| 任务 | 产出 |
|------|------|
| test_ingestion.py | 数据接入验证（S1-01 ~ S1-06） |
| test_storage.py | 存储验证（S2-01 ~ S2-06） |
| test_query.py | 查询验证 + PIT 隔离（S3-01 ~ S3-06） |

### Phase 3 - 质量验证（Day 6-7）

| 任务 | 产出 |
|------|------|
| test_quality.py | L1/L2/L3 检查 + 跨源对账（S4-01 ~ S4-06） |
| 预期快照 | `tests/fixtures/golden_expected/` |

### Phase 4 - 收尾（Day 8）

| 任务 | 产出 |
|------|------|
| E2EReporter | Markdown 报告生成 |
| CI配置 | GitHub Actions workflow |
| 验收 | 完整运行 + 文档更新 |

## 8. 验收标准

| 指标 | 要求 | 验证方式 |
|------|------|---------|
| 黄金数据集通过率 | 100% | 25 个标的全部通过 |
| PIT 一致性 | 100% | 无未来数据泄漏 |
| 跨源对账偏差 | < 0.01% | Tushare vs TDX |
| 报告生成 | 完整 | Markdown 格式正确 |

## 9. 参考文档

- [E2E 验证计划](./2026-02-17-e2e-validation-plan.md)
- [黄金数据集设计](../design/13_golden_dataset_design.md)
- [测试规范](../../.claude/rules/python-test.md)
- [PIT 安全规范](../../.claude/rules/pit.md)
