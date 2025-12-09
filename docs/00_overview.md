# Ditto 系统设计文档

**版本：v2.0 Final（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-08**

---

## 1. 设计目标与约束

本系统设计文档用于回答：

> "Ditto 的模块拆分是什么？数据、引擎、API、UI 之间如何协作？关键流程怎么走？"

### 1.1 主要目标

1. 固化一套**清晰、可扩展**的架构骨架，支持 Phase 0–3 的渐进演进
2. 让"半年后的你"和 LLM 工具都能看懂、接得上
3. 降低"改一点点策略 → 牵一发动全身"的风险
4. **组合层作为一等公民**，即使当前只有一个策略

### 1.2 关键约束

- 单机 Windows 环境，禁止强依赖云基础设施
- 日线数据为主，不引入分钟级数据
- 当期仅支持 ETF 行业轮动，但抽象要支持未来扩展
- **数据必须支持 PIT（Point-in-Time）查询**
- **回测引擎必须支持涨跌停过滤**

---

## 2. 上下文视图（Context View）

```
┌──────────────────────────────────────────────────────────────┐
│                          用户（你）                          │
│  - 策略研究、回测                                            │
│  - 查看调仓建议                                              │
│  - 手工在券商交易系统下单                                    │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ 浏览器 (HTTP)
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                        Ditto Web UI                          │
│   Next.js 前端，展示 Regime / 回测 / 调仓 / 风控等           │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ HTTP/WS
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                        DittoServer (API)                     │
│   FastAPI：                                                  │
│   - 调用 Application Services                                │
│   - 编排引擎执行                                             │
│   - 内置 APScheduler 调度                                    │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ 函数调用
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                    Application Services Layer                │
│   RegimeSvc / RotationSvc / BacktestSvc / RiskSvc / DataSvc  │
│   PortfolioSvc / FactorHealthSvc / HeartbeatSvc              │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ 调用 Core Engine + Data Access
                             ▼
┌──────────────────────────────────────────────────────────────┐
│   Core Engines & Data Access (Regime/Factor/Rotation/...)    │
│   - DuckDB & SQLite 持久化                                   │
│   - PIT 数据查询                                             │
│   - 复权价动态计算                                           │
└──────────────────────────────────────────────────────────────┘
                             ▲
                             │ SDK/HTTP 请求
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                         外部系统                             │
│  - Tushare Pro / AkShare（数据）                             │
│  - 券商终端 / MiniQMT (Phase 2+ 实盘)                        │
│  - Telagram/钉钉（心跳通知）                                     │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 逻辑视图（Logical View）

### 3.1 按层划分

**1. Core Domain（核心域）**

- 因子、Regime、轮动、回测、风控等模型与算法
- **组合与策略生命周期管理**

**2. Application Services（应用服务）**

- 面向"用例"的编排逻辑
- **心跳服务**：证明系统还活着

**3. API Layer（适配层）**

- HTTP / REST / WS 封装与序列化

**4. Web UI Layer（表现层）**

- 前端展示与交互

**5. Infrastructure（基础设施层）**

- DuckDB/SQLite 访问层
- 外部数据源适配
- **作业调度（APScheduler）**与配置加载

### 3.2 模块与职责（按目录）

```
apps/
  server/
    src/
      api/           # HTTP 接口（FastAPI Router）
      services/      # Application Services
      models/        # API 层 DTO / Pydantic 模型
      scheduler/     # APScheduler 作业调度
      main.py        # 启动入口

  web/
    src/
      app/           # Next.js 页面路由
      components/    # UI 组件
      stores/        # Zustand 全局状态
      types/         # 与后端共享的 TS 类型

packages/
  core/
    src/
      data/          # DataService / DuckDBAdapter / SQLiteAdapter
      indicators/    # technical_indicators 技术指标MA、EMA、RSI等
      factor/        # factor_analyzer 
      engine/        # Regime/Factor/Backtest/Risk 引擎
      strategy/      # 策略抽象 & ETF 行业轮动策略实现
      portfolio/     # 组合管理 & 多策略协调
      config/        # 配置模型（Pydantic Settings）
      util/          # 公共工具

  foundation/
    src/
      types/           # 前后端共享 schema
      contracts/       # Data Contract 定义
```

---

## 4. 领域模型详细设计

### 4.1 核心实体

```python
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

class LifecycleState(Enum):
    """策略生命周期状态"""
    RESEARCH = "research"           # 研究阶段
    PAPER = "paper"                 # 模拟盘
    LIVE_SMALL = "live_small"       # 小规模实盘
    LIVE_FULL = "live_full"         # 全量实盘
    DEPRECATED = "deprecated"       # 已下线

class InstrumentType(Enum):
    """金融工具类型"""
    ETF = "ETF"
    INDEX = "INDEX"
    STOCK = "STOCK"
    CONVERTIBLE_BOND = "CB"

@dataclass
class Instrument:
    """金融工具"""
    symbol: str
    name: str
    instrument_type: InstrumentType
    list_date: date
    delist_date: Optional[date]
    is_active: bool
    
@dataclass
class StrategyInstance:
    """策略实例"""
    strategy_id: str
    name: str
    strategy_type: str
    lifecycle_state: LifecycleState
    risk_budget_pct: float          # 风险预算百分比
    config: dict
    created_at: date
    last_updated: date
    
    def can_trade(self) -> bool:
        """是否可以交易"""
        return self.lifecycle_state in (
            LifecycleState.PAPER,
            LifecycleState.LIVE_SMALL,
            LifecycleState.LIVE_FULL
        )

@dataclass
class Portfolio:
    """投资组合"""
    portfolio_id: str
    name: str
    strategies: list[StrategyInstance]
    total_capital: float
    risk_budget: "RiskBudget"
    
@dataclass
class RiskBudget:
    """风险预算"""
    total_equity_min: float
    total_equity_max: float
    single_position_max: float
    target_volatility: float
    max_drawdown_hard_limit: float

@dataclass
class Signal:
    """交易信号"""
    trade_date: date
    strategy_id: str
    symbol: str
    signal_type: str      # 'BUY' / 'SELL' / 'HOLD'
    signal_strength: float
    reason: str

@dataclass
class TargetPosition:
    """目标持仓"""
    trade_date: date
    strategy_id: str
    symbol: str
    target_weight: float
    current_weight: float
    action: str           # 'INCREASE' / 'DECREASE' / 'HOLD' / 'NEW' / 'EXIT'

@dataclass
class Order:
    """订单"""
    order_id: str
    trade_date: date
    symbol: str
    direction: str        # 'BUY' / 'SELL'
    quantity: int
    price: Optional[float]
    order_type: str       # 'MARKET' / 'LIMIT'
    status: str           # 'PENDING' / 'FILLED' / 'PARTIAL' / 'CANCELLED'
    strategy_id: str

@dataclass
class Position:
    """持仓"""
    symbol: str
    quantity: int
    cost_basis: float
    market_value: float
    unrealized_pnl: float
    weight: float
```

### 4.2 实体关系图

```
Portfolio (1) ────────────── (N) StrategyInstance
    │                              │
    │                              │ generates
    │                              ▼
    │                         Signal (N)
    │                              │
    │                              │ aggregates to
    │                              ▼
    │                      TargetPosition (N)
    │                              │
    │ risk check                   │ generates
    ▼                              ▼
RiskBudget ◄──────────────── Order (N)
                                   │
                                   │ executes to
                                   ▼
                              Position (N)
```

---

## 5. 关键模块设计

### 5.1 数据访问模块（Data Layer）

**职责**：

- 为上层提供统一的数据访问接口
- 屏蔽 DuckDB/SQLite 实现细节
- **支持 PIT（Point-in-Time）查询**
- **动态计算复权价**
- 负责数据缓存与简单聚合

**核心组件**：

```python
class DataService:
    """数据服务 - 统一数据访问接口"""
    
    def __init__(self, duckdb_path: str, sqlite_path: str):
        self.duckdb = DuckDBAdapter(duckdb_path)
        self.sqlite = SQLiteAdapter(sqlite_path)
    
    # === K线数据（动态复权）===
    def get_kline(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        adjust: str = "hfq"  # 'hfq' / 'qfq' / 'none'
    ) -> pl.DataFrame:
        """获取K线数据，运行时动态计算复权价"""
        raw = self.duckdb.query("""
            SELECT k.*, a.adj_factor
            FROM etf_kline_daily k
            LEFT JOIN etf_adj_factor a 
              ON k.symbol = a.symbol AND k.trade_date = a.trade_date
            WHERE k.symbol = ? AND k.trade_date BETWEEN ? AND ?
        """, [symbol, start_date, end_date])
        
        if adjust == "none":
            return raw
        return self._apply_adjustment(raw, adjust)
    
    # === 因子数据（PIT 查询）===
    def get_factors_pit(
        self,
        symbols: list[str],
        trade_date: date,
        as_of_date: date
    ) -> pl.DataFrame:
        """获取因子数据（Point-in-Time 安全）
        
        Args:
            symbols: 标的列表
            trade_date: 交易日期
            as_of_date: 数据可知日期（通常等于 trade_date）
        """
        return self.duckdb.query("""
            SELECT * FROM etf_factor_daily
            WHERE symbol IN (?)
              AND trade_date = ?
              AND knowledge_date <= ?
        """, [symbols, trade_date, as_of_date])
    
    # === Regime 数据 ===
    def get_regime(self, trade_date: date) -> dict:
        """获取指定日期的 Regime"""
        pass
    
    # === 涨跌停状态 ===
    def get_limit_status(
        self,
        symbol: str,
        trade_date: date
    ) -> str:
        """获取涨跌停状态
        
        Returns:
            'NORMAL' / 'LIMIT_UP' / 'LIMIT_DOWN' / 'SUSPENDED'
        """
        row = self.duckdb.query_one("""
            SELECT high, low, close, prev_close, volume, status
            FROM etf_kline_daily
            WHERE symbol = ? AND trade_date = ?
        """, [symbol, trade_date])
        
        if row["status"] == "SUSPENDED" or row["volume"] == 0:
            return "SUSPENDED"
        if row["high"] == row["low"] == row["close"]:
            change_pct = (row["close"] - row["prev_close"]) / row["prev_close"]
            if change_pct > 0.09:
                return "LIMIT_UP"
            elif change_pct < -0.09:
                return "LIMIT_DOWN"
        return "NORMAL"
```

### 5.2 引擎模块（Engine Layer）

详细见 `03_engine_design.md`，这里只列模块：

- **RegimeEngine**：基于沪深 300 计算 Regime + **自适应阈值**
- **FactorEngine**：实现若干 Factor 类 + **健康度监控**
- **RotationEngine**：综合得分与 TopN
- **BacktestEngineFast** & **BacktestEngineProd**：+ **涨跌停过滤**
- **RiskEngine**：风险指标 + **回撤速度检测** + Kill Switch
- **PortfolioEngine**：多策略协调（Phase 2+）

这些引擎不直接访问数据库，而是依赖 DataService，以保证可测试性与可替换性。

### 5.3 应用服务模块（Application Services）

以"用例"为中心划分：

#### 5.3.1 RegimeSvc

```python
class RegimeSvc:
    """Regime 服务"""
    
    def get_current_regime(self) -> RegimeResult:
        """获取当前 Regime"""
        pass
    
    def get_regime_history(
        self,
        start_date: date,
        end_date: date
    ) -> list[RegimeResult]:
        """获取 Regime 历史"""
        pass
    
    def recalc_regime(self, trade_date: date) -> None:
        """重新计算指定日期的 Regime"""
        pass
```

#### 5.3.2 RotationSvc

```python
class RotationSvc:
    """行业轮动服务"""
    
    def get_rotation_scores(
        self,
        trade_date: date
    ) -> list[RotationScore]:
        """获取轮动得分"""
        pass
    
    def generate_rebalance_plan(
        self,
        trade_date: date,
        current_positions: list[Position]
    ) -> RebalancePlan:
        """生成调仓计划"""
        # 1. 获取 Regime
        regime = self.regime_svc.get_current_regime()
        
        # 2. 获取轮动得分
        scores = self.get_rotation_scores(trade_date)
        
        # 3. 选择 TopN
        top_n = self._select_top_n(scores, regime)
        
        # 4. 计算目标权重
        target_weights = self._calc_target_weights(top_n, regime)
        
        # 5. Pre-Trade 风控检查
        risk_decision = self.risk_svc.pre_trade_check(
            target_weights, 
            current_positions
        )
        if risk_decision.action == "BLOCK":
            raise RiskBlockedException(risk_decision.reason)
        
        # 6. 生成调仓计划
        plan = self._generate_plan(
            target_weights,
            current_positions,
            trade_date
        )
        
        return plan
```

#### 5.3.3 BacktestSvc

```python
class BacktestSvc:
    """回测服务"""
    
    def run_fast(self, config: BacktestConfig) -> BacktestResult:
        """运行快速回测（向量化）"""
        pass
    
    def run_production(self, config: BacktestConfig) -> BacktestResult:
        """运行生产回测（事件驱动）"""
        pass
    
    def run_alignment_test(
        self,
        config: BacktestConfig
    ) -> AlignmentReport:
        """运行对齐测试"""
        fast_result = self.run_fast(config)
        prod_result = self.run_production(config)
        
        return AlignmentReport(
            return_diff=abs(fast_result.total_return - prod_result.total_return),
            drawdown_diff=abs(fast_result.max_drawdown - prod_result.max_drawdown),
            rebalance_count_match=(
                fast_result.rebalance_count == prod_result.rebalance_count
            ),
            daily_holdings_match=self._compare_daily_holdings(
                fast_result, prod_result
            ),
            passed=self._check_alignment_criteria(fast_result, prod_result)
        )
```

#### 5.3.4 RiskSvc

```python
class RiskSvc:
    """风控服务"""
    
    def get_current_metrics(self) -> RiskMetrics:
        """获取当前风险指标"""
        pass
    
    def check_kill_switch(self) -> KillSwitchStatus:
        """检查 Kill Switch 状态"""
        pass
    
    def pre_trade_check(
        self,
        target_weights: dict[str, float],
        current_positions: list[Position]
    ) -> RiskDecision:
        """下单前风控检查"""
        pass
    
    def post_trade_check(self) -> RiskDecision:
        """盘后风控检查"""
        pass
```

#### 5.3.5 HeartbeatSvc

```python
class HeartbeatSvc:
    """心跳服务 - 证明系统还活着"""
    
    def __init__(self, config: HeartbeatConfig):
        self.config = config
        self.targets = config.targets  # Telagram/钉钉/邮件
    
    async def send_heartbeat(self) -> None:
        """发送心跳"""
        status = self._collect_system_status()
        
        for target in self.targets:
            try:
                await target.send(
                    message=f"Ditto Heartbeat: {status.summary}",
                    details=status.to_dict()
                )
            except Exception as e:
                logger.error("heartbeat_send_failed", target=target.name, error=str(e))
    
    def _collect_system_status(self) -> SystemStatus:
        """收集系统状态"""
        return SystemStatus(
            timestamp=datetime.now(),
            data_latest_date=self._get_latest_data_date(),
            kill_switch_active=self._check_kill_switch(),
            last_error=self._get_last_error(),
            summary="OK" if self._is_healthy() else "DEGRADED"
        )
```

#### 5.3.6 FactorHealthSvc

```python
class FactorHealthSvc:
    """因子健康度服务"""
    
    def get_factor_health(self, factor_name: str) -> FactorHealthMetrics:
        """获取单个因子健康度"""
        pass
    
    def get_all_factor_health(self) -> list[FactorHealthMetrics]:
        """获取所有因子健康度"""
        pass
    
    def check_factor_degradation(self) -> list[FactorAlert]:
        """检查因子退化"""
        alerts = []
        for factor in self.active_factors:
            health = self.get_factor_health(factor)
            if health.ic_mean_12m < 0:
                alerts.append(FactorAlert(
                    factor_name=factor,
                    severity="CRITICAL",
                    message=f"Factor {factor} IC negative for 12M",
                    suggested_action="REMOVE_FROM_PRODUCTION"
                ))
            elif health.ic_mean_6m < 0.02:
                alerts.append(FactorAlert(
                    factor_name=factor,
                    severity="WARNING",
                    message=f"Factor {factor} IC below threshold",
                    suggested_action="REDUCE_WEIGHT_50PCT"
                ))
        return alerts
```

---

## 6. 关键流程设计（Sequence）

### 6.1 每日数据更新流程（T+1）

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│Scheduler│     │ DataSvc │     │ Tushare │     │ AkShare │     │ DuckDB  │
└────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘
     │               │               │               │               │
     │ trigger       │               │               │               │
     │──────────────>│               │               │               │
     │               │               │               │               │
     │               │ fetch_daily   │               │               │
     │               │──────────────>│               │               │
     │               │               │               │               │
     │               │ raw_data      │               │               │
     │               │<──────────────│               │               │
     │               │               │               │               │
     │               │ cross_validate│               │               │
     │               │───────────────────────────────>│               │
     │               │               │               │               │
     │               │ validation_result              │               │
     │               │<───────────────────────────────│               │
     │               │               │               │               │
     │               │ if price_diff > 0.2%: mark_suspicious          │
     │               │               │               │               │
     │               │ sanity_check + save (不复权价 + 复权因子)      │
     │               │───────────────────────────────────────────────>│
     │               │               │               │               │
     │               │ calc_regime   │               │               │
     │               │───────────────────────────────────────────────>│
     │               │               │               │               │
     │               │ calc_factors (with knowledge_date)             │
     │               │───────────────────────────────────────────────>│
     │               │               │               │               │
     │               │ calc_rotation_scores                           │
     │               │───────────────────────────────────────────────>│
     │               │               │               │               │
     │ send_heartbeat│               │               │               │
     │<──────────────│               │               │               │
     │               │               │               │               │
```

### 6.2 生成调仓计划流程

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  User   │     │   API   │     │RotatSvc │     │ RiskSvc │     │ SQLite  │
└────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘
     │               │               │               │               │
     │ POST /rotation/generate_plan  │               │               │
     │──────────────>│               │               │               │
     │               │               │               │               │
     │               │ generate_plan │               │               │
     │               │──────────────>│               │               │
     │               │               │               │               │
     │               │               │ get_regime + get_scores        │
     │               │               │───────────────────────────────>│
     │               │               │               │               │
     │               │               │ calc_target_weights            │
     │               │               │               │               │
     │               │               │ pre_trade_check                │
     │               │               │──────────────>│               │
     │               │               │               │               │
     │               │               │ RiskDecision  │               │
     │               │               │<──────────────│               │
     │               │               │               │               │
     │               │               │ if BLOCK: raise exception      │
     │               │               │               │               │
     │               │               │ save_plan     │               │
     │               │               │───────────────────────────────>│
     │               │               │               │               │
     │               │ plan_id + details             │               │
     │               │<──────────────│               │               │
     │               │               │               │               │
     │ RebalancePlan │               │               │               │
     │<──────────────│               │               │               │
```

### 6.3 回测流程（含涨跌停过滤）

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  User   │     │BacktSvc │     │FastBT   │     │DataSvc  │     │RiskEng  │
└────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘
     │               │               │               │               │
     │ run_backtest  │               │               │               │
     │──────────────>│               │               │               │
     │               │               │               │               │
     │               │ load_data     │               │               │
     │               │──────────────────────────────>│               │
     │               │               │               │               │
     │               │ kline + factors + regime + limit_status        │
     │               │<──────────────────────────────│               │
     │               │               │               │               │
     │               │ run           │               │               │
     │               │──────────────>│               │               │
     │               │               │               │               │
     │               │               │ for each rebalance_date:       │
     │               │               │   calc_signals                 │
     │               │               │   filter_limit_locked          │
     │               │               │   apply_cost_model             │
     │               │               │   update_positions             │
     │               │               │   check_risk                   │
     │               │               │──────────────────────────────>│
     │               │               │               │               │
     │               │ BacktestResult│               │               │
     │               │<──────────────│               │               │
     │               │               │               │               │
     │ result        │               │               │               │
     │<──────────────│               │               │               │
```

### 6.4 Kill Switch 触发流程（含回撤速度）

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│RiskSvc  │     │RiskEng  │     │KillSwSvc│     │ SQLite  │
└────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘
     │               │               │               │
     │ post_trade_check              │               │
     │──────────────>│               │               │
     │               │               │               │
     │               │ calc_current_drawdown         │
     │               │ calc_drawdown_velocity        │
     │               │               │               │
     │               │ if 3d_drawdown > 5%:          │
     │               │   trigger Level1 (速度触发)   │
     │               │──────────────>│               │
     │               │               │               │
     │               │ elif drawdown >= 10%:         │
     │               │   trigger Level1 (绝对触发)   │
     │               │──────────────>│               │
     │               │               │               │
     │               │ elif drawdown >= 18%:         │
     │               │   trigger Level2              │
     │               │──────────────>│               │
     │               │               │               │
     │               │ elif drawdown >= 20%:         │
     │               │   trigger Level3              │
     │               │──────────────>│               │
     │               │               │               │
     │               │               │ update_state  │
     │               │               │──────────────>│
     │               │               │               │
     │               │               │ log_event     │
     │               │               │──────────────>│
     │               │               │               │
     │ RiskDecision  │               │               │
     │<──────────────│               │               │
```

---

## 7. BrokerAdapter 接口（Phase 2+ 预留）

```python
from abc import ABC, abstractmethod

class BrokerAdapter(ABC):
    """券商适配器接口"""
    
    @abstractmethod
    async def connect(self) -> bool:
        """连接券商"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接"""
        pass
    
    @abstractmethod
    async def query_positions(self) -> list[Position]:
        """查询持仓（Source of Truth）"""
        pass
    
    @abstractmethod
    async def query_account(self) -> AccountInfo:
        """查询账户信息"""
        pass
    
    @abstractmethod
    async def send_order(self, order: Order) -> OrderResult:
        """发送订单"""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        pass
    
    @abstractmethod
    async def query_order(self, order_id: str) -> OrderStatus:
        """查询订单状态"""
        pass


class MiniQMTAdapter(BrokerAdapter):
    """MiniQMT 适配器（Phase 2+ 实现）"""
    pass
```

---

## 8. 质量属性与架构决策的对应关系

| 质量属性 | 实现方式 |
|----------|----------|
| 性能 | DuckDB 向量化查询 + FastBacktester；避免复杂分布式系统 |
| 可用性 | 单机 + 定期备份 + 简单恢复流程 + **心跳监控** |
| 可维护性 | 清晰的分层与命名；core 与 apps 分离；文档齐全 |
| 可测试性 | 引擎与 DataService 隔离；**严格对齐测试**；Fast/Prod 对齐 |
| 可扩展性 | Strategy/Factor 抽象；**Portfolio 层预留**；Regime/Rotation 不绑定具体资产类型 |
| 数据完整性 | **PIT 查询**；**复权分离存储**；数据版本化 |
| 安全性 | 本地文件 + OS 权限；无远程访问；实盘前不保存交易账号密码 |

---

## 9. 未来扩展点（Phase 2–3 升级路径）

### 9.1 策略层扩展

- 新增 SelectionEngine、ConvertibleBondEngine
- 多策略组合层（PortfolioEngine 启用）
- **因子墓地**：记录失效因子，检测风格切换

### 9.2 实盘层扩展

- 新增 TradingSvc + BrokerAdapter（MiniQMT 等）
- **券商持仓为 Source of Truth**
- 增加订单状态同步、成交回报落地逻辑

### 9.3 ML 层扩展

- 增加 MLModelEngine 用于因子权重学习
- 在 BacktestSvc 中引入"训练期/验证期"划分
- **数据版本化**支持 ML 实验可复现

### 9.4 多基准评估

当策略包含可转债和红利时，Benchmark 应该是：

```
Composite Benchmark = 0.6 × 沪深300 + 0.2 × 中证红利 + 0.2 × 中证转债
```

---

*本系统设计文档与 `02_data_design.md`、`03_engine_design.md`、`04_deployment_topology.md` 紧密配合，共同构成 Ditto 的技术架构基础。*
