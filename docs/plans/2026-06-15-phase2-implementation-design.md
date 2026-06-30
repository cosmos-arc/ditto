# Phase 2 实现设计（个股/宏观数据 Promotion + 真实数据联通）

> 制定日期: 2026-06-15
> 上级路线图: [docs/plans/2026-06-14-production-launch-roadmap.md](2026-06-14-production-launch-roadmap.md) §四 Phase 2
> 范围: F2-#1 promotion evidence 全套 + F2-#2 FRED realtime PIT + F2-#3 真实数据联通

本文档记录 Phase 2 三任务的**实现设计决策**（路线图已覆盖"做什么"，本文补充"怎么做的细节决策"），作为 brainstorming 产出与 writing-plans 输入。

---

## F2-#2 FRED realtime PIT 接入

### 现状

- [client.py](packages/data/src/ditto_data/sources/fred/client.py) `get_series_observations` **已支持** `realtime_start/realtime_end`（ALFRED 模式）。
- [macro.py](packages/data/src/ditto_data/sources/fred/adapters/macro.py) `MacroFredAdapter.fetch_indicators` **未透传** realtime；`knowledge_date = observation date`（注释自承非真正 PIT）。
- 多数 macro 指标 `need_pit=True`（GDP/CPI/PCE 等，会修订）；UNRATE/PAYEMS 等 `need_pit=False`。

### 设计决策

**ALFRED realtime 语义映射**：`realtime_end` 是"数据在 realtime_end 时刻对公众已知"的 PIT 锚点。

| 指标 need_pit | realtime 透传 | knowledge_date |
|---|---|---|
| `True`（会修订） | 传 `realtime_start/realtime_end` | `realtime_end`（真正 PIT） |
| `False`（不修订） | 不传 | `observation date`（保持旧行为） |

**API 形态**：`MacroFredAdapter.fetch_indicators` 新增可选 `realtime_start: str | None`、`realtime_end: str | None`，缺省回退旧行为（向后兼容，不破坏现有调用）。`FredSource.fetch_macro_indicators*` 对应透传。

**realtime 多版本处理**：realtime 模式 FRED 会返回历史修订行（同一 `date` 多个 realtime 版本）。按 `(date)` 分组取 `realtime_end <= 请求 realtime_end` 的最新版本，避免一个 observation 多行污染下游。

**入参边界**：`realtime_start` 缺省时用 `observation_start`，`realtime_end` 缺省时用 `observation_end`（与 FRED 默认一致）。

### TDD

- mock `FredClient`：(a) need_pit 透传 realtime、(b) 非 PIT 不透传、(c) knowledge_date 映射正确、(d) realtime 多版本取最新、(e) 缺省回退旧行为。

---

## F2-#1 Promotion Evidence 全套

### 现状

- 机制完整：[promotion.py](packages/data/src/ditto_data/catalog/promotion.py) `assess_dataset_promotion` + [catalog.py](packages/application/src/ditto_application/commands/catalog.py) `ReviewDatasetPromotionEvidenceHandler`。
- 所有 experimental 数据集共享统一 3 条 `_EXPERIMENTAL_PROMOTION_CRITERIA`。
- **从未有真实数据集提交过 evidence 并持久化晋级**。

### 硬约束（CLAUDE.md）

> 晋级证据必须通过 `assess_dataset_promotion(...)` 按 criteria 精确匹配评估，并通过 `DatasetPromotionEvidenceWriter` / `ReviewDatasetPromotionEvidenceHandler` 提交，**不得由 application/apps 层自造通过条件**。

→ 工具只**收集客观证据材料**，**晋级决策与 maturity override 写入唯一路径是 handler**。

### 设计决策

#### 1. `ditto ops promotion-collect <dataset>`（证据收集，只读 + 生成报告）

收集 3 条 criteria 的客观测量，生成 Markdown 报告存 `data_root/promotion_evidence/<dataset>/<ISO-date>.md`：

| criterion | 客观测量来源 |
|---|---|
| complete PIT/replay coverage for the dataset | catalog reader 统计该数据集 PIT 存储覆盖期 + replay 覆盖检查 |
| document runtime owner, freshness SLA, and source failover policy | 校验 `DatasetMetadata` 是否声明 `runtime_sources`/`freshness_sla_hours`/`default_source` |
| pass catalog-backed runtime/read-model tests without research opt-in | 跑该数据集相关 golden/replay/read-model 测试统计通过率 |

报告含每条 criterion 的客观测量 + 工具建议（pass/fail），**报告本身不构成晋级决策**。

#### 2. `ditto ops promotion-submit <dataset>`（提交，reviewer 把关 `passed`）

读最新报告 → 调 `ReviewDatasetPromotionEvidenceHandler` 逐条提交 3 条 evidence（`evidence_uri` = 报告路径）→ handler 自动 assess + ready 时写 maturity promotion override。`passed` 由 reviewer 确认（提交时交互确认或 `--approve` flag）。

#### 3. golden 测试（[test_catalog_promotion_unit.py](packages/application/tests/unit/commands/test_catalog_promotion_unit.py) 扩展）

用真实 `ReviewDatasetPromotionEvidenceHandler` + in-memory store，证明完整 governance 闭环：
- 提交 3 条 passed evidence → assess `ready` → maturity `experimental→initial-focus`
- 提交前 2 条 → `blocked`（missing 第 3 条）→ 不晋级
- 提交 1 条 `passed=False` → `blocked`（rejected）→ 不晋级
- 晋级后 revoke → 回退 `initial-focus→experimental` + 记录 governance event

#### 4. 文档

`docs/operations/dataset-promotion.md`：collect → 审阅 → submit → revoke 操作手册 + 各数据集证据清单。

### 合规边界

- 工具**绝不**直接调 `DatasetMaturityPromotionWriter` 或自行判定 ready。
- `evidence_uri` 必须指向真实存在的报告（handler 不校验 URI 存在性，但 collect 先生成、submit 再引用）。
- `assess_dataset_promotion` 是唯一评估器；工具的"建议 pass/fail"仅辅助 reviewer。

---

## F2-#3 真实数据联通

### 现状

- keyring 已就绪：`tushare/token`、`fred/api_key`（生产 [config.py](packages/apps/src/ditto_apps/registry/infra/config.py) 命名）。
- [e2e/conftest.py](packages/apps/tests/e2e/conftest.py) 用 `ditto/tushare` 命名（与生产不一致）。
- [test_ingestion.py](packages/apps/tests/e2e/test_ingestion.py) `@pytest.mark.e2e`，CI 跳过。

### 设计决策

**最小联通全链路**：3-5 只 ETF + 5 只个股 + FRED 宏观指标，2-3 个月。

**新增** `packages/apps/tests/e2e/test_real_data_pipeline.py`，`@pytest.mark.e2e`：

```
keyring 取 key → Tushare+FRED 拉取（ingestion 协调器）
  → materialize 因子
  → stock_selection 选股
  → backtest 全链路
  → 断言 NAV>0 / alpha 存在 / 报告产出 / 确定性（两次跑结果一致）
```

**CI 跳过本地可跑**：无 key 时 `pytest.skip`。复用 e2e conftest，顺手统一 keyring 命名为生产 `tushare/token`、`fred/api_key`。

**容错**：网络/积分失败时给出结构化 skip message（不 fail，标记环境问题）。

---

## 任务执行顺序与依赖

```
F2-#2（FRED realtime PIT，独立，最小）
  ↓
F2-#1（promotion evidence 全套，独立）
  ↓
F2-#3（真实数据联通，依赖 F2-#2 的 FRED PIT + F2-#1 的数据默认可用后链路更完整）
```

每个任务独立 TDD（RED→GREEN→REFACTOR），完工 `pixi run -e dev check` + 37 架构合约全绿。

---

## 合规性

- F2-#2 在 data 层 adapter（不引入跨层依赖）。
- F2-#1 工具/CLI 在 apps 层，调 application handler（不绕过），不动架构边界。
- F2-#3 仅 e2e 测试 + conftest keyring 命名修复，不改架构。
- 全部遵循 TDD + `pixi run -e dev check` + 37 架构合约门禁。
