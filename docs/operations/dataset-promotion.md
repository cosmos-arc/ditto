# 数据集晋级治理操作手册

> 适用: experimental 数据集晋级到 initial-focus（生产默认可用）
> 相关规范: [data/CLAUDE.md](../../packages/data/CLAUDE.md) 数据集成熟度、[application/CLAUDE.md](../../packages/application/CLAUDE.md) promotion governance

## 一、治理模型

每个 experimental 数据集声明一组 `promotion_criteria`（见 `default_dataset_metadata()`）。晋级遵循**证据驱动 + 审核人决策**：

```
ditto ops promotion-collect <dataset>     # 工具收集客观证据 → Markdown 报告
  → reviewer 审阅报告 + 决定每条 criterion pass/fail
  → ditto ops promotion-review <dataset> --criterion ...   # 逐条提交 evidence
  → 全部 criterion passed → assess ready → 自动晋级 experimental→initial-focus
  → ditto ops promotion-revoke <dataset> ...  # 如需回退
```

**硬边界**: 工具只收集客观证据，**晋级决策与 maturity override 写入唯一路径是 `ReviewDatasetPromotionEvidenceHandler`**。工具不得自造通过条件或绕过 handler 直接写 store。

## 二、统一晋级条件

所有 experimental 数据集共享 3 条 criteria：

1. **complete PIT/replay coverage for the dataset** — PIT 存储覆盖期 + replay 覆盖
2. **document runtime owner, freshness SLA, and source failover policy** — `DatasetMetadata` 声明 `default_source`/`freshness_sla_hours`/`supported_sources`
3. **pass catalog-backed runtime/read-model tests without research opt-in** — catalog-backed 测试通过（reviewer 提供 CI golden-e2e 证据）

## 三、命令

### `ditto ops promotion-collect` — 收集证据

```bash
pixi run -e dev ditto ops promotion-collect stock_daily
pixi run -e dev ditto ops promotion-collect stock_daily --output data_root/promotion_evidence/stock_daily/2026-06-15.md
```

收集每条 criterion 的客观测量，输出 Markdown 报告：

- **criterion 1 (coverage)**: 注入 `DataCatalogReader` 时统计该数据集 catalog 资产（数量/freshness/rows）→ `measured`；无资产或无 reader → `needs_review`
- **criterion 2 (documentation)**: 检查 metadata 声明 → `measured`（完整）或 `needs_review`（缺失）
- **criterion 3 (tests)**: 始终 `needs_review` — 工具不自动判定测试通过，reviewer 须提供 CI golden-e2e run 证据

> 报告 `status`（`measured`/`needs_review`）是**可测性报告**，不是晋级决策。最终 pass/fail 由 reviewer 通过 `promotion-review` 提交。

### `ditto ops promotion-review` — 提交 evidence

```bash
pixi run -e dev ditto ops promotion-review stock_daily \
  --criterion "complete PIT/replay coverage for the dataset" \
  --evidence-uri "ditto://evidence/stock_daily/pit" \
  --reviewed-by architecture-review --passed
```

每条 criterion 提交一次（3 条共调 3 次）。全部 `passed` 后，handler 自动 `assess_dataset_promotion` → `ready` → 写 maturity promotion override → `experimental→initial-focus`。

`--passed/--rejected` 控制 evidence 通过状态；`--evidence-uri` 指向证据材料（如 collect 报告路径、CI run）。

### `ditto ops promotion-history` — 查看治理历史

```bash
pixi run -e dev ditto ops promotion-history stock_daily
```

### `ditto ops promotion-revoke` — 撤销晋级

```bash
pixi run -e dev ditto ops promotion-revoke stock_daily \
  --revoked-by architecture-review --reason failed_revalidation
```

撤销当前 override，回退 `initial-focus→experimental`，并追加 append-only governance event。`--reason` ∈ {`policy_regression`, `failed_revalidation`, `manual_override`, `evidence_invalidated`}。

## 四、Production Launch Closure 目标数据集

2026-06-21 production launch gate 要求以下 14 个数据集全部具备 catalog
storage URI、schema hash、row count、fresh freshness，并通过 maturity gate。

| 数据集 | 域 | Launch 处理 |
|---|---|---|
| `stock_basic` | metadata | experimental → promotion review → initial-focus |
| `stock_daily` | market | experimental → promotion review → initial-focus |
| `stock_status` | market | experimental → promotion review → initial-focus |
| `balance_sheet` | fundamental | experimental → promotion review → initial-focus |
| `income_statement` | fundamental | experimental → promotion review → initial-focus |
| `cash_flow` | fundamental | experimental → promotion review → initial-focus |
| `valuation_metrics` | capital | experimental → promotion review → initial-focus |
| `etf_basic` | metadata | initial-focus；无需 promotion review，但必须有 catalog evidence |
| `etf_daily` | market | initial-focus；无需 promotion review，但必须有 catalog evidence |
| `index_basic` | metadata | initial-focus；无需 promotion review，但必须有 catalog evidence |
| `index_daily` | market | initial-focus；无需 promotion review，但必须有 catalog evidence |
| `adj_factor` | market | initial-focus；无需 promotion review，但必须有 catalog evidence |
| `fund_adj` | market | initial-focus；无需 promotion review，但必须有 catalog evidence |
| `macro_indicators` | macro | experimental → promotion review → initial-focus |

experimental 数据集按上述流程：collect → 审阅 → review（3 条）→ 自动晋级。
initial-focus 数据集没有 promotion criteria，但 RC acceptance 仍要求 catalog evidence
完整且 freshness 未过期。

## 五、Launch evidence 工作流

Production launch closure 使用固定 evidence 目录，便于 RC acceptance 和人工审阅复查：

```bash
# 1. 确认 launch 数据集 catalog/freshness/read-model 状态
pixi run -e dev python -m ditto_apps.cli.main ops status --json

# 2. 为 14 个 launch 数据集生成 promotion evidence report
for dataset in \
  stock_basic stock_daily stock_status balance_sheet income_statement cash_flow \
  valuation_metrics etf_basic etf_daily index_basic index_daily adj_factor \
  fund_adj macro_indicators; do
  pixi run -e dev python -m ditto_apps.cli.main ops promotion-collect "$dataset" \
    --output "artifacts/promotion/${dataset}/2026-06-21.md"
done

# 3. 对 experimental 数据集逐条提交 reviewer evidence
for dataset in \
  stock_basic stock_daily stock_status balance_sheet income_statement cash_flow \
  valuation_metrics macro_indicators; do
  for criterion in \
    "complete PIT/replay coverage for the dataset" \
    "document runtime owner, freshness SLA, and source failover policy" \
    "pass catalog-backed runtime/read-model tests without research opt-in"; do
    pixi run -e dev python -m ditto_apps.cli.main ops promotion-review "$dataset" \
      --criterion "$criterion" \
      --evidence-uri "artifacts/promotion/${dataset}/2026-06-21.md" \
      --reviewed-by codex-rc1-launch \
      --passed
  done
done

# 4. 保存 launch dataset status 快照
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py \
  --real-data --require-promoted \
  --output artifacts/acceptance/rc1-report.json
```

`artifacts/acceptance/launch-dataset-status.json` 应保存 14 个 launch 数据集的
最终状态快照：maturity、promotion status、catalog storage URI、schema hash、row
count、freshness status。该 artifact 是发布检查证据，不属于代码提交范围，除非发布
流程明确要求归档。

## 六、典型单数据集工作流

```bash
# 1. 收集 stock_daily 证据
pixi run -e dev ditto ops promotion-collect stock_daily \
  --output /tmp/stock_daily-evidence.md

# 2. reviewer 审阅报告，确认 3 条 criterion 通过

# 3. 逐条提交（evidence-uri 指向报告 + CI run）
for criterion in \
  "complete PIT/replay coverage for the dataset" \
  "document runtime owner, freshness SLA, and source failover policy" \
  "pass catalog-backed runtime/read-model tests without research opt-in"; do
  pixi run -e dev ditto ops promotion-review stock_daily \
    --criterion "$criterion" \
    --evidence-uri "ditto://evidence/stock_daily/2026-06-15" \
    --reviewed-by architecture-review --passed
done

# 第 3 条提交后，handler 自动晋级 stock_daily → initial-focus

# 4. 验证
pixi run -e dev ditto ops promotion-history stock_daily
```
