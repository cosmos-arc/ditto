---
paths: packages/core/src/ditto_core/{risk,execution,portfolio}/**/*.py
---

# 风险管理规范

> 保护本金，控制回撤，确保系统稳定运行

## 核心原则

1. **风控优先**：任何交易必须先通过风控检查
2. **同步执行**：风控检查不可异步跳过
3. **自动化**：Kill Switch 自动触发，无需人工干预
4. **可配置**：所有阈值可配置，禁止硬编码

## Kill Switch 三级机制

### 级别定义

| 级别 | 触发条件 | 动作 | 恢复条件 |
|------|----------|------|----------|
| **L0** | 正常 | 正常交易 | - |
| **L1** | 回撤 ≥ 5% | 减仓 50%，告警 | 回撤恢复 < 3% |
| **L2** | 回撤 ≥ 10% | 清仓，停止新开仓 | 人工确认 |
| **L3** | 回撤 ≥ 15% 或系统异常 | 系统停机 | 人工干预 |

### 回撤计算

```python
from dataclasses import dataclass
from datetime import date


@dataclass
class DrawdownState:
    """回撤状态"""
    peak_value: float           # 历史峰值
    current_value: float        # 当前净值
    drawdown: float             # 当前回撤 (0~1)
    drawdown_start: date | None # 回撤开始日期

    @classmethod
    def calculate(
        cls,
        equity_curve: list[float],
        dates: list[date],
    ) -> "DrawdownState":
        """计算当前回撤状态"""
        peak = equity_curve[0]
        peak_idx = 0

        for i, value in enumerate(equity_curve):
            if value > peak:
                peak = value
                peak_idx = i

        current = equity_curve[-1]
        drawdown = (peak - current) / peak if peak > 0 else 0

        return cls(
            peak_value=peak,
            current_value=current,
            drawdown=drawdown,
            drawdown_start=dates[peak_idx] if drawdown > 0 else None,
        )
```

### Kill Switch 实现

```python
from enum import IntEnum
from typing import Protocol


class KillSwitchLevel(IntEnum):
    NORMAL = 0
    WARNING = 1      # L1: 减仓
    CRITICAL = 2     # L2: 清仓
    EMERGENCY = 3    # L3: 停机


@dataclass
class KillSwitchConfig:
    """Kill Switch 配置"""
    l1_threshold: float = 0.05   # 5%
    l2_threshold: float = 0.10   # 10%
    l3_threshold: float = 0.15   # 15%
    l1_recovery: float = 0.03    # 3% 恢复阈值
    l1_reduce_ratio: float = 0.5 # L1 减仓比例


class KillSwitchChecker:
    """Kill Switch 检查器"""

    def __init__(self, config: KillSwitchConfig):
        self._config = config
        self._current_level = KillSwitchLevel.NORMAL

    def check(self, drawdown: float) -> KillSwitchLevel:
        """检查并更新 Kill Switch 级别"""

        # 升级检查
        if drawdown >= self._config.l3_threshold:
            new_level = KillSwitchLevel.EMERGENCY
        elif drawdown >= self._config.l2_threshold:
            new_level = KillSwitchLevel.CRITICAL
        elif drawdown >= self._config.l1_threshold:
            new_level = KillSwitchLevel.WARNING
        else:
            # 降级检查（只有 L1 可自动恢复）
            if (
                self._current_level == KillSwitchLevel.WARNING
                and drawdown < self._config.l1_recovery
            ):
                new_level = KillSwitchLevel.NORMAL
            else:
                new_level = self._current_level

        # 级别只能升不能自动降（除 L1）
        if new_level > self._current_level:
            self._current_level = new_level
        elif new_level == KillSwitchLevel.NORMAL:
            self._current_level = new_level

        return self._current_level

    def force_reset(self, level: KillSwitchLevel = KillSwitchLevel.NORMAL) -> None:
        """人工重置（需要审计日志）"""
        self._current_level = level
```

### 集成到执行流程

```python
class ExecutionService:
    """交易执行服务"""

    def __init__(
        self,
        kill_switch: KillSwitchChecker,
        portfolio: PortfolioManager,
    ):
        self._kill_switch = kill_switch
        self._portfolio = portfolio

    def execute_signals(self, signals: list[Signal]) -> ExecutionResult:
        """执行交易信号"""

        # 1. 检查 Kill Switch（必须同步）
        drawdown = self._portfolio.current_drawdown
        level = self._kill_switch.check(drawdown)

        # 2. 根据级别处理
        if level == KillSwitchLevel.EMERGENCY:
            raise KillSwitchError(level=3, reason="Emergency stop triggered")

        if level == KillSwitchLevel.CRITICAL:
            # 清仓，不执行新信号
            return self._liquidate_all()

        if level == KillSwitchLevel.WARNING:
            # 减仓 50%
            signals = self._reduce_signals(signals, ratio=0.5)

        # 3. 执行信号
        return self._execute(signals)

    def _execute(self, signals: list[Signal]) -> ExecutionResult:
        """实际执行（风控已通过）"""
        # ...
```

## 持仓限制

### 限制规则

| 维度 | 限制 | 说明 |
|------|------|------|
| 单 ETF 持仓 | ≤ 30% | 分散风险 |
| 最大持仓数 | 5-10 | 可配置 |
| 单日换手 | ≤ 50% | 控制交易成本 |
| 现金最低 | ≥ 5% | 保留流动性 |

### 实现

```python
@dataclass
class PositionLimits:
    """持仓限制配置"""
    max_single_weight: float = 0.30      # 单一资产最大权重
    max_positions: int = 5               # 最大持仓数量
    max_daily_turnover: float = 0.50     # 最大日换手率
    min_cash_ratio: float = 0.05         # 最小现金比例


class PositionChecker:
    """持仓检查器"""

    def __init__(self, limits: PositionLimits):
        self._limits = limits

    def check_order(
        self,
        order: Order,
        current_portfolio: Portfolio,
    ) -> CheckResult:
        """检查订单是否符合限制"""
        errors = []

        # 检查单一资产权重
        new_weight = self._calc_new_weight(order, current_portfolio)
        if new_weight > self._limits.max_single_weight:
            errors.append(
                f"Single position weight {new_weight:.1%} exceeds limit "
                f"{self._limits.max_single_weight:.1%}"
            )

        # 检查持仓数量
        if order.direction == "buy" and order.code not in current_portfolio.positions:
            if len(current_portfolio.positions) >= self._limits.max_positions:
                errors.append(
                    f"Position count {len(current_portfolio.positions)} "
                    f"would exceed limit {self._limits.max_positions}"
                )

        # 检查换手率
        turnover = self._calc_turnover(order, current_portfolio)
        if turnover > self._limits.max_daily_turnover:
            errors.append(
                f"Daily turnover {turnover:.1%} exceeds limit "
                f"{self._limits.max_daily_turnover:.1%}"
            )

        return CheckResult(passed=len(errors) == 0, errors=errors)
```

## 速度检测

### 异常波动检测

```python
@dataclass
class VelocityConfig:
    """速度检测配置"""
    hourly_drawdown_limit: float = 0.02   # 小时级回撤限制
    daily_drawdown_limit: float = 0.05    # 日内回撤限制
    check_interval_seconds: int = 60       # 检查间隔


class VelocityChecker:
    """速度检测器：检测异常快速下跌"""

    def __init__(self, config: VelocityConfig):
        self._config = config
        self._value_history: list[tuple[datetime, float]] = []

    def record(self, timestamp: datetime, value: float) -> None:
        """记录净值"""
        self._value_history.append((timestamp, value))
        # 只保留最近 24 小时
        cutoff = timestamp - timedelta(hours=24)
        self._value_history = [
            (t, v) for t, v in self._value_history if t > cutoff
        ]

    def check(self) -> VelocityAlert | None:
        """检查是否触发速度告警"""
        if len(self._value_history) < 2:
            return None

        current_time, current_value = self._value_history[-1]

        # 检查小时级回撤
        hour_ago = current_time - timedelta(hours=1)
        hourly_values = [v for t, v in self._value_history if t >= hour_ago]
        if hourly_values:
            hourly_peak = max(hourly_values)
            hourly_dd = (hourly_peak - current_value) / hourly_peak
            if hourly_dd > self._config.hourly_drawdown_limit:
                return VelocityAlert(
                    type="hourly",
                    drawdown=hourly_dd,
                    message=f"Hourly drawdown {hourly_dd:.2%} exceeds limit",
                )

        return None
```

## 风控模块测试要求

### 覆盖率要求

**风险管理模块必须 100% 测试覆盖。**

### 必须测试的场景

```python
class TestKillSwitch:
    """Kill Switch 测试"""

    def test_l1_trigger_at_threshold(self):
        """精确在 L1 阈值触发"""
        checker = KillSwitchChecker(KillSwitchConfig(l1_threshold=0.05))
        assert checker.check(0.05) == KillSwitchLevel.WARNING

    def test_l1_not_trigger_below_threshold(self):
        """低于 L1 阈值不触发"""
        checker = KillSwitchChecker(KillSwitchConfig(l1_threshold=0.05))
        assert checker.check(0.0499) == KillSwitchLevel.NORMAL

    def test_level_upgrade_l1_to_l2(self):
        """从 L1 升级到 L2"""
        checker = KillSwitchChecker(KillSwitchConfig())
        checker.check(0.05)  # 触发 L1
        assert checker.check(0.10) == KillSwitchLevel.CRITICAL

    def test_level_no_auto_downgrade_from_l2(self):
        """L2 不自动降级"""
        checker = KillSwitchChecker(KillSwitchConfig())
        checker.check(0.10)  # 触发 L2
        assert checker.check(0.02) == KillSwitchLevel.CRITICAL  # 仍然是 L2

    def test_l1_auto_recovery(self):
        """L1 可自动恢复"""
        config = KillSwitchConfig(l1_threshold=0.05, l1_recovery=0.03)
        checker = KillSwitchChecker(config)
        checker.check(0.05)  # 触发 L1
        assert checker.check(0.02) == KillSwitchLevel.NORMAL  # 恢复

    def test_boundary_values(self):
        """边界值测试"""
        config = KillSwitchConfig(l1_threshold=0.05)
        checker = KillSwitchChecker(config)

        # 4.99% 不触发
        assert checker.check(0.0499) == KillSwitchLevel.NORMAL
        # 5.00% 触发
        assert checker.check(0.0500) == KillSwitchLevel.WARNING
        # 5.01% 触发
        checker = KillSwitchChecker(config)  # 重置
        assert checker.check(0.0501) == KillSwitchLevel.WARNING


class TestPositionLimits:
    """持仓限制测试"""

    def test_reject_overweight_position(self):
        """拒绝超权重持仓"""
        checker = PositionChecker(PositionLimits(max_single_weight=0.30))
        order = Order(code="510300", direction="buy", amount=400_000)
        portfolio = Portfolio(total_value=1_000_000, positions={})

        result = checker.check_order(order, portfolio)
        assert not result.passed
        assert "weight" in result.errors[0].lower()

    def test_reject_exceed_max_positions(self):
        """拒绝超过最大持仓数"""
        checker = PositionChecker(PositionLimits(max_positions=5))
        # 已有 5 个持仓
        portfolio = Portfolio(
            total_value=1_000_000,
            positions={f"ETF{i}": 100_000 for i in range(5)},
        )
        # 尝试买入新的
        order = Order(code="NEW_ETF", direction="buy", amount=100_000)

        result = checker.check_order(order, portfolio)
        assert not result.passed
```

## 审计日志

所有风控动作必须记录：

```python
@dataclass
class RiskAuditLog:
    """风控审计日志"""
    timestamp: datetime
    event_type: str        # 'kill_switch_triggered' | 'order_rejected' | ...
    level: int | None
    details: dict

    def save(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO audit_logs (event_type, entity_type, new_value, created_at)
            VALUES (?, 'risk', ?, ?)
            """,
            (self.event_type, json.dumps(self.details), self.timestamp.isoformat()),
        )
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 异步风控检查 | 可能被跳过 | 同步执行 |
| 硬编码阈值 | 不可调整 | 使用配置类 |
| 跳过风控的「后门」 | 破坏安全 | 无例外 |
| L2/L3 自动恢复 | 需要人工确认 | 只允许人工重置 |
| 风控模块 <100% 覆盖 | 遗漏边界 | 完整测试 |
| 不记录审计日志 | 无法追溯 | 所有动作记录 |
