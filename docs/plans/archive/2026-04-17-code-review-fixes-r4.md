# Code Review 全量修复计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 6 维度并行审查发现的 14 项阻塞问题 + 3 项建议改进

**Context:** `feat/v1-sprint` 分支的 corporate_actions PIT 支持变更中，Writer/Reader 已改为新列名（`action_date`/`knowledge_date`/`effective_from`/`effective_to`），但上游 Source 层（Mapping/Schema/DQ Rules/Adapter）仍使用旧列名（`announcement_date`/`effective_date`），导致数据管道断裂（运行时 KeyError）。

---

## Task 总览

| # | Phase | 任务 | 复杂度 | 文件 |
|---|-------|------|--------|------|
| 1 | P0 | CORPporate_ACTIONS_MAPPING 列名对齐 | M | capital.py (mappings) |
| 2 | P0 | CORPORATE_ACTIONS_SOURCE_SCHEMA 对齐 | S | capital_schemas.py |
| 3 | P0 | DQ 规则列名对齐 | S | corporate_actions.yml |
| 4 | P0 | Adapter docstring 更新 | S | capital.py (adapter) |
| 5 | P0 | critical_fields 列名对齐 | S | config.py |
| 6 | P0 | Adapter 测试断言更新 | S | test_capital_adapter_unit.py |
| 7 | P0 | FundamentalService 测试 mock 数据更新 | S | test_fundamental_service.py |
| 8 | P1 | Reader `if start_date:` → `is not None` | S | corporate_actions_reader.py |
| 9 | P1 | `InstrumentIdentifierParams` 重命名 | M | params.py + fundamental.py |
| 10 | P1 | Writer 测试 `mocker: Mock` 类型修复 | S | test_corporate_actions_writer_unit.py |
| 11 | P2 | PIT 测试添加 `@pytest.mark.pit` | S | test_corporate_actions_reader_unit.py |

---

## Phase 1: P0 — 数据管道列名断裂修复

### Task 1 [M]: CORPporate_ACTIONS_MAPPING 列名对齐

**文件:** `packages/data/src/ditto_data/sources/tushare/processors/mappings/capital.py:130-148`

**修改内容:**

```python
CORPORATE_ACTIONS_MAPPING = ColumnMapping(
    rename={
        "ts_code": "source_ticker",
        "ba_type": "action_type",
        "ann_date": "action_date",        # announcement_date → action_date
        "act_date": "effective_from",      # effective_date → effective_from
        "name": "description",
    },
    date_columns={"action_date": "%Y%m%d", "effective_from": "%Y%m%d"},
    float_columns=[],
    computed_columns={
        "knowledge_date": pl.col("action_date"),  # 公告日 = 知识日
        "effective_to": pl.lit(None, dtype=pl.Date),  # 首版无失效日期
    },
    output_columns=(
        "source_ticker",
        "action_type",
        "action_date",
        "knowledge_date",
        "effective_from",
        "effective_to",
        "description",
    ),
)
```

**验证:** `pixi run -e dev pytest packages/data/tests/unit/sources/tushare/test_capital_adapter_unit.py -k "corporate" -x`

### Task 2 [S]: CORPORATE_ACTIONS_SOURCE_SCHEMA 对齐

**文件:** `packages/data/src/ditto_data/sources/schemas/capital_schemas.py:182-193`

**修改内容:**

```python
CORPORATE_ACTIONS_SOURCE_SCHEMA = SourceSchema(
    dataset="corporate_actions",
    key_columns=("instrument_id", "action_type", "action_date"),
    schema={
        "instrument_id": pl.String,
        "action_type": pl.String,
        "action_date": pl.Date,
        "knowledge_date": pl.Date,
        "effective_from": pl.Date,
        "effective_to": pl.Date,
        "description": pl.String,
    },
    pit_columns=("effective_from", "effective_to"),
)
```

**验证:** Schema 加载无报错

### Task 3 [S]: DQ 规则列名对齐

**文件:** `config/default/dq_rules/corporate_actions.yml`

**修改内容:**
- L8: `columns: [instrument_id, action_type, action_date]`
- L12: `columns: [instrument_id, action_type, action_date]`
- L13: message 中 `announcement_date` → `action_date`
- L21-26: type_check columns 替换为 `action_date: date`, `knowledge_date: date`, `effective_from: date`, `effective_to: date`

### Task 4 [S]: Adapter docstring 更新

**文件:** `packages/data/src/ditto_data/sources/tushare/adapters/capital.py:522-528`

**修改内容:** Returns 段落列名替换为 `action_date`/`knowledge_date`/`effective_from`/`effective_to`

### Task 5 [S]: critical_fields 列名对齐

**文件:** `packages/app/src/ditto_app/config.py:512`

**修改内容:** `"effective_date"` → `"action_date"`

### Task 6 [S]: Adapter 测试断言更新

**文件:** `packages/data/tests/unit/sources/tushare/test_capital_adapter_unit.py`

**修改内容:**
- L230: `"announcement_date"` → `"action_date"`，新增 `knowledge_date`/`effective_from`/`effective_to` 断言
- L262-263: 同上（share_buyback 相关断言）
- L319: 同上（rights_issue 相关断言）

**验证:** `pixi run -e dev pytest packages/data/tests/unit/sources/tushare/test_capital_adapter_unit.py -x`

### Task 7 [S]: FundamentalService 测试 mock 数据更新

**文件:** `packages/data/tests/unit/services/test_fundamental_service.py:259`

**修改内容:** `"announcement_date": [date(2024, 1, 1)]` → `"action_date": [date(2024, 1, 1)]`

---

## Phase 2: P1 — 正确性缺陷修复

### Task 8 [S]: Reader falsy 检查修复

**文件:** `packages/data/src/ditto_data/storage/fundamental/corporate/corporate_actions_reader.py:76,80`

**修改内容:**
- L76: `if start_date:` → `if start_date is not None:`
- L80: `if end_date:` → `if end_date is not None:`

**验证:** `pixi run -e dev pytest packages/data/tests/unit/storage/fundamental/corporate/ -x`

### Task 9 [M]: InstrumentIdentifierParams 重命名

**文件:** `interfaces/src/ditto_interfaces/api/params.py`

**修改内容:**
- L8: `class InstrumentIdentifierParams` → `class InstrumentIdentifierQuery`
- L9: docstring `标的标识符参数` → `标的标识符查询`
- L18: `PITQueryParams(InstrumentIdentifierParams)` → `PITQueryParams(InstrumentIdentifierQuery)`
- L24: `DateRangeQueryParams(InstrumentIdentifierParams)` → `DateRangeQueryParams(InstrumentIdentifierQuery)`

**文件:** `interfaces/src/ditto_interfaces/api/routes/fundamental.py`
- 无需修改（导入的是子类 `PITQueryParams`/`DateRangeQueryParams`，未直接引用基类名）

**验证:** `pixi run -e dev pytest interfaces/tests/ -x`

### Task 10 [S]: Writer 测试 mocker 类型修复

**文件:** `packages/data/tests/unit/storage/fundamental/corporate/test_corporate_actions_writer_unit.py`

**修改内容:**
- 删除 `from unittest.mock import Mock`（L7）
- 所有 `mocker: Mock,` → `mocker: MockerFixture,`（7 处）
- 添加 `from pytest_mock import MockerFixture` 到 import 区域

**验证:** `pixi run -e dev pytest packages/data/tests/unit/storage/fundamental/corporate/test_corporate_actions_writer_unit.py -x`

---

## Phase 3: P2 — 测试规范

### Task 11 [S]: PIT 测试添加 @pytest.mark.pit

**文件:** `packages/data/tests/unit/storage/fundamental/corporate/test_corporate_actions_reader_unit.py:313`

**修改内容:** 在 `@pytest.mark.unit` 下方添加 `@pytest.mark.pit`

**验证:** `pixi run -e dev pytest packages/data/tests/unit/storage/fundamental/corporate/ -m pit -x`

---

## 执行顺序

```
Phase 1 (P0, 必须最先完成):
  Task 1-5 并行（源码修改）
  Task 6-7 依赖 Task 1（测试修复）
  → Phase 1 验证

Phase 2 (P1, 独立):
  Task 8-10 并行
  → Phase 2 验证

Phase 3 (P2, 独立):
  Task 11
  → Phase 3 验证
```

---

## 最终验证

```bash
pixi run -e dev check          # lint + fmt + type + test --fast
pixi run -e dev arch-check     # importlinter 24 合约
```

---

## 不在本次修复范围

| 问题 | 原因 |
|------|------|
| Mock 全量迁移（160 文件） | 技术债务，范围远超本次审查 |
| SourceDataQueryParams DRY | `start_date`/`end_date` 是 `str` 类型（vs `date`），需独立评估 |
| Engine logger 导入 | 既有模式（2 文件），非本次引入 |
| hash_universe `__all__` | 内部函数，无外部 import |
| Docstring 语言统一 | 既有技术债务 |
| Plan 文件管理 | 用户自行决定 |
| knowledge_date WHERE 过滤 | 项目一致模式（所有 11 个 Reader 均不过滤） |
