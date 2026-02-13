# CLI 按数据用途重构设计

> 创建日期: 2026-02-12
> 状态: Ready

## 背景

当前 CLI 命令结构是混合划分的：
- 部分按资产类型（stock, etf, index）
- 部分按数据类型（fundamental, capital, macro）

这种混合结构不够清晰，用户需要记忆多个不同维度的命令。

## 目标

1. 按**数据用途**重新组织 CLI 命令
2. 采用**动词-域-数据集**结构，为未来扩展预留空间

---

## 命令结构

```
ditto <ACTION> <DOMAIN> <DATASET> [ARGS]

ACTION:
  - ingest    # 摄取数据
  - backfill  # 回补历史数据
  - query     # 查询数据（未来）
  - export    # 导出数据（未来）
  - validate  # 验证数据质量（未来）

DOMAIN:
  - metadata     # 元数据（T0参考数据）
  - market       # 行情数据
  - fundamental  # 基本面数据
  - capital      # 资本面数据
  - macro        # 宏观数据
```

---

## 最终结构

```
ditto
├── ingest              # 摄取数据
│   ├── metadata        # 元数据
│   │   ├── calendar    # 交易日历
│   │   └── basic       # 基础信息 (stock/etf/index)
│   ├── market          # 行情数据
│   │   ├── stock       # 股票日行情
│   │   ├── etf         # ETF日行情
│   │   ├── index       # 指数日行情
│   │   ├── adj         # 复权因子
│   │   └── status      # 股票状态
│   ├── fundamental     # 基本面数据
│   │   ├── balance     # 资产负债表
│   │   ├── income      # 利润表
│   │   ├── cash-flow   # 现金流量表
│   │   ├── dividend    # 分红送配
│   │   └── corporate-actions  # 公司行为
│   ├── capital         # 资本面数据
│   │   ├── valuation   # 估值指标
│   │   ├── margin      # 融资融券
│   │   ├── pledge      # 股权质押
│   │   └── futures-position  # 期货持仓
│   └── macro           # 宏观数据
│       └── indicators  # 宏观指标
│
└── backfill            # 回补历史数据
    └── (同上结构)
```

---

## 使用示例

```bash
# 摄取
ditto ingest metadata calendar 2024-01-02
ditto ingest metadata basic 2024-01-02
ditto ingest market stock 2024-01-02
ditto ingest market etf 2024-01-02
ditto ingest fundamental balance 2024-01-02
ditto ingest capital valuation 2024-01-02
ditto ingest macro indicators 2024-01-02

# 回补
ditto backfill metadata calendar --start 2020-01-01 --end 2024-12-31
ditto backfill market stock --start 2024-01-01 --end 2024-12-31 --parallel 4

# 查询（未来）
ditto query market stock --symbol 000001.SZ --date 2024-01-02

# 导出（未来）
ditto export market stock --start 2024-01-01 --end 2024-12-31 --format parquet
```

---

## 数据集映射

### 旧结构 → 新结构

| 旧命令 | 新命令 | 数据集 |
|--------|--------|--------|
| `ditto calendar` | `ditto ingest metadata calendar` | CALENDAR |
| `ditto stock basic` | `ditto ingest metadata basic` | STOCK_BASIC |
| `ditto etf basic` | `ditto ingest metadata basic` | ETF_BASIC |
| `ditto index basic` | `ditto ingest metadata basic` | INDEX_BASIC |
| `ditto stock daily` | `ditto ingest market stock` | STOCK_DAILY |
| `ditto etf daily` | `ditto ingest market etf` | ETF_DAILY |
| `ditto index daily` | `ditto ingest market index` | INDEX_DAILY |
| `ditto adj` | `ditto ingest market adj` | ADJ_FACTOR, FUND_ADJ |
| `ditto stock status` | `ditto ingest market status` | STOCK_STATUS |
| `ditto fundamental balance` | `ditto ingest fundamental balance` | BALANCE_SHEET |
| `ditto fundamental income` | `ditto ingest fundamental income` | INCOME_STATEMENT |
| `ditto fundamental cash-flow` | `ditto ingest fundamental cash-flow` | CASH_FLOW |
| `ditto fundamental dividend` | `ditto ingest fundamental dividend` | DIVIDEND |
| `ditto corporate-actions` | `ditto ingest fundamental corporate-actions` | CORPORATE_ACTIONS |
| `ditto capital valuation` | `ditto ingest capital valuation` | VALUATION_METRICS |
| `ditto capital margin` | `ditto ingest capital margin` | MARGIN_TRADING |
| `ditto capital pledge` | `ditto ingest capital pledge` | PLEDGE_RATIO |
| `ditto futures` | `ditto ingest capital futures-position` | FUTURES → FUTURES_POSITION |
| `ditto macro indicators` | `ditto ingest macro indicators` | MACRO_INDICATORS |

---

## 命名变更

### Dataset 枚举重命名

| 原名称 | 新名称 | 说明 |
|--------|--------|------|
| `FUTURES` | `FUTURES_POSITION` | 强调是持仓数据，非期货行情 |

### 文件重命名

| 原路径 | 新路径 |
|--------|--------|
| `cli/commands/futures_cmd.py` | `cli/commands/` (合并到 capital) |
| `cli/commands/corporate_actions.py` | `cli/commands/` (合并到 fundamental) |
| `cli/commands/stock.py` | 删除，合并到 market |
| `cli/commands/etf.py` | 删除，合并到 market |
| `cli/commands/index.py` | 删除，合并到 market + metadata |
| `cli/commands/calendar.py` | 删除，合并到 metadata |
| `cli/commands/adj.py` | 删除，合并到 market |
| `stores/capital/futures/` | `stores/capital/futures_position/` |

---

## 新 CLI 命令文件结构

```
cli/commands/
├── __init__.py
├── factory.py           # 保留，命令工厂
├── ingest/              # 新建：摄取命令组
│   ├── __init__.py
│   ├── metadata.py      # calendar + basic
│   ├── market.py        # stock + etf + index + adj + status
│   ├── fundamental.py   # balance + income + cash-flow + dividend + corporate-actions
│   ├── capital.py       # valuation + margin + pledge + futures-position
│   └── macro.py         # indicators
├── backfill/            # 新建：回补命令组
│   ├── __init__.py
│   └── (同 ingest 结构)
└── (未来)
    ├── query/
    └── export/
```

---

## 影响范围

### 需要修改的文件

1. **Dataset 枚举** (`packages/datahub/src/ditto_datahub/models/common.py`)
   - `FUTURES` → `FUTURES_POSITION`

2. **INGESTION_SPECS** (`apps/port/src/ditto_port/models/config.py`)
   - 更新 `FUTURES` → `FUTURES_POSITION`
   - 更新描述

3. **CLI 命令** (`apps/port/src/ditto_port/cli/commands/`)
   - 删除: stock.py, etf.py, index.py, calendar.py, adj.py, futures_cmd.py, corporate_actions.py
   - 新建: ingest/ 目录及其子文件, backfill/ 目录

4. **CLI 主入口** (`apps/port/src/ditto_port/cli/main.py`)
   - 注册 ingest 和 backfill 命令组

5. **Coordinator** (`apps/port/src/ditto_port/services/ingestion/coordinator.py`)
   - 更新 Dataset 枚举引用

6. **DataWriter** (`apps/port/src/ditto_port/services/ingestion/data_writer.py`)
   - 更新 Dataset 枚举引用

7. **Store 目录** (`packages/datahub/src/ditto_datahub/stores/capital/`)
   - `futures/` → `futures_position/`

8. **CapitalService** (`packages/datahub/src/ditto_datahub/services/capital_service.py`)
   - 更新导入路径

9. **DataSource Protocol** (`apps/port/src/ditto_port/services/ingestion/protocols.py`)
   - `fetch_futures` → `fetch_futures_position`

10. **Tushare Source** (`packages/datahub/src/ditto_datahub/sources/tushare/`)
    - 更新方法名

11. **测试文件**
    - 更新所有引用

---

## 兼容性

### 不提供向后兼容

- 删除旧命令，用户需要适应新命令结构
- 理由：当前处于开发阶段，用户基数小

---

## 验收标准

- [ ] `ditto ingest --help` 显示帮助
- [ ] `ditto ingest metadata --help` 显示帮助
- [ ] `ditto ingest market --help` 显示帮助
- [ ] `ditto ingest fundamental --help` 包含 corporate-actions
- [ ] `ditto ingest capital --help` 包含 futures-position
- [ ] `ditto ingest capital futures-position 2024-01-02` 执行成功
- [ ] `ditto backfill --help` 显示帮助
- [ ] `pixi run -e dev check` 全部通过
