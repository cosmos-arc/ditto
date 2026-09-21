# 数据集晋级治理操作手册

> 适用: experimental 数据集晋级到 initial-focus（生产默认可用）
> 相关规范: [data/AGENTS.md](../AGENTS.md) 数据集成熟度、[application/AGENTS.md](../../application/AGENTS.md) promotion governance

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
uv run --no-sync ditto ops promotion-collect stock_daily
uv run --no-sync ditto ops promotion-collect stock_daily --output data_root/promotion_evidence/stock_daily/2026-06-15.md
```

收集每条 criterion 的客观测量，输出 Markdown 报告：

- **criterion 1 (coverage)**: 注入 `DataCatalogReader` 时统计该数据集 catalog 资产（数量/freshness/rows）→ `measured`；无资产或无 reader → `needs_review`
- **criterion 2 (documentation)**: 检查 metadata 声明 → `measured`（完整）或 `needs_review`（缺失）
- **criterion 3 (tests)**: 始终 `needs_review` — 工具不自动判定测试通过，reviewer 须提供 CI golden-e2e run 证据

> 报告 `status`（`measured`/`needs_review`）是**可测性报告**，不是晋级决策。最终 pass/fail 由 reviewer 通过 `promotion-review` 提交。

### `ditto ops promotion-review` — 提交 evidence

```bash
uv run --no-sync ditto ops promotion-review stock_daily \
  --criterion "complete PIT/replay coverage for the dataset" \
  --evidence-uri "ditto://evidence/stock_daily/pit" \
  --reviewed-by architecture-review --passed
```

每条 criterion 提交一次（3 条共调 3 次）。全部 `passed` 后，handler 自动 `assess_dataset_promotion` → `ready` → 写 maturity promotion override → `experimental→initial-focus`。

`--passed/--rejected` 控制 evidence 通过状态；`--evidence-uri` 指向证据材料（如 collect 报告路径、CI run）。

### `ditto ops promotion-history` — 查看治理历史

```bash
uv run --no-sync ditto ops promotion-history stock_daily
```

### `ditto ops promotion-revoke` — 撤销晋级

```bash
uv run --no-sync ditto ops promotion-revoke stock_daily \
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
uv run --no-sync python -m ditto_apps.cli.main ops status --json

# 2. 为 14 个 launch 数据集生成 promotion evidence report
for dataset in \
  stock_basic stock_daily stock_status balance_sheet income_statement cash_flow \
  valuation_metrics etf_basic etf_daily index_basic index_daily adj_factor \
  fund_adj macro_indicators; do
  uv run --no-sync python -m ditto_apps.cli.main ops promotion-collect "$dataset" \
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
    uv run --no-sync python -m ditto_apps.cli.main ops promotion-review "$dataset" \
      --criterion "$criterion" \
      --evidence-uri "artifacts/promotion/${dataset}/2026-06-21.md" \
      --reviewed-by codex-rc1-launch \
      --passed
  done
done

# 4. 保存 launch dataset status 快照
uv run --no-sync python scripts/acceptance/rc1_real_data_acceptance.py \
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
uv run --no-sync ditto ops promotion-collect stock_daily \
  --output /tmp/stock_daily-evidence.md

# 2. reviewer 审阅报告，确认 3 条 criterion 通过

# 3. 逐条提交（evidence-uri 指向报告 + CI run）
for criterion in \
  "complete PIT/replay coverage for the dataset" \
  "document runtime owner, freshness SLA, and source failover policy" \
  "pass catalog-backed runtime/read-model tests without research opt-in"; do
  uv run --no-sync ditto ops promotion-review stock_daily \
    --criterion "$criterion" \
    --evidence-uri "ditto://evidence/stock_daily/2026-06-15" \
    --reviewed-by architecture-review --passed
done

# 第 3 条提交后，handler 自动晋级 stock_daily → initial-focus

# 4. 验证
uv run --no-sync ditto ops promotion-history stock_daily
```

## 字段用途准入与选股输入迁移（#256）

`field-admission-v1` 是 Selection 创建入口的数据门禁。`POST /api/v1/selections/admission`
只读检查与创建请求相同的输入包；`POST /api/v1/selections/runs` 在任何保存之前重新检查。
页面可选择输入包内证券，再选择字段查看用途、范围、时间精度、许可/认证和快照引用。
单个证券下钻不改变输入包；执行始终重新校验全部输入证券。数据合格仍不能代替策略验证、晋级或 Paper 审批。

旧输入包须补充 `data_from`、`data_to` 及 `data_fields`。每个绑定包含
`dataset_id`、`field`、`snapshot_id`、`consumer_field`；例如
`consumer_field="instruments.factor_values.liquidity_rank"`。服务端从实际消费的因子、
过滤字段、行业观察、证券池及上下文引用推导必需绑定；策略必读的可空字段即使取
`null` 也视为已消费，绑定并哈希显式缺失值，防止把已审事实改为缺失绕过门禁；
额外未消费字段不阻塞本次选股。
绑定的 `snapshot_id` 只能来自该消费字段所属阶段声明的来源列表
（`instruments.*` 与 `universe_snapshot_id` 对应 `selection_source_snapshot_ids`，
其余对应 `rotation_source_snapshot_ids`），跨阶段引用返回 `SNAPSHOT_CONFLICT`；
声明的来源也必须被本阶段消费字段的绑定引用，未被任何绑定声明的来源返回
`SNAPSHOT_UNBOUND`，不能进入已保存运行的血缘。
按 `/api/v1` 兼容规则（contracts/openapi/README.md），在显式废弃窗口内，
未声明任何数据绑定（既无 `data_fields` 也无 `data_from`/`data_to`）的旧请求保持
#256 之前的原行为，不触发门禁；声明了任一绑定即进入门禁，缺失其余绑定返回
`SELECTION_DATA_ADMISSION_BLOCKED`。`/admission` 预览始终报告严格结论；
转为强制门禁属于破坏性变更，须按契约规则另行审批后执行。
既有已保存运行仍可按精确 ID 读取，不重写其身份。

字段证明存入既有 `DatasetCertificationReport.evidence.certified_fields`，使用
`selection-fields-v1` profile。`CertifiedField` 指定字段、精确快照、显式证券集合、覆盖区间、
可得/公开时间上界、时间精度、原件引用和获审查的 `consumer_bindings`（消费字段名、输入 SHA-256）。
`selection_field_payload` 固定该消费字段的实际数值、证券身份、区间、时点、证券池/上下文引用及完整依赖组。
消费者工件的 `field_inputs` 数组保留这些规范化对象；`consumer_input_digest` 计算其 SHA-256。
生产输入是 `ditto data-products build-certification --profile selection-fields-v1
--certified-fields-file <claims.json>`：claims 为 `CertifiedField` 的序列化数组
（`field_from_payload` 编码）。`CertificationBuildRequest.certified_fields` 校验声明唯一、
真实 catalog 字段、已校验工件字节及其中的输入摘要；
调用已有 builder、freeze、review 流程，不从网页输入直接写入资格。
审核者需确认映射、证券范围和时间上界有原件支持；日期精度须先通过交易日历解析成保守时间上界，
不能用摄取时间代替。缺失时间保留未知。许可有效期按实际使用日（Asia/Shanghai）校验，
与历史数据覆盖区间分开；展示和探索同样执行许可限制。

旧报告没有字段证明时不推断合格，其序列化与 hash 不变。补证通过新的认证与审核完成；
撤销保留旧报告但阻止新的正式消费。已有 live discovery 脚本或外部输入包需先完成同样的字段绑定与
认证迁移后再运行；本改动不自动填造认证、购买权益或修改真实 catalog。
