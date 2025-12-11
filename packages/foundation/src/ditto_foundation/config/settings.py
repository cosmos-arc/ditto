"""
Ditto 系统配置管理.

使用 Pydantic Settings 进行配置管理, 支持:
1. 环境变量自动加载
2. 类型验证和转换
3. 默认值设置
4. 配置分组管理
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """数据库配置."""

    model_config = SettingsConfigDict(
        env_prefix="DB_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # DuckDB 配置 (分析型数据库)
    duckdb_path: str = Field(
        default="./data/duckdb/ditto.duckdb", description="DuckDB数据库文件路径"
    )

    # SQLite 配置 (事务型数据库)
    sqlite_path: str = Field(
        default="./data/sqlite/ditto.sqlite", description="SQLite数据库文件路径"
    )

    # 连接池配置
    pool_size: int = Field(default=10, ge=1, le=100, description="数据库连接池大小")

    max_overflow: int = Field(
        default=20, ge=0, le=100, description="连接池最大溢出数量"
    )


class DataSourceSettings(BaseSettings):
    """数据源配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Tushare 配置
    tushare_token: str = Field(description="Tushare Pro API Token", min_length=1)

    tushare_pro_api_url: str = Field(
        default="https://api.tushare.pro", description="Tushare Pro API地址"
    )

    tushare_rate_limit: int = Field(
        default=200, ge=1, le=1000, description="Tushare API每分钟调用次数限制"
    )

    # AkShare 配置
    akshare_enable: bool = Field(
        default=True, description="是否启用AkShare作为备用数据源"
    )

    akshare_timeout: int = Field(
        default=30, ge=5, le=300, description="AkShare请求超时时间(秒)"
    )

    # 数据更新配置
    data_update_enabled: bool = Field(default=True, description="是否启用自动数据更新")

    data_update_time: str = Field(
        default="02:30", description="每日数据更新时间 (HH:MM格式)"
    )

    data_update_retry: int = Field(
        default=3, ge=0, le=10, description="数据更新失败重试次数"
    )

    @field_validator("data_update_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """验证时间格式 HH:MM."""
        try:
            hour, minute = v.split(":")
            h, m = int(hour), int(minute)
            # Define constants for time validation
            MIN_HOUR = 0
            MAX_HOUR = 23
            MIN_MINUTE = 0
            MAX_MINUTE = 59
            if not (MIN_HOUR <= h <= MAX_HOUR and MIN_MINUTE <= m <= MAX_MINUTE):
                raise ValueError
            return v
        except (ValueError, AttributeError) as err:
            raise ValueError(
                "时间格式必须为 HH:MM, 且小时在0-23之间, 分钟在0-59之间"
            ) from err


class APISettings(BaseSettings):
    """FastAPI 服务配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 服务器配置
    host: str = Field(default="0.0.0.0", description="服务器监听地址")

    port: int = Field(default=8000, ge=1, le=65535, description="服务器监听端口")

    workers: int = Field(default=1, ge=1, le=10, description="工作进程数量")

    # API配置
    api_prefix: str = Field(default="/api/v1", description="API路径前缀")

    docs_url: str = Field(default="/docs", description="API文档路径")

    redoc_url: str = Field(default="/redoc", description="ReDoc文档路径")

    # 安全配置
    secret_key: str = Field(description="JWT密钥, 生产环境必须修改", min_length=32)

    access_token_expire_minutes: int = Field(
        default=30, ge=5, le=1440, description="访问令牌过期时间(分钟)"
    )

    algorithm: str = Field(default="HS256", description="JWT签名算法")

    # CORS配置
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="允许的CORS来源",
    )


class TradingSettings(BaseSettings):
    """交易执行配置 (Phase 2+ 使用)."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # MiniQMT配置
    miniqmt_enable: bool = Field(default=False, description="是否启用MiniQMT实盘交易")

    miniqmt_path: str | None = Field(default=None, description="MiniQMT客户端路径")

    miniqmt_user_id: str | None = Field(default=None, description="MiniQMT用户ID")

    miniqmt_password: str | None = Field(default=None, description="MiniQMT密码")

    # 模拟交易配置
    paper_trading_enabled: bool = Field(default=True, description="是否启用模拟交易")

    paper_trading_initial_capital: float = Field(
        default=100000.0, ge=1000.0, description="模拟交易初始资金"
    )

    paper_trading_commission_rate: float = Field(
        default=0.0003, ge=0.0, le=0.01, description="交易佣金费率"
    )

    paper_trading_min_commission: float = Field(
        default=5.0, ge=0.0, description="最低交易佣金"
    )


class RiskSettings(BaseSettings):
    """风险管理配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Kill Switch配置
    kill_switch_enabled: bool = Field(default=True, description="是否启用Kill Switch")

    kill_switch_daily_loss_threshold: float = Field(
        default=0.02, ge=0.0, le=0.10, description="日亏损阈值"
    )

    kill_switch_weekly_loss_threshold: float = Field(
        default=0.05, ge=0.0, le=0.20, description="周亏损阈值"
    )

    kill_switch_max_drawdown_threshold: float = Field(
        default=0.15, ge=0.0, le=0.30, description="最大回撤阈值"
    )

    kill_switch_emergency_threshold: float = Field(
        default=0.25, ge=0.0, le=0.50, description="紧急止损阈值"
    )

    # 仓位限制
    max_single_position_weight: float = Field(
        default=0.15, ge=0.01, le=0.50, description="单只证券最大权重"
    )

    max_sector_weight: float = Field(
        default=0.30, ge=0.01, le=0.80, description="单行业最大权重"
    )

    min_cash_ratio: float = Field(
        default=0.05, ge=0.0, le=0.50, description="最小现金比例"
    )


class NotificationSettings(BaseSettings):
    """通知配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Telegram通知
    telegram_bot_token: str | None = Field(
        default=None, description="Telegram机器人Token"
    )

    telegram_chat_id: str | None = Field(default=None, description="Telegram聊天ID")

    telegram_enabled: bool = Field(default=False, description="是否启用Telegram通知")

    # 邮件通知
    smtp_host: str = Field(default="smtp.gmail.com", description="SMTP服务器地址")

    smtp_port: int = Field(default=587, ge=1, le=65535, description="SMTP服务器端口")

    smtp_user: str | None = Field(default=None, description="SMTP用户名")

    smtp_password: str | None = Field(default=None, description="SMTP密码")

    email_enabled: bool = Field(default=False, description="是否启用邮件通知")


class SystemSettings(BaseSettings):
    """系统基础配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 环境配置
    ditto_env: Literal["development", "testing", "production"] = Field(
        default="development", description="系统运行环境"
    )

    log_level: Literal["TRACE", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = (
        Field(default="INFO", description="日志级别")
    )

    timezone: str = Field(default="Asia/Shanghai", description="系统时区")

    # 性能配置
    max_concurrent_requests: int = Field(
        default=100, ge=1, le=1000, description="最大并发请求数"
    )

    request_timeout: int = Field(
        default=30, ge=5, le=300, description="请求超时时间(秒)"
    )

    # 缓存配置
    cache_enabled: bool = Field(default=True, description="是否启用缓存")

    cache_ttl: int = Field(
        default=3600, ge=60, le=86400, description="缓存过期时间(秒)"
    )

    # 调试配置
    debug: bool = Field(default=False, description="是否启用调试模式")

    profiling_enabled: bool = Field(default=False, description="是否启用性能分析")

    # Mock数据配置
    use_mock_data: bool = Field(default=False, description="是否使用Mock数据(用于测试)")


class FileStorageSettings(BaseSettings):
    """文件存储配置."""

    model_config = SettingsConfigDict(
        env_prefix="", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 存储路径
    data_root: str = Field(default="./data", description="数据存储根目录")

    log_root: str = Field(default="./logs", description="日志存储根目录")

    backup_root: str = Field(default="./backups", description="备份存储根目录")

    temp_root: str = Field(default="./temp", description="临时文件存储根目录")

    # 保留策略
    log_retention_days: int = Field(
        default=30, ge=1, le=365, description="日志保留天数"
    )

    backup_retention_days: int = Field(
        default=90,
        ge=1,
        le=1095,  # 3年
        description="备份保留天数",
    )

    temp_retention_days: int = Field(
        default=7, ge=1, le=30, description="临时文件保留天数"
    )


class Settings(BaseSettings):
    """
    Ditto系统主配置类.

    集成所有配置子模块, 提供统一的配置访问接口
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略未定义的环境变量
    )

    # 配置子模块
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    data_source: DataSourceSettings = Field(default_factory=DataSourceSettings)
    api: APISettings = Field(default_factory=APISettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    notification: NotificationSettings = Field(default_factory=NotificationSettings)
    system: SystemSettings = Field(default_factory=SystemSettings)
    file_storage: FileStorageSettings = Field(default_factory=FileStorageSettings)

    def __init__(self, **kwargs: Any) -> None:
        """Initialize Settings and ensure directories exist."""
        super().__init__(**kwargs)
        # 确保目录存在
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """确保必要的目录存在."""
        directories = [
            self.file_storage.data_root,
            self.file_storage.log_root,
            self.file_storage.backup_root,
            self.file_storage.temp_root,
            Path(self.database.duckdb_path).parent,
            Path(self.database.sqlite_path).parent,
        ]

        for directory in directories:
            if isinstance(directory, str):
                Path(directory).mkdir(parents=True, exist_ok=True)
            elif hasattr(directory, "mkdir"):
                directory.mkdir(parents=True, exist_ok=True)

    @property
    def is_development(self) -> bool:
        """是否为开发环境."""
        return self.system.ditto_env == "development"

    @property
    def is_production(self) -> bool:
        """是否为生产环境."""
        return self.system.ditto_env == "production"

    @property
    def is_testing(self) -> bool:
        """是否为测试环境."""
        return self.system.ditto_env == "testing"

    def get_log_config(self) -> dict[str, Any]:
        """获取日志配置字典."""
        return {
            "level": self.system.log_level,
            "timezone": self.system.timezone,
            "log_root": self.file_storage.log_root,
            "retention_days": self.file_storage.log_retention_days,
            "debug": self.system.debug,
        }


# 全局配置实例
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    获取全局配置实例.

    使用单例模式, 避免重复加载配置

    Returns
    -------
        Settings: 配置实例

    """
    global _settings  # noqa: PLW0603 - Intentional singleton pattern
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    重新加载配置.

    主要用于测试或配置热更新场景

    Returns
    -------
        Settings: 新的配置实例

    """
    global _settings  # noqa: PLW0603 - Intentional singleton pattern
    _settings = Settings()
    return _settings


# 配置验证函数
def validate_settings(settings: Settings) -> list[str]:  # noqa: PLR0912
    """
    验证配置的有效性.

    Args:
    ----
        settings: 配置实例

    Returns:
    -------
        List[str]: 验证错误信息列表, 空列表表示验证通过

    """
    errors = []

    # 验证必要的API密钥
    if not settings.data_source.tushare_token:
        errors.append("TUSHARE_TOKEN 环境变量未设置")

    # 验证安全配置
    if settings.is_production:
        if settings.api.secret_key == "your_secret_key_here_change_in_production":
            errors.append("生产环境必须修改默认的SECRET_KEY")

        if settings.system.debug:
            errors.append("生产环境不建议启用DEBUG模式")

    # 验证路径配置
    try:
        Path(settings.database.duckdb_path).parent.mkdir(parents=True, exist_ok=True)
        Path(settings.database.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        errors.append(f"无法创建数据库目录: {e}")

    # 验证交易配置
    if settings.trading.miniqmt_enable:
        if not settings.trading.miniqmt_path:
            errors.append("启用MiniQMT时必须设置MINIQMT_PATH")
        if not settings.trading.miniqmt_user_id:
            errors.append("启用MiniQMT时必须设置MINIQMT_USER_ID")
        if not settings.trading.miniqmt_password:
            errors.append("启用MiniQMT时必须设置MINIQMT_PASSWORD")

    # 验证通知配置
    if settings.notification.telegram_enabled:
        if not settings.notification.telegram_bot_token:
            errors.append("启用Telegram通知时必须设置TELEGRAM_BOT_TOKEN")
        if not settings.notification.telegram_chat_id:
            errors.append("启用Telegram通知时必须设置TELEGRAM_CHAT_ID")

    if settings.notification.email_enabled:
        if not settings.notification.smtp_user:
            errors.append("启用邮件通知时必须设置SMTP_USER")
        if not settings.notification.smtp_password:
            errors.append("启用邮件通知时必须设置SMTP_PASSWORD")

    return errors


if __name__ == "__main__":
    # 配置测试
    settings = get_settings()

    print("=== Ditto 系统配置 ===")
    print(f"环境: {settings.system.ditto_env}")
    print(f"日志级别: {settings.system.log_level}")
    print("数据库路径:")
    print(f"  DuckDB: {settings.database.duckdb_path}")
    print(f"  SQLite: {settings.database.sqlite_path}")
    print(f"API服务: {settings.api.host}:{settings.api.port}")

    # 验证配置
    errors = validate_settings(settings)
    if errors:
        print("\n=== 配置错误 ===")
        for error in errors:
            print(f"❌ {error}")
    else:
        print("\n✅ 配置验证通过")
