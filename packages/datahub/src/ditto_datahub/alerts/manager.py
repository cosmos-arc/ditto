"""Alert manager for coordinating multiple alert channels."""

from ditto_foundation import logger

from ditto_datahub.alerts.base import AlertLevel, AlertMessage, AlertSender

# Type alias for alert context values
AlertContextValue = str | int | float | bool | list[str] | None


class AlertManager:
    """Manages multiple alert channels and sends alerts to appropriate channels."""

    def __init__(self, senders: list[AlertSender]) -> None:
        """
        Initialize alert manager.

        Args:
            senders: List of alert senders to use.

        """
        self._senders = senders
        logger.debug(
            "AlertManager initialized",
            event="alert_manager_init",
            senders_count=len(senders),
        )

    def send_alert(
        self,
        level: AlertLevel,
        title: str,
        message: str,
        **context: AlertContextValue,
    ) -> dict[str, bool]:
        """
        Send alert to all configured channels.

        Args:
            level: Alert level.
            title: Alert title.
            message: Alert message content.
            **context: Additional context information.

        Returns:
            Dict mapping sender names to send results.

        """
        alert_msg = AlertMessage(
            level=level,
            title=title,
            content=message,
            context=context or {},
        )

        results: dict[str, bool] = {}
        for sender in self._senders:
            try:
                success = sender.send(alert_msg)
                results[sender.name] = success
                if success:
                    logger.info(
                        "Alert sent successfully",
                        event="alert_sent",
                        sender=sender.name,
                        level=level.value,
                        title=title,
                    )
                else:
                    logger.warning(
                        "Alert send failed",
                        event="alert_failed",
                        sender=sender.name,
                        level=level.value,
                        title=title,
                    )
            except Exception as e:
                results[sender.name] = False
                logger.error(
                    "Alert send error",
                    event="alert_error",
                    sender=sender.name,
                    level=level.value,
                    title=title,
                    error=str(e),
                )

        return results

    def alert_ingestion_failure(
        self,
        dataset: str,
        trade_date: str,
        error: str,
    ) -> None:
        """
        Send alert for ingestion failure.

        Args:
            dataset: Dataset name.
            trade_date: Trade date.
            error: Error message.

        """
        self.send_alert(
            level=AlertLevel.ERROR,
            title=f"数据摄取失败: {dataset}",
            message=f"日期 {trade_date} 的 {dataset} 数据摄取失败",
            dataset=dataset,
            trade_date=trade_date,
            error=error,
        )

    def alert_dq_failure(
        self,
        dataset: str,
        trade_date: str,
        failed_rules: list[str],
        error_count: int,
    ) -> None:
        """
        Send alert for DQ check failures.

        Args:
            dataset: Dataset name.
            trade_date: Trade date.
            failed_rules: List of failed rule names.
            error_count: Number of errors.

        """
        level = AlertLevel.ERROR if error_count > 0 else AlertLevel.WARNING

        self.send_alert(
            level=level,
            title=f"数据质量检查失败: {dataset}",
            message=(
                f"日期 {trade_date} 的 {dataset} 数据质量检查发现 {error_count} 个错误"
            ),
            dataset=dataset,
            trade_date=trade_date,
            failed_rules=failed_rules,
            error_count=error_count,
        )


def create_default_manager() -> AlertManager:
    """Create alert manager with default configuration (logging only)."""
    return AlertManager(senders=[LoggingAlertSender()])


class LoggingAlertSender(AlertSender):
    """Alert sender that logs messages instead of sending to external services."""

    @property
    def name(self) -> str:
        """Sender name."""
        return "logging"

    def send(self, message: AlertMessage) -> bool:
        """Log alert message."""
        formatted = message.format()

        if message.level >= AlertLevel.ERROR:
            log_func = logger.error
        elif message.level >= AlertLevel.WARNING:
            log_func = logger.warning
        else:
            log_func = logger.info

        log_func(
            formatted,
            event="alert_logged",
            level=message.level.value,
            title=message.title,
        )
        return True
