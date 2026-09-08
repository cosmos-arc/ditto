> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-031: State Snapshot ABI

**状态**: 已决策（2026-03-10）

---

## 背景

STATE 类因子（B 类）需要维护状态快照，支持：
1. 盘前从 Parquet 计算初始快照
2. 盘中增量更新快照
3. 快速读取最新状态

状态快照的存储格式需要平衡：
- **读取效率**：盘中主链路需要低延迟读取
- **扩展性**：不同因子可能有不同的状态结构
- **版本兼容**：状态格式演进时需要向前兼容

---

## 核心决策

| 决策项 | 决策 | 理由 |
|--------|------|------|
| 存储格式策略 | **Hash + Blob 双模式** | 简单状态用 Hash（高效），复杂状态用 Blob（灵活） |
| Key 命名规范 | `ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}` | 统一到 derived state namespace，并显式区分 per-instance snapshot |
| 版本兼容 | schema_ver 字段 | 支持状态格式演进 |

> **补充说明**: `ditto:derived:state:factor:{factor_id}` 根 key 由 Catalog/运行时控制面保留，用于 watermark、coverage、latest_run 等最新状态；本 ADR 只定义 `snapshot:{instrument_id}` 子空间中的快照 ABI。

---

## StateSnapshotStrategy 枚举

```python
# packages/kernel/src/ditto_kernel/specs.py

from enum import Enum

class StateSnapshotStrategy(str, Enum):
    """状态快照存储策略"""

    HASH = "HASH"  # 简单状态，用 Kvrocks Hash
    BLOB = "BLOB"  # 复杂状态，用版本化 blob

    @classmethod
    def auto_select(cls, data_fields: set[str]) -> "StateSnapshotStrategy":
        """根据数据字段自动选择策略"""
        simple_fields = {"value", "ts", "trade_date", "calc_ver"}

        if data_fields <= simple_fields:
            return cls.HASH
        return cls.BLOB
```

---

## HASH 模式（简单状态）

### Key 结构

```redis
ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}
```

### Hash 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `v` | float | 因子值 |
| `ts` | ISO8601 timestamp | 计算时间戳 |
| `td` | date | 交易日期 |
| `ver` | int | 计算版本号 |

### 示例

```redis
HSET ditto:derived:state:factor:alpha_001:snapshot:000001.SZ v 0.75 ts "2026-03-10T14:30:00.123Z" td "2026-03-10" ver 3

# 读取
HGETALL ditto:derived:state:factor:alpha_001:snapshot:000001.SZ
# => {"v": "0.75", "ts": "2026-03-10T14:30:00.123Z", "td": "2026-03-10", "ver": "3"}
```

### Python 读写

```python
# packages/data/src/ditto_data/stores/derived/kvrocks_state_writer.py

import orjson
from datetime import datetime, date

class KvrocksStateWriter:
    def __init__(self, client: Redis):
        self.client = client

    async def write_hash_state(
        self,
        factor_id: str,
        instrument_id: str,
        value: float,
        ts: datetime,
        trade_date: date,
        calc_ver: int,
    ) -> None:
        """写入简单状态（Hash 格式）"""
        key = (
            f"ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}"
        )

        await self.client.hset(key, mapping={
            "v": str(value),
            "ts": ts.isoformat(),
            "td": trade_date.isoformat(),
            "ver": str(calc_ver),
        })

    async def read_hash_state(
        self,
        factor_id: str,
        instrument_id: str,
    ) -> dict | None:
        """读取简单状态"""
        key = (
            f"ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}"
        )
        data = await self.client.hgetall(key)

        if not data:
            return None

        return {
            "value": float(data["v"]),
            "ts": datetime.fromisoformat(data["ts"]),
            "trade_date": date.fromisoformat(data["td"]),
            "calc_ver": int(data["ver"]),
        }

    async def batch_read_hash_states(
        self,
        factor_id: str,
        instrument_ids: list[str],
    ) -> dict[str, dict]:
        """批量读取（Pipeline 优化）"""
        pipe = self.client.pipeline()
        for sid in instrument_ids:
            key = f"ditto:derived:state:factor:{factor_id}:snapshot:{sid}"
            pipe.hgetall(key)

        results = await pipe.execute()

        return {
            sid: self._parse_hash_state(data)
            for sid, data in zip(instrument_ids, results)
            if data
        }
```

---

## BLOB 模式（复杂状态）

### Key 结构

```redis
ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}
```

### Blob JSON 结构

```json
{
    "schema_ver": 1,
    "factor_id": "alpha_001",
    "instrument_id": "000001.SZ",
    "serve_mode": "STATE",
    "ts": "2026-03-10T14:30:00.123Z",
    "trade_date": "2026-03-10",
    "calc_ver": 3,
    "data": {
        "value": 0.75,
        "long_term_mean": 0.6,
        "long_term_std": 0.15,
        "zscore": 1.0,
        "percentile": 84.5,
        "components": {
            "momentum": 0.3,
            "mean_reversion": 0.45
        }
    }
}
```

### Schema 版本演进

```python
# 版本 1：初始结构
class StateSnapshotV1(BaseModel):
    schema_ver: Literal[1] = 1
    factor_id: str
    instrument_id: str
    serve_mode: str
    ts: datetime
    trade_date: date
    calc_ver: int
    data: dict[str, Any]

# 版本 2：添加新字段（示例）
class StateSnapshotV2(BaseModel):
    schema_ver: Literal[2] = 2
    factor_id: str
    instrument_id: str
    serve_mode: str
    ts: datetime
    trade_date: date
    calc_ver: int
    data: dict[str, Any]
    # 新增字段
    lineage: list[str] = []  # 数据血缘

# 版本迁移
def migrate_snapshot(raw: bytes, target_ver: int) -> dict:
    """迁移快照到目标版本"""
    data = orjson.loads(raw)
    current_ver = data.get("schema_ver", 1)

    while current_ver < target_ver:
        data = _migrate_v1_to_v2(data) if current_ver == 1 else data
        current_ver += 1

    return data
```

### Python 读写

```python
# packages/data/src/ditto_data/stores/derived/kvrocks_state_writer.py

class KvrocksStateWriter:
    CURRENT_SCHEMA_VER = 2

    async def write_blob_state(
        self,
        factor_id: str,
        instrument_id: str,
        data: dict[str, Any],
        ts: datetime,
        trade_date: date,
        calc_ver: int,
        lineage: list[str] | None = None,
    ) -> None:
        """写入复杂状态（Blob 格式）"""
        key = (
            f"ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}"
        )

        snapshot = {
            "schema_ver": self.CURRENT_SCHEMA_VER,
            "factor_id": factor_id,
            "instrument_id": instrument_id,
            "serve_mode": "STATE",
            "ts": ts.isoformat(),
            "trade_date": trade_date.isoformat(),
            "calc_ver": calc_ver,
            "data": data,
        }

        if lineage:
            snapshot["lineage"] = lineage

        await self.client.set(key, orjson.dumps(snapshot))

    async def read_blob_state(
        self,
        factor_id: str,
        instrument_id: str,
    ) -> dict | None:
        """读取复杂状态"""
        key = (
            f"ditto:derived:state:factor:{factor_id}:snapshot:{instrument_id}"
        )
        raw = await self.client.get(key)

        if not raw:
            return None

        data = orjson.loads(raw)

        # 自动迁移到最新版本
        if data.get("schema_ver", 1) < self.CURRENT_SCHEMA_VER:
            data = migrate_snapshot(raw, self.CURRENT_SCHEMA_VER)
            # 回写迁移后的数据
            await self.client.set(key, orjson.dumps(data))

        return data

    async def batch_read_blob_states(
        self,
        factor_id: str,
        instrument_ids: list[str],
    ) -> dict[str, dict]:
        """批量读取（Pipeline 优化）"""
        pipe = self.client.pipeline()
        for sid in instrument_ids:
            key = f"ditto:derived:state:factor:{factor_id}:snapshot:{sid}"
            pipe.get(key)

        results = await pipe.execute()

        return {
            sid: orjson.loads(raw) if raw else None
            for sid, raw in zip(instrument_ids, results)
            if raw
        }
```

---

## 策略选择指南

### 何时用 HASH

- 因子值是单一标量
- 只需要基础元信息（ts, trade_date, ver）
- 盘中高频读取场景

### 何时用 BLOB

- 状态包含多个字段（如长期均值、标准差、分位数等）
- 需要存储结构化数据（如因子分解组件）
- 预期状态格式会演进

### 自动选择逻辑

```python
# packages/kernel/src/ditto_kernel/specs.py

class FactorSpec(BaseSpec):
    # ... 现有字段 ...

    state_snapshot_strategy: StateSnapshotStrategy | None = None

    def get_snapshot_strategy(self) -> StateSnapshotStrategy:
        """获取快照策略（自动或显式配置）"""
        if self.state_snapshot_strategy:
            return self.state_snapshot_strategy

        # 根据因子特征自动选择
        # 如果表达式包含长窗口聚合（> 60 天），通常需要存储中间状态
        if self._has_long_term_state():
            return StateSnapshotStrategy.BLOB

        return StateSnapshotStrategy.HASH

    def _has_long_term_state(self) -> bool:
        """检查是否需要长期状态"""
        # 检查表达式中的最大窗口
        analysis = analyze_expression(self.expression)
        return analysis.max_lookback > 60
```

---

## TTL 策略

| 策略 | TTL | 说明 |
|------|-----|------|
| HASH | 7 天 | latest snapshot 热状态，非唯一真相 |
| BLOB | 7 天 | 与 HASH 一致 |

**注意**：
- TTL 是 key 级别，不是 field 级别
- Value 中必须带 `ts` 和 `trade_date` 用于判断时效性
- TTL 只负责回收，不承担正确性或发布语义
- 过期后通过盘前初始化或显式 rebuild 重建

---

## FactorSpec 扩展

```python
# packages/kernel/src/ditto_kernel/specs.py

class FactorSpec(BaseSpec):
    id: str
    expression: str
    serve_mode: FactorServeMode = FactorServeMode.OFFLINE

    # STATE 模式专用
    state_snapshot_strategy: StateSnapshotStrategy | None = None
    state_schema_version: int = 1  # BLOB 模式的 schema 版本

    @property
    def state_key_pattern(self) -> str:
        """状态 Key 模式"""
        return (
            f"ditto:derived:state:factor:{self.id}:snapshot:{{instrument_id}}"
        )
```

---

## 批量操作优化

### 管道写入

```python
async def batch_write_states(
    self,
    factor_id: str,
    states: list[StateSnapshot],
    strategy: StateSnapshotStrategy,
) -> None:
    """批量写入状态（Pipeline 优化）"""
    pipe = self.client.pipeline()

    for state in states:
        key = (
            "ditto:derived:state:factor:"
            f"{factor_id}:snapshot:{state.instrument_id}"
        )

        if strategy == StateSnapshotStrategy.HASH:
            pipe.hset(key, mapping={
                "v": str(state.value),
                "ts": state.ts.isoformat(),
                "td": state.trade_date.isoformat(),
                "ver": str(state.calc_ver),
            })
        else:
            pipe.set(key, orjson.dumps(state.to_dict()))

    await pipe.execute()
```

### 模式匹配删除

```python
async def clear_factor_states(self, factor_id: str) -> int:
    """清除某个因子的所有状态"""
    pattern = f"ditto:derived:state:factor:{factor_id}:snapshot:*"
    keys = []
    async for key in self.client.scan_iter(match=pattern):
        keys.append(key)

    if keys:
        return await self.client.delete(*keys)
    return 0
```

---

## 相关 ADR

- [ADR-029: 盘中实时路径与盘后批量路径](../adr-029-intraday-postmarket-paths.md) - STATE 因子使用场景
- [ADR-010: Catalog 完整表结构与存储架构](../adr-010-catalog-schema.md) - Kvrocks Key 设计
- [ADR-030: Online Data Access Boundary](../adr-030-online-data-access-boundary.md) - 状态查询路径
