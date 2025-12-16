---
paths: packages/core/src/ditto_core/engine/**/*.py
---

# 引擎基类与通用规范

> 所有引擎的共同约束和设计模式

## 引擎架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    Engine Layer                          │
├─────────────────────────────────────────────────────────┤
│  RegimeEngine   →  市场状态识别                          │
│       ↓                                                  │
│  FactorEngine   →  因子计算                              │
│       ↓                                                  │
│  RotationEngine →  标的选择                              │
│       ↓                                                  │
│  BacktestEngine →  策略验证                              │
│       ↓                                                  │
│  RiskEngine     →  风险控制（见 risk.md）                │
└─────────────────────────────────────────────────────────┘
```

## Protocol 定义

```python
from typing import Protocol, TypeVar, Generic
from abc import abstractmethod
from dataclasses import dataclass
import polars as pl

TConfig = TypeVar("TConfig")
TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")


class Engine(Protocol[TConfig, TInput, TOutput]):
    """引擎协议：所有引擎必须实现"""

    @abstractmethod
    def initialize(self, config: TConfig) -> None:
        """初始化引擎配置"""
        ...

    @abstractmethod
    def process(self, data: TInput) -> TOutput:
        """处理数据，返回结果"""
        ...

    @abstractmethod
    def validate(self) -> "ValidationResult":
        """验证引擎状态"""
        ...

    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        """是否已初始化"""
        ...


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    errors: list[str]
    warnings: list[str]

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(valid=True, errors=[], warnings=[])

    @classmethod
    def error(cls, *errors: str) -> "ValidationResult":
        return cls(valid=False, errors=list(errors), warnings=[])
```

## 基类实现

```python
from abc import ABC, abstractmethod
from typing import Generic
import logging

logger = logging.getLogger(__name__)


class BaseEngine(ABC, Generic[TConfig, TInput, TOutput]):
    """引擎基类：提供通用功能"""

    def __init__(self):
        self._config: TConfig | None = None
        self._initialized: bool = False
        self._name: str = self.__class__.__name__

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def config(self) -> TConfig:
        if self._config is None:
            raise RuntimeError(f"{self._name} not initialized")
        return self._config

    # ========== 公开方法 ==========

    def initialize(self, config: TConfig) -> None:
        """初始化引擎"""
        logger.info(f"Initializing {self._name}")

        # 验证配置
        self._validate_config(config)
        self._config = config

        # 子类钩子
        self._on_initialize()

        self._initialized = True
        logger.info(f"{self._name} initialized successfully")

    def process(self, data: TInput) -> TOutput:
        """处理数据"""
        if not self._initialized:
            raise RuntimeError(
                f"{self._name} not initialized. Call initialize() first."
            )

        logger.debug(f"{self._name} processing data")

        # 验证输入
        self._validate_input(data)

        # 执行处理
        result = self._do_process(data)

        # 验证输出
        self._validate_output(result)

        return result

    def validate(self) -> ValidationResult:
        """验证引擎状态"""
        errors = []
        warnings = []

        if not self._initialized:
            errors.append("Engine not initialized")

        # 子类扩展验证
        sub_result = self._do_validate()
        errors.extend(sub_result.errors)
        warnings.extend(sub_result.warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def reset(self) -> None:
        """重置引擎状态"""
        self._on_reset()
        self._config = None
        self._initialized = False
        logger.info(f"{self._name} reset")

    # ========== 子类必须实现 ==========

    @abstractmethod
    def _validate_config(self, config: TConfig) -> None:
        """验证配置（抛出 ValueError）"""
        ...

    @abstractmethod
    def _do_process(self, data: TInput) -> TOutput:
        """实际处理逻辑"""
        ...

    # ========== 子类可选覆盖 ==========

    def _on_initialize(self) -> None:
        """初始化后钩子"""
        pass

    def _on_reset(self) -> None:
        """重置前钩子"""
        pass

    def _validate_input(self, data: TInput) -> None:
        """验证输入数据"""
        pass

    def _validate_output(self, result: TOutput) -> None:
        """验证输出结果"""
        pass

    def _do_validate(self) -> ValidationResult:
        """子类扩展验证"""
        return ValidationResult.ok()
```

## 配置基类

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaseConfig:
    """配置基类"""

    def validate(self) -> None:
        """验证配置，无效则抛出 ValueError"""
        pass

    def to_dict(self) -> dict[str, Any]:
        """转为字典（用于序列化）"""
        return {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_")
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseConfig":
        """从字典创建"""
        return cls(**data)
```

## 结果基类

```python
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BaseResult:
    """结果基类"""

    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_metadata(self, key: str, value: Any) -> None:
        self.metadata[key] = value
```

## 引擎生命周期

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Created    │────▶│ Initialized │────▶│  Processing │
│             │     │             │     │             │
│ __init__()  │     │ initialize()│     │  process()  │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                   │
                           │    reset()        │
                           ◀───────────────────┘
```

### 状态检查

```python
# Good: 检查初始化状态
if not engine.is_initialized:
    engine.initialize(config)
result = engine.process(data)

# Bad: 不检查直接调用
result = engine.process(data)  # 可能 RuntimeError
```

## 引擎组合模式

### Pipeline 模式

```python
class EnginePipeline:
    """引擎流水线"""

    def __init__(self):
        self._engines: list[BaseEngine] = []

    def add(self, engine: BaseEngine) -> "EnginePipeline":
        self._engines.append(engine)
        return self

    def run(self, initial_data: Any) -> Any:
        """依次执行所有引擎"""
        data = initial_data
        for engine in self._engines:
            data = engine.process(data)
        return data


# 使用
pipeline = (
    EnginePipeline()
    .add(regime_engine)
    .add(factor_engine)
    .add(rotation_engine)
)
result = pipeline.run(market_data)
```

### 依赖注入模式

```python
class RotationEngine(BaseEngine):
    """轮动引擎：依赖因子引擎"""

    def __init__(self, factor_engine: FactorEngine):
        super().__init__()
        self._factor_engine = factor_engine

    def _do_process(self, data: MarketData) -> RotationResult:
        # 先计算因子
        factors = self._factor_engine.process(data)
        # 再做轮动选择
        return self._select_top_n(factors)
```

## 测试规范

### 每个引擎必须的测试

```python
class TestBaseEngine:
    """引擎基础测试模板"""

    def test_init_without_config(self, engine):
        """未初始化状态"""
        assert not engine.is_initialized

    def test_process_before_init_raises(self, engine):
        """未初始化调用 process 应报错"""
        with pytest.raises(RuntimeError, match="not initialized"):
            engine.process(mock_data)

    def test_initialize_with_valid_config(self, engine, valid_config):
        """有效配置初始化"""
        engine.initialize(valid_config)
        assert engine.is_initialized

    def test_initialize_with_invalid_config_raises(self, engine, invalid_config):
        """无效配置应报错"""
        with pytest.raises(ValueError):
            engine.initialize(invalid_config)

    def test_process_after_init(self, engine, valid_config, sample_data):
        """初始化后正常处理"""
        engine.initialize(valid_config)
        result = engine.process(sample_data)
        assert result is not None

    def test_reset(self, engine, valid_config):
        """重置后状态"""
        engine.initialize(valid_config)
        engine.reset()
        assert not engine.is_initialized

    def test_validate_initialized(self, engine, valid_config):
        """初始化后验证通过"""
        engine.initialize(valid_config)
        result = engine.validate()
        assert result.valid

    def test_validate_not_initialized(self, engine):
        """未初始化验证失败"""
        result = engine.validate()
        assert not result.valid
        assert "not initialized" in result.errors[0].lower()
```

## 日志规范

```python
import logging

# 引擎内使用模块级 logger
logger = logging.getLogger(__name__)

class MyEngine(BaseEngine):
    def _do_process(self, data):
        logger.debug(f"Processing {len(data)} rows")

        # 重要节点用 info
        logger.info(f"Computed {len(factors)} factors")

        # 异常情况用 warning
        if missing_data:
            logger.warning(f"Missing data for {missing_codes}")

        return result
```

## 禁止清单

| 禁止 | 原因 | 替代方案 |
|------|------|----------|
| 不继承 BaseEngine | 缺少通用保障 | 继承基类 |
| 跳过 initialize | 状态不确定 | 必须初始化 |
| process 中修改 config | 副作用 | config 应不可变 |
| 引擎持有外部状态 | 难以测试 | 通过参数传入 |
| 吞掉异常不抛出 | 隐藏问题 | 正确抛出或记录 |
| 硬编码参数 | 不可配置 | 放入 Config |
