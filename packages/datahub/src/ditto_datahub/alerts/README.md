# Alerts - 告警模块

## 功能概述

提供统一的告警发送接口，支持多种通知渠道（日志、邮件、Telegram、企业微信），实现告警分级管理和多渠道分发。

## 核心组件

| 组件 | 描述 | 文件 |
|------|------|------|
| `AlertManager` | 告警管理器，协调多个发送器 | `manager.py` |
| `AlertSender` | 告警发送器基类 | `base.py` |
| `LoggingAlertSender` | 日志发送器 | `manager.py` |
| `EmailAlertSender` | 邮件发送器 | `email.py` |
| `TelegramAlertSender` | Telegram 发送器 | `telegram.py` |
| `WeChatAlertSender` | 企业微信发送器 | `wechat.py` |

## 告警级别

```python
class AlertLevel(str, Enum):
    """告警严重程度"""

    INFO = "info"       # 信息通知
    WARNING = "warning" # 警告
    ERROR = "error"     # 错误
    CRITICAL = "critical" # 严重错误
```

### 级别比较

```python
# 支持级别比较
if AlertLevel.ERROR > AlertLevel.WARNING:
    print("ERROR 严重程度高于 WARNING")

# 常用判断
if message.level >= AlertLevel.ERROR:
    # 发送紧急通知
    pass
```

## AlertMessage - 告警消息

### 消息结构

```python
@dataclass(frozen=True)
class AlertMessage:
    """告警消息数据"""

    level: AlertLevel                      # 告警级别
    title: str                             # 标题
    content: str                           # 内容
    context: dict[str, Any] | None = None  # 上下文信息

    def format(self) -> str:
        """格式化消息用于显示"""
```

### 消息格式化

```python
from ditto_datahub.alerts import AlertMessage, AlertLevel

# 创建消息
msg = AlertMessage(
    level=AlertLevel.ERROR,
    title="数据摄取失败",
    content="stock_daily 数据摄取失败",
    context={
        "dataset": "stock_daily",
        "trade_date": "2024-01-02",
        "error": "Connection timeout",
    },
)

# 格式化输出
formatted = msg.format()
print(formatted)
# [ERROR] 数据摄取失败
# stock_daily 数据摄取失败
#   dataset: stock_daily
#   trade_date: 2024-01-02
#   error: Connection timeout
```

## AlertManager - 告警管理器

### 初始化

```python
from ditto_datahub.alerts import (
    AlertManager,
    LoggingAlertSender,
    EmailAlertSender,
)

# 创建多渠道管理器
manager = AlertManager(senders=[
    LoggingAlertSender(),    # 日志
    EmailAlertSender(...),    # 邮件
])

# 使用默认配置（仅日志）
from ditto_datahub.alerts import create_default_manager
manager = create_default_manager()
```

### 发送告警

```python
# 基本用法
results = manager.send_alert(
    level=AlertLevel.ERROR,
    title="数据摄取失败",
    message="stock_daily 数据摄取失败",
    dataset="stock_daily",
    trade_date="2024-01-02",
)

# 返回结果
# {
#     "logging": True,
#     "email": False,  # 邮件发送失败
# }
```

### 预定义告警方法

```python
# 数据摄取失败告警
manager.alert_ingestion_failure(
    dataset="stock_daily",
    trade_date="2024-01-02",
    error="Connection timeout",
)

# DQ 检查失败告警
manager.alert_dq_failure(
    dataset="stock_daily",
    trade_date="2024-01-02",
    failed_rules=["not_null", "unique"],
    error_count=5,
)
```

### 告警处理流程

```python
# 1. 创建告警消息
alert_msg = AlertMessage(
    level=level,
    title=title,
    content=message,
    context=context,
)

# 2. 遍历所有发送器
for sender in self._senders:
    try:
        success = sender.send(alert_msg)
        results[sender.name] = success

        # 记录结果
        if success:
            logger.info("Alert sent successfully")
        else:
            logger.warning("Alert send failed")
    except Exception as e:
        results[sender.name] = False
        logger.error("Alert send error", error=str(e))

# 3. 返回结果
return results
```

## AlertSender - 发送器接口

### 基类接口

```python
class AlertSender(ABC):
    """告警发送器基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """获取发送器名称"""
        pass

    @abstractmethod
    def send(self, message: AlertMessage) -> bool:
        """
        发送告警消息

        Args:
            message: 告警消息

        Returns:
            True: 发送成功
            False: 发送失败
        """
        pass
```

### 自定义发送器

```python
from ditto_datahub.alerts.base import AlertSender, AlertMessage

class SlackAlertSender(AlertSender):
    """Slack 告警发送器"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "slack"

    def send(self, message: AlertMessage) -> bool:
        try:
            # 调用 Slack Webhook
            import httpx
            response = httpx.post(
                self.webhook_url,
                json={
                    "text": message.format(),
                },
                timeout=10,
            )
            return response.status_code == 200
        except Exception:
            return False
```

## LoggingAlertSender - 日志发送器

### 功能

将告警消息记录到日志系统，默认使用的发送器。

### 使用

```python
from ditto_datahub.alerts import LoggingAlertSender, AlertLevel, AlertMessage

sender = LoggingAlertSender()

# 根据级别选择日志级别
msg = AlertMessage(
    level=AlertLevel.ERROR,
    title="测试告警",
    content="这是一条测试消息",
)

success = sender.send(msg)
# 自动记录到 logger.error()
```

### 日志级别映射

```python
# AlertLevel -> Loguru Level
if message.level >= AlertLevel.ERROR:
    logger.error(formatted)
elif message.level >= AlertLevel.WARNING:
    logger.warning(formatted)
else:
    logger.info(formatted)
```

## EmailAlertSender - 邮件发送器

### 配置

```python
from ditto_datahub.alerts import EmailAlertSender

sender = EmailAlertSender(
    smtp_server="smtp.gmail.com",
    smtp_port=587,
    username="your-email@gmail.com",
    password="your-app-password",
    from_addr="your-email@gmail.com",
    to_addrs=["recipient@example.com"],
)
```

### 使用

```python
# 添加到 AlertManager
manager = AlertManager(senders=[
    LoggingAlertSender(),
    sender,  # EmailAlertSender
])

# 发送告警（自动同步发送到邮件）
manager.send_alert(
    level=AlertLevel.ERROR,
    title="数据摄取失败",
    message="stock_daily 数据摄取失败",
)
```

## TelegramAlertSender - Telegram 发送器

### 配置

```python
from ditto_datahub.alerts import TelegramAlertSender

sender = TelegramAlertSender(
    bot_token="your-bot-token",
    chat_id="your-chat-id",
)
```

### 使用

```python
# 添加到 AlertManager
manager = AlertManager(senders=[
    LoggingAlertSender(),
    sender,  # TelegramAlertSender
])

# 发送告警
manager.send_alert(
    level=AlertLevel.ERROR,
    title="数据摄取失败",
    message="stock_daily 数据摄取失败",
)
```

## WeChatAlertSender - 企业微信发送器

### 配置

```python
from ditto_datahub.alerts import WeChatAlertSender

sender = WeChatAlertSender(
    webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
)
```

### 使用

```python
# 添加到 AlertManager
manager = AlertManager(senders=[
    LoggingAlertSender(),
    sender,  # WeChatAlertSender
])

# 发送告警
manager.send_alert(
    level=AlertLevel.ERROR,
    title="数据摄取失败",
    message="stock_daily 数据摄取失败",
)
```

## 告警类型

### 数据质量告警

```python
# L1 错误告警
manager.alert_dq_failure(
    dataset="stock_daily",
    trade_date="2024-01-02",
    failed_rules=["not_null", "unique"],
    error_count=5,
)

# L3 统计异常告警
manager.send_alert(
    level=AlertLevel.WARNING,
    title="数据质量告警",
    message=f"检测到 {anomaly_count} 个价格异常",
    dataset="stock_daily",
    trade_date="2024-01-02",
)
```

### 数据摄取告警

```python
# 摄取失败
manager.alert_ingestion_failure(
    dataset="stock_daily",
    trade_date="2024-01-02",
    error="Connection timeout",
)

# 数据源异常
manager.send_alert(
    level=AlertLevel.WARNING,
    title="数据源异常",
    message="Tushare API 响应超时",
    source="tushare",
)
```

### 系统告警

```python
# 磁盘空间不足
manager.send_alert(
    level=AlertLevel.CRITICAL,
    title="系统告警",
    message="磁盘空间不足 10%",
    path="/data",
    available="5GB",
    total="100GB",
)

# 并发冲突
manager.send_alert(
    level=AlertLevel.WARNING,
    title="并发冲突",
    message="文件锁获取超时",
    lock_name="bars_write_stock_daily_2024",
    timeout="60s",
)
```

## 与系统集成

### 与 Ingestion 集成

```python
# 在数据摄入任务中集成
class IngestionTask:
    def __init__(self, alert_manager: AlertManager):
        self._alert_manager = alert_manager

    def run(self, trade_date: str):
        try:
            # 执行摄入
            self._ingest(trade_date)
        except Exception as e:
            # 发送告警
            self._alert_manager.alert_ingestion_failure(
                dataset=self.dataset,
                trade_date=trade_date,
                error=str(e),
            )
            raise
```

### 与 DQ 集成

```python
# 在 DQ 检查失败时发送告警
result = engine.check(df, dataset)

if result.has_errors:
    manager.alert_dq_failure(
        dataset=dataset,
        trade_date=trade_date,
        failed_rules=[i.rule_name for i in result.issues],
        error_count=result.error_count,
    )
```

### 与 Scheduler 集成

```python
# 在定时任务中监控
@task
def monitor_data_quality():
    result = engine.check_statistical(
        dataset="stock_daily",
        trade_date=get_last_trading_day(),
        hub=hub,
    )

    if result.has_alerts:
        manager.send_alert(
            level=AlertLevel.WARNING,
            title="数据质量监控",
            message=f"发现 {result.alert_count} 个统计异常",
        )
```

## 配置示例

### 多渠道配置

```python
from ditto_datahub.alerts import (
    AlertManager,
    LoggingAlertSender,
    EmailAlertSender,
    TelegramAlertSender,
)

# 创建多渠道管理器
manager = AlertManager(senders=[
    LoggingAlertSender(),  # 始终记录日志
    EmailAlertSender(      # ERROR 及以上发送邮件
        smtp_server="smtp.gmail.com",
        smtp_port=587,
        username="alerts@example.com",
        password="password",
        from_addr="alerts@example.com",
        to_addrs=["team@example.com"],
    ),
    TelegramAlertSender(  # CRITICAL 发送 Telegram
        bot_token="xxx",
        chat_id="xxx",
    ),
])

# 根据级别自动选择渠道
# - INFO/WARNING: 仅日志
# - ERROR: 日志 + 邮件
# - CRITICAL: 日志 + 邮件 + Telegram
```

### 级别过滤

```python
class FilteredAlertSender(AlertSender):
    """带级别过滤的发送器"""

    def __init__(self, sender: AlertSender, min_level: AlertLevel):
        self._sender = sender
        self._min_level = min_level

    @property
    def name(self) -> str:
        return self._sender.name

    def send(self, message: AlertMessage) -> bool:
        if message.level < self._min_level:
            return True  # 跳过发送
        return self._sender.send(message)

# 使用
manager = AlertManager(senders=[
    LoggingAlertSender(),
    # 仅发送 ERROR 及以上
    FilteredAlertSender(
        EmailAlertSender(...),
        min_level=AlertLevel.ERROR,
    ),
])
```

## 最佳实践

### 1. 告警去重

```python
# 避免短时间内重复告警
class DedupAlertManager(AlertManager):
    def __init__(self, senders, dedup_window=300):
        super().__init__(senders)
        self._dedup_window = dedup_window  # 5分钟
        self._recent_alerts: dict[str, float] = {}

    def send_alert(self, level, title, message, **context):
        # 生成告警指纹
        fingerprint = f"{level}:{title}:{message}"

        # 检查是否在去重窗口内
        last_time = self._recent_alerts.get(fingerprint, 0)
        if time.time() - last_time < self._dedup_window:
            return {}  # 跳过发送

        # 发送告警
        results = super().send_alert(level, title, message, **context)
        self._recent_alerts[fingerprint] = time.time()
        return results
```

### 2. 告警聚合

```python
# 批量发送时聚合告警
class AggregatingAlertManager(AlertManager):
    def __init__(self, senders, aggregate_window=60):
        super().__init__(senders)
        self._aggregate_window = aggregate_window
        self._pending_alerts: list[AlertMessage] = []

    def send_alert(self, level, title, message, **context):
        self._pending_alerts.append(AlertMessage(
            level=level,
            title=title,
            content=message,
            context=context,
        ))

        # 定时批量发送
        if len(self._pending_alerts) >= 10:
            self._flush()

    def _flush(self):
        """批量发送待发送告警"""
        for msg in self._pending_alerts:
            super().send_alert(
                msg.level,
                msg.title,
                msg.content,
                **(msg.context or {}),
            )
        self._pending_alerts.clear()
```

### 3. 降级处理

```python
# 告警发送失败时降级到日志
class FallbackAlertManager(AlertManager):
    def __init__(self, senders):
        super().__init__(senders + [LoggingAlertSender()])

    def send_alert(self, level, title, message, **context):
        results = super().send_alert(level, title, message, **context)

        # 如果所有发送器失败，确保至少记录到日志
        if not any(results.values()):
            logger.error(
                f"[{level.value}] {title}\n{message}",
                **context,
            )

        return results
```

## 相关文档

- [DQ 模块](../dq/README.md)
- [Ingestion 模块](../../../../../apps/port/src/ditto_server/ingestion/)
- [日志设计](../../../../../docs/design/05_observability_design.md)
