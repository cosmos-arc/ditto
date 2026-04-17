# 修复 app.process ↔ app.command 循环依赖

> **状态：已完成** (2026-04-11) — arch-check 24 kept, 0 broken; lint/type/test 全绿

## Context

importlinter 检测到 `ditto_app` 包内存在循环依赖：`process → command` 与 `command → process` 形成环路。
虽然 R8 规则允许双向依赖，但"无循环依赖"合约要求打破此环。

**循环链路分析：**

| 方向 | 文件 | 导入内容 | 类型 |
|------|------|---------|------|
| process→command | `range_process.py` | `IngestDateCommand` | 运行时 DTO |
| process→command | `coordinator.py` | `CheckDataQualityCommand` | 运行时 DTO |
| process→command | `config.py` | `CheckDataQualityHandler` | TYPE_CHECKING |
| process→command | `coordinator_factory.py` | `CheckDataQualityHandler` | TYPE_CHECKING |
| process→command | `range_process.py` | `IngestDateHandler` | TYPE_CHECKING |
| command→process | `command/ingestion.py` | `IngestionCoordinator` | TYPE_CHECKING |
| command→process | `command/trade.py` | `ManualTracker` | 运行时 |
| command→process | `command/trade.py` | DTO re-export shim | 运行时 |

**策略：** 消除 `process → command` 方向（提取 DTO + Protocol 反转），保留 `command → process`（R8 允许的单向依赖）。

## 修改计划

### Step 1: 创建 `ditto_app/contracts.py` — 共享 Command DTO

从 `command/ingestion.py` 和 `command/quality_check.py` 中提取被 process 使用的 DTO：

```python
# ditto_app/contracts.py
@dataclass(frozen=True) class IngestDateCommand: ...    # 从 command/ingestion.py 迁移
@dataclass(frozen=True) class CheckDataQualityCommand: ...  # 从 command/quality_check.py 迁移
```

其余 DTO（`IngestRangeCommand`, `BackfillRangeCommand`, `RecordFillCommand` 等）留在原处——它们不被 process 导入。

**文件：** `packages/app/src/ditto_app/contracts.py`（新建）

### Step 2: 创建 `process/ingestion/ports.py` — Handler Protocol

用 Protocol 替代 TYPE_CHECKING 对具体 Handler 类的依赖：

```python
# process/ingestion/ports.py
class IngestDateHandlerProtocol(Protocol):
    def handle(self, command: IngestDateCommand) -> IngestionResult: ...

class QualityCheckerProtocol(Protocol):
    def handle(self, command: CheckDataQualityCommand) -> tuple[pl.DataFrame, bool]: ...
```

DTO 从 `ditto_app.contracts` 导入（不经过 command）。

**文件：** `packages/app/src/ditto_app/process/ingestion/ports.py`（新建）

### Step 3: 更新 `command/ingestion.py`

- DTO `IngestDateCommand` 改为从 `ditto_app.contracts` 导入（不再本地定义）
- 保留 `IngestRangeCommand`, `BackfillRangeCommand`, `IngestDateHandler` 在原处

**文件：** `packages/app/src/ditto_app/command/ingestion.py`

### Step 4: 更新 `command/quality_check.py`

- DTO `CheckDataQualityCommand` 改为从 `ditto_app.contracts` 导入
- 保留 `CheckDataQualityHandler` 在原处

**文件：** `packages/app/src/ditto_app/command/quality_check.py`

### Step 5: 更新 `command/__init__.py` re-export

- `IngestDateCommand` 和 `CheckDataQualityCommand` 从 `ditto_app.contracts` 导入
- 其余不变

**文件：** `packages/app/src/ditto_app/command/__init__.py`

### Step 6: 更新 `process/ingestion/range_process.py`

- `from ditto_app.command.ingestion import IngestDateCommand` → `from ditto_app.contracts import IngestDateCommand`
- `TYPE_CHECKING: from ditto_app.command.ingestion import IngestDateHandler` → `from .ports import IngestDateHandlerProtocol`
- 构造函数参数类型 `IngestDateHandler` → `IngestDateHandlerProtocol`

**文件：** `packages/app/src/ditto_app/process/ingestion/range_process.py`

### Step 7: 更新 `process/ingestion/coordinator.py`

- `from ditto_app.command.quality_check import CheckDataQualityCommand` → `from ditto_app.contracts import CheckDataQualityCommand`

**文件：** `packages/app/src/ditto_app/process/ingestion/coordinator.py`

### Step 8: 更新 `process/ingestion/config.py`

- `TYPE_CHECKING: from ditto_app.command.quality_check import CheckDataQualityHandler` → `from .ports import QualityCheckerProtocol`
- 字段类型 `quality_checker: CheckDataQualityHandler | None` → `QualityCheckerProtocol | None`

**文件：** `packages/app/src/ditto_app/process/ingestion/config.py`

### Step 9: 更新 `process/ingestion/coordinator_factory.py`

- `TYPE_CHECKING: from ditto_app.command.quality_check import CheckDataQualityHandler` → `from .ports import QualityCheckerProtocol`
- 参数类型 `quality_checker: CheckDataQualityHandler | None` → `QualityCheckerProtocol | None`

**文件：** `packages/app/src/ditto_app/process/ingestion/coordinator_factory.py`

### Step 10: 清理 `command/trade.py` 的 re-export shim 导入

- `from ditto_app.process.execution.types import ...` → `from ditto_app.types import ...`
- 消除对 re-export shim 的不必要间接依赖

**文件：** `packages/app/src/ditto_app/command/trade.py`

### Step 11: 更新受影响的测试文件

测试中的 `from ditto_app.command.ingestion import IngestDateCommand` 等导入路径不变（`command/__init__.py` 仍 re-export）。但需确认以下测试文件无需修改：

- `packages/app/tests/unit/process/ingestion/test_range_process_unit.py` — 使用 `IngestDateHandler` mock，需检查是否改为 Protocol mock
- `packages/app/tests/unit/process/quality/test_service_unit.py` — 直接导入 `CheckDataQualityCommand`，路径不变

### Step 12: 验证

```bash
pixi run -e dev arch-check   # 循环依赖应消失
pixi run -e dev check        # lint + fmt + type + test 全绿
```

## 影响范围

| 变更类型 | 文件数 |
|---------|--------|
| 新建 | 2 (`contracts.py`, `ports.py`) |
| 修改源码 | 6 (command/ingestion, command/quality_check, command/__init__, command/trade, range_process, coordinator, config, coordinator_factory) |
| 修改测试 | ≤2 (可能需适配 Protocol mock) |

## 风险

- **Protocol 兼容性：** `CheckDataQualityHandler` 和 `IngestDateHandler` 的 `handle()` 方法签名必须与 Protocol 完全匹配。已验证一致。
- **re-export 链：** `command/__init__.py` re-export `IngestDateCommand` 从 `contracts`，消费者无感知。
