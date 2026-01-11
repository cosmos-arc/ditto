# Ditto CLI 使用指南

> **Ditto 量化系统命令行工具** - 本地执行数据摄取、回补和管理操作

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [命令参考](#命令参考)
- [配置](#配置)
- [常见问题](#常见问题)

---

## 安装

CLI 随 `ditto-port` 包一起安装，使用 pixi 管理依赖：

```bash
# 安装依赖
pixi install

# 验证安装
pixi run ditto --help
```

---

## 快速开始

### 摄取单日数据

获取指定交易日的股票/ETF 日行情数据：

```bash
# 股票日行情
pixi run ditto stock daily 2024-01-02

# ETF 日行情
pixi run ditto etf daily 2024-01-02

# 强制重新摄取（覆盖已有数据）
pixi run ditto stock daily 2024-01-02 --force
```

### 回补历史数据

批量获取日期范围内的历史数据：

```bash
# 股票历史回补（顺序执行）
pixi run ditto stock backfill --start 2024-01-01 --end 2024-01-31

# ETF 历史回补（并行执行）
pixi run ditto etf backfill --start 2024-01-01 --end 2024-01-31 --parallel 4
```

### 更新基础信息

更新股票基础信息、交易日历等静态数据：

```bash
# 股票基础信息（代码、名称、行业等）
pixi run ditto stock basic

# ETF 基础信息
pixi run ditto etf basic

#交易日历
pixi run ditto calendar
```

### 复权因子

获取复权因子数据：

```bash
# 股票复权因子
pixi run ditto adj adj-factor

# 基金复权因子
pixi run ditto adj fund-adj
```

---

## 命令参考

### 全局选项

| 选项 | 简写 | 说明 |
|------|------|------|
| `--data-root` | `-d` | 指定数据根目录（默认：配置文件中设置的路径） |
| `--verbose` | `-v` | 启用详细输出模式 |
| `--help` | `-h` | 显示帮助信息 |

### Stock 命令组

股票数据摄取命令。

#### `stock daily` - 摄取股票日行情

```bash
pixi run ditto stock daily <DATE> [OPTIONS]
```

**参数：**

| 参数 | 说明 |
|------|------|
| `DATE` | 交易日期，格式：YYYY-MM-DD |

**选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--force` | `-f` | 强制重新摄取，覆盖已有数据 |

**示例：**

```bash
pixi run ditto stock daily 2024-01-02
pixi run ditto stock daily 2024-01-02 --force
pixi run ditto stock daily 2024-01-02 -f -v  # 详细模式
```

#### `stock backfill` - 回补股票历史数据

```bash
pixi run ditto stock backfill [OPTIONS]
```

**必填选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--start` | `-s` | 开始日期 (YYYY-MM-DD) |
| `--end` | `-e` | 结束日期 (YYYY-MM-DD) |

**可选选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--parallel` | `-p` | 并行度（默认：1） |

**示例：**

```bash
pixi run ditto stock backfill --start 2024-01-01 --end 2024-01-31
pixi run ditto stock backfill -s 2024-01-01 -e 2024-01-31 -p 4
```

#### `stock basic` - 摄取股票基础信息

```bash
pixi run ditto stock basic [OPTIONS]
```

**选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--force` | `-f` | 强制重新摄取 |

---

### ETF 命令组

ETF 数据摄取命令，用法与 Stock 命令组相同。

#### `etf daily` - 摄取 ETF 日行情

```bash
pixi run ditto etf daily <DATE> [OPTIONS]
```

#### `etf backfill` - 回补 ETF 历史数据

```bash
pixi run ditto etf backfill [OPTIONS]
```

#### `etf basic` - 摄取 ETF 基础信息

```bash
pixi run ditto etf basic [OPTIONS]
```

---

### Calendar 命令组

交易日历管理命令。

#### `calendar default` - 更新交易日历

```bash
pixi run ditto calendar [OPTIONS]
```

**选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--force` | `-f` | 强制重新获取 |

---

### Adj 命令组

复权因子数据命令。

#### `adj adj-factor` - 股票复权因子

```bash
pixi run ditto adj adj-factor [OPTIONS]
```

**选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--force` | `-f` | 强制重新获取 |

#### `adj fund-adj` - 基金复权因子

```bash
pixi run ditto adj fund-adj [OPTIONS]
```

**选项：**

| 选项 | 简写 | 说明 |
|------|------|------|
| `--force` | `-f` | 强制重新获取 |

---

## 配置

### 数据根目录

CLI 使用与项目相同的配置系统，数据根目录默认为项目配置中的设置。

使用 `--data-root` 选项可以临时覆盖：

```bash
pixi run ditto --data-root /path/to/data stock daily 2024-01-02
```

### 环境变量

支持通过环境变量配置：

```bash
export DITTO_DATA_ROOT=/path/to/data
pixi run ditto stock daily 2024-01-02
```

---

## 常见问题

### Q: 如何查看所有可用命令？

```bash
pixi run ditto --help
pixi run ditto stock --help  # 查看子命令帮助
```

### Q: 日期格式支持哪些格式？

仅支持 `YYYY-MM-DD` 格式（ISO 8601），例如：`2024-01-02`。

### Q: 如何理解执行结果？

CLI 输出包含：
- **状态**：success（成功）、skipped（跳过）、failed（失败）
- **行数**：摄取的数据行数
- **错误信息**：失败时的详细错误

示例输出：

```
状态: success
数据集: stock_daily
交易日期: 2024-01-02
行数: 5234
```

### Q: backfill 命令的并行度如何选择？

- `parallel=1`：顺序执行，适合网络不稳定场景
- `parallel=4`：4 线程并行，适合快速回补历史数据
- 建议值：2-8，根据网络条件和 API 限制调整

### Q: 如何处理摄取失败的数据？

1. 检查错误信息，确认失败原因
2. 使用 `--force` 选项重新摄取单个日期
3. 或使用 backfill 命令重新回补失败日期范围

---

## 架构说明

CLI 模块位于 `apps/port/src/ditto_port/cli/`，架构如下：

```
cli/
├── main.py          # Typer 应用入口
├── executor.py      # 核心执行器（调用 services）
├── commands/        # 命令实现
│   ├── stock.py
│   ├── etf.py
│   ├── calendar.py
│   └── adj.py
└── utils/           # 工具函数
    ├── output.py    # 输出格式化
    └── validation.py # 参数验证
```

CLI 通过 `CLIExecutor` 调用 `services.ingestion.IngestionCoordinator` 和 `BackfillManager`，与 Prefect Flow 共享相同的业务逻辑。

---

## 相关文档

- [数据摄取架构](../../design/data-ingestion.md)
- [数据集配置](../datasets/README.md)
- [CLI 入口实施计划](../plans/2025-01-11-cli-entry.md)
