# 环境配置架构全面改进计划

> 注：本文档为历史归档，配置项已统一为无前缀键名 + config/{env}/*.env，仅在 apps/port 读取；文中提及的环境变量/前缀请视为配置键名示例。


**日期**: 2026-01-19
**范围**: P0 + P1 + P2 全部改进
**工作量**: 约 3-4 天

---

## 一、设计概述

### 核心目标

1. **Environment 枚举**（P0）：创建类型安全的环境枚举，替换字符串类型
2. **移除 Mode 枚举**（P0）：统一使用 Environment + 独立布尔标志
3. **配置键命名**（P1）：统一使用无前缀（直接字段名）
4. **配置文件结构**（P1）：实现 `config/{env}/` 目录结构
5. **预设配置**（P2）：实现预设 + 独立开关覆盖模式

### 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 配置目录结构 | 两层覆盖（无共享目录） | 每个环境目录完整独立，清晰隔离 |
| 配置键命名 | 无前缀（直接字段名） | 避免映射歧义，保持一致 |
| 配置加载方式 | Pydantic Settings 自动加载 | 与框架深度集成 |
| Mode 替代方案 | 独立布尔标志 | 更清晰、更灵活 |
| 预设模式 | 预设 + 覆盖 | 兼顾易用性和灵活性 |

---

## 二、目录结构

```
config/
├── development/
│   ├── system.env              # 系统基础（DITTO_ENV, TIMEZONE）
│   ├── observability.env       # 可观测性（无前缀（直接字段名））
│   ├── database.env            # 数据库（SQLITE_PATH/DUCKDB_PATH）
│   ├── data_source.env         # 数据源（HTTP_/RETRY_/RATE_LIMIT_/TUSHARE_TOKEN）
│   ├── api.env                 # API 服务（API_*）
│   └── performance.env         # 性能（PERF_*）
│
├── testing/
│   └── ...（同上，值不同）
│
└── production/
    └── ...（同上，值不同）
```

**配置键命名示例**：

| 配置域 | 示例键 |
|--------|--------|
| 可观测性 | `LOG_LEVEL`, `TRACING_ENABLED` |
| 数据库 | `SQLITE_PATH`, `DUCKDB_PATH` |
| 数据源 | `HTTP_BASE_URL`, `TUSHARE_TOKEN` |
| API 服务 | `API_HOST` |
| 系统配置 | `DITTO_ENV`, `TIMEZONE` |

---

## 三、实施步骤

### P0-1: 创建 Environment 枚举

**文件**: `packages/foundation/src/ditto_foundation/config/environment.py`（新建）

```python
from enum import Enum

class Environment(str, Enum):
    """系统运行环境枚举."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

    @classmethod
    def from_str(cls, value: str) -> "Environment":
        """从字符串创建 Environment，带验证."""
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join(e.value for e in cls)
            raise ValueError(
                f"Invalid environment '{value}'. Valid values: {valid}"
            ) from None

    @property
    def is_development(self) -> bool:
        return self == Environment.DEVELOPMENT

    @property
    def is_testing(self) -> bool:
        return self == Environment.TESTING

    @property
    def is_production(self) -> bool:
        return self == Environment.PRODUCTION
```

**测试**: `tests/unit/config/test_environment.py`

---

### P0-2: SystemSettings 使用 Environment

**文件**: `packages/foundation/src/ditto_foundation/config/settings.py`

```python
from .environment import Environment

class SystemSettings(BaseSettings):
    """系统基础配置"""
    ditto_env: Environment = Field(default=Environment.DEVELOPMENT)
    timezone: str = Field(default="Asia/Shanghai")
    debug: bool = Field(default=False)
```

**更新导出**: `config/__init__.py` 导出 `Environment`

---

### P0-3: 移除 Mode 枚举，添加独立标志

**文件**: `packages/foundation/src/ditto_foundation/observability/config.py`

**删除**:
```python
# ❌ 删除 Mode 枚举
class Mode(Enum):
    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TESTING = "testing"
    TESTING_WITH_ASSERTIONS = "testing_assertions"
```

**替换为**:
```python
@dataclass
class ObservabilityConfig:
    """可观测性配置"""

    # === 环境相关 ===
    environment: Environment = Environment.DEVELOPMENT

    # === 运行时标志（替代 Mode）===
    pytest_running: bool = False
    assertions_enabled: bool = True
    verbose_logging: bool = True
```

**更新调用方**:
- `bootstrap/initializer.py`
- 所有使用 `Mode` 的地方

---

### P1-1: 更新配置键命名为 无前缀（直接字段名）

**文件**: `packages/foundation/src/ditto_foundation/config/settings.py`

```python
class ObservabilitySettings(BaseSettings):
    """可观测性配置"""
    model_config = SettingsConfigDict(
        env_prefix="",  # 从 ??? 改为 ???
        env_file="config/development/observability.env",
        extra="ignore",
    )

    log_level: str = "INFO"
    log_format: str = "console"
    log_to_console: bool = True
    log_to_file: bool = True
    tracing_enabled: bool = True
    tracing_exporter: str = "otlp"
    tracing_sample_rate: float = 1.0
    metrics_enabled: bool = True
    metrics_exporter: str = "victoriametrics"
    vm_endpoint: str = "http://localhost:8428/opentelemetry/v1/metrics"
```

---

### P1-2: 创建 config/{env}/ 目录结构

**创建目录和文件**:

```bash
# 创建目录
mkdir -p config/development
mkdir -p config/testing
mkdir -p config/production

# 创建配置文件（示例）
touch config/development/{system,observability,database,data_source,api,performance}.env
touch config/testing/{system,observability,database,data_source,api,performance}.env
touch config/production/{system,observability,database,data_source,api,performance}.env
```

**config/development/system.env**:
```bash
DITTO_ENV=development
TIMEZONE=Asia/Shanghai
DEBUG=true
```

**config/development/observability.env**:
```bash
LOG_LEVEL=DEBUG
LOG_FORMAT=console
TRACING_ENABLED=true
TRACING_SAMPLE_RATE=1.0
METRICS_ENABLED=true
VM_ENDPOINT=http://localhost:8428/opentelemetry/v1/metrics
```

---

### P1-3: 实现 ConfigLoader 自动加载

**文件**: `packages/foundation/src/ditto_foundation/config/loader.py`（新建）

```python
from pathlib import Path
from .environment import Environment

class ConfigLoader:
    """配置加载器"""

    def __init__(self, environment: Environment):
        self.environment = environment
        self.config_dir = Path("config") / environment.value

    def get_env_file(self, name: str) -> str:
        """获取特定配置文件的路径"""
        return str(self.config_dir / f"{name}.env")
```

**更新 Settings 初始化**:

```python
class Settings(BaseSettings):
    """Ditto 系统主配置类"""

    def __init__(self, **kwargs):
        env_str = os.getenv("DITTO_ENV", "development")
        environment = Environment.from_str(env_str)
        config_dir = f"config/{environment.value}"

        super().__init__(
            system=SystemSettings(
                _env_file=f"{config_dir}/system.env",
                **kwargs.get("system", {})
            ),
            observability=ObservabilitySettings(
                _env_file=f"{config_dir}/observability.env",
                **kwargs.get("observability", {})
            ),
            # ... 其他配置
            **kwargs
        )
```

---

### P2-1: 实现预设配置系统

**文件**: `packages/foundation/src/ditto_foundation/observability/config.py`

```python
@dataclass
class ObservabilityConfig:
    """可观测性配置（预设 + 独立开关覆盖）"""

    # === 预设配置 ===
    profile: Literal["development", "testing", "production"] = "development"

    # === 独立开关（None 表示使用预设值）===
    log_level: str | None = None
    tracing_enabled: bool | None = None
    tracing_sample_rate: float | None = None
    metrics_enabled: bool | None = None
    vm_endpoint: str | None = None

    # === 运行时标志 ===
    pytest_running: bool = False
    assertions_enabled: bool = True
    verbose_logging: bool = True

    def get_effective_config(self) -> "EffectiveConfig":
        """获取生效配置（预设 + 覆盖）."""
        presets = {
            "development": _Preset(
                log_level="DEBUG",
                tracing_enabled=True,
                tracing_sample_rate=1.0,
                metrics_enabled=True,
                assertions_enabled=True,
                verbose_logging=True,
            ),
            "testing": _Preset(
                log_level="WARNING",
                tracing_enabled=False,
                tracing_sample_rate=0.0,
                metrics_enabled=False,
                assertions_enabled=False,
                verbose_logging=False,
            ),
            "production": _Preset(
                log_level="INFO",
                tracing_enabled=True,
                tracing_sample_rate=0.1,
                metrics_enabled=True,
                assertions_enabled=False,
                verbose_logging=False,
            ),
        }

        preset = presets[self.profile]

        return EffectiveConfig(
            log_level=self.log_level or preset.log_level,
            tracing_enabled=self.tracing_enabled if self.tracing_enabled is not None else preset.tracing_enabled,
            tracing_sample_rate=self.tracing_sample_rate if self.tracing_sample_rate is not None else preset.tracing_sample_rate,
            metrics_enabled=self.metrics_enabled if self.metrics_enabled is not None else preset.metrics_enabled,
            vm_endpoint=self.vm_endpoint or preset.vm_endpoint,
            assertions_enabled=self.assertions_enabled if self.assertions_enabled is not None else preset.assertions_enabled,
            verbose_logging=self.verbose_logging if self.verbose_logging is not None else preset.verbose_logging,
            pytest_running=self.pytest_running,
        )
```

---

### P2-2: 实现覆盖合并逻辑

（已在 P2-1 中实现）

---

## 四、关键文件清单

### 新建文件

| 文件 | 说明 |
|------|------|
| `packages/foundation/src/ditto_foundation/config/environment.py` | Environment 枚举 |
| `packages/foundation/src/ditto_foundation/config/loader.py` | ConfigLoader |
| `config/development/*.env` | 开发环境配置 |
| `config/testing/*.env` | 测试环境配置 |
| `config/production/*.env` | 生产环境配置 |

### 修改文件

| 文件 | 主要改动 |
|------|----------|
| `packages/foundation/src/ditto_foundation/config/settings.py` | 使用 Environment，更新 env_prefix |
| `packages/foundation/src/ditto_foundation/observability/config.py` | 移除 Mode，添加预设系统 |
| `packages/foundation/src/ditto_foundation/bootstrap/initializer.py` | 更新 Mode 使用为独立标志 |
| `packages/foundation/src/ditto_foundation/config/__init__.py` | 导出 Environment |
| `packages/foundation/src/ditto_foundation/observability/__init__.py` | 更新导出 |

### 测试文件

| 文件 | 说明 |
|------|------|
| `tests/unit/config/test_environment.py` | Environment 枚举测试 |
| `tests/unit/config/test_loader.py` | ConfigLoader 测试 |
| `tests/unit/config/test_settings.py` | Settings 类测试 |
| `tests/unit/observability/test_config.py` | ObservabilityConfig 测试 |
| `tests/integration/test_config_loading.py` | 端到端配置加载测试 |

---

## 五、验证计划

### 功能验证

1. **Environment 枚举**
   ```python
   assert Environment.from_str("development") == Environment.DEVELOPMENT
   assert Environment.DEVELOPMENT.is_development == True
   ```

2. **配置文件加载**
   ```bash
   DITTO_ENV=development pixi run -e dev python -c "from ditto_foundation.config import get_settings; print(get_settings())"
   DITTO_ENV=testing pixi run -e dev python -c "from ditto_foundation.config import get_settings; print(get_settings())"
   DITTO_ENV=production pixi run -e dev python -c "from ditto_foundation.config import get_settings; print(get_settings())"
   ```

3. **预设 + 覆盖**
   ```python
   config = ObservabilityConfig(profile="testing")
   effective = config.get_effective_config()
   assert effective.log_level == "WARNING"  # 预设值

   config = ObservabilityConfig(profile="testing", log_level="ERROR")
   effective = config.get_effective_config()
   assert effective.log_level == "ERROR"  # 覆盖值
   ```

### 质量检查

```bash
# 类型检查
pixi run -e dev type

# 代码检查
pixi run -e dev lint

# 测试
pixi run -e dev test

# 完整 CI
pixi run -e dev ci
```

---

## 六、依赖关系

```
Environment 枚举
    ↓
SystemSettings 使用 Environment
    ↓
移除 Mode 枚举
    ↓
更新配置键命名
    ↓
创建 config/{env}/ 目录
    ↓
实现 ConfigLoader
    ↓
实现预设配置系统
    ↓
测试验证
```

---

## 七、注意事项

1. **无需向后兼容**：直接废弃旧设计，无需迁移
2. **配置文件精简**：每个 .env 文件控制在 10-20 行
3. **TDD 流程**：每个步骤先写测试，再实现
4. **质量检查**：每步完成后运行 `pixi run -e dev check`
