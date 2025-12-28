---
name: engine-template
description: 引擎开发模板。当开发 Engine 类时使用。
---

# 引擎开发指南

## 架构

```
RegimeEngine  → 市场状态
     ↓
FactorEngine  → 因子计算
     ↓
RotationEngine → 标的选择
     ↓
BacktestEngine → 策略验证
     ↓
RiskEngine    → 风险控制
```

---

## 协议

```python
class Engine(Protocol[TConfig, TInput, TOutput]):
    def initialize(self, config: TConfig) -> None: ...
    def process(self, data: TInput) -> TOutput: ...
    def validate(self) -> ValidationResult: ...
    @property
    def is_initialized(self) -> bool: ...
```

---

## 基类模板

```python
class MyEngine(BaseEngine[MyConfig, pl.DataFrame, MyResult]):
    
    def _validate_config(self, config: MyConfig) -> None:
        config.validate()

    def _validate_input(self, data: pl.DataFrame) -> None:
        required = {"code", "trade_date", "close"}
        missing = required - set(data.columns)
        if missing:
            raise ValueError(f"Missing: {missing}")

    def _do_process(self, data: pl.DataFrame) -> MyResult:
        data = data.sort(["code", "trade_date"])
        result = self._compute(data)
        return MyResult(data=result)
```

---

## 生命周期

```
Created → Initialized → Processing
__init__   initialize()   process()
              ↑              │
              └── reset() ───┘
```

---

## 必须的测试

```python
def test_not_initialized_raises(engine):
    with pytest.raises(RuntimeError):
        engine.process(data)

def test_invalid_config_raises(engine):
    with pytest.raises(ValueError):
        engine.initialize(invalid_config)

def test_process_returns_result(engine, config, data):
    engine.initialize(config)
    result = engine.process(data)
    assert result is not None
```

---

## 禁止

| 禁止 | 替代 |
|------|------|
| 不继承 BaseEngine | 继承基类 |
| 跳过 initialize | 必须初始化 |
| process 中改 config | config 不可变 |
