> **⚠️ Historical Document**: 本文档撰写于旧架构（engine/analytics/infra/interfaces）时期。
> 当前架构请参考 `CLAUDE.md` 和 `docs/architecture/` 下的活跃文档。
# ADR-024: 因子版本管理

**状态**: 已决策（2026-03-05）

---

## 背景

因子计算逻辑会随时间演进，需要一套版本管理机制来处理：
1. 因子逻辑变更后的历史数据如何处理
2. 多版本因子如何共存（A/B 测试场景）
3. 如何安全地切换和归档版本

参考了业界最佳实践：
- **MLflow Model Registry**: Stage 指针机制（Production/Staging/Archived）
- **Feast Feature Store**: Feature View 版本化 + Point-in-Time 正确性
- **Git 分支指针**: 可移动的引用，指向具体版本

---

## 核心概念

```
Factor Family（因子族）
    │
    ├── pe_ratio@v1  (status: active, online: false, primary: false)
    ├── pe_ratio@v2  (status: active, online: true,  primary: true)  ← primary 指针
    └── pe_ratio@v3  (status: draft,  online: false, primary: false)
```

**唯一标识**：`因子名@版本`，如 `pe_ratio@v2`

**状态维度**：

| 字段 | 说明 | 取值 |
|------|------|------|
| `status` | 生命周期状态 | draft / active / deprecated / archived |
| `online` | 显式上线状态 | true / false |
| `primary` | 查询默认指针 | true / false |
| `referenced_by` | 被引用列表 | ["strategy_alpha_001"] |

**指针语义**：
- `primary=true` 决定查询时的默认返回版本
- 同一因子族只能有一个 `primary=true`
- `primary` 不影响调度计算，仅影响查询默认值

---

## 调度与查询语义

| 操作 | 行为 |
|------|------|
| **默认调度** | 计算所有 `status != archived` 的因子 |
| **指定因子族** | `--id pe_ratio` 计算该族所有未归档版本 |
| **指定版本** | `--id pe_ratio@v2` 只计算 v2 |
| **查询默认** | `get_factor("pe_ratio")` 返回 primary 版本 |
| **查询版本** | `get_factor("pe_ratio@v1")` 返回 v1 |

---

## 可修改性约束

```
可以直接修改 ⇔ online == false 且 referenced_by 为空

可以下线 ⇔ referenced_by 为空
```

**约束矩阵**：

| online | referenced_by | 能直接修改 | 能下线 |
|--------|---------------|-----------|--------|
| false | 空 | ✅ | - |
| true | 有 | ❌ | ❌ 先解除引用 |
| true | 空 | ❌ | ✅ |

---

## 操作命令

```bash
# 新建版本
ditto factor create --id pe_ratio --expression "新公式"

# 直接修改（仅 draft 状态可用）
ditto factor update --id pe_ratio@v3 --expression "调整公式"

# 补数据（任意版本可独立执行）
ditto factor backfill --id pe_ratio@v3 --start 2024-01-01

# 上线
ditto factor online --id pe_ratio@v3

# 下线（需 referenced_by 为空）
ditto factor offline --id pe_ratio@v2

# 切换 primary 指针
ditto factor set-primary --id pe_ratio@v3

# 切换 + 同时下线旧版本
ditto factor set-primary --id pe_ratio@v3 --offline-old

# 归档（需 online=false）
ditto factor archive --id pe_ratio@v2
```

---

## 典型工作流

```
场景：v2 → v3 升级

Step 1: 创建 v3（draft 状态）
        ditto factor create --id pe_ratio --expression "close * market_cap / net_profit"

Step 2: 验证 v3（draft 可直接修改调整）
        ditto factor backfill --id pe_ratio@v3 --start 2024-01-01
        ditto factor validate --id pe_ratio@v3
        （反复调整直到满意）

Step 3: 上线 v3
        ditto factor online --id pe_ratio@v3

Step 4: 切换 primary
        ditto factor set-primary --id pe_ratio@v3
        # 或同时下线旧版本
        ditto factor set-primary --id pe_ratio@v3 --offline-old

Step 5: 归档 v2（可选）
        ditto factor offline --id pe_ratio@v2   # 如果之前没下线
        ditto factor archive --id pe_ratio@v2
        # 7天后自动删除 v2 数据
```

---

## 删除策略

- `status == archived` 的因子数据保留 **7 天**
- 7 天后自动清理（数据文件 + Catalog 记录）
- 可手动提前删除

---

## 数据模型

```python
class FactorVersion(BaseModel):
    entity_id: str           # "pe_ratio"
    version: int             # 2

    # 生命周期状态
    status: Literal["draft", "active", "deprecated", "archived"]
    online: bool             # 显式上线状态

    # 指针与引用
    primary: bool            # 是否是当前指针（仅影响查询默认值）
    referenced_by: list[str] # 手动声明的引用列表

    # Spec
    expression: str
    spec_hash: str

    # 元信息
    created_at: datetime
    created_by: str

    @property
    def full_id(self) -> str:
        return f"{self.entity_id}@v{self.version}"
```
