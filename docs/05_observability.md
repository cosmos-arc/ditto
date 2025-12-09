# Ditto 可观测性设计文档

**版本：v2.0 Final（Phase 0–1：ETF 行业轮动）**

**日期：2025-12-08**

---

## 1. 设计目标

本文档定义 Ditto 的日志、指标、追踪与告警设计，确保：

1. **问题可定位**：出错时能快速找到原因
2. **状态可感知**：随时了解系统运行状况
3. **外部可验证**：心跳机制证明系统存活
4. **历史可追溯**：关键操作有审计记录

---

## 2. 日志设计

### 2.1 日志框架

使用 **loguru** 作为日志框架，配置如下：

```python
# packages/core/ditto/config/logging.py

from loguru import logger
import sys
from pathlib import Path

def setup_logging(
    log_dir: str = "logs",
    level: str = "INFO",
    rotation: str = "00:00",
    retention: str = "30 days"
):
    """配置日志系统"""

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 移除默认 handler
    logger.remove()

    # 控制台输出（带颜色）
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
               "<level>{message}</level>",
        colorize=True
    )

    # 文件输出（结构化 JSON）
    logger.add(
        log_path / "ditto_{time:YYYYMMDD}.log",
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation=rotation,
        retention=retention,
        compression="gz",
        serialize=True  # JSON 格式
    )

    # 错误日志单独文件
    logger.add(
        log_path / "error_{time:YYYYMMDD}.log",
        level="ERROR",
        rotation=rotation,
        retention="90 days",
        compression="gz"
    )

    logger.info("logging_initialized", log_dir=str(log_path), level=level)
```

### 2.2 日志级别使用规范

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| DEBUG | 开发调试信息 | 函数入参、中间计算结果 |
| INFO | 正常业务流程 | 任务开始/完成、数据更新成功 |
| WARNING | 异常但可恢复 | 数据源降级、因子健康度警告 |
| ERROR | 错误但系统可继续 | 单个标的数据获取失败 |
| CRITICAL | 严重错误需人工介入 | Kill Switch 触发、数据库损坏 |

### 2.3 结构化日志字段规范

```python
# 标准字段
logger.info(
    "message",                    # 必须：事件描述
    event="data_update_complete", # 推荐：事件类型（便于搜索）
    duration_ms=1234,            # 推荐：耗时
    **context                    # 可选：上下文信息
)

# 示例
logger.info(
    "daily_data_update_complete",
    event="data_update",
    duration_ms=45000,
    records_inserted=1250,
    symbols_updated=50,
    source="tushare"
)

logger.error(
    "factor_calculation_failed",
    event="factor_error",
    factor_name="rs_20d",
    symbol="510300.SH",
    error_type="ValueError",
    error_msg="Invalid price data"
)

logger.critical(
    "kill_switch_triggered",
    event="kill_switch",
    level=2,
    current_drawdown=0.185,
    threshold=0.18,
    action="REDUCE_50PCT"
)
```

### 2.4 敏感信息处理

```python
# 脱敏处理
logger.info(
    "api_request",
    api_key=api_key[:4] + "****",  # 只显示前4位
    token="[REDACTED]"
)

# 不记录的信息
# - 完整 API Key / Token
# - 账户密码
# - 券商账号信息
```

---

## 3. 指标设计

### 3.1 核心业务指标

```python
# packages/core/ditto/metrics/business_metrics.py

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

@dataclass
class DailyMetrics:
    """每日业务指标"""

    # 时间
    trade_date: date
    calc_time: datetime

    # 组合指标
    portfolio_value: float
    daily_return: float
    cumulative_return: float
    current_drawdown: float
    drawdown_3d: float              # 3日回撤（速度检测）
    peak_value: float

    # 持仓指标
    total_position_ratio: float
    position_count: int
    max_single_position: float

    # Regime
    regime_type: str
    regime_score: float

    # 成本
    daily_cost: float
    cumulative_cost: float
    cost_ratio: float               # 成本/毛收益

    # 风控
    kill_switch_level: int
    risk_alerts_count: int

@dataclass
class DataQualityMetrics:
    """数据质量指标"""

    trade_date: date

    # 完整性
    expected_records: int
    actual_records: int
    completeness_rate: float

    # 准确性
    cross_validation_errors: int
    suspicious_records: int

    # 时效性
    data_delay_hours: float

    # 异常
    price_jump_count: int
    missing_adj_factor_count: int

@dataclass
class FactorHealthMetrics:
    """因子健康度指标"""

    factor_name: str
    calc_date: date

    # IC 指标
    ic_1m: float
    ic_3m: float
    ic_6m: float
    ic_12m: float
    ic_ir: float

    # 状态
    health_status: str              # 'HEALTHY'/'CAUTION'/'WARNING'/'CRITICAL'

    # 趋势
    ic_trend: str                   # 'IMPROVING'/'STABLE'/'DECLINING'
```

### 3.2 系统运行指标

```python
@dataclass
class SystemMetrics:
    """系统运行指标"""

    timestamp: datetime

    # 数据库
    duckdb_size_mb: float
    sqlite_size_mb: float
    duckdb_query_count: int
    duckdb_avg_query_ms: float

    # API
    api_request_count: int
    api_avg_response_ms: float
    api_error_count: int

    # 调度
    scheduler_job_count: int
    scheduler_failed_jobs: int

    # 资源
    memory_usage_mb: float
    disk_free_gb: float
```

### 3.3 指标存储

指标存储在 SQLite 中，便于查询和展示：

```sql
CREATE TABLE IF NOT EXISTS metrics_daily (
    trade_date      TEXT PRIMARY KEY,
    portfolio_value REAL,
    daily_return    REAL,
    cumulative_return REAL,
    current_drawdown REAL,
    drawdown_3d     REAL,
    regime_type     TEXT,
    kill_switch_level INTEGER,
    metrics_json    TEXT,           -- 完整指标 JSON
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS metrics_data_quality (
    trade_date      TEXT PRIMARY KEY,
    completeness_rate REAL,
    cross_validation_errors INTEGER,
    suspicious_records INTEGER,
    data_delay_hours REAL,
    details_json    TEXT,
    created_at      TEXT
);

CREATE TABLE IF NOT EXISTS metrics_factor_health (
    factor_name     TEXT,
    calc_date       TEXT,
    ic_6m           REAL,
    ic_12m          REAL,
    health_status   TEXT,
    PRIMARY KEY (factor_name, calc_date)
);
```

---

## 4. 告警设计

### 4.1 告警级别

| 级别 | 名称 | 响应时间 | 通知方式 | 示例 |
|------|------|----------|----------|------|
| P0 | 紧急 | 立即 | Telagram+钉钉+邮件+短信 | Kill Switch Level 3 |
| P1 | 严重 | 1 小时内 | Telagram+钉钉+邮件 | Kill Switch Level 2、数据源全部失败 |
| P2 | 警告 | 当日 | Telagram+钉钉 | Kill Switch Level 1、因子健康度下降 |
| P3 | 通知 | 下次检查 | 仅日志 | 数据源降级、小幅偏差 |

### 4.2 告警规则

```python
# packages/core/ditto/alerts/rules.py

from dataclasses import dataclass
from typing import Callable, Any

@dataclass
class AlertRule:
    """告警规则"""
    name: str
    description: str
    level: str                      # 'P0'/'P1'/'P2'/'P3'
    condition: Callable[[Any], bool]
    message_template: str

ALERT_RULES = [
    # P0 - 紧急
    AlertRule(
        name="kill_switch_level3",
        description="Kill Switch Level 3 触发",
        level="P0",
        condition=lambda m: m.kill_switch_level >= 3,
        message_template="🚨 紧急：Kill Switch Level 3 触发！回撤 {drawdown:.1%}，已强制清仓"
    ),

    # P1 - 严重
    AlertRule(
        name="kill_switch_level2",
        description="Kill Switch Level 2 触发",
        level="P1",
        condition=lambda m: m.kill_switch_level == 2,
        message_template="⚠️ 严重：Kill Switch Level 2 触发，回撤 {drawdown:.1%}，已减仓 50%"
    ),
    AlertRule(
        name="all_data_sources_failed",
        description="所有数据源失败",
        level="P1",
        condition=lambda m: m.data_source_status == "ALL_FAILED",
        message_template="⚠️ 严重：所有数据源不可用，已暂停数据更新"
    ),

    # P2 - 警告
    AlertRule(
        name="kill_switch_level1",
        description="Kill Switch Level 1 触发",
        level="P2",
        condition=lambda m: m.kill_switch_level == 1,
        message_template="⚡ 警告：Kill Switch Level 1 触发，回撤 {drawdown:.1%}，已停止新开仓"
    ),
    AlertRule(
        name="fast_drawdown",
        description="3日快速回撤",
        level="P2",
        condition=lambda m: m.drawdown_3d > 0.05,
        message_template="⚡ 警告：3日回撤 {drawdown_3d:.1%}，已触发速度保护"
    ),
    AlertRule(
        name="factor_critical",
        description="因子严重退化",
        level="P2",
        condition=lambda m: any(f.health_status == "CRITICAL" for f in m.factor_health),
        message_template="⚡ 警告：因子 {factor_name} IC 为负，建议移除"
    ),

    # P3 - 通知
    AlertRule(
        name="data_source_degraded",
        description="数据源降级",
        level="P3",
        condition=lambda m: m.data_source_status == "DEGRADED",
        message_template="📝 通知：主数据源不可用，已降级到备用源"
    ),
    AlertRule(
        name="factor_warning",
        description="因子健康度下降",
        level="P3",
        condition=lambda m: any(f.health_status == "WARNING" for f in m.factor_health),
        message_template="📝 通知：因子 {factor_name} IC 低于阈值，建议观察"
    ),
]
```

### 4.3 告警服务

```python
# packages/core/ditto/alerts/alert_service.py

from loguru import logger
from datetime import datetime
import httpx

class AlertService:
    """告警服务"""

    def __init__(self, config):
        self.config = config
        self.telagram_webhook = config.telagram_webhook
        self.dingtalk_webhook = config.dingtalk_webhook
        self.email_config = config.email

    async def send_alert(self, rule: AlertRule, context: dict):
        """发送告警"""
        message = rule.message_template.format(**context)

        logger.log(
            "CRITICAL" if rule.level in ("P0", "P1") else "WARNING",
            f"alert_triggered: {rule.name}",
            alert_level=rule.level,
            alert_name=rule.name,
            message=message
        )

        # 根据级别选择通知方式
        if rule.level == "P0":
            await self._send_all_channels(message, urgent=True)
        elif rule.level == "P1":
            await self._send_feishu(message)
            await self._send_dingtalk(message)
            await self._send_email(message)
        elif rule.level == "P2":
            await self._send_feishu(message)
            await self._send_dingtalk(message)
        # P3 只记录日志

    async def _send_telagram(self, message: str, urgent: bool = False):
        """发送到Telagram"""
        if not self.telagram_webhook:
            return

        payload = {
            "msg_type": "text",
            "content": {"text": message}
        }

        async with httpx.AsyncClient() as client:
            await client.post(self.telagram_webhook, json=payload, timeout=10)

    async def _send_dingtalk(self, message: str, urgent: bool = False):
        """发送到钉钉"""
        if not self.dingtalk_webhook:
            return

        payload = {
            "msgtype": "text",
            "text": {"content": message}
        }

        if urgent:
            payload["at"] = {"isAtAll": True}

        async with httpx.AsyncClient() as client:
            await client.post(self.dingtalk_webhook, json=payload, timeout=10)

    async def _send_email(self, message: str):
        """发送邮件"""
        # 实现邮件发送
        pass

    async def _send_all_channels(self, message: str, urgent: bool = False):
        """发送到所有渠道"""
        await self._send_feishu(message, urgent)
        await self._send_dingtalk(message, urgent)
        await self._send_email(message)
```

---

## 5. 健康检查 API

### 5.1 端点设计

```python
# apps/server/src/api/health.py

from fastapi import APIRouter
from datetime import datetime

router = APIRouter(tags=["Health"])

@router.get("/healthz")
async def healthz():
    """简单存活检查（用于心跳）"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@router.get("/health")
async def health():
    """详细健康检查"""
    checks = await health_service.check_all()

    return {
        "status": checks.overall_status,
        "timestamp": datetime.now().isoformat(),
        "checks": [
            {
                "component": c.component,
                "status": c.status,
                "message": c.message,
                "last_check": c.last_check.isoformat()
            }
            for c in checks.details
        ]
    }

@router.get("/health/data")
async def data_health():
    """数据健康检查"""
    return await health_service.check_data_quality()

@router.get("/health/factors")
async def factor_health():
    """因子健康检查"""
    return await health_service.check_factor_health()

@router.get("/health/risk")
async def risk_health():
    """风控健康检查"""
    return await health_service.check_risk_status()
```

### 5.2 健康检查项

| 组件 | 检查内容 | 健康标准 | 降级标准 | 不健康标准 |
|------|----------|----------|----------|------------|
| duckdb | 连接+查询 | 可查询 | - | 无法连接 |
| sqlite | 连接+查询 | 可查询 | - | 无法连接 |
| data_freshness | 最新数据日期 | ≤1天 | 2-3天 | >3天 |
| scheduler | 运行状态 | 正在运行 | - | 未运行 |
| kill_switch | 触发状态 | Level 0 | Level 1 | Level 2-3 |
| factor_health | 因子 IC | 全部健康 | 有警告 | 有严重 |
| heartbeat | 最近心跳 | ≤2小时 | 2-6小时 | >6小时 |

---

## 6. 审计日志

### 6.1 审计事件

需要记录审计日志的事件：

| 事件类型 | 记录内容 |
|----------|----------|
| config_change | 配置变更：变更前后值、操作人 |
| kill_switch_trigger | Kill Switch 触发：级别、触发条件、当前值 |
| kill_switch_deactivate | Kill Switch 解除：操作人、原因 |
| rebalance_plan_create | 调仓计划创建：计划详情 |
| rebalance_plan_confirm | 调仓计划确认：操作人 |
| factor_weight_change | 因子权重变更：变更前后值 |
| strategy_state_change | 策略状态变更：前后状态 |

### 6.2 审计日志表

```sql
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    event_time  TEXT NOT NULL,
    operator    TEXT,                   -- 操作人（系统或人工）
    target      TEXT,                   -- 操作对象
    old_value   TEXT,                   -- 变更前值（JSON）
    new_value   TEXT,                   -- 变更后值（JSON）
    reason      TEXT,
    ip_address  TEXT,
    details     TEXT                    -- 其他详情（JSON）
);

CREATE INDEX idx_audit_event_type ON audit_log(event_type);
CREATE INDEX idx_audit_event_time ON audit_log(event_time);
```

### 6.3 审计日志记录

```python
# packages/core/ditto/audit/audit_logger.py

import json
from datetime import datetime
from loguru import logger

class AuditLogger:
    """审计日志记录器"""

    def __init__(self, db_adapter):
        self.db = db_adapter

    def log(
        self,
        event_type: str,
        target: str,
        old_value: any = None,
        new_value: any = None,
        operator: str = "system",
        reason: str = None,
        **details
    ):
        """记录审计日志"""

        # 写入数据库
        self.db.execute("""
            INSERT INTO audit_log
            (event_type, event_time, operator, target, old_value, new_value, reason, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_type,
            datetime.now().isoformat(),
            operator,
            target,
            json.dumps(old_value) if old_value else None,
            json.dumps(new_value) if new_value else None,
            reason,
            json.dumps(details) if details else None
        ))

        # 同时写入日志文件
        logger.info(
            f"audit_{event_type}",
            event="audit",
            event_type=event_type,
            operator=operator,
            target=target,
            reason=reason,
            **details
        )

# 使用示例
audit = AuditLogger(db)

# Kill Switch 触发
audit.log(
    event_type="kill_switch_trigger",
    target="portfolio",
    new_value={"level": 2, "drawdown": 0.185},
    reason="Drawdown exceeded 18%"
)

# Kill Switch 解除
audit.log(
    event_type="kill_switch_deactivate",
    target="portfolio",
    old_value={"level": 2},
    new_value={"level": 0},
    operator="user:admin",
    reason="Market stabilized, manual review passed"
)
```

---

## 7. 仪表盘设计

### 7.1 首页仪表盘

展示内容：

1. **系统状态卡片**
   - 整体状态（健康/降级/异常）
   - Kill Switch 状态
   - 最近心跳时间
   - 数据新鲜度

2. **组合概览**
   - 当前净值
   - 当日收益
   - 累计收益
   - 当前回撤

3. **Regime 状态**
   - 当前 Regime（Bull/Osc/Bear）
   - Regime Score
   - 近期 Regime 变化

4. **风控指标**
   - 回撤进度条（显示距各级阈值的距离）
   - 3日回撤速度
   - 仓位使用率

5. **待办事项**
   - 未确认的调仓计划
   - 需要关注的告警
   - 因子健康度警告

### 7.2 监控页面

| 页面 | 内容 |
|------|------|
| 数据监控 | 数据更新状态、质量指标、异常标的 |
| 因子监控 | 各因子 IC 趋势、健康状态、因子墓地 |
| 回测监控 | 对齐测试结果、历史回测记录 |
| 风控监控 | Kill Switch 历史、风控事件时间线 |
| 系统监控 | 资源使用、任务执行、错误统计 |

---

## 8. 日志保留与归档

### 8.1 保留策略

| 日志类型 | 保留期 | 归档 |
|----------|--------|------|
| 运行日志 | 30 天 | 压缩后保留 90 天 |
| 错误日志 | 90 天 | 压缩后保留 1 年 |
| 审计日志 | 永久 | 定期归档 |
| 指标数据 | 永久 | 定期归档 |

### 8.2 归档脚本

```powershell
# scripts/archive_logs.ps1

$logDir = "logs"
$archiveDir = "logs/archived"
$cutoffDays = 30

# 创建归档目录
if (-not (Test-Path $archiveDir)) {
    New-Item -ItemType Directory -Path $archiveDir
}

# 归档旧日志
Get-ChildItem "$logDir/*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$cutoffDays) } |
    ForEach-Object {
        $archiveName = "$archiveDir/$($_.BaseName)_$(Get-Date -Format 'yyyyMM').gz"
        # 压缩并移动
        Compress-Archive -Path $_.FullName -DestinationPath $archiveName -Update
        Remove-Item $_.FullName
    }
```

---

*本可观测性文档定义了 Ditto 的日志、指标、告警和审计设计，确保系统运行状态可感知、问题可追溯。*
