# ADR 0009: 影响模型 ImpactModel 治理

> **[历史参考]** 本文档记录架构演进过程中的决策，包名引用可能已过时。当前包名请参考 CLAUDE.md。

**状态**: 已接受
**日期**: 2026-04-13
**决策者**: 架构团队
**相关 ADR**: [ADR 0006](0006-hybrid-plane-v2-accepted-deviations.md)

---

## 背景

`ImpactModel` 定义回测中冲击成本模型的合法值，涉及两层契约：

1. **Strategy 层**：`ditto_strategy.alpha.specs.ImpactModel = Literal["none", "volume_share"]`
2. **Apps 层**：`ditto_apps.models.backtest.CostConfigRequest.impact_model`

在 App 层反序列化时，`_normalize_impact_model()` 负责将 API 输入规范化为 Engine 层合法值。

此前存在两个问题：

| 问题 | 说明 | 影响 |
|------|------|------|
| **非法值静默回退** | `_normalize_impact_model()` 对不在白名单中的值回退为 `"none"` | 用户配置错误（如拼写错误）被隐藏，回测结果偏离预期 |
| **测试夹具使用废弃值** | 测试中使用 `"flat"`、`"linear"` 等废弃模型值 | 掩盖了生产代码与测试代码的不一致 |

---

## 决策

### 决策 1：非法值统一抛 ValueError

`_normalize_impact_model()` 对非 `None` 且不在白名单中的值，统一抛出 `ValueError`：

```python
# packages/application/src/ditto_application/builders/runtime_builder.py

def _normalize_impact_model(raw: str | None) -> ImpactModel:
    """将 impact_model 字符串规范化为 ImpactModel 合法值."""
    if raw is None:
        return "none"
    if raw in ("none", "volume_share"):
        return raw
    msg = f"非法 impact_model 值: {raw!r}, 合法值: 'none', 'volume_share'"
    raise ValueError(msg)
```

**行为变更**：

| 输入值 | 旧行为 | 新行为 |
|--------|--------|--------|
| `None` | `"none"` | `"none"`（不变） |
| `"none"` | `"none"` | `"none"`（不变） |
| `"volume_share"` | `"volume_share"` | `"volume_share"`（不变） |
| `"flat"` | `"none"`（静默回退） | `ValueError`（拒绝） |
| `"linear"` | `"none"`（静默回退） | `ValueError`（拒绝） |

### 决策 2：合法值限定为 "none" 和 "volume_share"

`ImpactModel` 类型定义收窄为 `Literal["none", "volume_share"]`，同时在 Interfaces 层 `CostConfigRequest` 的 Pydantic 模型中通过 `Literal` 类型约束确保 API 层即拒绝非法值：

```python
# apps/backend/src/ditto_apps/models/backtest.py

class CostConfigRequest(BaseModel):
    impact_model: ImpactModel = Field(
        default="none",
        description="冲击成本模型",
    )
```

三层防线：

| 层级 | 机制 | 效果 |
|------|------|------|
| **Interfaces (Pydantic)** | `ImpactModel = Literal[...]` | API 请求阶段拒绝非法值，返回 422 |
| **App (_normalize_impact_model)** | 白名单 + `ValueError` | 反序列化阶段兜底校验 |
| **Engine (CostModelSpec)** | `impact_model: ImpactModel` | 类型系统保证，编译期约束 |

### 决策 3：测试夹具清除废弃值

所有测试夹具中 `impact_model` 仅使用 `"none"` 或 `"volume_share"`，删除 `"flat"`、`"linear"` 等废弃值。

---

## 后果

### 积极面

- **更早暴露配置错误**：非法值在 API 层（422）或反序列化时（ValueError）即被拒绝，而非静默回退
- **测试与生产一致**：测试夹具仅使用合法值，消除"测试通过但生产异常"的风险
- **类型安全**：`Literal` 类型在 basedpyright 编译期即可检测非法赋值
- **可扩展**：新增模型值（如 `"square_root"`）仅需修改 `Literal` 定义 + 白名单

### 消极面

- **向后不兼容**：此前使用 `"flat"` / `"linear"` 的配置文件或 API 调用将报错。但这些值从未有实际实现，属于无效配置
- **需更新文档**：API 文档需明确说明 `impact_model` 的合法枚举值

---

## 考虑的替代方案

### 方案 A：保持静默回退 + 添加 warning 日志

对非法值记录 warning 日志并回退为 `"none"`。

**拒绝理由**：warning 日志在异步 API 场景中容易被忽略。配置错误应 fail-fast，而非产生"看起来正常但结果不准"的回测。

### 方案 B：废弃值映射表

维护 `"flat" -> "none"`, `"linear" -> "volume_share"` 的映射表。

**拒绝理由**：这些值从未有实际实现，映射表会暗示它们曾经有效，增加维护负担。

### 方案 C：仅在 Engine 层校验

移除 App 层的 `_normalize_impact_model()`，依赖 Engine 层 `Literal` 类型约束。

**拒绝理由**：`Literal` 在运行时不做校验（Python 的 typing 仅提供类型注解），需要在运行时显式检查。三层防线各有职责，不可互相替代。

---

## 相关决策

- [ADR 0006 - Hybrid Plane v2 已接受偏离 D7](0006-hybrid-plane-v2-accepted-deviations.md)：Engine 层 `CostModelSpec` 与 App 层 `CostConfigRequest` 的契约对齐

---

**文档版本**: 1.0
**最后更新**: 2026-04-13
