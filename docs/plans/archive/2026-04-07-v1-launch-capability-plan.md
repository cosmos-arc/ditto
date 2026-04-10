# V1 上线能力计划 — 日线策略 + 纸面信号 API 服务

> 日期：2026-04-07
> 状态：设计完成，待实施
> 范围：不含实盘、不含分钟级实时数据

---

## 1. V1 目标定义

### 1.1 产品形态

完整的 REST API 服务，支持：
- 策略定义与管理（CRUD + 启停）
- 手动/自动触发回测 + 绩效报告查询
- 每日收盘后自动运行策略，产出纸面交易信号
- 通过 API 查询信号和持仓建议，供人工下单参考

### 1.2 策略方向

| 策略类型 | 数据依赖 | 模板状态 |
|---------|---------|---------|
| ETF 行业轮动 | 日线行情 + 资金面 | `etf_rotation` ✅ |
| ETF 趋势跟踪 | 日线行情 | `etf_trend_swing` ✅ |
| 多因子选股 | 日线行情 + 基本面 + 资金面 | `stock_selection_trend` ✅ |
| 行业轮动（股票） | 日线行情 + 行业分类 | `stock_sector_rotation` ✅ |

### 1.3 技术栈

- API 框架：FastAPI
- ASGI 服务：Granian
- 任务调度：Prefect
- 数据存储：Parquet + SQLite + DuckDB
- 认证鉴权：V1 不需要（内部使用）

---

## 2. 已有能力盘点

### 2.1 数据层（ditto_data）— 完备 ✅

| 数据类型 | 存储位置 | 状态 |
|---------|---------|------|
| ETF 日线行情 | `storage/market/etf/` | ✅ |
| 股票日线行情 | `storage/market/stock/` | ✅ |
| 指数数据 | `storage/market/index/` | ✅ |
| 基本面（财务/预测/公司治理） | `storage/fundamental/` | ✅ |
| 宏观指标 | `storage/macro/` | ✅ |
| 资金面（估值/融资融券/成分） | `storage/capital/` | ✅ |
| 行业分类 | `storage/metadata/industry/` | ✅ |
| 因子/特征 | `storage/features/` + `storage/factors/` | ✅ |
| 数据源 | Tushare + FRED + TDX | ✅ |
| 质量检查 | L1-L4 四级 | ✅ |

### 2.2 因子引擎（ditto_analytics）— 完备 ✅

| 能力 | 模块 | 状态 |
|------|------|------|
| 表达式编译 | `expression/` (Lexer→Parser→Codegen) | ✅ |
| 因子物化 | `materialization/` | ✅ |
| IC 评估 | `evaluation/` (Pearson/Rank/Decay/Regime) | ✅ |
| 分层收益/多空 | `evaluation/metrics/` | ✅ |
| Fama-MacBeth | `evaluation/metrics/` | ✅ |
| 正交化 | `evaluation/metrics/` | ✅ |

### 2.3 策略引擎（ditto_engine）— 完备 ✅

| 能力 | 模块 | 状态 |
|------|------|------|
| Pipeline 框架 | `alpha/pipeline.py` (8 Stages) | ✅ |
| 4 个策略模板 | `alpha/templates/` | ✅ |
| 回测引擎 | `backtest/engine.py` (EngineLoop) | ✅ |
| A 股规则模型 | `execution/reality/` (T+1/涨跌停/费率) | ✅ |
| PreTrade 风控 | `risk/pre_trade.py` (6 规则) | ✅ |
| PostTrade 风控 | `risk/post_trade.py` (4 规则) | ✅ |
| 绩效统计 | `backtest/statistics.py` (NAV/Sharpe/Drawdown) | ✅ |
| 账户体系 | `accounting/` (Account/Position/CashBook) | ✅ |

### 2.4 应用层（ditto_app）— 基本可用 ⚠️

| 能力 | 模块 | 状态 |
|------|------|------|
| 回测服务 | `process/backtest_service.py` | ✅ |
| 策略运行服务 | `process/strategy_run_service.py` | ✅ |
| 数据摄入 | `process/ingestion_coordinator.py` | ✅ |
| 因子物化 | `process/materialization_orchestrator.py` | ✅ |
| CQRS 骨架 | `query/` + `command/` + `builders/` | ✅ |

### 2.5 接口层（ditto_interfaces）— 部分缺失 ❌

| 能力 | 模块 | 状态 |
|------|------|------|
| 数据查询 API | `api/routes/` (market/fundamental/capital/macro) | ✅ |
| CLI 策略命令 | `cli/commands/strategy.py` (research/backtest) | ✅ |
| Prefect 数据调度 | `jobs/daily.py` + `jobs/materialization.py` | ✅ |
| 策略管理 API | 无 | ❌ |
| 回测结果 API | 无（portfolio.py 是 stub） | ❌ |
| 信号查询 API | 无 | ❌ |
| 策略运行调度 | 无 | ❌ |

---

## 3. 关键断点

### 断点 1：策略信号 → API 暴露

- `StrategyRunService` + `strategy_run_store` 能持久化运行记录和 artifact
- 信号快照（`SignalSnapshot`）的查询 API 完全不存在
- 需要 `SignalQueryService` + API 路由

### 断点 2：定时调度 → 策略自动运行

- Prefect daily flow 仅覆盖数据摄入
- 需要新增策略运行 Prefect flow/task
- 需与 ingestion T1/T2/T3 调度衔接

---

## 4. V1 架构设计

### 4.1 新增模块

```
新增/修改的模块（M=修改, N=新增）:

packages/app/
  query/
    signal.py              N  ← 信号查询服务
    strategy.py            N  ← 策略管理查询
    backtest.py            N  ← 回测结果查询
  process/
    signal_publisher.py    N  ← 信号发布（持久化+通知）
  command/
    strategy.py            N  ← 策略命令（创建/更新/删除/触发）
    backtest.py            N  ← 回测命令（触发/取消）

interfaces/
  api/routes/
    strategy.py            N  ← 策略管理 API
    signal.py              N  ← 信号查询 API
    backtest.py            N  ← 回测 API
  jobs/
    strategy_daily.py      N  ← 策略每日运行 Prefect flow
```

**不动的内容**：engine、data、analytics 三个核心包完全不动。

### 4.2 API 设计

```
/api/v1/
├── strategies/                        # 策略管理
│   GET    /                           列表（分页、状态过滤）
│   POST   /                           创建策略
│   GET    /{strategy_id}              详情
│   PUT    /{strategy_id}              更新
│   DELETE /{strategy_id}              删除
│   PATCH  /{strategy_id}/status       启停
│   POST   /{strategy_id}/run          手动触发运行（可覆盖参数）
│   GET    /{strategy_id}/signals      历史信号
│   GET    /{strategy_id}/signals/latest  最新信号
│
├── backtests/                         # 回测管理
│   POST   /                           触发回测
│   GET    /                           列表
│   GET    /{run_id}                   详情（状态/进度）
│   GET    /{run_id}/report            绩效报告（NAV/Sharpe/Drawdown）
│   GET    /{run_id}/trades            交易明细
│   GET    /{run_id}/positions         持仓历史
│
├── signals/                           # 全局信号查询
│   GET    /daily?date=YYYY-MM-DD      按日期查所有策略信号
│   GET    /latest                     所有策略最新信号
│
├── jobs/                              # 调度管理
│   GET    /                           任务列表
│   GET    /{job_id}                   任务详情
│
└── data/                              # 已有数据查询 API（✅ 不变）
    ├── market/
    ├── fundamental/
    ├── capital/
    ├── macro/
    └── factors/
```

### 4.3 信号存储设计

混合存储方案：

```
信号明细（Parquet，按策略分目录）：
  signals/
    {strategy_id}/
      YYYY/
        MM/
          signals.parquet
          columns: [date, instrument_id, code, name, weight,
                    signal_value, score, action, run_id]

信号摘要（SQLite，用于快速查询）：
  strategy_signal_summary 表：
    - strategy_id TEXT
    - signal_date DATE
    - position_count INTEGER
    - cash_weight FLOAT
    - run_id TEXT
    - generated_at TIMESTAMP
    索引: (strategy_id, signal_date DESC)
```

### 4.4 信号 JSON 示例

```json
{
  "strategy_id": "etf_rotation_momentum",
  "signal_date": "2026-04-07",
  "positions": [
    {
      "instrument_id": 159915,
      "code": "159915.SZ",
      "name": "创业板ETF",
      "weight": 0.12,
      "signal_value": 0.85,
      "score": 3,
      "action": "BUY"
    },
    {
      "instrument_id": 512000,
      "code": "512000.SH",
      "name": "券商ETF",
      "weight": 0.11,
      "signal_value": 0.78,
      "score": 5,
      "action": "HOLD"
    }
  ],
  "cash_weight": 0.15,
  "run_id": "run_20260407_001",
  "generated_at": "2026-04-07T18:45:00Z"
}
```

### 4.5 定时调度设计

与现有 T0-T3 调度衔接：

```
T0 (08:00)  元数据摄入              ✅ 已有
T1 (18:00)  日线数据摄入              ✅ 已有
T1'(18:30)  因子物化（materialization）✅ 已有
T2 (02:00)  缺口扫描+回填            ✅ 已有
T3 (T1后)   质量检查                ✅ 已有

T4 (T1'后)  策略信号运行              ← 新增
            ├── 等待 T1' 完成（Prefect dependency）
            ├── 获取所有 enabled 策略
            ├── 串行执行 Pipeline → SignalPublisher
            └── 产出信号 → 持久化 → 通知（可选）
```

---

## 5. 垂直切片实施计划

### Slice 1：回测 API

**目标**：通过 API 触发回测、查询回测状态、获取绩效报告

**已有基础**：
- `BacktestService` — 应用层回测编排
- `BacktestReportSerializer` — SQLite 持久化
- CLI `ditto strategy backtest` — 已可用

**新增组件**：

| 组件 | 位置 | 说明 |
|------|------|------|
| `BacktestQueryService` | `app/query/backtest.py` | 查询回测历史、状态、报告 |
| `BacktestCommandService` | `app/command/backtest.py` | 触发/取消回测 |
| `backtest` API 路由 | `interfaces/api/routes/backtest.py` | REST 端点 |
| DI 注册 | `interfaces/registry/` | 新增依赖注入 |

**API 端点**：
```
POST   /api/v1/backtests              触发回测
GET    /api/v1/backtests              列表
GET    /api/v1/backtests/{run_id}     详情
GET    /api/v1/backtests/{run_id}/report   绩效报告
GET    /api/v1/backtests/{run_id}/trades    交易明细
```

**交付标准**：curl 可触发回测并查看绩效报告 JSON

**估算工作量**：~1500 行

---

### Slice 2：策略管理 API

**目标**：通过 API 管理策略定义（创建/读取/更新/删除/启停）

**已有基础**：
- `StrategyCatalogService` — 规格存储
- `StrategySpecStore` — Parquet 持久化
- 4 个策略模板

**新增组件**：

| 组件 | 位置 | 说明 |
|------|------|------|
| `StrategyQueryService` | `app/query/strategy.py` | 策略查询 |
| `StrategyCommandService` | `app/command/strategy.py` | 策略 CRUD + 启停 |
| `strategy` API 路由 | `interfaces/api/routes/strategy.py` | REST 端点 |

**API 端点**：
```
GET    /api/v1/strategies                  列表
POST   /api/v1/strategies                  创建
GET    /api/v1/strategies/{id}             详情
PUT    /api/v1/strategies/{id}             更新
DELETE /api/v1/strategies/{id}             删除
PATCH  /api/v1/strategies/{id}/status      启停
```

**交付标准**：可通过 API 创建 ETF 轮动策略、查看策略列表

**估算工作量**：~800 行

---

### Slice 3：信号 API（核心切片）

**目标**：手动/自动运行策略 → 产出信号 → 通过 API 查询信号和持仓建议

**已有基础**：
- `StrategyRunService` — 运行编排
- `SignalSnapshot` — 信号数据模型
- `TargetPortfolio` — 持仓建议模型
- `StrategyArtifactService` — artifact 持久化

**新增组件**：

| 组件 | 位置 | 说明 |
|------|------|------|
| `SignalPublisher` | `app/process/signal_publisher.py` | 信号持久化 |
| `SignalQueryService` | `app/query/signal.py` | 信号查询 |
| `signal` API 路由 | `interfaces/api/routes/signal.py` | 信号 REST 端点 |
| `strategy` API 扩展 | `interfaces/api/routes/strategy.py` | 增加 POST /{id}/run |

**API 端点**：
```
POST   /api/v1/strategies/{id}/run          手动触发
GET    /api/v1/strategies/{id}/signals      历史信号
GET    /api/v1/strategies/{id}/signals/latest  最新信号
GET    /api/v1/signals/daily?date=YYYY-MM-DD   全策略信号
GET    /api/v1/signals/latest                全策略最新信号
```

**交付标准**：通过 API 运行 ETF 轮动策略 → 获取今日信号 → 看到持仓建议

**估算工作量**：~2000 行

---

### Slice 4：每日自动调度

**目标**：收盘后自动运行所有已启用策略，产出信号

**已有基础**：
- Prefect daily flow — 数据摄入调度
- materialization flow — 因子物化调度

**新增组件**：

| 组件 | 位置 | 说明 |
|------|------|------|
| `strategy_daily` flow | `interfaces/jobs/strategy_daily.py` | 策略运行 flow |
| `strategy_run` task | `interfaces/jobs/tasks/strategy_run.py` | 单策略运行 task |

**调度依赖**：
```
daily_ingestion_flow (T1) → materialization_flow (T1') → strategy_daily_flow (T4)
```

**交付标准**：每日收盘后自动产出所有策略信号，无需人工干预

**估算工作量**：~500 行

---

## 6. 工作量汇总

| 切片 | 估算代码量 | 复杂度 |
|------|-----------|--------|
| Slice 1: 回测 API | ~1500 行 | 中 |
| Slice 2: 策略管理 API | ~800 行 | 低 |
| Slice 3: 信号 API | ~2000 行 | 高 |
| Slice 4: 每日调度 | ~500 行 | 低 |
| **总计** | **~4800 行** | |

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| StrategyInputBundle 构建逻辑复杂 | API 层入口设计困难 | Slice 1 先走通一条路 |
| 信号存储查询性能 | 全策略信号查询慢 | 混合方案：Parquet 明细 + SQLite 摘要 |
| 回测耗时（5-10 年日线） | API 超时 | 异步模式：POST 触发 → 轮询状态 |
| Prefect 调度依赖衔接 | 调度失败 | 利用 Prefect `wait_for` 机制 |
