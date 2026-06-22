# RC1 发布验收清单

> 适用版本: Production Launch Closure, 2026-06-21 hard-gate acceptance
> 范围: 后端日频 A 股个股、ETF、指数、宏观数据、选股、研究回测、手工信号包流程

## 一、验收口径

RC1 只在硬门禁全部通过时可发布。早期 `pixi run -e dev check`、synthetic golden
或单项真实数据联通结果只能作为历史证据,不得单独描述为最终上线证明。

最终发布必须生成:

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py \
  --real-data \
  --require-promoted \
  --output artifacts/acceptance/rc1-report.json
```

报告必须满足:

```text
passed == true
business_failures == []
```

## 二、必需数据集

以下 launch 数据集全部为发布必需项:

- `stock_basic`
- `stock_daily`
- `stock_status`
- `balance_sheet`
- `income_statement`
- `cash_flow`
- `valuation_metrics`
- `etf_basic`
- `etf_daily`
- `index_basic`
- `index_daily`
- `adj_factor`
- `fund_adj`
- `macro_indicators`

行业映射必须通过选股链路实际使用的 metadata/industry read path 验证,即使其物理存储
标识不等同于上表的 market/fundamental 数据集名称。

## 三、数据治理硬门禁

每个必需数据集都必须满足:

- maturity 为 `initial-focus` 或 `stable`。
- promotion status 为 `ready`/`promoted`,或在 maturity 已达标时为 `not_applicable`。
- catalog storage URI 存在。
- catalog schema hash 存在。
- catalog row count 大于 0。
- catalog freshness status 为 `fresh` 或 `not_applicable`。

任何 `experimental`、`blocked`、缺 catalog 证据、schema hash 缺失、row count 缺失或
freshness 过期的必需数据集都必须导致 RC acceptance 失败。

## 四、真实数据 E2E

RC acceptance 必须覆盖以下真实数据路径:

- `packages/apps/tests/e2e/test_real_data_pipeline.py`
- `packages/apps/tests/e2e/test_real_data_stock_selection_pipeline.py`

真实数据验收需在具备 Tushare/FRED 凭证的发布环境运行。凭证不可用时,不得把本地跳过
结果当作最终发布证明;必须在有凭证环境补跑并附上 `artifacts/acceptance/rc1-report.json`。

## 五、选股与信号硬门禁

发布必须验证:

- catalog-backed stock selection 产出 ranked candidates、target weights、reason payload。
- signal package 持久化后可通过既有 trade signal read path 读取最新版本。
- 手工 fill 记录后会在同一验收链路重算 position。
- deviation report 在手工 fill 后产出并可审阅。

相关测试:

- `packages/apps/tests/integration/test_stock_selection_golden_e2e.py`
- `packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py`
- `packages/application/tests/integration/test_manual_signal_fill_deviation_e2e.py`

## 六、生产因子硬门禁

生产选股因子必须由 production factor guard 审核:

- 当前表达式 codegen 可安全支持的因子才允许进入 production registry。
- 不安全的 cross-sectional/time-series 嵌套必须 fail closed。
- 研究可用但生产未验证的因子不得绕过 guard。

相关测试:

- `packages/features/tests/unit/test_production_factor_guard_unit.py`

## 七、最终命令

上线前必须重新运行:

```bash
pixi run -e dev check
```

```bash
pixi run -e dev pytest \
  packages/apps/tests/integration/test_golden_e2e.py \
  packages/apps/tests/integration/test_stock_selection_golden_e2e.py \
  packages/apps/tests/integration/test_stock_selection_signal_package_e2e.py \
  -q --no-cov
```

```bash
pixi run -e dev python scripts/acceptance/rc1_real_data_acceptance.py \
  --real-data \
  --require-promoted \
  --output artifacts/acceptance/rc1-report.json
```

`artifacts/` 默认作为发布证据目录保留在工作区,不提交到代码仓库;若发布流程要求归档,
应由 release owner 明确授权后再提交。
