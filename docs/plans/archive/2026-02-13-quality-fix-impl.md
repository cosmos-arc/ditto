# 质量问题修复实施计划

## 概述

修复 70 个测试失败，按优先级分 4 个阶段执行。

| 阶段 | 问题 | 失败数 | 预估时间 |
|------|------|--------|----------|
| P0-1 | datetime.date 类型不支持 | 51 | 30 分钟 |
| P0-2 | 数据库 Schema 不匹配 | 6 | 15 分钟 |
| P1-1 | SourceSchema API 变更 | 4 | 15 分钟 |
| P1-2 | Mock 配置不完整 | 2 | 15 分钟 |
| P2 | 低覆盖率模块补充 | - | 持续 |

---

## 阶段 P0-1: datetime.date 类型修复 (51 个失败)

### 根因

**Typer 不支持 `datetime.date` 类型**。当 CLI app 加载时，typer 递归检查所有命令的类型注解，遇到 `date` 类型抛出：
```
RuntimeError: Type not yet supported: <class 'datetime.date'>
```

### 修复方案

将 query 命令中的 `date` 类型改为 `str`，在函数内部解析。

### 需要修改的文件

#### 1. `apps/port/src/ditto_port/cli/commands/query/market.py`

```python
# 修改前
from datetime import date

@app.command("bars")
def query_bars(
    start_date: date = typer.Option(..., "--start-date", "-s"),
    end_date: date = typer.Option(..., "--end-date", "-e"),
    ...
)

# 修改后
from datetime import datetime

def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")

@app.command("bars")
def query_bars(
    start_date: str = typer.Option(..., "--start-date", "-s", help="开始日期 (YYYY-MM-DD)"),
    end_date: str = typer.Option(..., "--end-date", "-e", help="结束日期 (YYYY-MM-DD)"),
    ...
):
    start = _parse_date(start_date)
    end = _parse_date(end_date)
```

**具体修改位置**：
- 第 59-60 行：`start_date`, `end_date`
- 第 125 行：`as_of_date`

#### 2. `apps/port/src/ditto_port/cli/commands/query/capital.py`

**修改位置**：
- 第 48 行：`as_of_date`
- 第 100 行：`as_of_date`
- 第 145 行：`as_of_date`

#### 3. `apps/port/src/ditto_port/cli/commands/query/fundamental.py`

**修改位置**：
- 第 65 行：`as_of_date`
- 第 130 行：`as_of_date`
- 第 171-172 行：`start_date`, `end_date`

#### 4. `apps/port/src/ditto_port/cli/commands/query/macro.py`

**修改位置**：
- 第 88-89 行：`start_date`, `end_date`

### 实施步骤

1. 在每个文件顶部添加 `_parse_date` 辅助函数（如果不存在）
2. 将所有 `date` 类型的 typer 参数改为 `str`
3. 在函数体开头解析日期字符串
4. 更新 help 文档，添加日期格式说明

### 验证

```bash
pixi run -e dev test apps/port/tests/unit/cli/commands/ingest/ -v
```

---

## 阶段 P0-2: 数据库 Schema 修复 (6 个失败)

### 根因

测试代码使用 `symbol` 列名，但 `schema.sql` 中实际是 `ticker`。

### 需要修改的文件

#### 1. `packages/datahub/tests/integration/runtime/test_sqlite_pool_integration.py`

| 行号 | 修改内容 |
|------|---------|
| 143 | SQL 中的 `symbol` → `ticker` |
| 155 | `row["symbol"]` → `row["ticker"]` |
| 166 | SQL 中的 `symbol` → `ticker` |
| 203 | SQL 中的 `symbol` → `ticker` |
| 226 | SQL 中的 `symbol` → `ticker` |

#### 2. `packages/datahub/tests/integration/stores/test_security_store_integration.py`

| 行号 | 修改内容 |
|------|---------|
| 94 | `row["symbol"]` → `row["ticker"]` |
| 261 | `row["symbol"]` → `row["ticker"]` |

### 验证

```bash
pixi run -e dev test packages/datahub/tests/integration/runtime/test_sqlite_pool_integration.py -v
pixi run -e dev test packages/datahub/tests/integration/stores/test_security_store_integration.py -v
```

---

## 阶段 P1-1: SourceSchema API 修复 (4 个失败)

### 根因

`SourceSchema.validate()` 方法在重构中被移除，但测试仍在调用。

### 修复方案

**删除过时的测试文件**。原因：
1. `SourceSchema` 现在是简单的 dataclass，不再包含验证逻辑
2. 验证逻辑已迁移到其他组件（如数据写入器）
3. 测试的功能已被新的测试覆盖

### 需要删除的文件

```
packages/datahub/tests/integration/sources/test_source_schema_integration.py
```

### 验证

```bash
pixi run -e dev test packages/datahub/tests/integration/sources/ -v
```

---

## 阶段 P1-2: Mock 配置修复 (2 个失败)

### 根因

测试 Mock 的是 `write` 方法，但实际代码调用的是 `save_adj_factor`。

### 需要修改的文件

#### `apps/port/tests/integration/ingestion/test_adj_factor_ingestion_integration.py`

**修改 1：第一个测试 (test_ingest_adj_factor_uses_source_ticker_column)**

```python
# 修改前 (第 33 行)
mock_market_service.write.return_value = mocker.Mock(rows=2, files=1)

# 修改后
mock_market_service.save_adj_factor.return_value = 2
```

**修改 2：验证逻辑 (第 70-87 行)**

```python
# 修改前
call_args = mock_market_service.write.call_args
command = call_args.args[0]
df_written = command.df
assert command.dataset == "adj_factor"

# 修改后
call_args = mock_market_service.save_adj_factor.call_args
df_written = call_args.kwargs["df"]
# save_adj_factor 是专门处理 adj_factor 的，无需检查 dataset
```

**修改 3：第二个测试 (test_ingest_fund_adj_uses_source_ticker_column)**

同样的修改应用于第 109 行和第 146-163 行。

### 验证

```bash
pixi run -e dev test apps/port/tests/integration/ingestion/test_adj_factor_ingestion_integration.py -v
```

---

## 阶段 P2: 低覆盖率模块补充

### 需要提升覆盖率的模块 (< 50%)

| 模块 | 当前覆盖率 | 优先级 |
|------|-----------|--------|
| `runtime/quality/comparison_reader.py` | 22.58% | P2 |
| `runtime/quality/comparison_writer.py` | 20.59% | P2 |
| `runtime/quality/quarantine_reader.py` | 23.81% | P2 |
| `runtime/quality/quarantine_writer.py` | 33.33% | P2 |
| `metadata/instrument_reader.py` | 55.65% | P3 |
| `metadata/industry_mapping_reader.py` | 23.40% | P3 |
| `metadata/industry_reader.py` | 34.29% | P3 |
| `metadata/universe_reader.py` | 24.49% | P3 |
| `metadata/universe_writer.py` | 33.33% | P3 |
| `market/status/status_writer.py` | 26.76% | P3 |
| `notification/channels/email.py` | 30.19% | P4 |

### 建议

这些模块的测试补充作为持续优化任务，不阻塞当前质量修复。

---

## 最终验证

完成所有修复后运行：

```bash
pixi run -e dev check
```

确保：
- [ ] Lint 检查通过
- [ ] 类型检查通过
- [ ] 所有测试通过 (2067/2067)
- [ ] 覆盖率 ≥ 80%
