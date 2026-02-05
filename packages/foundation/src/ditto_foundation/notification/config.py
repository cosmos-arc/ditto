"""Notification configuration settings."""

from pydantic import BaseModel, ConfigDict, Field


class NotificationSettings(BaseModel):
    """Notification channel settings (pure model)."""

    model_config = ConfigDict(extra="ignore")

    # Email settings
    email_smtp_host: str = Field(default="localhost", description="SMTP server host")
    email_smtp_port: int = Field(default=587, description="SMTP server port")
    email_username: str | None = Field(default=None, description="SMTP username")
    email_password: str | None = Field(default=None, description="SMTP password")
    email_from: str = Field(default="noreply@ditto.local", description="From address")
    email_to: str = Field(default="", description="To addresses (comma-separated)")

    # Telegram settings
    telegram_bot_token: str | None = Field(
        default=None,
        description="Telegram bot token",
    )
    telegram_chat_id: str | None = Field(default=None, description="Telegram chat ID")

    # WeChat settings
    wechat_webhook_url: str | None = Field(
        default=None,
        description="WeChat webhook URL",
    )
    wechat_corp_id: str | None = Field(default=None, description="WeChat corp ID")
    wechat_agent_id: str | None = Field(default=None, description="WeChat agent ID")

    # DingTalk settings
    dingtalk_webhook_url: str | None = Field(
        default=None,
        description="DingTalk webhook URL",
    )
    dingtalk_secret: str | None = Field(default=None, description="DingTalk secret")

    # Slack settings
    slack_webhook_url: str | None = Field(default=None, description="Slack webhook URL")
    slack_channel: str | None = Field(default=None, description="Slack channel")

    # Webhook settings (generic)
    webhook_url: str | None = Field(default=None, description="Generic webhook URL")
    webhook_headers: dict[str, str] = Field(
        default_factory=dict,
        description="Webhook HTTP headers",
    )


__all__ = ["NotificationSettings"]
