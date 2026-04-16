# 审查修复计划 — Round 2

## 概述

- Sprint: V1 Sprint | Phase: 代码审查修复（第二轮）
- 创建: 2026-04-16
- 范围: 6 维度并行审查发现的 6 项问题全量修复
- 来源: `feat/v1-sprint` 当前 uncommitted diff

## 调研发现

### 额外发现：corporate_actions 列名不一致 Bug

调研 Issue 1（PIT 穿透）时发现 Writer/Reader 与 Schema DDL 列名不一致：

| 角色 | action_date 列 | effective 列 |
|------|---------------|-------------|
| Schema DDL | `action_date` | `effective_from` / `effective_to` |
| Writer INSERT | `announcement_date` | `effective_date` |
| Reader SELECT | `announcement_date` | `effective_date` |

DB 表已设计为 PIT 表（有 `knowledge_date`、`effective_from`/`effective_to` + PIT 索引），但 Reader 完全忽略 PIT 字段。

**根因推测**：DDL 后续更新了列名但 Writer/Reader 未同步（或反之）。需先验证实际 DB 列名再决定修复方向。

---

## 技术方案

### Task 1: corporate_actions as_of_date PIT 穿透 `[L]`

**风险加权**: PIT + Schema 变更 → 复杂度 +1

**修复范围**：全调用链 4 层 + 列名统一

#### Step 1.1: 验证 DB 实际列名

- 连接 testing 环境 SQLite，执行 `PRAGMA table_info(corporate_actions)`
- 确认实际列名是 DDL 版（`action_date`/`effective_from`/`effective_to`）还是 Writer 版（`announcement_date`/`effective_date`）
- **决策点**：根据验证结果决定修复方向

#### Step 1.2: 统一列名

- 如果 DB 使用 DDL 列名 → 修复 Writer/Reader 的列名引用
- 如果 DB 使用 Writer 列名 → 修复 DDL 的列名定义
- 更新 `schema.sql` 与实际代码保持一致
- **验收**: Writer INSERT + Reader SELECT 使用相同列名

#### Step 1.3: Reader 添加 PIT WHERE 条件

- `CorporateActionsReader.get` 签名增加 `as_of_date: date | None`
- 当 `as_of_date` 非 None 时，SQL 追加：
  ```sql
  AND effective_from <= ?
  AND (effective_to IS NULL OR effective_to > ?)
  ```
- 当 `as_of_date` 为 None 时保持当前行为（返回最新版本）
- **验收**: PIT 过滤正确生效

#### Step 1.4: Service/Facade/API 签名穿透

| 文件 | 修改 |
|------|------|
| `packages/data/src/ditto_data/services/fundamental_service.py` | `list_corporate_actions` 增加 `as_of_date` 参数 |
| `packages/app/src/ditto_app/query/fundamental.py` | `FundamentalQueryFacade.list_corporate_actions` 增加参数 |
| `interfaces/src/ditto_interfaces/api/routes/fundamental.py` | 调用 `fundamental_facade.list_corporate_actions(..., as_of_date=as_of_date)` |

**注意**: API 层 `as_of_date` 当前为 `Optional`，保持不变（与 `financials`/`dividend` 的必填设计不同，因为公司行动有时需要查询"全部历史"）。

#### Step 1.5: 测试

- Reader 单元测试：PIT 过滤 + None 回退
- Facade 单元测试：参数穿透
- **验收**: 新增测试通过

### Task 2: fundamental.py Request Model 重构 `[M]`

**目标**: 消除 `# noqa: PLR0913`，统一 3 个端点的参数模式

#### Step 2.1: 创建公共参数模型

新建 `interfaces/src/ditto_interfaces/api/params.py`：

```python
class InstrumentIdentifierParams(BaseModel):
    """标的标识符参数（三选一）."""
    instrument_id: int | None = Field(None, description="Canonical 标的 ID")
    ticker: str | None = Field(None, description="裸代码, 如 000001")
    standard_ticker: str | None = Field(None, description="标准代码, 如 000001.XSHE")

class PITQueryParams(InstrumentIdentifierParams):
    """PIT 查询参数."""
    as_of_date: date = Field(..., description="PIT 查询日期")

class DateRangeQueryParams(InstrumentIdentifierParams):
    """日期范围查询参数."""
    start_date: date = Field(..., description="开始日期")
    end_date: date = Field(..., description="结束日期")
    as_of_date: date | None = Field(None, description="PIT 查询日期（可选）")
```

#### Step 2.2: 重构 3 个端点

| 端点 | 原参数数 | 新 Params | 效果 |
|------|---------|-----------|------|
| `get_financials` | 6 | `PITQueryParams` | 3 → 2 参数 |
| `get_dividend` | 6 | `PITQueryParams` | 3 → 2 参数 |
| `list_corporate_actions` | 8 | `DateRangeQueryParams` | 4 → 2 参数 |

每个端点的 `resolve_identifier_for_api` 调用改为：
```python
resolved_id = resolve_identifier_for_api(
    metadata_facade,
    instrument_id=params.instrument_id,
    standard_ticker=params.standard_ticker,
    ticker=params.ticker,
    as_of_date=params.as_of_date,
    domain="fundamental",
)
```

#### Step 2.3: 测试

- 更新现有 API 测试中的参数传递
- 新增 `params.py` 单元测试（验证字段约束）
- **验收**: noqa 移除，所有测试通过

### Task 3: 测试 docstring 中文化 `[M]`

**文件**: `packages/engine/tests/unit/execution/test_brokerage_helpers_unit.py`

**范围**: 37 处英文 docstring/注释改为中文

| 类别 | 数量 | 示例 |
|------|------|------|
| 模块 docstring | 1 | `"""Tests for extracted..."""` → `"""撮合辅助函数单元测试..."""` |
| 分隔注释 | 4 | `# Helpers` → `# 辅助函数` |
| 类/函数 docstring | 20 | `"""BUY orders are executable..."""` → `"""买单在结算模型允许时可执行."""` |
| 行内注释 | 12 | `# Patch settlement_model` → `# 替换结算模型` |

**注意**: 不修改已有测试的 `assert` 消息（如有），仅改 docstring 和注释。

**验收**: `grep -c "[a-zA-Z]\{20\}" test_brokerage_helpers_unit.py` 仅在 import 语句中匹配

### Task 4: MagicMock 添加 spec `[S]`

**文件**: `packages/engine/tests/unit/execution/test_brokerage_helpers_unit.py`

| 行号 | 当前 | 修改为 |
|------|------|--------|
| 165 | `MagicMock()` | `MagicMock(spec=SettlementModel)` |
| 293 | `MagicMock()` | `MagicMock(spec=BrokerageModel)` |
| 360 | `MagicMock()` | `MagicMock(spec=BrokerageModel)` |
| 419 | `MagicMock()` | `MagicMock(spec=BrokerageModel)` |
| 460 | `MagicMock()` | `MagicMock(spec=BrokerageModel)` |

需新增 import：
```python
from ditto_engine.execution.reality.brokerage import BrokerageModel
```

`SettlementModel` 已在现有 import 中（`from ditto_engine.execution.reality.settlement import SimpleSettlementModel`），需确认 `SettlementModel` Protocol 的 import 路径。

**验收**: basedpyright 无新 warning

### Task 5: 文档修复 `[S]`

#### 5a: README 补充 ports.py

**文件**: `packages/app/README.md`

在 `process/ingestion/` 子目录列表中 `fetch_handlers.py` 之后添加：
```
│   │   ├── ports.py                # 摄取流程 Handler Protocol（解耦 command 依赖）
```

#### 5b: Plan 文档状态标注

**文件**: `docs/plans/2026-04-16-code-review-full-fixes.md`

标题添加 `[COMPLETED]` 标记，Task 1-10 状态改为 `[x]`。

### Task 6: 完整验证 `[S]`

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # importlinter 24 合约
```

**验收**: 全部通过，0 errors

---

## 执行顺序

```
Task 1 (PIT 穿透) ──────────────────┐
Task 2 (Request Model) ─────────────┤ 可并行
Task 3 (docstring 中文化) ──────────┤
Task 4 (MagicMock spec) ────────────┤
Task 5 (文档修复) ──────────────────┘
         │
         ▼
Task 6 (完整验证)
```

Task 1-5 之间无依赖，可并行执行。
Task 3 和 Task 4 修改同一文件，建议在同一 agent 中顺序执行。

## 统计

| Task | 复杂度 | 文件数 | 说明 |
|------|--------|--------|------|
| 1. PIT 穿透 | L | 5-6 | 含列名统一 + 全链路穿透 |
| 2. Request Model | M | 3-4 | 新建 params.py + 重构 3 端点 |
| 3. docstring 中文化 | M | 1 | 37 处文本替换 |
| 4. MagicMock spec | S | 1 | 5 处 + 1 import |
| 5. 文档修复 | S | 2 | 2 处小修改 |
| 6. 验证 | S | 0 | 运行检查命令 |
