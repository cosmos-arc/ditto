# Phase 4 代码审查修复计划

## 概述
- 创建: 2026-04-07
- 来源: 6 维度并行审查（架构/PIT/规约/可维护/质量/文档）
- 范围: 5 CRITICAL + 7 高优先 WARNING

## 技术方案

### 修复优先级
1. PIT 安全缺陷（C-PIT-1）— 影响回测正确性
2. 文档错误（C-DOC-1, W-DOC-1/2/3）— 误导开发者
3. 代码质量（C-QUAL-1/2）— 可维护性
4. 配置清理（C-MAINT-1）— 死规则
5. 测试补充（W-QUAL-2）— 覆盖率

---

## 任务清单

### Phase 1: PIT 安全修复 `[M]`

- [x] Task 1.1: 修复 `_find_pit` 缺少 `effective_to` 过滤 `[S]`
  - 验收: `_find_pit` 同时检查 `effective_from <= as_of_date` 和 `(effective_to is None or effective_to > as_of_date)`
  - 文件: `packages/engine/src/ditto_engine/execution/rules.py:265-290`
  - 方案: `TradingRuleSet`/`FeeSchedule` 的字段名为 `as_of_date`（非 `effective_from`），当前实现用 `getattr(rec, "as_of_date")` 是正确的。**真正缺失的是 `effective_to` 过滤**。由于这两个 dataclass 当前无 `effective_to` 字段（V1 简化），应在 `_find_pit` 中用 `getattr(rec, "effective_to", None)` 做可选过滤，保持前向兼容
  - 测试: 新增 `_find_pit` 的单元测试，覆盖多版本规则场景

### Phase 2: 文档修正 `[S]`

- [x] Task 2.1: 修复 Data README 错误导入路径 `[S]`
  - 验收: 示例代码 `from ditto_engine.quality` → `from ditto_data.quality`
  - 文件: `packages/data/README.md:748`

- [x] Task 2.2: 修正 architecture.md 合约计数 `[S]`
  - 验收: "共 18 条合约" → "共 22 条合约"
  - 文件: `.claude/rules/architecture.md:93`

- [x] Task 2.3: 修正 Engine AGENTS.md 虚构目录引用 `[S]`
  - 验收: 移除不存在的 `engine/` 和 `orchestrator/` 子目录描述，或对齐实际代码结构
  - 文件: `packages/engine/AGENTS.md`

- [x] Task 2.4: 修正 Infra 文档与 importlinter 矛盾 `[S]`
  - 验收: Infra CLAUDE.md/AGENTS.md 中 `engine → infra` 标记为禁止，与 importlinter `engine-no-infra-dependency` 合约一致
  - 文件: `packages/infra/CLAUDE.md`, `packages/infra/AGENTS.md`

### Phase 3: 配置清理 `[S]`

- [x] Task 3.1: 清理 pre-commit 已删除目录排除规则 `[S]`
  - 验收: 移除 `apps/web/\.next/|` 行
  - 文件: `.pre-commit-config.yaml:119`

### Phase 4: 代码质量改善 `[L]`

- [x] Task 4.1: 清理 ingestion_coordinator.py 多余空行 `[S]`
  - 验收: 双空行对消除，`__init__` 属性赋值间保留单空行，文件从 1499 行降至约 1100 行
  - 文件: `packages/app/src/ditto_app/process/ingestion_coordinator.py`
  - 注意: 纯格式修改，不改变任何逻辑

- [x] Task 4.2: 拆分 `backfill_adj_factor` 长方法 `[M]`
  - 验收: 169 行的 `backfill_adj_factor` 拆分为 3-4 个 ≤50 行的私有方法（如 `_detect_adj_factor_gaps`, `_fetch_adj_factor_data`, `_write_adj_factor_data`）
  - 文件: `packages/app/src/ditto_app/process/ingestion_coordinator.py:1277-1445`
  - 测试: 现有测试应继续通过（公开接口不变）

- [x] Task 4.3: 拆分 `_auto_init_stock_instrument` 长方法 `[M]`
  - 验收: 125 行拆分为 2-3 个 ≤50 行的私有方法
  - 文件: `packages/app/src/ditto_app/process/ingestion_coordinator.py:894-1018`
  - 测试: 现有测试应继续通过

### Phase 5: 测试补充 `[M]`

- [x] Task 5.1: 补充 `_coordinator_constants.py` 单元测试 `[S]`
  - 验收: 测试 `get_all_index_codes`、`get_sw_index_codes`、`get_default_index_codes` 返回值合理性；测试 `SUPPORTED_INSTRUMENT_DATASETS` 与 `Dataset` 枚举的一致性
  - 文件: 新增 `packages/app/tests/unit/process/test_coordinator_constants.py`

---

## 执行约束

- 每个任务完成后运行 `pixi run -e dev check` 验证
- Phase 1 和 Phase 2 可并行
- Phase 4 各 Task 有依赖（先清理空行再拆分方法，避免 diff 噪音）
- Phase 5 独立于 Phase 4

## 风险评估

| Task | 风险 | 缓解 |
|------|------|------|
| 1.1 | 低 | `effective_to` 字段可选，前向兼容 |
| 4.2-4.3 | 中 | 公开接口不变，重构仅涉及私有方法拆分 |
