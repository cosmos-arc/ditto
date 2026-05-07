# ADR 0008: 策略产物 I/O 分层

> **[历史参考]** 本文档记录架构演进过程中的决策，包名引用可能已过时。当前包名请参考 CLAUDE.md。

**状态**: 已接受
**日期**: 2026-04-13
**决策者**: 架构团队
**相关 ADR**: [ADR 0002](0002-monorepo-structure.md), [ADR 0006](0006-hybrid-plane-v2-accepted-deviations.md)

---

## 背景

App 层 `BacktestQueryFacade` 负责回测结果的查询编排。当前实现中，`get_report()` 和 `get_nav_series()` 方法包含直接文件 I/O：

```python
# packages/application/src/ditto_application/query/backtest.py

def get_report(self, run_id: str) -> dict[str, Any] | None:
    record = find_artifact(self._artifact_service, run_id)
    report_path = Path(record.file_path) / _REPORT_FILENAME
    if not report_path.exists():
        return None
    return orjson.loads(report_path.read_bytes())   # 直接 Path I/O

def get_nav_series(self, run_id: str) -> list[dict[str, object]]:
    record = find_artifact(self._artifact_service, run_id)
    nav_path = Path(record.file_path) / "nav.parquet"
    if not nav_path.exists():
        return []
    df = pl.read_parquet(nav_path)                   # 直接 Path I/O
    return df.to_dicts()
```

这违反了项目的分层架构原则：

| 问题 | 说明 |
|------|------|
| **App 层直接操作文件系统** | App 层是编排层，不应包含 I/O 实现细节 |
| **耦合了文件路径约定** | `backtest_report.json` / `nav.parquet` 的文件名硬编码在 App 层 |
| **难以替换存储后端** | 若将产物迁移到数据库或对象存储，需修改 App 层代码 |
| **违反 Data 层职责** | 数据读取应通过 Data 层服务完成 |

---

## 决策

文件读取下沉到 Data 层，引入 `BacktestArtifactReader` 服务及其 Protocol。App 层通过 Protocol 接口调用，不直接操作文件 I/O。

### Data 层：BacktestArtifactReaderProtocol + BacktestArtifactReader

```python
# packages/data/src/ditto_data/services/strategy/backtest_artifact_reader.py

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import orjson
import polars as pl

@runtime_checkable
class BacktestArtifactReaderProtocol(Protocol):
    """回测产物文件读取协议."""

    def read_json(self, file_path: str) -> dict[str, Any] | None:
        """读取 JSON 文件，不存在返回 None."""
        ...

    def read_parquet(self, file_path: str) -> pl.DataFrame | None:
        """读取 Parquet 文件，不存在返回 None."""
        ...

    def exists(self, file_path: str) -> bool:
        """检查文件是否存在."""
        ...


class BacktestArtifactReader:
    """回测产物文件读取服务 — 封装 JSON/Parquet 文件 I/O."""

    def read_json(self, file_path: str) -> dict[str, Any] | None:
        """读取 JSON 文件，文件不存在时返回 None."""
        path = Path(file_path)
        if not path.exists():
            return None
        return orjson.loads(path.read_bytes())

    def read_parquet(self, file_path: str) -> pl.DataFrame | None:
        """读取 Parquet 文件，文件不存在时返回 None."""
        path = Path(file_path)
        if not path.exists():
            return None
        return pl.read_parquet(path)

    def exists(self, file_path: str) -> bool:
        """检查文件是否存在."""
        return Path(file_path).exists()
```

**设计要点**：
- `BacktestArtifactReader` 是无状态服务，无 `__init__` 参数
- 接口按**文件类型**（`read_json` / `read_parquet`）而非**业务语义**（`read_report` / `read_nav_series`）设计，提升复用性
- 文件路径约定（文件名拼接）由 App 层的 `_build_path` 辅助函数管理

### App 层：通过 Protocol + find_artifact 编排调用

```python
# packages/application/src/ditto_application/query/backtest.py

from pathlib import Path

from ditto_data.services.strategy.backtest_artifact_reader import (
    BacktestArtifactReaderProtocol,
)
from ditto_application.query._artifact_utils import find_artifact

_REPORT_FILENAME = "backtest_report.json"


def _build_path(base: str, filename: str) -> str:
    """拼接产物目录与文件名，返回字符串路径."""
    return str(Path(base) / filename)


class BacktestQueryFacade:
    def __init__(
        self,
        trade_facade: BacktestTradeQueryFacade,
        run_model: RunReadModel,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        artifact_reader: BacktestArtifactReaderProtocol,
    ) -> None: ...

    def get_report(self, run_id: str) -> dict[str, Any] | None:
        run = self._run_model.get_run(run_id)
        if run is None:
            return None
        record = find_artifact(self._artifact_service, run_id)
        if record is None:
            return None
        report_path = _build_path(record.file_path, _REPORT_FILENAME)
        return self._artifact_reader.read_json(report_path)

    def get_nav_series(self, run_id: str) -> list[dict[str, object]]:
        record = find_artifact(self._artifact_service, run_id)
        if record is None:
            return []
        nav_path = _build_path(record.file_path, "nav.parquet")
        df = self._artifact_reader.read_parquet(nav_path)
        return df.to_dicts() if df is not None else []
```

**调用模式**：
1. `find_artifact()` 定位产物记录，获取 `file_path`
2. `_build_path()` 拼接目录与文件名
3. `artifact_reader.read_json()` / `read_parquet()` 执行实际 I/O

### 变更的依赖

| 变更的导入 | 说明 |
|-----------|------|
| `import orjson` → 移除 | JSON 反序列化下沉到 Data 层 |
| `import polars as pl` → 移除 | Parquet 读取下沉到 Data 层 |
| `from pathlib import Path` → 保留 | 用于 `_build_path` 辅助函数的路径拼接 |
| `BacktestArtifactReaderProtocol` → 新增 | App 层依赖 Protocol 接口，非具体实现 |

---

## 后果

### 积极面

- **职责更清晰**：App 层纯编排（路径拼接 + 记录定位），Data 层封装 I/O
- **I/O 实现可替换**：`BacktestArtifactReaderProtocol` 允许测试 mock 和未来存储后端替换
- **可测试性提升**：App 层测试可通过 Protocol mock `artifact_reader`，不依赖文件系统
- **通用文件接口**：`read_json` / `read_parquet` / `exists` 按文件类型设计，可被多个 App 查询复用

### 消极面

- **新增服务类 + Protocol**：代码量略增，但换来可测试性和可替换性
- **路径约定仍留在 App 层**：`_build_path` 和 `_REPORT_FILENAME` 在 App 层，产物文件名约定未完全集中到 Data 层
- **需更新 DI 注册**：`BacktestArtifactReader` 需在 DI 容器中注册并注入

## 实施偏差

ADR 设计阶段拒绝了 Protocol 方案（方案 C），但实施中引入了 `BacktestArtifactReaderProtocol`。偏差原因：

| 原因 | 说明 |
|------|------|
| **测试 mock 需求** | `BacktestQueryFacade` 的单元测试需要 mock `artifact_reader`，Protocol 是标准 mock 方式 |
| **`@runtime_checkable`** | Protocol 使用 `@runtime_checkable` 装饰器，支持 `isinstance` 检查，符合项目 Protocol 使用惯例 |
| **依赖倒置** | App 层依赖 Protocol 而非具体类，符合依赖倒置原则，即使当前只有一个实现 |

---

## 考虑的替代方案

### 方案 A：保持现状，添加注释

在 App 层文件 I/O 处添加注释说明"已知的分层偏离"。

**拒绝理由**：注释无法解决架构违规问题，违反项目的分层原则（CLAUDE.md 明确禁止 App 层直接 I/O）。

### 方案 B：将产物读取合并到 StrategyArtifactService

扩展现有 `StrategyArtifactService` 增加 `read_report()` / `read_nav_series()` 方法。

**拒绝理由**：`StrategyArtifactService` 的职责是产物元数据管理（记录定位、路径查询），读取产物内容是不同关注点。合并会导致职责膨胀。独立 `BacktestArtifactReader` 更符合单一职责原则。

### 方案 C：App 层定义 Protocol，Data 层实现

在 App 层定义 `ArtifactReaderProtocol`，Data 层提供实现。

**初始拒绝理由**：当前仅有一个实现，Protocol 引入过度设计。直接依赖具体类即可，未来需要替换时再提取 Protocol。

**实施偏差**：实际代码引入了 `BacktestArtifactReaderProtocol`（定义在 Data 层，非 App 层）。原因是 App 层单元测试需要 mock `artifact_reader`，Protocol 是标准 mock 方式。Protocol 定义在 Data 层而非 App 层，是因为它同时服务于 Data 层内部测试和其他消费方。详见上方"实施偏差"段落。

---

## 相关决策

- [ADR 0002 - Monorepo Structure](0002-monorepo-structure.md)：packages 分层架构基础
- [ADR 0006 - Hybrid Plane v2 已接受偏离 D2](0006-hybrid-plane-v2-accepted-deviations.md)：App 层 DI Provider 注册模式

---

**文档版本**: 1.1
**最后更新**: 2026-04-16
