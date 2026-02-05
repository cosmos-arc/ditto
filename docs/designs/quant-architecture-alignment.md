# Ditto 量化系统架构对标与最终结构（行业参考）

## 1. 目标与取舍
本方案不强制套用 DDD/六边形形式，而是采用**量化行业主流的“引擎中心 + 模块化可插拔 + 事件驱动 + 数据管线”**模式，并兼顾向量化研究的高吞吐需求。

核心取舍：
- **事件驱动是主路径**（回测/实盘一致性）
- **向量化是研究路径**（速度与吞吐优先）
- **DataFrame 是领域语言**（不做刻意对象化）
- **配置与组装只在 Port 层**（唯一入口）
- **插件化扩展点清晰**（数据源/执行/风险/费用/滑点/指标等）

## 2. 行业对标映射（架构功能对齐）
> 注：为避免误导，本表只对齐“功能类型/角色”，不对齐细节实现。

| Ditto 目标模块 | 行业系统对标 | 对标部位 | 说明 |
|---|---|---|---|
| 引擎核心（事件循环/调度/时钟/事件总线） | QuantConnect LEAN / Zipline / Backtrader | Engine / TradingAlgorithm / Cerebro | 事件驱动主循环 |
| 策略接口（OnData/OnOrderEvent） | LEAN QCAlgorithm / Backtrader Strategy | Algorithm/Strategy | 标准策略入口 |
| 数据馈送/订阅 | LEAN DataFeed / Zipline DataPortal | DataFeed/DataPortal | 数据流接入 |
| 交易撮合/成交模型 | LEAN TransactionHandler / FillModel | Fill/Transaction | 交易撮合模拟 |
| 费用/滑点模型 | LEAN Fee/Slippage Model | Fee/Slippage | 交易成本模型 |
| 组合与风险模块 | QSTrader/LEAN Portfolio/Risk | Portfolio/Risk | 组合与风险逻辑 |
| 数据管线（provider/handler/dataset） | Qlib | Provider/Handler/Dataset | 数据处理流水线 |
| 向量化研究 | vectorbt/Qlib pipeline | Vectorized Backtest | 研究与快速评估 |
| 指标定义（catalog） | OTel Semantic Conventions 思路 | Metrics Catalog | 统一指标定义 |
| 监控实现（OTel/日志） | LEAN logging/monitoring | Observability | 观测落地实现 |

## 3. 最终目录结构（终极目标态）

```
ditto/
├─ apps/
│  ├─ port/                          # 组合根 + 配置加载 + DI
│  │  ├─ src/ditto_port/
│  │  │  ├─ bootstrap/               # 启动/关闭流程
│  │  │  ├─ config/                  # 唯一配置入口
│  │  │  ├─ cli/                     # CLI 入口
│  │  │  ├─ api/                     # API 入口
│  │  │  ├─ jobs/                    # 事件驱动任务/调度
│  │  │  ├─ eventbus/                # 事件总线适配器
│  │  │  └─ wiring/                  # DI 注册
│  │  └─ tests/
│  └─ web/
│
├─ packages/
│  ├─ engine/                        # 事件驱动核心引擎
│  │  ├─ core/                       # loop/clock/scheduler/bus
│  │  ├─ algo/                       # 策略接口
│  │  ├─ handlers/                   # datafeed/transaction/result
│  │  ├─ models/                     # fee/slippage/fill/margin
│  │  └─ runtime/                    # backtest/live runtime
│  │
│  ├─ data/                          # 数据管线（研究与实盘共用）
│  │  ├─ ingestion/
│  │  ├─ providers/                  # 数据源适配器
│  │  ├─ handlers/                   # 处理器/特征/清洗
│  │  ├─ datasets/                   # dataset registry
│  │  └─ store/                      # parquet/sqlite 等
│  │
│  ├─ research/                      # 向量化研究路径
│  │  ├─ pipeline/
│  │  ├─ experiments/
│  │  └─ backtest_vec/
│  │
│  ├─ trading/                       # 交易与组合逻辑
│  │  ├─ portfolio/
│  │  ├─ risk/
│  │  ├─ execution/
│  │  └─ broker_ports/
│  │
│  ├─ infra/                          # 基础设施整合包（Foundation+Infra）
│  │  ├─ common/                      # 纯净基础能力
│  │  │  ├─ util/
│  │  │  ├─ cache/
│  │  │  ├─ concurrency/
│  │  │  └─ time/
│  │  ├─ observability/               # OTel/Loguru 实现
│  │  └─ adapters/                    # notification/http/db/messaging
│  │
│  ├─ telemetry/                      # 指标 catalog（纯定义）
│  │  └─ metrics_catalog.py
│  │
│  └─ shared/                         # 极小共享类型（谨慎）
│
├─ config/                            # 权威配置（仅 Port 读取）
│  ├─ development/
│  ├─ testing/
│  └─ production/
│
└─ docs/
```

## 4. 关键模块说明（量化友好）

### 4.1 Engine（事件驱动主引擎）
- 处理行情事件、订单事件、时间事件
- 插件化 handlers（datafeed/transaction/result）
- 适配实盘与回测 runtime

### 4.2 Data（数据管线）
- 数据源 provider / handler / dataset 的标准流水线
- 与研究/实盘共用
- 支持数据校验、血缘、可重复构建

### 4.3 Research（向量化研究）
- 高吞吐实验与批量回测
- 不强求完全一致交易仿真

### 4.4 Trading（组合与风险）
- 组合管理、风险控制、执行策略
- 可插拔风险模型与执行模型

### 4.5 Infra / Telemetry
- Infra 只做“能力与适配”
- Telemetry 仅定义指标 catalog，不包含 OTel 实现

## 5. 依赖规则（强约束）
- **配置只允许在 apps/port/config 读取**
- **Domain/Engine/Trading 不允许直接读取环境变量**
- **Infra.adapters 不允许反向依赖 Engine/Data/Research**
- **Telemetry 仅是规范层，不依赖 OTel**

## 6. 事件驱动与向量化双路径
事件驱动与向量化并存的规则：
- **实盘/严格仿真**：走事件驱动引擎（订单/成交/撮合/费用/滑点都可插拔）
- **研究/批量评估**：走向量化 pipeline（速度优先，允许近似）
- **同一份数据管线**：数据清洗与特征计算可共用，避免重复实现

## 7. 插件化扩展点（必须显式）
建议统一插件接口注册位置：
- 数据源 Provider（Tushare/TDX/自研）
- 数据处理 Handler（清洗/对齐/特征）
- 交易模型（Fee/Slippage/Fill/Margin）
- 交易通道（Broker/Execution）
- 观测输出（日志/指标/追踪）

## 8. 验收标准
- 核心引擎不依赖外部系统（IO/HTTP/DB）
- 配置只有一个入口（apps/port/config）
- DataFrame 作为领域语言在核心计算中可直接使用
- 指标定义唯一来源（telemetry catalog）
