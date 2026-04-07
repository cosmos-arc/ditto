# ADR-030: Online Data Access Boundary

**状态**: 已决策（2026-03-10）

---

## 背景

盘中主链路（自动下单、自动风控、实时排序、信号触发）必须保证低延迟和高可用性。直接查询 Parquet 文件会带来以下问题：

1. **延迟不稳定**：Parquet 读取受磁盘 I/O 和文件大小影响
2. **并发受限**：多进程同时读取大文件可能导致资源竞争
3. **缓存未优化**：Parquet 不是为实时查询设计的

需要建立明确的在线数据访问边界，隔离 Parquet 访问，确保盘中主链路的稳定性。

---

## 核心原则

> **盘中主链路不查 Parquet；如果盘中需要一个原本在 Parquet 的因子，就把它升级成 SERIES/STATE/DERIVE。**

---

## 四层隔离保护

```
┌─────────────────────────────────────────────────────────────────┐
│                    第一层：接口隔离                              │
│                                                                  │
│  查询层（OnlineFactorQueryService）不直接暴露 Parquet 读取接口   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    第二层：运行时模式                            │
│                                                                  │
│  RuntimeMode: ONLINE | OFFLINE | DEGRADED                       │
│  ONLINE 模式下禁止 Parquet 读取                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    第三层：可观测性                              │
│                                                                  │
│  online_parquet_reads_total 指标记录所有 ONLINE 模式下的        │
│  Parquet 读取事件，触发告警                                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    第四层：显式降级                              │
│                                                                  │
│  ONLINE → DEGRADED 必须通过 CLI/API 显式触发                    │
│  记录降级原因、操作人、时间                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 第一层：接口隔离

### 查询服务设计

```python
# packages/data/src/ditto_data/services/factor_query_service.py

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import polars as pl

class RuntimeMode(str, Enum):
    """运行时模式"""
    ONLINE = "ONLINE"      # 盘中模式，禁止 Parquet 读取
    OFFLINE = "OFFLINE"    # 盘后/研究模式，允许 Parquet 读取
    DEGRADED = "DEGRADED"  # 降级模式，允许 Parquet 读取（需显式触发）

class OnlineFactorQueryService:
    """在线因子查询服务（盘中主链路）"""

    def __init__(self, runtime_mode: RuntimeMode = RuntimeMode.ONLINE):
        self.runtime_mode = runtime_mode
        self._parquet_reader = ParquetFactorReader()  # 内部持有，不对外暴露

    async def get_latest_values(
        self,
        factor_id: str,
        instrument_ids: list[str],
    ) -> dict[str, float]:
        """获取最新因子值

        只从 Kvrocks 读取，不访问 Parquet
        """
        return await self._kvrocks_reader.get_latest_values(factor_id, instrument_ids)

    async def get_time_series(
        self,
        factor_id: str,
        instrument_id: str,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """获取时间序列

        ONLINE 模式：只从 QuestDB 读取
        OFFLINE/DEGRADED 模式：可从 Parquet 读取
        """
        if self.runtime_mode == RuntimeMode.ONLINE:
            # ONLINE 模式强制走 QuestDB
            return await self._questdb_reader.read_factor_series(
                factor_id, instrument_id, start, end
            )
        else:
            # OFFLINE/DEGRADED 模式允许 Parquet
            return await self._read_with_fallback(factor_id, instrument_id, start, end)

    async def _read_with_fallback(
        self,
        factor_id: str,
        instrument_id: str,
        start: datetime,
        end: datetime,
    ) -> pl.DataFrame:
        """带可观测性的回退读取"""
        # 先尝试 QuestDB
        try:
            result = await self._questdb_reader.read_factor_series(
                factor_id, instrument_id, start, end
            )
            if len(result) > 0:
                return result
        except QuestDBError:
            pass

        # 回退到 Parquet（记录指标）
        self._record_parquet_read(factor_id, instrument_id)
        return await self._parquet_reader.read_factor_series(
            factor_id, instrument_id, start, end
        )

    def _record_parquet_read(self, factor_id: str, instrument_id: str) -> None:
        """记录 Parquet 读取事件"""
        online_parquet_reads_total.labels(
            runtime_mode=self.runtime_mode.value,
            factor_id=factor_id,
        ).inc()

        if self.runtime_mode == RuntimeMode.ONLINE:
            # ONLINE 模式下读取 Parquet 是异常，记录 ERROR
            logger.error(
                "Parquet read in ONLINE mode",
                extra={
                    "factor_id": factor_id,
                    "instrument_id": instrument_id,
                    "runtime_mode": self.runtime_mode.value,
                }
            )
        else:
            logger.info(
                "Parquet read in fallback mode",
                extra={
                    "factor_id": factor_id,
                    "instrument_id": instrument_id,
                    "runtime_mode": self.runtime_mode.value,
                }
            )
```

### 接口暴露控制

```python
# 只暴露 OnlineFactorQueryService，不暴露底层 Parquet 读取器
__all__ = [
    "OnlineFactorQueryService",
    "RuntimeMode",
]

# ParquetFactorReader 只在内部使用
# 禁止在 interfaces 的 API 层直接导入
```

---

## 第二层：运行时模式

### RuntimeMode 配置

```python
# config/production/settings.py

class ProductionSettings(BaseSettings):
    # 运行时模式配置
    RUNTIME_MODE: RuntimeMode = RuntimeMode.ONLINE

    # 允许的模式切换
    ALLOWED_MODE_TRANSITIONS: set[tuple[RuntimeMode, RuntimeMode]] = {
        (RuntimeMode.ONLINE, RuntimeMode.DEGRADED),    # ONLINE → DEGRADED
        (RuntimeMode.DEGRADED, RuntimeMode.ONLINE),    # DEGRADED → ONLINE
        (RuntimeMode.OFFLINE, RuntimeMode.ONLINE),     # OFFLINE → ONLINE
        (RuntimeMode.ONLINE, RuntimeMode.OFFLINE),     # ONLINE → OFFLINE
    }
```

### 模式切换验证

```python
class RuntimeModeManager:
    def __init__(self, settings: ProductionSettings):
        self.settings = settings
        self._current_mode = settings.RUNTIME_MODE
        self._mode_history: list[ModeTransition] = []

    async def switch_mode(
        self,
        target_mode: RuntimeMode,
        reason: str,
        operator: str,
    ) -> None:
        """切换运行时模式（需显式触发）"""
        current = self._current_mode

        # 验证允许的转换
        if (current, target_mode) not in self.settings.ALLOWED_MODE_TRANSITIONS:
            raise InvalidModeTransitionError(
                f"Transition from {current} to {target_mode} not allowed"
            )

        # 记录历史
        transition = ModeTransition(
            from_mode=current,
            to_mode=target_mode,
            reason=reason,
            operator=operator,
            timestamp=datetime.now(),
        )
        self._mode_history.append(transition)

        # 执行切换
        self._current_mode = target_mode

        # 更新全局状态
        await self._notify_mode_change(target_mode)

        logger.warning(
            f"Runtime mode switched: {current} → {target_mode}",
            extra={
                "reason": reason,
                "operator": operator,
            }
        )
```

---

## 第三层：可观测性

### Prometheus 指标

```python
# packages/infra/src/ditto_infra/metrics/factor_metrics.py

from prometheus_client import Counter, Histogram

# 在线模式下 Parquet 读取计数
online_parquet_reads_total = Counter(
    "ditto_online_parquet_reads_total",
    "Total number of Parquet reads in online mode",
    ["runtime_mode", "factor_id"],
)

# Parquet 读取延迟
parquet_read_latency_seconds = Histogram(
    "ditto_parquet_read_latency_seconds",
    "Latency of Parquet reads",
    ["factor_id"],
)

# 运行时模式变更计数
runtime_mode_changes_total = Counter(
    "ditto_runtime_mode_changes_total",
    "Total number of runtime mode changes",
    ["from_mode", "to_mode"],
)
```

### 告警规则

```yaml
# deploy/derived/prometheus/alerts.yml

groups:
  - name: ditto_online_boundary
    rules:
      - alert: OnlineParquetRead
        expr: sum(rate(ditto_online_parquet_reads_total{runtime_mode="ONLINE"}[5m])) > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Parquet read in ONLINE mode"
          description: "Parquet was read in ONLINE mode, indicating potential performance issue or misconfiguration"

      - alert: FrequentDegradedMode
        expr: sum(rate(ditto_runtime_mode_changes_total{to_mode="DEGRADED"}[1h])) > 3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Frequent degraded mode switches"
          description: "Runtime mode switched to DEGRADED more than 3 times in the last hour"
```

---

## 第四层：显式降级

### 降级触发方式

```python
# interfaces/src/ditto_interfaces/cli/commands/runtime.py

import click

@click.group()
def runtime():
    """运行时模式管理"""
    pass

@runtime.command()
@click.option("--reason", required=True, help="降级原因")
@click.option("--operator", default="cli", help="操作人")
def degrade(reason: str, operator: str) -> None:
    """切换到降级模式

    显式降级，允许 ONLINE → DEGRADED
    """
    manager = get_runtime_mode_manager()

    manager.switch_mode(
        target_mode=RuntimeMode.DEGRADED,
        reason=reason,
        operator=operator,
    )

    click.echo(f"Switched to DEGRADED mode: {reason}")

@runtime.command()
@click.option("--operator", default="cli", help="操作人")
def restore(operator: str) -> None:
    """恢复到在线模式

    DEGRADED → ONLINE
    """
    manager = get_runtime_mode_manager()

    manager.switch_mode(
        target_mode=RuntimeMode.ONLINE,
        reason="Manual restore",
        operator=operator,
    )

    click.echo("Restored to ONLINE mode")
```

### API 端点（受限访问）

```python
# interfaces/src/ditto_interfaces/api/routes/runtime.py

from fastapi import APIRouter, Depends, HTTPException
from ditto_infra.auth import require_admin

router = APIRouter(prefix="/runtime", tags=["runtime"])

@router.post("/degrade")
async def degrade_mode(
    reason: str,
    operator: str = Depends(require_admin),
) -> dict:
    """切换到降级模式（需管理员权限）"""
    manager = get_runtime_mode_manager()

    await manager.switch_mode(
        target_mode=RuntimeMode.DEGRADED,
        reason=reason,
        operator=operator,
    )

    return {"status": "degraded", "reason": reason}

@router.post("/restore")
async def restore_mode(
    operator: str = Depends(require_admin),
) -> dict:
    """恢复到在线模式（需管理员权限）"""
    manager = get_runtime_mode_manager()

    await manager.switch_mode(
        target_mode=RuntimeMode.ONLINE,
        reason="Manual restore",
        operator=operator,
    )

    return {"status": "online"}
```

---

## 场景矩阵

### 盘中主链路（ONLINE 模式）

| 场景 | Parquet | QuestDB | Kvrocks | 说明 |
|------|---------|---------|---------|------|
| 自动下单 | ❌ | ✅ | ✅ | 只查热层 |
| 自动风控 | ❌ | ✅ | ✅ | 只查热层 |
| 实时排序 | ❌ | ✅ | ✅ | 只查热层 |
| 信号触发 | ❌ | ✅ | ✅ | 只查热层 |

### 盘后/研究（OFFLINE 模式）

| 场景 | Parquet | QuestDB | Kvrocks | 说明 |
|------|---------|---------|---------|------|
| 盘前预计算 | ✅ | ❌ | ❌ | 读取历史，计算快照 |
| 盘后重算 | ✅ | ❌ | ❌ | 全量重算 |
| 审计对拍 | ✅ | ✅ | ✅ | 多源对比 |
| 人工研究 | ✅ | ❌ | ❌ | Parquet 优先 |

### 故障降级（DEGRADED 模式）

| 场景 | Parquet | QuestDB | Kvrocks | 说明 |
|------|---------|---------|---------|------|
| QuestDB 故障 | ✅ | ❌ | ✅ | 降级读取 Parquet |
| Kvrocks 故障 | ✅ | ✅ | ❌ | 现算替代 |
| 全热层故障 | ✅ | ❌ | ❌ | 纯 Parquet 模式 |

---

## 相关 ADR

- [ADR-026: DuckDB 定位与使用规范](storage/adr-026-duckdb-positioning.md) - DuckDB 可用于审计对拍
- [ADR-028: QuestDB 热表与物化视图 DDL](storage/adr-028-questdb-hot-tables.md) - 热层存储
- [ADR-029: 盘中实时路径与盘后批量路径](adr-029-intraday-postmarket-paths.md) - 因子分级模型
- [ADR-017: 服务层与 API 设计](adr-017-service-layer-api.md) - API 权限控制
- [ADR-018: 可观测性与监控](adr-018-observability-monitoring.md) - 指标与告警
