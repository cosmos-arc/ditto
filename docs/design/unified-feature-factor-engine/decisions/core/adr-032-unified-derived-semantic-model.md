# ADR-032: 统一派生语义模型（Unified Derived Semantic Model）

**状态**: ✅ 已决策（2026-03-12）

---

## 背景

`DerivedSpec` 是统一特征/因子引擎的根抽象，影响 engine、catalog、query、publish、storage 全链路。

当前 `FeatureSpec` / `FactorSpec` 已有基础字段，但缺少关键的语义元数据字段，导致：
1. 实体标识语义不明确
2. 时间粒度和日历依赖隐含在代码中
3. 跨系统交互缺乏统一契约

本 ADR 定义 `DerivedSpec` 的完整字段模型。

---

## 决策记录

### D-1: entity_keys（实体键）

| 属性 | 值 |
|------|------|
| **字段类型** | `list[str]` |
| **默认值** | `["instrument_id"]` |
| **本期实现** | 单键模式（长度=1） |
| **复合键处理** | Spec 校验阶段报错："复合键已预留、暂未实现" |
| **扩展时机** | 后续有明确需求时再全链路改造（cache key、state key、表主键、接口） |

**决策理由**：
- 当前 Ditto 主路径围绕单一 `instrument_id` 展开
- 复合键涉及 cache key、state key、表主键、query/publish 接口的改造，范围过大
- `instrument_id` 本身是规范化后的唯一标识，复合键更像未来特殊实体类型的扩展能力
- 数据结构预留扩展性，但明确当前阶段边界

**代码示例**：
```python
@dataclass
class DerivedSpec(BaseModel):
    entity_keys: list[str] = Field(default=["instrument_id"])

    def validate(self) -> None:
        if len(self.entity_keys) != 1:
            raise NotImplementedError(
                f"复合键已预留、暂未实现: entity_keys={self.entity_keys}"
            )
```

---

### D-2: calendar（交易日历）

| 属性 | 值 |
|------|------|
| **字段类型** | `CalendarId = Literal["cn_stock"]` |
| **默认值** | `"cn_stock"` |
| **本期支持** | 仅 `cn_stock` |
| **扩展方式** | 未来 P2-1 时显式扩展 `CalendarId` 类型定义 |

**决策理由**：
- `calendar` 不是普通展示元数据，直接参与增量回溯、分区和多市场语义判断
- 当前只有 `cn_stock` 一个可用实现，允许任意字符串的收益小但静默错误风险大
- P2-1 "多市场日历支持" 已标记暂缓，新增市场值应通过显式代码变更开启
- 使用 `Literal` 提供类型安全和 IDE 自动补全

**代码示例**：
```python
from typing import Literal

CalendarId = Literal["cn_stock"]

@dataclass
class DerivedSpec(BaseModel):
    calendar: CalendarId = "cn_stock"
```

---

### D-3: grain + time_keys（时间粒度与时间键）

| 属性 | 值 |
|------|------|
| **GrainId 类型** | `Literal["1d", "1m"]` |
| **grain 字段** | 必填 |
| **time_keys 字段** | 可选，默认由 grain 推导 |
| **推导规则** | 见下表 |
| **校验规则** | 显式 time_keys 必须与 grain 兼容 |
| **本期实现** | 仅 `1d` 完整支持，`1m` 预留暂未实现 |

**grain → time_keys 推导规则**：

| grain | 默认 time_keys | 说明 |
|-------|----------------|------|
| `"1d"` | `["trade_date"]` | 日线 |
| `"1m"` | `["trade_date", "bar_time"]` | 分钟线（预留） |

**决策理由**：
- **grain 是频率概念**，不绑定具体列名 —— 1m/5m/15m/60m 可能共享 `["trade_date", "bar_time"]`，只是 bucket 不同
- **与现有模型对齐** —— Ditto 现有模型是 `trade_date + bar_time`，而非不存在的 `trade_datetime`
- **TimeSpec 语义分离** —— 时间语义（event_time / availability_time）本就不该由 grain 一把推死

**代码示例**：
```python
from typing import Literal

GrainId = Literal["1d", "1m"]

GRAIN_TO_TIME_KEYS: dict[GrainId, list[str]] = {
    "1d": ["trade_date"],
    "1m": ["trade_date", "bar_time"],
}

@dataclass
class DerivedSpec(BaseModel):
    grain: GrainId
    time_keys: list[str] | None = None

    def effective_time_keys(self) -> list[str]:
        return self.time_keys or GRAIN_TO_TIME_KEYS[self.grain]

    def validate(self) -> None:
        if self.grain == "1m":
            raise NotImplementedError(
                "grain='1m' 已预留、暂未实现"
            )
        # 显式 time_keys 需与 grain 兼容（本期可选校验）
        if self.time_keys:
            expected = GRAIN_TO_TIME_KEYS[self.grain]
            # 校验逻辑：至少包含预期键的超集
            ...
```

---

### D-4: timezone（时区）

| 属性 | 值 |
|------|------|
| **字段性质** | 只读计算属性（derived field） |
| **数据来源** | 由 `calendar` 推导 |
| **是否持久化** | 不持久化，可序列化输出 |
| **本期映射** | `cn_stock → Asia/Shanghai` |

**calendar → timezone 映射**：

| calendar | timezone |
|----------|----------|
| `"cn_stock"` | `"Asia/Shanghai"` |

**决策理由**：
- 仓库已有"市场 → 时区"映射，不是让调用方手填时区
- TimeSpec 中 timezone 更像 calendar 的从属属性，而非并列独立输入
- 系统层默认时区是 `Asia/Shanghai`，本期无多时区运行需求
- 作为 derived field 彻底避免 `cn_stock + America/New_York` 脏配置

**代码示例**：
```python
CALENDAR_TO_TIMEZONE: dict[CalendarId, str] = {
    "cn_stock": "Asia/Shanghai",
}

@dataclass
class DerivedSpec(BaseModel):
    calendar: CalendarId = "cn_stock"

    @property
    def timezone(self) -> str:
        """时区由日历推导，只读属性。"""
        return CALENDAR_TO_TIMEZONE[self.calendar]
```

**序列化说明**：
- catalog/接口层展示时可序列化输出 `effective_timezone`
- 但校验源头只有 `calendar`，timezone 不可外部传入

---

### D-5: 元数据字段分层

| 字段 | 归属 | 说明 |
|------|------|------|
| `description` | DerivedSpec 语义层 | 可选，提升人类可读性 |
| `owner` | Catalog 治理层 | 责任追溯，不放核心语义 |
| `created_at` | Catalog 治理层 | 系统生成，审计必需 |
| `updated_at` | **不加** | versioned spec 不可变，修改即新版本 |

**决策理由**：
- **语义与治理分层**：DerivedSpec 只承载计算语义契约，治理能力由 Catalog 层承担
- `description` 提升可读性，expression + id 对机器足够但对人通常不够
- `owner`/`created_at` 归 catalog 表治理字段，不是表达式语义本身
- `updated_at` 对不可变 versioned spec 传递错误信号，修改应产生新版本

---

### D-6: `DerivedSpec` 与研究数据集契约分层

| 对象 | 职责 | 是否在本 ADR 内定义 |
|------|------|------------------|
| `DerivedSpec` | 定义单个派生实体的计算语义、时间粒度、实体键与物化配置 | 是 |
| `SpineSpec` | 定义研究/训练左表与样本时点 | 否，见 ADR-041 |
| `ResearchDatasetSpec` | 定义多派生输入如何组成研究数据集 | 否，见 ADR-041 |
| `DatasetSnapshot` | 定义一次不可变数据集构建结果 | 否，见 ADR-041 |

**决策理由**：
- `DerivedSpec` 解决的是“单个派生定义的统一语义”，不是“研究数据集如何组装”
- `event_time / availability_time` 语义在本 ADR 中只做字段边界定义，真正的 `known_at` 与 left-preserving PIT join 契约由研究数据集模型承接
- 避免把数据集构建、左表选择、snapshot manifest 等跨实体职责硬塞进单个 spec 模型

---

## 完整 DerivedSpec 模型

```python
from typing import Literal
from datetime import date
from pydantic import BaseModel, Field

# 类型别名
DerivedRole = Literal["feature", "factor", "signal", "label"]
MaterializationProfile = Literal["SERIES", "STATE", "DERIVE", "OFFLINE"]
CalendarId = Literal["cn_stock"]
GrainId = Literal["1d", "1m"]

# 推导映射
GRAIN_TO_TIME_KEYS: dict[GrainId, list[str]] = {
    "1d": ["trade_date"],
    "1m": ["trade_date", "bar_time"],
}

CALENDAR_TO_TIMEZONE: dict[CalendarId, str] = {
    "cn_stock": "Asia/Shanghai",
}


class DerivedSpec(BaseModel):
    """统一派生语义模型 - 核心语义契约。"""

    # 标识
    id: str
    version: int

    # 角色与物化
    role: DerivedRole
    materialization_profile: MaterializationProfile

    # 表达式
    expression: str

    # 实体键（本期只支持单键）
    entity_keys: list[str] = Field(default=["instrument_id"])

    # 时间粒度与键
    grain: GrainId = "1d"
    time_keys: list[str] | None = None

    # 日历
    calendar: CalendarId = "cn_stock"

    # 可读性
    description: str | None = None

    # --- 计算属性 ---

    @property
    def effective_time_keys(self) -> list[str]:
        """时间键由 grain 推导，可显式覆盖。"""
        return self.time_keys or GRAIN_TO_TIME_KEYS[self.grain]

    @property
    def timezone(self) -> str:
        """时区由日历推导，只读属性。"""
        return CALENDAR_TO_TIMEZONE[self.calendar]

    # --- 校验 ---

    def validate_spec(self) -> None:
        """Spec 校验：本期边界约束。"""
        # 单键约束
        if len(self.entity_keys) != 1:
            raise NotImplementedError(
                f"复合键已预留、暂未实现: entity_keys={self.entity_keys}"
            )
        # grain 边界
        if self.grain == "1m":
            raise NotImplementedError("grain='1m' 已预留、暂未实现")
```

**Catalog 治理层字段**（存储于 `derived_spec` 表，非 DerivedSpec 本体）：

```sql
-- derived_spec 表（治理字段）
CREATE TABLE derived_spec (
    id TEXT NOT NULL,
    version INTEGER NOT NULL,
    spec_json TEXT NOT NULL,  -- DerivedSpec 序列化
    owner TEXT,               -- 责任人/团队
    created_at TEXT NOT NULL, -- 系统生成
    PRIMARY KEY (id, version)
);
```

---

## 待决策项

（无剩余待决策项）

---

## 影响范围

| 层级 | 影响 |
|------|------|
| **Core** | `specs.py` 模型定义、校验逻辑 |
| **DataHub** | Catalog 表结构、状态存储 key 设计 |
| **Port** | Facade 接口签名、DTO 定义 |
| **Infra** | 无直接影响 |

---

## 与其他 ADR 的关系

- **扩展**: ADR-024 因子版本管理（版本语义继承）
- **依赖**: ADR-006 增量计算（依赖 lookback/推导）
- **相关**: ADR-021 PIT 一致性（时间语义）
- **扩展**: ADR-041 Research Dataset / Spine / Availability-Time 契约

---

## 更新记录

### 2026-03-12

- 创建 ADR
- 决策 D-1: entity_keys 采用可配置单键或复合，本期只实现单键
- 决策 D-2: calendar 采用 Literal["cn_stock"] 枚举
- 决策 D-3: grain + time_keys 采用 grain 驱动 + time_keys 默认推导模式，1d → ["trade_date"]，1m → ["trade_date", "bar_time"]
- 决策 D-4: timezone 作为只读计算属性，由 calendar 推导，cn_stock → Asia/Shanghai
- 决策 D-5: 元数据字段分层 - description 归语义层，owner/created_at 归 Catalog 治理层，updated_at 不加
- 决策 D-6: `DerivedSpec` 只负责单实体语义，研究数据集契约由 ADR-041 承接
- **ADR 完成**：P0-1 DerivedSpec 完整字段模型已决策
