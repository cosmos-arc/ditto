# Ditto 项目环境架构完善计划

> 注：本文档为历史归档，配置项已统一为无前缀键名 + config/{env}/*.env，仅在 apps/port 读取；文中提及的环境变量/前缀请视为配置键名示例。


## 一、当前环境架构分析

### 1.1 双层环境架构

```
┌─────────────────────────────────────────────────────────────────┐
│                   环境控制层次（从外到内）                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Layer 1: Pixi 环境 (依赖管理层)                          │    │
│  │                                                          │    │
│  │  default → 生产依赖（polars, fastapi, prefect...）       │    │
│  │  dev      → default + 开发工具（pytest, ruff...）        │    │
│  │                                                          │    │
│  │  控制内容: 安装哪些包、哪些命令可用                         │    │
│  │  切换方式: pixi run -e dev / pixi run                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          ↓                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Layer 2: 运行时环境 (行为控制层)                          │    │
│  │                                                          │    │
│  │  DITTO_ENV = development | testing | production         │    │
│  │                                                          │    │
│  │  控制内容: 日志级别、调试模式、功能开关、错误处理           │    │
│  │  切换方式: 环境变量、.env 文件                             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                          ↓                                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Layer 3: 可观测性模式 (细粒度行为层)                      │    │
│  │                                                          │    │
│  │  Mode.PRODUCTION | DEVELOPMENT | TESTING                │    │
│  │                                                          │    │
│  │  控制内容: 日志格式、指标导出、tracing 开关               │    │
│  │  派生方式: 从 DITTO_ENV 自动检测                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 联动关系

```
Pixi 环境               运行时环境              可观测性模式        实际效果
─────────────           ─────────────           ───────────────     ──────────────────────────────────────

pixi run -e dev    →    DITTO_ENV=development  →  Mode.DEVELOPMENT  →  彩色日志、详细错误、DEBUG级别
                         (默认值)

pixi run -e dev    →    DITTO_ENV=testing      →  Mode.TESTING      →  静默日志、快速测试、无指标导出
                         (pytest自动设置)

pixi run           →    DITTO_ENV=production   →  Mode.PRODUCTION   →  JSON日志、简化错误、INFO级别
(default环境)          (需手动设置)
```

### 1.3 发现的问题

| 问题类型 | 当前状态 | 影响 | 优先级 |
|---------|---------|------|--------|
| **环境值缩写** | `ObservabilityConfig.environment` 默认 `"dev"` | 与 `ditto_env` 的 `"development"` 不一致 | P0 |
| **检测逻辑缺失** | `detect_mode()` 只检查 `"production"` | `"testing"` 环境会被误判为 `DEVELOPMENT` | P0 |
| **概念重复** | `ditto_env` 和 `ObservabilityConfig.environment` | 应该统一为单一环境来源 | P1 |
| **类型验证缺失** | 环境值是字符串，无枚举约束 | 容易出现拼写错误 | P0 |
| **文档缺失** | 没有关于双层环境架构的说明 | 开发者容易混淆 | P3 |
| **命名混淆** | `Mode` 使用 `PRODUCTION/DEVELOPMENT/TESTING` | 与 `Environment` 命名重叠，概念不清 | P1 |

### 1.4 业界最佳实践调研

基于对 [OpenTelemetry 规范](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/) 和 [structlog 最佳实践](https://www.structlog.org/en/stable/logging-best-practices.html) 的调研：

#### OpenTelemetry 的做法
**不定义"运行模式"枚举**，而是通过独立的功能开关控制：
```bash
OTEL_LOG_LEVEL=info              # 日志级别
OTEL_SDK_DISABLED=false          # 是否禁用SDK
OTEL_TRACES_EXPORTER=otlp        # 追踪导出器
OTEL_METRICS_EXPORTER=prometheus # 指标导出器
```
**设计哲学**：每个功能独立配置，而非用单一"模式"控制所有行为。

#### structlog 的做法
**自动检测运行环境**来决定输出格式：
```python
if sys.stderr.isatty():
    # 终端模式：彩色、格式化
    processors = [structlog.dev.ConsoleRenderer()]
else:
    # 容器/生产模式：JSON 结构化
    processors = [structlog.processors.JSONRenderer()]
```
**设计哲学**：基于输出目标（终端 vs 文件 vs 容器）决定行为。

#### 对 Ditto 的启示

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **A: 拆分成独立开关**（OTEL风格） | 完全灵活、业界标准 | 配置复杂、用户心智负担高 | ⭐⭐ |
| **B: 自动检测**（structlog风格） | 零配置、智能 | 难以覆盖所有场景 | ⭐⭐⭐ |
| **C: 保留 Mode 枚举，重命名** | 平衡灵活性和易用性 | 需要清晰文档 | ⭐⭐⭐⭐ |

**推荐方案**：采用 OTEL 风格的独立功能开关，并支持环境配置文件区分。

### 1.5 独立开关设计方案

**移除 Mode 枚举**，改用独立的功能开关：

```python
@dataclass
class ObservabilityConfig:
    """可观测性配置类.

    采用 OTEL 风格的独立开关设计，每个功能可单独控制。
    """
    # === 日志配置 ===
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"  # 控制日志格式
    log_to_console: bool = True                         # 控制是否输出到控制台
    log_to_file: bool = True                            # 控制是否输出到文件

    # === 追踪配置 ===
    tracing_enabled: bool = True
    tracing_exporter: Literal["otlp", "none"] = "otlp"
    tracing_sample_rate: float = 1.0                     # 采样率 0-1

    # === 指标配置 ===
    metrics_enabled: bool = True
    metrics_exporter: Literal["victoriametrics", "none"] = "victoriametrics"
    metrics_export_interval_ms: int = 15000

    # === 断言配置 ===
    assertions_enabled: bool = False                     # 是否启用断言检查
```

### 1.6 环境配置文件区分（方案 B：config/ 文件夹）

采用 `config/{environment}/具体配置文件` 的清晰结构：

```
config/
├── development/
│   ├── observability.env      # 可观测性配置
│   ├── database.env            # 数据库配置
│   ├── api.env                 # API 配置
│   └── data_source.env         # 数据源配置
├── testing/
│   ├── observability.env
│   ├── database.env
│   ├── api.env
│   └── data_source.env
└── production/
    ├── observability.env
    ├── database.env
    ├── api.env
    └── data_source.env
```

**优势**：
1. **按环境分组**：一眼看到某个环境的所有配置
2. **按功能分离**：不同 Settings 类加载不同配置文件
3. **易于维护**：修改某环境配置只需进入对应文件夹
4. **支持扩展**：新增配置模块只需添加新文件

**加载逻辑**：

```python
def load_environment_config(env: Environment) -> None:
    """
    加载指定环境的所有配置文件.

    Parameters
    ----------
    env: Environment
        运行环境
    """
    config_dir = Path(__file__).parent.parent.parent / "config" / env.value

    # 加载该环境下的所有 .env 文件
    for env_file in config_dir.glob("*.env"):
        load_dotenv(env_file, override=True)
```

**Pydantic Settings 配置**：

```python
class ObservabilitySettings(BaseSettings):
    """可观测性配置."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file="config/development/observability.env",  # 会自动切换
        env_file_encoding="utf-8",
    )

class DatabaseSettings(BaseSettings):
    """数据库配置."""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file="config/development/database.env",  # 会自动切换
        env_file_encoding="utf-8",
    )
```

**配置示例**：

`config/development/observability.env`:
```bash
# 开发环境可观测性配置
LOG_LEVEL=DEBUG
LOG_FORMAT=console
TRACING_ENABLED=true
TRACING_EXPORTER=otlp
TRACING_SAMPLE_RATE=1.0
METRICS_ENABLED=true
METRICS_EXPORTER=victoriametrics
ASSERTIONS_ENABLED=true
```

`config/testing/observability.env`:
```bash
# 测试环境可观测性配置（最小化）
LOG_LEVEL=WARNING
LOG_TO_FILE=false
TRACING_ENABLED=false
TRACING_EXPORTER=none
METRICS_ENABLED=false
METRICS_EXPORTER=none
```

`config/production/observability.env`:
```bash
# 生产环境可观测性配置
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_TO_CONSOLE=false
TRACING_ENABLED=true
TRACING_EXPORTER=otlp
TRACING_SAMPLE_RATE=0.1
METRICS_ENABLED=true
METRICS_EXPORTER=victoriametrics
```

### 1.7 与原设计的对比

| 维度 | 原设计（Mode 枚举） | 新设计（独立开关） |
|------|---------------------|-------------------|
| **控制粒度** | 粗粒度（4个预设模式） | 细粒度（每个功能独立控制） |
| **灵活性** | 低（只能选预设模式） | 高（任意组合） |
| **配置复杂度** | 低（一个参数） | 中（多个参数） |
| **可扩展性** | 差（需修改枚举） | 好（新增开关即可） |
| **与 OTEL 对齐** | 否 | 是 |
| **环境配置文件** | 不支持 | 支持 `.env.{environment}` |

**新设计的优势**：
1. **完全灵活**：每个功能可独立开关
2. **业界标准**：与 OTEL 保持一致
3. **环境区分**：通过配置文件自然区分
4. **易于扩展**：新增功能只需添加配置项
5. **消除混淆**：不再有 Mode vs Environment 的概念重叠

## 二、改进方案设计（OTEL 风格）

### 2.1 P0: 创建 Environment 枚举类型

**目标**: 消除类型错误风险，支持环境配置文件自动加载

**实现位置**: `packages/foundation/src/ditto_foundation/config/settings.py`

```python
from enum import Enum

class Environment(str, Enum):
    """系统运行环境枚举.

    用于类型安全的环境值定义，确保整个项目使用一致的环境命名。
    """

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

    @classmethod
    def from_str(cls, value: str) -> "Environment":
        """从字符串解析环境值，提供清晰的错误信息."""
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join(e.value for e in cls)
            raise ValueError(
                f"无效的环境值: '{value}'. "
                f"有效值为: {valid}"
            ) from None

    @property
    def env_file_suffix(self) -> str:
        """获取对应的环境配置文件后缀."""
        return f".env.{self.value}"
```

**更新 SystemSettings**:

```python
class SystemSettings(BaseSettings):
    """系统基础配置."""

    ditto_env: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="系统运行环境",
    )
    # ... 其他字段
```

### 2.2 P1: 重构 ObservabilityConfig 为独立开关

**目标**: 采用 OTEL 风格的独立功能开关，移除 Mode 枚举

**实现位置**: `packages/foundation/src/ditto_foundation/observability/config.py`

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class ObservabilityConfig:
    """可观测性配置类（OTEL 风格）.

    采用独立的功能开关设计，每个功能可单独控制。
    """

    # === 日志配置 ===
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"
    log_to_console: bool = True
    log_to_file: bool = True

    # === 追踪配置 ===
    tracing_enabled: bool = True
    tracing_exporter: Literal["otlp", "none"] = "otlp"
    tracing_sample_rate: float = 1.0

    # === 指标配置 ===
    metrics_enabled: bool = True
    metrics_exporter: Literal["victoriametrics", "none"] = "victoriametrics"
    metrics_export_interval_ms: int = 15000
    vm_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics"

    # === 断言配置 ===
    assertions_enabled: bool = False

    # === 兼容性方法 ===
    def is_testing_mode(self) -> bool:
        """判断是否为测试模式（最小化配置）.

        测试模式定义：
        - tracing_exporter == "none"
        - metrics_exporter == "none"
        - log_to_file == False
        """
        return (
            self.tracing_exporter == "none"
            and self.metrics_exporter == "none"
            and not self.log_to_file
        )

    @classmethod
    def from_settings(cls, settings: "SystemSettings") -> "ObservabilityConfig":
        """从 SystemSettings 创建 ObservabilityConfig.

        根据环境自动应用默认配置，保持向后兼容。
        """
        env = settings.ditto_env

        # 根据环境设置默认值
        if env == Environment.TESTING:
            return cls(
                log_format="console",
                log_to_file=False,
                tracing_enabled=False,
                tracing_exporter="none",
                metrics_enabled=False,
                metrics_exporter="none",
            )
        elif env == Environment.PRODUCTION:
            return cls(
                log_format="json",
                log_level="INFO",
                tracing_sample_rate=0.1,  # 生产环境降低采样率
            )
        else:  # DEVELOPMENT
            return cls(
                log_format="console",
                log_level="DEBUG",
                assertions_enabled=True,
            )
```

### 2.3 P1: 实现 config/{environment}/ 配置文件自动加载

**目标**: 实现 `config/{environment}/` 结构的配置文件自动加载

**实现位置**: `packages/foundation/src/ditto_foundation/config/initializer.py`（新增）

```python
from pathlib import Path
from dotenv import load_dotenv
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .settings import Environment

def load_environment_config(env: "Environment") -> dict[str, Path]:
    """
    加载指定环境的所有配置文件.

    Parameters
    ----------
    env: Environment
        运行环境

    Returns
    -------
    dict[str, Path]
        加载的配置文件映射 {配置名: 文件路径}

    Raises
    ------
    FileNotFoundError
        如果环境配置目录不存在
    """
    # config/ 目录位于项目根目录
    config_dir = Path(__file__).parent.parent.parent.parent / "config" / env.value

    if not config_dir.exists():
        raise FileNotFoundError(
            f"环境配置目录不存在: {config_dir}\n"
            f"请确保目录存在并包含必要的配置文件"
        )

    loaded_files = {}

    # 加载该环境下的所有 .env 文件
    for env_file in sorted(config_dir.glob("*.env")):
        load_dotenv(env_file, override=True)
        loaded_files[env_file.stem] = env_file

    return loaded_files


class ConfigCoordinator:
    """配置协调器，负责多环境配置的加载和管理."""

    def __init__(self) -> None:
        """初始化配置协调器."""
        self._current_env: "Environment | None" = None
        self._loaded_files: dict[str, Path] = {}

    def initialize(self, env: "Environment") -> None:
        """
        初始化指定环境的配置.

        Parameters
        ----------
        env: Environment
            运行环境
        """
        self._current_env = env
        self._loaded_files = load_environment_config(env)

    @property
    def current_env(self) -> "Environment":
        """获取当前环境."""
        if self._current_env is None:
            raise RuntimeError("配置协调器未初始化，请先调用 initialize()")
        return self._current_env

    @property
    def config_dir(self) -> Path:
        """获取当前环境的配置目录."""
        return (
            Path(__file__).parent.parent.parent.parent
            / "config"
            / self._current_env.value
        )

    def get_config_file(self, name: str) -> Path:
        """
        获取指定配置文件的路径.

        Parameters
        ----------
        name: str
            配置文件名（不含 .env 后缀）

        Returns
        -------
        Path
            配置文件路径
        """
        return self.config_dir / f"{name}.env"


# 全局单例
_coordinator: ConfigCoordinator | None = None


def get_config_coordinator() -> ConfigCoordinator:
    """获取全局配置协调器."""
    global _coordinator
    if _coordinator is None:
        _coordinator = ConfigCoordinator()
    return _coordinator
```

### 2.4 P1: 更新 ObservabilitySettings 支持新字段

**目标**: 在 Pydantic Settings 中添加新的独立开关字段

**实现位置**: `packages/foundation/src/ditto_foundation/config/settings.py`

```python
class ObservabilitySettings(BaseSettings):
    """可观测性配置（Pydantic Settings 版本）."""

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    enabled: bool = Field(default=True, description="是否启用可观测性")

    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_format: str = Field(
        default="console",
        description="日志格式 (console/json)",
        pattern="^(console|json)$",
    )
    log_to_console: bool = Field(default=True, description="是否输出到控制台")
    log_to_file: bool = Field(default=True, description="是否输出到文件")

    # 追踪配置
    tracing_enabled: bool = Field(default=True, description="是否启用追踪")
    tracing_exporter: str = Field(
        default="otlp",
        description="追踪导出器 (otlp/none)",
        pattern="^(otlp|none)$",
    )
    tracing_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="追踪采样率 (0-1)",
    )

    # 指标配置
    metrics_enabled: bool = Field(default=True, description="是否启用指标")
    metrics_exporter: str = Field(
        default="victoriametrics",
        description="指标导出器 (victoriametrics/none)",
        pattern="^(victoriametrics|none)$",
    )
    metrics_export_interval_ms: int = Field(
        default=15000,
        ge=1000,
        description="指标导出间隔(毫秒)",
    )
    vm_endpoint: str = Field(
        default="http://localhost:8428/opentelemetry/v1/metrics",
        description="VictoriaMetrics OTLP 端点",
    )

    # 断言配置
    assertions_enabled: bool = Field(default=False, description="是否启用断言检查")
```

### 2.5 P1: 更新 observability init() 函数

**目标**: 使用独立的配置项而非 Mode 枚举

**实现位置**: `packages/foundation/src/ditto_foundation/observability/__init__.py`

```python
def init(
    service_name: str,
    environment: str,
    log_level: str = "INFO",
    log_dir: str = "logs",
    log_format: str = "console",  # 新增
    log_to_console: bool = True,  # 新增
    log_to_file: bool = True,     # 新增
    vm_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics",
    tracing_enabled: bool = True,         # 新增
    tracing_exporter: str = "otlp",       # 新增
    tracing_sample_rate: float = 1.0,     # 新增
    metrics_enabled: bool = True,         # 新增
    metrics_exporter: str = "victoriametrics",  # 新增
    metrics_export_interval_ms: int = 15000,
    assertions_enabled: bool = False,     # 新增
    force: bool = False,
) -> None:
    """
    初始化可观测性系统（OTEL 风格）.

    Parameters
    ----------
    service_name: str
        服务名称
    environment: str
        运行环境
    log_format: str
        日志格式 (console/json)
    tracing_enabled: bool
        是否启用追踪
    tracing_exporter: str
        追踪导出器 (otlp/none)
    ... 其他参数
    """
    # 根据配置初始化各个组件
    _init_logging(
        service_name=service_name,
        log_level=log_level,
        log_format=log_format,
        log_to_console=log_to_console,
        log_to_file=log_to_file,
        log_dir=log_dir,
    )

    if tracing_enabled and tracing_exporter != "none":
        _init_tracing(
            service_name=service_name,
            environment=environment,
            sample_rate=tracing_sample_rate,
        )

    if metrics_enabled and metrics_exporter != "none":
        _init_metrics(
            vm_endpoint=vm_endpoint,
            export_interval_ms=metrics_export_interval_ms,
        )
```

### 2.6 P1: 更新 app_initializer.py

**目标**: 从 ObservabilitySettings 传递配置到 init()

**实现位置**: `packages/foundation/src/ditto_foundation/app_initializer.py`

```python
def _setup_observability(self, settings: Any) -> None:
    """Set up observability (logging, tracing, metrics)."""
    obs_settings = settings.observability

    if not obs_settings.enabled:
        logger.info("Observability disabled by configuration")
        return

    # 直接传递各个配置项，不再使用 Mode
    init(
        service_name="ditto",
        environment=settings.system.ditto_env.value,
        log_level=obs_settings.log_level,
        log_dir=str(settings.file_storage.log_root),
        # 新增的独立配置项
        log_format=obs_settings.log_format,
        log_to_console=obs_settings.log_to_console,
        log_to_file=obs_settings.log_to_file,
        tracing_enabled=obs_settings.tracing_enabled,
        tracing_exporter=obs_settings.tracing_exporter,
        tracing_sample_rate=obs_settings.tracing_sample_rate,
        metrics_enabled=obs_settings.metrics_enabled,
        metrics_exporter=obs_settings.metrics_exporter,
        metrics_export_interval_ms=obs_settings.metrics_export_interval_ms,
        vm_endpoint=obs_settings.vm_endpoint,
        assertions_enabled=obs_settings.assertions_enabled,
    )
```

### 2.7 P1: 更新 main.py

**实现位置**: `apps/port/src/ditto_port/main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager."""
    logger.info("Starting Ditto API server", event="server_start")
    try:
        # 环境会自动加载对应的 .env.{environment} 文件
        env_str = os.getenv("DITTO_ENV", Environment.DEVELOPMENT.value)
        env = Environment.from_str(env_str)

        # 配置已通过 .env 文件加载，直接使用
        settings = get_settings()
        obs = settings.observability

        init(
            service_name="ditto-server",
            environment=env.value,
            log_level=obs.log_level,
            log_dir=str(project_root / "logs"),
            log_format=obs.log_format,
            log_to_console=obs.log_to_console,
            log_to_file=obs.log_to_file,
            tracing_enabled=obs.tracing_enabled,
            tracing_exporter=obs.tracing_exporter,
            tracing_sample_rate=obs.tracing_sample_rate,
            metrics_enabled=obs.metrics_enabled,
            metrics_exporter=obs.metrics_exporter,
            metrics_export_interval_ms=obs.metrics_export_interval_ms,
            vm_endpoint=obs.vm_endpoint,
            assertions_enabled=obs.assertions_enabled,
        )
        # ... 其余代码
```

### 2.8 P3: 创建 config/{environment}/ 配置文件

**新增目录结构和文件**：

```
config/
├── development/
│   ├── observability.env      # 可观测性配置
│   ├── database.env            # 数据库配置
│   ├── api.env                 # API 配置
│   └── data_source.env         # 数据源配置
├── testing/
│   ├── observability.env
│   ├── database.env
│   ├── api.env
│   └── data_source.env
└── production/
    ├── observability.env
    ├── database.env
    ├── api.env
    └── data_source.env
```

**`config/development/observability.env`**:
```bash
# 开发环境可观测性配置
LOG_LEVEL=DEBUG
LOG_FORMAT=console
LOG_TO_CONSOLE=true
LOG_TO_FILE=true

TRACING_ENABLED=true
TRACING_EXPORTER=otlp
TRACING_SAMPLE_RATE=1.0

METRICS_ENABLED=true
METRICS_EXPORTER=victoriametrics

ASSERTIONS_ENABLED=true
```

**`config/testing/observability.env`**:
```bash
# 测试环境可观测性配置（最小化）
LOG_LEVEL=WARNING
LOG_FORMAT=console
LOG_TO_CONSOLE=true
LOG_TO_FILE=false

TRACING_ENABLED=false
TRACING_EXPORTER=none

METRICS_ENABLED=false
METRICS_EXPORTER=none

ASSERTIONS_ENABLED=false
```

**`config/production/observability.env`**:
```bash
# 生产环境可观测性配置
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_TO_CONSOLE=false
LOG_TO_FILE=true

TRACING_ENABLED=true
TRACING_EXPORTER=otlp
TRACING_SAMPLE_RATE=0.1

METRICS_ENABLED=true
METRICS_EXPORTER=victoriametrics

ASSERTIONS_ENABLED=false
```

**其他配置文件示例**：

**`config/development/database.env`**:
```bash
# 开发环境数据库配置
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
```

**`config/production/database.env`**:
```bash
# 生产环境数据库配置
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=40
```

## 三、实施计划（OTEL 风格 + config/ 文件夹）

### 阶段 1: 核心修复 (P0)

| 任务 | 文件 | 说明 |
|------|------|------|
| 创建 Environment 枚举 | `config/settings.py` | 类型安全的环境值 |
| 实现 ConfigCoordinator | `config/initializer.py` | 多环境配置加载 |
| 更新 SystemSettings | `config/settings.py` | 使用 Environment 枚举 |

### 阶段 2: 可观测性重构 (P1)

| 任务 | 文件 | 说明 |
|------|------|------|
| 重构 ObservabilityConfig | `observability/config.py` | 独立功能开关 |
| 更新 ObservabilitySettings | `config/settings.py` | 添加新字段 |
| 更新 observability init() | `observability/__init__.py` | 接受独立配置项 |
| 更新 app_initializer | `app_initializer.py` | 传递独立配置 |
| 更新 main.py | `apps/port/src/ditto_port/main.py` | 使用新配置 |

### 阶段 3: 配置文件创建 (P3)

| 任务 | 文件 | 说明 |
|------|------|------|
| 创建 config/ 目录结构 | `config/{environment}/` | 按环境分组 |
| 创建 observability 配置 | `config/*/observability.env` | 可观测性配置 |
| 创建 database 配置 | `config/*/database.env` | 数据库配置 |
| 创建 api 配置 | `config/*/api.env` | API 配置 |
| 创建 data_source 配置 | `config/*/data_source.env` | 数据源配置 |
| 更新 .gitignore | `.gitignore` | 忽略敏感配置 |

### 阶段 4: 文档完善 (P3)

| 任务 | 文件 | 说明 |
|------|------|------|
| 更新部署拓扑文档 | `docs/design/04_deployment_topology.md` | 添加环境配置说明 |
| 更新 CLAUDE.md | `.claude/CLAUDE.md` | 更新环境配置规范 |
| 更新 foundation README | `packages/foundation/README.md` | 添加环境配置说明 |
| 创建配置模板 | `config/README.md` | 配置文件说明 |

## 四、验证计划

### 单元测试

```python
# tests/unit/config/test_environment_unit.py
def test_environment_from_str_valid():
    """测试有效的环境值解析."""
    assert Environment.from_str("development") == Environment.DEVELOPMENT
    assert Environment.from_str("testing") == Environment.TESTING
    assert Environment.from_str("production") == Environment.PRODUCTION

def test_environment_from_str_invalid():
    """测试无效的环境值抛出异常."""
    with pytest.raises(ValueError, match="无效的环境值"):
        Environment.from_str("dev")  # 缩写应该报错
    with pytest.raises(ValueError, match="无效的环境值"):
        Environment.from_str("prod")

# tests/unit/observability/test_config_unit.py
def test_observability_config_defaults():
    """测试 ObservabilityConfig 默认值."""
    config = ObservabilityConfig()

    assert config.log_format == "console"
    assert config.log_to_console is True
    assert config.tracing_enabled is True
    assert config.tracing_exporter == "otlp"
    assert config.metrics_enabled is True

def test_observability_config_from_settings():
    """测试从 SystemSettings 创建配置."""
    settings = SystemSettings(ditto_env=Environment.TESTING)
    config = ObservabilityConfig.from_settings(settings)

    # testing 环境应该使用最小化配置
    assert config.log_to_file is False
    assert config.tracing_enabled is False
    assert config.tracing_exporter == "none"
    assert config.metrics_enabled is False

def test_is_testing_mode():
    """测试测试模式判断."""
    config = ObservabilityConfig(
        tracing_exporter="none",
        metrics_exporter="none",
        log_to_file=False,
    )
    assert config.is_testing_mode() is True
```

### 集成测试

```bash
# 测试不同环境配置文件的加载
pixi run -e dev python -c "
import os
os.environ['DITTO_ENV'] = 'testing'
from ditto_foundation.config import get_settings
settings = get_settings()
# 应该加载 .env.testing 的配置
assert settings.observability.tracing_exporter == 'none'
assert settings.observability.metrics_exporter == 'none'
"

# 测试环境文件覆盖基础配置
pixi run -e dev python -c "
import os
os.environ['DITTO_ENV'] = 'production'
from ditto_foundation.config import get_settings
settings = get_settings()
# .env.production 应该覆盖 .env
assert settings.observability.log_format == 'json'
"

# 测试无效环境值
pixi run -e dev python -c "
import os
os.environ['DITTO_ENV'] = 'staging'
from ditto_foundation.config import get_settings
# 应该抛出清晰的错误信息
" || echo "Expected error for invalid environment"

# 测试独立开关功能
pixi run -e dev python -c "
from ditto_foundation.observability import init
# 测试只启用日志，禁用追踪和指标
init(
    service_name='test',
    environment='testing',
    tracing_enabled=False,
    tracing_exporter='none',
    metrics_enabled=False,
    metrics_exporter='none',
)
"
```

### 端到端测试

```bash
# 1. 开发环境启动测试
DITTO_ENV=development pixi run -e dev python -m ditto_port.main
# 验证：彩色日志、DEBUG级别、追踪和指标启用

# 2. 测试环境启动测试
DITTO_ENV=testing pixi run -e dev pytest
# 验证：追踪和指标禁用、测试快速执行

# 3. 生产环境启动测试
DITTO_ENV=production pixi run server
# 验证：JSON日志、INFO级别、追踪采样率0.1
```

## 五、关键文件清单

### 需要修改的文件

1. `packages/foundation/src/ditto_foundation/config/settings.py`
   - 添加 `Environment` 枚举
   - 更新 `SystemSettings.ditto_env` 类型
   - 更新 `ObservabilitySettings` 添加新字段

2. `packages/foundation/src/ditto_foundation/config/initializer.py`（新增）
   - 实现 `load_environment_config()` 函数
   - 实现 `ConfigCoordinator` 类

3. `packages/foundation/src/ditto_foundation/observability/config.py`
   - 重构 `ObservabilityConfig` 为独立开关
   - 移除 `Mode` 枚举（或保留为废弃）

4. `packages/foundation/src/ditto_foundation/observability/__init__.py`
   - 更新 `init()` 函数签名，接受独立配置项

5. `packages/foundation/src/ditto_foundation/app_initializer.py`
   - 使用 `ConfigCoordinator`
   - 传递独立配置到 `init()`

6. `apps/port/src/ditto_port/main.py`
   - 使用 `Environment.from_str()`
   - 传递独立配置到 `init()`

7. `.gitignore`
   - 添加 `config/production/` 忽略规则

### 需要新增的文件

**配置目录结构**：
```
config/
├── development/
│   ├── observability.env
│   ├── database.env
│   ├── api.env
│   └── data_source.env
├── testing/
│   ├── observability.env
│   ├── database.env
│   ├── api.env
│   └── data_source.env
└── production/
    ├── observability.env
    ├── database.env
    ├── api.env
    └── data_source.env
```

**文档**：
1. `docs/design/06_environment_architecture.md` - 环境架构文档
2. `config/README.md` - 配置文件说明

**测试**：
1. `packages/foundation/tests/unit/config/test_environment_unit.py` - 单元测试
2. `packages/foundation/tests/unit/config/test_initializer_unit.py` - 配置加载测试
3. `packages/foundation/tests/unit/observability/test_config_unit.py` - 可观测性配置测试

## 六、状态

- [x] 需求分析和调研
- [x] 方案设计
- [x] 文档更新（04_deployment_topology.md, CLAUDE.md）
- [ ] 阶段 1: 核心修复 (P0)
- [ ] 阶段 2: 可观测性重构 (P1)
- [ ] 阶段 3: 配置文件创建 (P3)
- [ ] 阶段 4: 文档完善 (P3)
- [ ] 单元测试
- [ ] 集成测试
- [ ] 端到端测试

## 七、相关文档

- [部署拓扑文档](../docs/design/04_deployment_topology.md#12-环境架构)
- [开发规约](../.claude/CLAUDE.md#环境配置规范)
- [OpenTelemetry 规范](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
- [structlog 最佳实践](https://www.structlog.org/en/stable/logging-best-practices.html)
