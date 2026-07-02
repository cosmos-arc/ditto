# Wave 1 Data Readiness Evidence

> Date: 2026-07-02 (Phase 1 完成)
> Scope: backend data readiness for Wave 1a and full RC1 promotion tracking.
> Branch: feat/wave1-backend-capabilities

## Summary

Phase 1 (Task 1.1-1.5) 全部完成：14 launch 数据集 catalog evidence 齐全 + 8 experimental 数据集经 governance 闭环提级到 initial-focus。`validate_maturity_status` 校验 `ok=True failures=0`（从 RED 阶段 72 failures 收敛）。

## Command Evidence

- `source scripts/acceptance/wave1_env.sh`（Phase 1 固化 env：`DITTO_DATA_ROOT` / `SQLITE_PATH` / `DUCKDB_PATH` / `ENVIRONMENT=testing` / `PYTHONUNBUFFERED`，data root 默认 `.tmp/ditto-rc1`，gitignore 已覆盖）。
- `pixi run -e dev python -m ditto_apps.cli.main init config --data-root .tmp/ditto-rc1 --force` → exit 0；建 31 directories + `metadata.sqlite`（catalog/promotion store 共用）。
- `pixi run -e dev python scripts/acceptance/wave1_catalog_check.py` → 跑 `ops status --json` + `validate_maturity_status`，输出 14 数据集 per-dataset 矩阵与 failure 清单。RED（空环境）72 failures → GREEN（Phase 1 完成）0 failures。
- `pixi run -e dev python -m ditto_apps.cli.main ops status --json` → exit 0；含 maturity_summary + per-dataset catalog/maturity/promotion 字段。
- `ditto ops promotion-collect <dataset> --output /tmp/wave1-rc1-promotion/<dataset>.md` × 8 experimental 数据集 → 客观证据 markdown（criterion 1/2 measured，criterion 3 needs_review）。
- `ditto ops promotion-review <dataset> --criterion <text> --evidence-uri <uri> --reviewed-by wave1-acceptance --passed` × 8 × 3 → 第 3 条 satisfied 后 `assess_dataset_promotion` 自动写 experimental→initial-focus override。
- `ditto ops promotion-history <dataset>` → `promoted experimental->initial-focus actor=wave1-acceptance` audit event 可查。
- golden-e2e（4 测试文件 / 9 用例）→ 9 passed，criterion 3 真实 evidence。

## V1a Dataset Matrix (7/7 ready)

| Dataset | Maturity | Promotion | Catalog Evidence | V1a Status |
|---|---|---|---|---|
| `calendar` | n/a (非 launch dataset) | n/a | trading_calendar 2025-01-01~2026-12-31 (485 交易日, 为 backfill 日期枚举服务) | ✅ ready (依赖) |
| `etf_basic` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=2851 | ✅ ready |
| `index_basic` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=8000 | ✅ ready |
| `etf_daily` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=2045 (359/359 success) | ✅ ready |
| `fund_adj` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=2000 (359/359 success) | ✅ ready |
| `index_daily` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=17 (近期 2 月 39/39 success) | ✅ ready |
| `adj_factor` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=1 (近期 2 月 39/39 success) | ✅ ready |

## RC1 Experimental Datasets (8/8 promoted)

| Dataset | Maturity | Promotion | Catalog Evidence | Status |
|---|---|---|---|---|
| `stock_basic` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=5859 | ✅ promoted |
| `stock_daily` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=5508 | ✅ promoted |
| `stock_status` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=10320 | ✅ promoted |
| `balance_sheet` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=1702 | ✅ promoted |
| `income_statement` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=2110 | ✅ promoted |
| `cash_flow` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=2562 | ✅ promoted |
| `valuation_metrics` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=5508 | ✅ promoted |
| `macro_indicators` | initial-focus | not_applicable | fresh / storage✅ / schema✅ / rows=1 | ✅ promoted |

## Phase 1 Implementation Notes

- **calendar/basic ingest 路径修正**: `backfill metadata calendar/basic` 会被 `backfill_range` 的 `list_trading_days` 阻断 (calendar 空表死循环) 或逐日循环浪费 (basic 不按日变化)。改用 `ingest metadata calendar <date>` (按 date 所在自然年拉 trade_cal 范围) 与 `ingest metadata basic <asset>` (单次全量)。market 日行情才用 `backfill --parallel`。
- **写瓶颈发现 (systematic-debugging)**: market backfill 每日期完整处理含 parquet 写 + catalog upsert + cursor + log, SQLite 写锁限制并发, `--parallel` 无法突破 (parallel 8 反因写竞争更慢)。fetch 本身毫秒级 (一秒内多次 HTTP), 瓶颈在写入链。`index_daily ~1min/日期 wall → 全年 ~6h`; `adj_factor` (~5000 股票) 预计更慢; `fund_adj` (ETF, 类似 etf_daily) 较快。全年范围不可行，V1a market + RC1 全 A 股逐日数据集均采用近期 2 月范围 (2026-05~06)。
- **稀疏财报扩范围**: `balance_sheet`/`income_statement`/`cash_flow` 近期 2 月 (5-6 月) 无披露日 rows=0 (不在财报季); 扩到 2025-08~2026-06 (含中报+年报披露日) 后 rows>0。
- **promotion governance 闭环**: collect (客观证据) → review (reviewer evidence: criterion 1=collect md replay coverage measured, 2=`docs/architecture/capability-maturity.md` freshness_sla/failover 文档, 3=`test_golden_e2e.py` 9 测试通过) → assess 自动提级。governance 红线遵守: evidence_uri 全部指向真实材料, 绝不自造通过; 逐数据集逐条 review, 未批量批过。

`adj_factor` 保守包含 (shared market/adjustment 路径仍引用)。若 ETF workflow 证明只需 `fund_adj` 可后续 demote。

## Runtime Store Readiness

Trade intent, fill, and position stores are not ingestion catalog datasets, so promotion review is not applicable. Their V1a readiness will be verified through backend trade query/API tests and the Daily Decision report contract.

## Full RC1 Status

Full RC1 required datasets are defined by `scripts/acceptance/rc1_requirements.py`:

`stock_basic`, `stock_daily`, `stock_status`, `balance_sheet`, `income_statement`, `cash_flow`, `valuation_metrics`, `etf_basic`, `etf_daily`, `index_basic`, `index_daily`, `adj_factor`, `fund_adj`, `macro_indicators`.

**Current validation result: `ok=True failures=0` (passed).**

`validate_maturity_status` 对 14 launch 数据集全过: catalog storage/schema/row_count/freshness 齐全 + `dataset_maturity=initial-focus` + promotion 合规。

## Required Next Actions

Phase 1 (Task 1.1-1.5) 全部完成。下一步:

1. Phase 2 (Task 2.1): 重跑 `pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py --real-data --require-promoted --output artifacts/acceptance/rc1-report.json`，确认 `passed==true && business_failures==[]`。
2. Phase 3-4: ditto-app 前端接线 (独立分支 `feat/wave1-backend-wiring`)。
