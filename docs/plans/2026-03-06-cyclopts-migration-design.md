# CLI 框架迁移设计：Typer → Cyclopts

## 1. 概述

### 1.1 目标

将 Ditto 项目的 CLI 框架从 Typer 迁移到 Cyclopts，以获得：
- **更好的 Pydantic 集成** - 原生支持 Pydantic 模型作为命令参数
- **减少样板代码** - 更简洁的参数定义语法
- **更好的自动文档** - 更丰富的帮助信息生成
- **性能优化** - 更快的 CLI 启动速度
- **技术现代化** - 采用更现代的 CLI 框架设计

### 1.2 范围

| 组件 | 涉及文件数 | 说明 |
|------|-----------|------|
| CLI 命令定义 | 28 | `apps/port/src/ditto_port/cli/` |
| CLI 测试 | 21 | `apps/port/tests/unit/cli/` + `tests/integration/cli/` |
| 依赖配置 | 1 | `pixi.toml` |

---

## 2. 当前状态分析

### 2.1 CLI 结构

```
ditto (root)
├── init          # 配置初始化 (3 commands)
│   ├── config
│   ├── dq
│   └── db
├── ingest        # 数据摄入 (20 commands)
│   ├── metadata  # calendar, basic
│   ├── market    # stock, etf, index, adj, status, fx, commodity
│   ├── fundamental  # balance, income, cash-flow, dividend, corporate-actions
│   ├── capital   # valuation, margin, pledge
│   └── macro     # indicators
├── backfill      # 历史回补 (18 commands)
│   └── (同 ingest 结构)
└── query         # 数据查询 (12 commands)
    ├── metadata  # instruments, instrument
    ├── market    # bars, constituents
    ├── fundamental  # financials, dividend, corporate-actions
    ├── capital   # margin, valuation
    └── macro     # indicators, metadata
```

**命令总数：约 53 个**

### 2.2 Typer 功能使用情况

| 功能 | 使用程度 | 代码示例 |
|------|---------|----------|
| `typer.Typer()` | 重度 | 28 个文件 |
| `app.add_typer()` | 重度 | 嵌套命令组注册 |
| `@app.command()` | 重度 | 53 个命令 |
| `typer.Option()` | 重度 | 大量参数定义 |
| `typer.Argument()` | 中度 | positional 参数 |
| `typer.Context` | 中度 | 上下文传递 (data_root, verbose) |
| `@app.callback()` | 轻度 | 仅主入口全局回调 |
| `typer.BadParameter` | 中度 | 参数验证错误 |
| `typer.Exit()` | 中度 | 退出控制 |
| `typer.testing.CliRunner` | 重度 | 所有测试 |

### 2.3 现有设计模式

#### 工厂模式 (`factory.py`)

```python
def create_daily_command(dataset: str, description: str):
    def command(ctx: typer.Context, date: str, force: bool):
        validate_date_format(date)
        with create_executor() as executor:
            result = executor.ingest_daily(dataset, date, force)
            print_ingestion_result(result, ctx.obj["verbose"])
    return command
```

#### 参数验证 (`validation.py`)

手动验证函数：
- `validate_date_format()` - 日期格式检查
- `validate_instrument_params()` - 标识符参数互斥验证
- `check_instrument_mode()` - 模式判断

---

## 3. Typer vs Cyclopts 详细对比

### 3.1 核心差异

| 特性 | Typer | Cyclopts |
|------|-------|----------|
| Pydantic 支持 | 需手动转换 | 原生支持，自动验证 |
| 参数定义 | `typer.Option()` 显式定义 | 类型注解 + `Parameter()` |
| 嵌套命令 | `add_typer()` | `app.command(SubApp)` |
| 环境变量 | 需额外配置 | 开箱即用 |
| 帮助文档 | 基础格式化 | Rich 原生，更美观 |
| Shell 补全 | 支持 | 支持更强大 |
| 启动速度 | 中等 | 更快（延迟导入优化）|
| 社区生态 | 成熟 | 新兴但活跃 |

### 3.2 API 映射表

| Typer | Cyclopts |
|-------|----------|
| `typer.Typer()` | `cyclopts.App()` |
| `app.add_typer(sub_app, name="x")` | `app.command(sub_app, name="x")` |
| `@app.command()` | `@app.command` (无需括号) |
| `typer.Option(default, "--opt", "-o")` | `Parameter(default, name=["--opt", "-o"])` |
| `typer.Argument(...)` | positional 参数 (无默认值) |
| `typer.Context` | 函数参数或 `App.get_context()` |
| `@app.callback()` | `@app.default` 或中间件 |
| `typer.BadParameter` | `cyclopts.exceptions.ValidationError` |
| `typer.Exit(code)` | `sys.exit(code)` 或 `raise` |
| `typer.echo()` | `console.print()` 或 `print()` |
| `typer.testing.CliRunner` | `cyclopts.test_utils.TestApp` |

---

## 4. 迁移策略

### 4.1 推荐方案：渐进式迁移

**分三个阶段完成迁移**，每个阶段独立可验证：

```
Phase 1: 基础设施 (1 天)
├── 添加 Cyclopts 依赖
├── 创建兼容层（保留 typer.testing.CliRunner 接口）
└── POC: 迁移 query 命令组

Phase 2: 核心迁移 (2-3 天)
├── 迁移 init 命令组
├── 迁移 ingest 命令组
├── 迁移 backfill 命令组
└── 更新工厂函数

Phase 3: 清理与优化 (1 天)
├── 移除 Typer 依赖
├── 更新所有测试
├── 更新文档
└── 性能验证
```

### 4.2 备选方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| **一次性全量迁移** | 周期短，变更集中 | 风险高，回滚困难 |
| **渐进式迁移** | 风险可控，可回滚 | 需要维护兼容层 |
| **新命令用 Cyclopts** | 无迁移成本 | 长期维护两套框架 |

---

## 5. 代码迁移示例

### 5.1 主入口 (`main.py`)

**Before (Typer)**:

```python
import typer
from ditto_port.cli.commands.backfill import app as backfill_app
from ditto_port.cli.commands.ingest import app as ingest_app
from ditto_port.cli.commands.init import app as init_app
from ditto_port.cli.commands.query import app as query_app

app = typer.Typer(
    name="ditto",
    help="Ditto 量化系统命令行工具",
    no_args_is_help=True,
    add_completion=True,
)

app.add_typer(init_app, name="init")
app.add_typer(ingest_app, name="ingest")
app.add_typer(backfill_app, name="backfill")
app.add_typer(query_app, name="query")

@app.callback()
def main(
    ctx: typer.Context,
    data_root: str = typer.Option(None, "--data-root", "-d"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    ctx.ensure_object(dict)
    ctx.obj["data_root"] = data_root
    ctx.obj["verbose"] = verbose

@app.command()
def version() -> None:
    typer.echo("ditto-cli v0.1.0")
```

**After (Cyclopts)**:

```python
from cyclopts import App, Parameter
from typing import Annotated

from ditto_port.cli.commands.backfill import app as backfill_app
from ditto_port.cli.commands.ingest import app as ingest_app
from ditto_port.cli.commands.init import app as init_app
from ditto_port.cli.commands.query import app as query_app

app = App(
    name="ditto",
    help="Ditto 量化系统命令行工具",
    version="0.1.0",
)

# 注册子命令组
app.command(init_app, name="init")
app.command(ingest_app, name="ingest")
app.command(backfill_app, name="backfill")
app.command(query_app, name="query")


@app.default
def main(
    data_root: Annotated[str | None, Parameter(name=["--data-root", "-d"])] = None,
    verbose: Annotated[bool, Parameter(name=["--verbose", "-v"])] = False,
) -> None:
    """Ditto 量化系统命令行工具."""
    # Cyclopts 会自动处理全局参数
    pass
```

### 5.2 复杂命令 (`ingest/market.py`)

**Before (Typer)** - 约 70 行/命令：

```python
@app.command("stock")
def stock(
    ctx: typer.Context,
    date: Annotated[str | None, typer.Argument(help="交易日期 (YYYY-MM-DD)")] = None,
    ticker: Annotated[str | None, typer.Option("--ticker", "-t")] = None,
    standard_ticker: Annotated[str | None, typer.Option("--standard-ticker")] = None,
    instrument_id: Annotated[int | None, typer.Option("--instrument-id", "-i")] = None,
    start: Annotated[str | None, typer.Option("--start", "-s")] = None,
    end: Annotated[str | None, typer.Option("--end", "-e")] = None,
    force: bool = typer.Option(False, "--force", "-f"),
) -> None:
    """摄取股票日行情."""
    validate_instrument_params(date, ticker, standard_ticker, instrument_id, start, end)

    if check_instrument_mode(date, ticker, standard_ticker, instrument_id):
        _run_instrument_ingest(ctx, "stock_daily", ticker, standard_ticker,
                              instrument_id, start, end, force)
    else:
        return _stock_daily_impl(ctx, date or "", force)
```

**After (Cyclopts with Pydantic)** - 约 40 行/命令：

```python
from datetime import date as Date
from cyclopts import App, Parameter
from pydantic import BaseModel, field_validator, model_validator

class StockIngestParams(BaseModel):
    """股票摄入参数."""

    ticker: str | None = None
    standard_ticker: str | None = None
    instrument_id: int | None = None
    start: Date | None = None
    end: Date | None = None
    force: bool = False

    @model_validator(mode="after")
    def validate_mode(self):
        """验证参数组合有效性."""
        has_identifier = any([self.ticker, self.standard_ticker, self.instrument_id])
        # Pydantic 自动验证，无需手动调用
        return self


@app.command
def stock(
    date: Date | None = None,
    /,  # positional-only
    params: Annotated[StockIngestParams, Parameter()] = StockIngestParams(),
) -> None:
    """
    摄取股票日行情.

    支持两种模式：
    1. 按日期批量摄取：ditto ingest market stock 2024-01-15
    2. 按标的+时间段：ditto ingest market stock --ticker 000001 -s 2024-01-01 -e 2024-01-31
    """
    # params 已完成所有验证
    has_identifier = any([params.ticker, params.standard_ticker, params.instrument_id])

    if has_identifier:
        _run_instrument_ingest(
            "stock_daily",
            ticker=params.ticker,
            standard_ticker=params.standard_ticker,
            instrument_id=params.instrument_id,
            start=params.start,
            end=params.end,
            force=params.force,
        )
    else:
        _run_daily_ingest("stock_daily", date, params.force)
```

**关键改进**：
- 参数验证从函数体移到 Pydantic 模型
- 类型注解更精确（`Date` 替代 `str`）
- 代码量减少约 40%
- 自动生成更完善的帮助文档

### 5.3 工厂函数重构 (`factory.py`)

**Before (Typer)**:

```python
def create_daily_command(
    dataset: str, description: str
) -> Callable[[typer.Context, str, bool], None]:
    def command(ctx: typer.Context, date: str, force: bool) -> None:
        validate_date_format(date)
        with create_executor() as executor:
            result = executor.ingest_daily(dataset, date, force)
            print_ingestion_result(result, ctx.obj["verbose"])
    command.__doc__ = description
    return command
```

**After (Cyclopts)**:

```python
from cyclopts import App, Parameter
from datetime import date as Date

def create_daily_command(dataset: str, description: str) -> App:
    """创建 daily 命令的工厂函数."""
    sub_app = App(name=dataset, help=description)

    @sub_app
    def command(
        date: Date,
        /,
        force: Annotated[bool, Parameter("--force", "-f")] = False,
        verbose: Annotated[bool, Parameter("--verbose", "-v")] = False,
    ) -> None:
        with create_executor() as executor:
            result = executor.ingest_daily(dataset, str(date), force)
            print_ingestion_result(result, verbose)

    return sub_app
```

### 5.4 查询命令 (`query/market.py`)

**Before (Typer)**:

```python
@app.command("bars")
def query_bars(
    instrument_id: int = typer.Option(..., "--instrument-id", "-i"),
    start_date: str = typer.Option(..., "--start-date", "-s"),
    end_date: str = typer.Option(..., "--end-date", "-e"),
    adjustment: str = typer.Option("none", "--adjustment", "-a"),
    json_output: bool = typer.Option(False, "--json", "-j"),
) -> None:
    _validate_date_range(start_date, end_date)
    # ... 业务逻辑
```

**After (Cyclopts with Pydantic)**:

```python
from cyclopts import App, Parameter
from datetime import date
from enum import Enum

class AdjustmentType(str, Enum):
    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class BarsQuery(BaseModel):
    """K线查询参数."""

    instrument_id: int
    start_date: date
    end_date: date
    adjustment: AdjustmentType = AdjustmentType.NONE
    json_output: bool = False

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_date > self.end_date:
            raise ValueError(f"start_date ({self.start_date}) 不能大于 end_date ({self.end_date})")
        return self


@app.command
def bars(params: Annotated[BarsQuery, Parameter()]) -> None:
    """查询 K 线数据."""
    with _get_market_service() as service:
        # params 已完成所有验证，直接使用
        ...
```

### 5.5 测试迁移

**Before (Typer)**:

```python
from typer.testing import CliRunner

runner = CliRunner()

def test_ingest_market_stock_success():
    result = runner.invoke(app, ["ingest", "market", "stock", "2024-01-02"])
    assert result.exit_code == 0
```

**After (Cyclopts)**:

```python
from cyclopts.test_utils import TestApp

test_app = TestApp(app)

async def test_ingest_market_stock_success():
    result = await test_app(["ingest", "market", "stock", "2024-01-02"])
    assert result.exit_code == 0
```

---

## 6. 新增能力

### 6.1 环境变量自动绑定

```python
@app.command
def ingest(
    api_key: Annotated[str, Parameter(env_var="TUSHARE_TOKEN")],
) -> None:
    # 自动从 TUSHARE_TOKEN 环境变量读取
    pass
```

### 6.2 参数组分组显示

```python
from cyclopts import Group

@app.command
def complex_command(
    # 连接参数组
    host: str = Parameter(group=Group("Connection")),
    port: int = Parameter(group=Group("Connection")),
    # 认证参数组
    username: str = Parameter(group=Group("Authentication")),
    password: str = Parameter(group=Group("Authentication")),
) -> None:
    pass
```

帮助输出：
```
Usage: ditto complex-command [OPTIONS]

Connection:
  --host TEXT
  --port INTEGER

Authentication:
  --username TEXT
  --password TEXT
```

### 6.3 更好的 Shell 补全

Cyclopts 支持更智能的 Shell 补全，包括：
- 文件路径补全
- 枚举值补全
- 自定义补全函数

---

## 7. 工作量估算

### 7.1 详细任务分解

| 阶段 | 任务 | 预估工时 | 优先级 |
|------|------|----------|--------|
| **Phase 1** | | **8h** | |
| | 添加 Cyclopts 依赖到 pixi.toml | 0.5h | P0 |
| | 创建测试兼容层 | 2h | P0 |
| | 迁移 query 命令组 (12 commands) | 4h | P0 |
| | 更新 query 相关测试 | 1.5h | P0 |
| **Phase 2** | | **16-24h** | |
| | 迁移 init 命令组 (3 commands) | 2h | P1 |
| | 迁移 ingest 命令组 (20 commands) | 6h | P1 |
| | 迁移 backfill 命令组 (18 commands) | 6h | P1 |
| | 重构工厂函数 | 3h | P1 |
| | 更新相关测试 | 4-8h | P1 |
| **Phase 3** | | **8h** | |
| | 移除 Typer 依赖 | 1h | P2 |
| | 更新 CLAUDE.md 文档 | 1h | P2 |
| | 更新 CLID.md 规范 | 1h | P2 |
| | 全量测试验证 | 2h | P2 |
| | 性能基准测试 | 2h | P2 |
| | Code Review 与调整 | 1h | P2 |

**总计：32-40 人时（4-5 人日）**

### 7.2 代码变更统计

| 类别 | 文件数 | 预估行数变化 |
|------|--------|-------------|
| 命令定义 | 28 | -400 行 (-33%) |
| 工厂函数 | 1 | -50 行 (-39%) |
| 参数验证 | 1 | -60 行 (-57%) |
| 测试文件 | 21 | -200 行 (-25%) |
| **总计** | **51** | **-710 行** |

---

## 8. 风险评估与缓解

### 8.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Cyclopts API 行为差异 | 中 | 中 | 详细测试覆盖，边界用例验证 |
| Pydantic 验证行为不一致 | 低 | 中 | 单元测试验证，文档对照 |
| Shell 补全脚本变化 | 低 | 低 | 更新安装脚本 |
| 性能回退 | 低 | 低 | 基准测试对比 |
| 团队学习曲线 | 低 | 低 | 内部培训 + 文档 |
| 上游框架 Bug | 低 | 高 | 锁定版本 + 灰度发布 |

### 8.2 回滚策略

1. **Git 分支隔离** - 在 `feature/cyclopts-migration` 分支开发
2. **兼容层保留** - Phase 1 保留 Typer 可切换
3. **功能开关** - 可通过环境变量切换框架（可选）

---

## 9. 验收标准

### 9.1 功能验收

- [ ] 所有现有命令功能不变
- [ ] 帮助文档正确显示
- [ ] 参数验证行为一致
- [ ] Shell 补全正常工作
- [ ] 错误提示清晰友好

### 9.2 质量验收

- [ ] 单元测试覆盖率 ≥ 80%
- [ ] 集成测试全部通过
- [ ] 类型检查 0 errors (basedpyright)
- [ ] Lint 检查通过 (ruff)

### 9.3 性能验收

- [ ] CLI 启动时间 ≤ 当前 (Typer)
- [ ] 内存占用无明显增加

---

## 10. 实施计划

### 10.1 时间线

```
Week 1:
  Day 1: Phase 1 - 基础设施 + query 迁移
  Day 2-3: Phase 2 - init/ingest 迁移
  Day 4: Phase 2 - backfill 迁移 + 测试更新
  Day 5: Phase 3 - 清理优化 + 验收

Week 2 (Buffer):
  Code Review
  Bug 修复
  文档完善
```

### 10.2 里程碑

| 里程碑 | 完成标志 | 预计日期 |
|--------|----------|----------|
| M1: POC 完成 | query 命令组迁移完成 | Day 1 |
| M2: 核心迁移 | init/ingest/backfill 迁移完成 | Day 4 |
| M3: 全量验收 | 所有测试通过，性能达标 | Day 5 |
| M4: 合并发布 | PR 合并，文档更新 | Day 7 |

---

## 11. 参考资料

- [Cyclopts 官方文档](https://cyclopts.readthedocs.io/)
- [Typer 官方文档](https://typer.tiangolo.com/)
- [Pydantic 验证器文档](https://docs.pydantic.dev/latest/concepts/validators/)
- 项目现有 CLI 规范：[apps/port/CLAUDE.md](../../apps/port/CLAUDE.md)
