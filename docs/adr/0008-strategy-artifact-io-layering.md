# ADR 0008: 策略产物 I/O 分层

**状态**: 已接受
**日期**: 2026-04-13
**决策者**: 架构团队
**相关 ADR**: [ADR 0002](0002-monorepo-structure.md), [ADR 0006](0006-hybrid-plane-v2-accepted-deviations.md)

---

## 背景

App 层 `BacktestQueryFacade` 负责回测结果的查询编排。当前实现中，`get_report()` 和 `get_nav_series()` 方法包含直接文件 I/O：

```python
# packages/app/src/ditto_app/query/backtest.py

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

文件读取下沉到 Data 层，引入 `BacktestArtifactReader` 服务。App 层通过服务接口调用，不直接操作 `Path`。

### Data 层：BacktestArtifactReader

```python
# packages/data/src/ditto_data/services/strategy/backtest_artifact_reader.py

class BacktestArtifactReader:
    """回测产物文件读取服务 — Data 层封装所有文件 I/O."""

    def __init__(self, artifact_service: StrategyArtifactService) -> None: ...

    def read_report(self, run_id: str) -> dict[str, Any] | None:
        """读取 backtest_report.json."""
        ...

    def read_nav_series(self, run_id: str) -> list[dict[str, object]]:
        """读取 nav.parquet，返回字典列表."""
        ...
```

### App 层：通过服务接口调用

```python
# packages/app/src/ditto_app/query/backtest.py

class BacktestQueryFacade:
    def __init__(
        self,
        trade_facade: BacktestTradeQueryFacade,
        run_model: RunReadModel,
        audit_service: ExecutionAuditService,
        artifact_service: StrategyArtifactService,
        artifact_reader: BacktestArtifactReader,  # 新增
    ) -> None: ...

    def get_report(self, run_id: str) -> dict[str, Any] | None:
        return self._artifact_reader.read_report(run_id)

    def get_nav_series(self, run_id: str) -> list[dict[str, object]]:
        return self._artifact_reader.read_nav_series(run_id)
```

### 删除的依赖

| 删除的导入 | 原因 |
|-----------|------|
| `from pathlib import Path` | App 层不再直接操作文件路径 |
| `import orjson` | JSON 反序列化下沉到 Data 层 |
| `import polars as pl` | Parquet 读取下沉到 Data 层 |

---

## 后果

### 积极面

- **职责更清晰**：App 层纯编排，Data 层封装 I/O
- **文件约定集中管理**：产物文件名约定仅在 Data 层定义
- **可测试性提升**：`BacktestArtifactReader` 可独立 mock，App 层测试不依赖文件系统
- **存储后端可替换**：未来迁移到数据库或对象存储仅需修改 Data 层

### 消极面

- **新增一个服务类**：代码量略增（约 30-40 行），但换来更清晰的职责边界
- **需更新 DI 注册**：`BacktestArtifactReader` 需在 DI 容器中注册并注入

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

**拒绝理由**：当前仅有一个实现，Protocol 引入过度设计。直接依赖具体类即可，未来需要替换时再提取 Protocol。

---

## 相关决策

- [ADR 0002 - Monorepo Structure](0002-monorepo-structure.md)：packages 分层架构基础
- [ADR 0006 - Hybrid Plane v2 已接受偏离 D2](0006-hybrid-plane-v2-accepted-deviations.md)：App 层 DI Provider 注册模式

---

**文档版本**: 1.0
**最后更新**: 2026-04-13
