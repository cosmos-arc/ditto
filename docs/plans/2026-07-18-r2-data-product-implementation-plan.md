# R2 A 股日频数据产品 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在现有 Ditto ingestion/catalog/lineage/promotion 主干上完成 R2 的数据产品契约、可恢复历史摄取、认证证据、19 数据集 readiness、R1 门禁和真实 API 数据工作台。

**Architecture:** 采用已批准的“薄认证底座 + 数据集纵向切片”。`ditto_data` 拥有静态产品契约和持久证据，`ditto_application` 负责 planner、certification 与 readiness 编排，`ditto_apps` 只暴露 API/CLI/job 和 DI；`ditto-app` 通过 OpenAPI 生成类型消费真实 API。Canonical catalog 保持消费者唯一视图，provider snapshot 使用独立 append-only identity，避免多来源证据覆盖。

**Tech Stack:** Python 3.13、dataclass/Protocol、SQLite、Parquet、Polars、Dishka、FastAPI、Pytest；React 19、TypeScript strict、TanStack Query/Router、Tailwind v4、Vitest/RTL。

> **执行状态（2026-07-18）**：16/16 项开发任务已完成并提交；文件清单已按
> 实际仓库布局对账。确定性与工程门禁通过，真实 provider、历史、性能和连续
> 运行仍是 release evidence Gate，不属于可由开发代码伪造关闭的任务。

---

## 实施约束

- 直接在用户指定的当前后端分支开发；不创建 worktree。
- 所有生产行为遵循 RED → GREEN → REFACTOR。
- 数据库迁移保持启动时幂等、可从旧 SQLite 原位升级；不删除历史证据。
- 不增加依赖，不修改 import-linter/CI 边界，不引入第二套 registry。
- 真实 provider 凭证、配额和 5 个连续交易日属于运行证据；代码不得伪造成功，缺失时以明确 preflight/acceptance 失败退出。

### Task 1: 冻结 19 个数据产品的静态契约

**Files:**
- Modify: `packages/data/src/ditto_data/catalog/metadata.py`
- Modify: `packages/data/src/ditto_data/catalog/__init__.py`
- Test: `packages/data/tests/unit/catalog/test_metadata_unit.py`

**Step 1: Write the failing tests**

为 19 个 hard-scope dataset 断言：owner、primary/partition keys、provider dataset、bootstrap chunk policy、native/raw/certified target、fallback mode、PIT/revision rule、runbook、license policy 均冻结；三个 deferred dataset 明确 `r2_scope="deferred"`。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/data/tests/unit/catalog/test_metadata_unit.py -q`
Expected: FAIL，`DatasetMetadata` 尚无 R2 产品字段。

**Step 3: Write minimal implementation**

增加冻结 value objects 和按 dataset 解析的契约表；在 `DatasetMetadata.__post_init__` 中验证日期、主键、许可、fallback、chunk 和 PIT 语义，确保 19/3 范围不会静默漂移。

**Step 4: Run test to verify it passes**

Run: `pixi run -e dev pytest packages/data/tests/unit/catalog/test_metadata_unit.py -q`
Expected: PASS。

### Task 2: Provider snapshot 与 license ledger 持久化

**Files:**
- Create: `packages/data/src/ditto_data/catalog/source_snapshot.py`
- Create: `packages/data/src/ditto_data/catalog/source_snapshot_store.py`
- Create: `packages/data/src/ditto_data/catalog/license.py`
- Create: `packages/data/src/ditto_data/catalog/license_store.py`
- Modify: `packages/data/src/ditto_data/catalog/__init__.py`
- Modify: `packages/data/src/ditto_data/di/runtime.py`
- Test: `packages/data/tests/unit/catalog/test_source_snapshot_store_unit.py`
- Test: `packages/data/tests/unit/catalog/test_license_store_unit.py`

**Step 1: Write the failing tests**

证明 identity 至少包含 dataset/source/request interval/schema/checksum；同一 canonical partition 的 Tushare/TDX snapshot 可并存；同一 snapshot 幂等、checksum 冲突 fail closed；license 记录不接受 token/secret 字段并保留 append-only revision。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/data/tests/unit/catalog/test_source_snapshot_store_unit.py packages/data/tests/unit/catalog/test_license_store_unit.py -q`
Expected: FAIL，模块不存在。

**Step 3: Write minimal implementation**

定义 reader/writer Protocol、frozen records 和 SQLite stores。表使用不可变复合唯一键；重复相同 payload 为 no-op，不同内容抛出冲突。通过 `RuntimeProvider` 暴露端口。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 3: 分区生命周期与 durable checkpoint

**Files:**
- Create: `packages/data/src/ditto_data/ingestion/partition_state.py`
- Create: `packages/data/src/ditto_data/ingestion/partition_state_store.py`
- Modify: `packages/data/src/ditto_data/di/runtime.py`
- Test: `packages/data/tests/unit/ingestion/test_partition_state_store_unit.py`

**Step 1: Write the failing tests**

覆盖合法 PLANNED→…→COMPLETE 迁移、FAILED/QUARANTINED/ORPHAN_PAYLOAD/LOG_ONLY/CATALOG_ONLY 异常、append-only event、checkpoint resume、重复 step 幂等和非法越级拒绝。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/data/tests/unit/ingestion/test_partition_state_store_unit.py -q`
Expected: FAIL，生命周期模块不存在。

**Step 3: Write minimal implementation**

建立 current-state + append-only events SQLite store，record 包含 chunk identity、request interval、attempt、retry budget、payload/catalog/lineage/log evidence IDs 与 error code。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 4: Schedule-aware bootstrap/chunk planner 与可信 missing 判断

**Files:**
- Create: `packages/application/src/ditto_application/processes/ingestion/bootstrap_planner.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/backfill_manager.py`
- Modify: `packages/application/src/ditto_application/providers_process.py`
- Modify: `packages/apps/src/ditto_apps/jobs/flows/backfill.py`
- Test: `packages/application/tests/unit/process/ingestion/test_bootstrap_planner_unit.py`
- Test: `packages/application/tests/unit/process/ingestion/test_backfill_manager_unit.py`

**Step 1: Write the failing tests**

覆盖 trading/natural/source-defined schedule、month/quarter/year chunk、instrument/range capability、resume 只重跑 missing/failed/evidence-incomplete，以及 ingestion log 为 SUCCESS 但 catalog/lineage/checkpoint 不完整时仍视为 missing。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_bootstrap_planner_unit.py packages/application/tests/unit/process/ingestion/test_backfill_manager_unit.py -q`
Expected: FAIL，planner 和 evidence-complete 判定不存在。

**Step 3: Write minimal implementation**

planner 从 `DatasetMetadata` 生成 expected partitions/chunks；`BackfillManager` 不再无条件使用交易日历或仅依赖日志日期，优先执行 range/instrument chunk，保留 date fallback。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 5: 摄取证据闭环与补偿

**Files:**
- Modify: `packages/application/src/ditto_application/processes/ingestion/config.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/coordinator_factory.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/post_ingest.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/instrument_ingestion.py`
- Create: `packages/application/src/ditto_application/processes/ingestion/evidence_commit.py`
- Test: `packages/application/tests/unit/process/ingestion/test_evidence_commit_unit.py`
- Test: `packages/application/tests/unit/process/ingestion/test_post_ingest_unit.py`
- Test: `packages/application/tests/integration/test_ingestion_evidence_recovery.py`

**Step 1: Write the failing tests**

分别注入 snapshot/catalog/lineage/log 失败，证明不会返回 success/COMPLETE；payload 已写时记录 ORPHAN_PAYLOAD；repair 从最后 durable stage 继续且不重复 fetch/overwrite；未注入 DQ checker 或未注册规则时 R2 certification profile fail closed。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_evidence_commit_unit.py packages/application/tests/integration/test_ingestion_evidence_recovery.py -q`
Expected: FAIL，当前普通路径 catalog/lineage 是 soft side effect。

**Step 3: Write minimal implementation**

以 partition lifecycle 为 durable saga：每阶段落状态，证据写成功后推进；失败写异常状态并返回明确 reason code。物理 payload 不伪装事务回滚，由 repair use case 补 attestation/lineage/log。

**Step 4: Run test to verify it passes**

Run: 同 Step 2，并运行现有 post-ingest/coordinator tests。
Expected: PASS。

### Task 6: 修复 `fund_adj` 独立写入与核查

**Files:**
- Modify: `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/data_writer.py`
- Modify: `packages/data/src/ditto_data/services/market_write_service.py`
- Test: `packages/data/tests/unit/services/test_market_write_service.py`
- Test: `packages/application/tests/unit/process/ingestion/test_data_writer_unit.py`
- Test: `packages/application/tests/unit/process/ingestion/test_dataset_registry_unit.py`
- Test: `packages/apps/tests/integration/ingestion/test_adj_factor_ingestion_integration.py`

**Step 1: Write the failing tests**

断言 `FUND_ADJ` 使用独立 `WriteKind.FUND_ADJ`、调用 ETF writer、URI 为 `fund_adj/...`、checksum 对应 ETF payload，绝不调用 `save_adj_factor()`/`stock_adj`。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_data_writer_unit.py -q -k fund_adj`
Expected: FAIL，当前共用 ADJ_FACTOR handler。

**Step 3: Write minimal implementation**

增加独立 write route 和 service 方法，保留共享 enrichment/checksum helper。

**Step 4: Run test to verify it passes**

Run: 上述 unit + integration tests。
Expected: PASS。

### Task 7: 闭环 effective-dated `index_weight`

**Files:**
- Modify: `packages/data/src/ditto_data/models/market.py`
- Modify: `packages/data/src/ditto_data/storage/capital/index_composition/index_composition_reader.py`
- Modify: `packages/data/src/ditto_data/storage/capital/index_composition/index_composition_writer.py`
- Modify: `packages/data/src/ditto_data/services/capital_store.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/data_writer.py`
- Modify: `packages/application/src/ditto_application/queries/market.py`
- Test: `packages/data/tests/unit/storage/capital/index_composition/test_index_composition_reader_unit.py`
- Test: `packages/data/tests/unit/storage/capital/index_composition/test_index_composition_writer_unit.py`
- Test: `packages/application/tests/unit/process/ingestion/test_data_writer_unit.py`
- Test: `packages/apps/tests/integration/ingestion/test_index_weight_ingestion_integration.py`

**Step 1: Write the failing tests**

覆盖 `index_id + constituent_id + effective_from` 主键、effective_to、weight 合计容差、as_of 查询、registry fetch/write、catalog maturity gate 和无前视回填。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_index_weight_ingestion_unit.py -q`
Expected: FAIL，当前为 UNSUPPORTED。

**Step 3: Write minimal implementation**

复用已有 index composition storage，补足 PIT schema、application route、writer dispatch、query facade。

**Step 4: Run test to verify it passes**

Run: 上述 unit + integration tests。
Expected: PASS。

### Task 8: 修复 PIT-safe `stock_status`

**Files:**
- Modify: `packages/data/src/ditto_data/sources/tushare/adapters/stock.py`
- Modify: `packages/data/src/ditto_data/sources/tushare/tushare_source.py`
- Modify: `packages/application/src/ditto_application/processes/ingestion/dataset_registry.py`
- Test: `packages/data/tests/unit/sources/tushare/adapters/test_stock_status_pit_unit.py`
- Test: `packages/application/tests/unit/process/ingestion/test_stock_status_pit_unit.py`

**Step 1: Write the failing tests**

断言目标 trade date 传入 ST/停复牌查询；上市/退市状态由有效日期重建；2016-01-01 前不能声明 certified complete；历史请求不读取当前 `stock_basic` 作为替代。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_stock_status_pit_unit.py -q`
Expected: FAIL，当前 adapter 未正确传目标日期。

**Step 3: Write minimal implementation**

修复 adapter 参数和标准化列，输出 `instrument_id + trade_date` PIT observation。

**Step 4: Run test to verify it passes**

Run: 上述 tests。
Expected: PASS。

### Task 9: Coverage、exception 与 immutable certification report

**Files:**
- Create: `packages/data/src/ditto_data/catalog/coverage.py`
- Create: `packages/data/src/ditto_data/catalog/certification.py`
- Create: `packages/data/src/ditto_data/catalog/certification_store.py`
- Modify: `packages/data/src/ditto_data/di/runtime.py`
- Create: `packages/application/src/ditto_application/queries/data_products.py`
- Create: `packages/application/src/ditto_application/commands/data_product_certification.py`
- Test: `packages/data/tests/unit/catalog/test_certification_store_unit.py`
- Test: `packages/application/tests/unit/query/test_data_products_unit.py`
- Test: `packages/application/tests/unit/commands/test_data_product_certification_unit.py`

**Step 1: Write the failing tests**

覆盖 raw/complete/certified 三起点、schedule-aware expected/actual/gap、exception code/owner/evidence、19 数据集独立 report、报告 hash 冻结、同 profile 内容冲突拒绝、reviewer approval、revoke/recertify append-only。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/data/tests/unit/catalog/test_certification_store_unit.py packages/application/tests/unit/query/test_data_products_unit.py -q`
Expected: FAIL，模块不存在。

**Step 3: Write minimal implementation**

coverage collector 聚合 metadata、canonical catalog、partition states、snapshot、DQ、lineage、license；certification command 仅冻结机器生成报告，人工 review 不能修改事实。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 10: R2 bundle readiness 与 R1 coverage preflight

**Files:**
- Create: `packages/application/src/ditto_application/queries/data_readiness.py`
- Modify: `packages/application/src/ditto_application/processes/execution/eod_coordinator.py`
- Modify: `packages/application/src/ditto_application/providers_process.py`
- Test: `packages/application/tests/unit/query/test_data_readiness_unit.py`
- Test: `packages/application/tests/unit/process/execution/test_eod_coordinator_r2_preflight_unit.py`
- Test: `packages/apps/tests/e2e/test_r1_daily_manual_trading.py`

**Step 1: Write the failing tests**

覆盖 dataset maturity + signal/lookback certified interval + PIT universe + profile/snapshot + partition health；失败返回 dataset/date/reason，状态 blocked，不回退 experimental；shadow/required 两模式可切换且默认保持迁移兼容。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/application/tests/unit/process/trading/test_daily_decision_r2_preflight_unit.py -q`
Expected: FAIL，coverage preflight 尚不存在。

**Step 3: Write minimal implementation**

实现 P0/P1 bundle 聚合和 `r2-modern-a-share-v1` profile gate，注入 daily decision preflight。

**Step 4: Run test to verify it passes**

Run: 上述 unit + R1 regression。
Expected: PASS。

### Task 11: 固定 seed 因子 certified snapshot smoke

**Files:**
- Modify: `packages/features/src/ditto_features/factors/production_guard.py`
- Modify: `packages/application/src/ditto_application/processes/materialization/catalog_dependency_validation.py`
- Create: `packages/application/src/ditto_application/processes/materialization/r2_seed_smoke.py`
- Test: `packages/features/tests/unit/test_production_factor_guard_unit.py`
- Test: `packages/application/tests/unit/process/materialization/test_r2_seed_smoke_unit.py`

**Step 1: Write the failing tests**

断言固定 seed 输入集合、最大 lookback、knowledge_date、certification profile、snapshot IDs 和两次 deterministic materialization checksum 一致；缺一 fail closed。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/application/tests/unit/process/materialization/test_r2_seed_smoke_unit.py -q`
Expected: FAIL，R2 smoke 不存在。

**Step 3: Write minimal implementation**

复用现有 dependency validation/materialization，不引入 IC、衰减、发现或策略治理。

**Step 4: Run test to verify it passes**

Run: 上述 tests。
Expected: PASS。

### Task 12: API、CLI、job 与 repair/certify commands

**Files:**
- Create: `packages/apps/src/ditto_apps/models/data_products.py`
- Create: `packages/apps/src/ditto_apps/api/routes/data_products.py`
- Modify: `packages/apps/src/ditto_apps/api/routes/__init__.py`
- Modify: `packages/apps/src/ditto_apps/main.py`
- Modify: `packages/apps/src/ditto_apps/registry/contexts/ingestion.py`
- Modify: `packages/apps/src/ditto_apps/cli/main.py`
- Modify: `packages/apps/src/ditto_apps/jobs/flows/backfill.py`
- Test: `packages/apps/tests/integration/api/test_data_products_api.py`
- Test: `packages/apps/tests/unit/cli/test_data_products_cli_unit.py`

**Step 1: Write the failing tests**

覆盖 Overview/Coverage/Quality/Runs/Evidence/License read models；bootstrap/repair/certify/promotion/revoke command 均有 preview + explicit confirm；OpenAPI 包含完整 schema。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/apps/tests/integration/api/test_data_products_api.py -q`
Expected: FAIL，route 不存在。

**Step 3: Write minimal implementation**

route 只映射 application DTO/command，不复制 coverage/certification 判断。

**Step 4: Run test to verify it passes**

Run: 上述 API/CLI tests。
Expected: PASS。

### Task 13: Provider preflight、benchmark、backup/restore 与 acceptance runner

**Files:**
- Create: `packages/application/src/ditto_application/processes/ingestion/r2_preflight.py`
- Create: `packages/apps/src/ditto_apps/scripts/r2_data_acceptance.py`
- Create: `packages/apps/tests/integration/ingestion/test_r2_backup_restore.py`
- Create: `packages/apps/tests/integration/ingestion/test_r2_idempotency.py`
- Test: `packages/application/tests/unit/process/ingestion/test_r2_preflight_unit.py`

**Step 1: Write the failing tests**

覆盖 entitlement/license/19-contract 检查、代表 chunk benchmark 外推、24h/30min/5s gate、SQLite + payload backup/restore、连续两次无重复写；无凭证/权限时明确 configuration_blocked 且非 success。

**Step 2: Run test to verify it fails**

Run: `pixi run -e dev pytest packages/application/tests/unit/process/ingestion/test_r2_preflight_unit.py packages/apps/tests/integration/ingestion/test_r2_backup_restore.py -q`
Expected: FAIL，runner 不存在。

**Step 3: Write minimal implementation**

实现 deterministic fixture 模式和 live 模式；live 模式只消费环境中已有凭证，不打印/落库 secret。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 14: 生成前端 API 类型并建立 Data Product feature

**Files:**
- Modify: `/home/chevy/projects/ditto-app/src/types/generated/api.d.ts`（generated）
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/api.ts`
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/hooks/index.ts`
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/hooks/use-data-products.ts`
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/index.ts`
- Test: `/home/chevy/projects/ditto-app/src/features/data-products/hooks/use-data-products.test.tsx`

**Step 1: Write the failing tests**

使用 MSW 验证真实 `/api/v1/data-products/*` typed calls、loading/error/empty/ready，确保 `VITE_USE_MOCK=false` 路径不依赖页面硬编码数据。

**Step 2: Run test to verify it fails**

Run: `bun run test:run -- src/features/data-products/hooks/use-data-products.test.tsx`
Expected: FAIL，feature 不存在。

**Step 3: Write minimal implementation**

先从后端 OpenAPI 执行 `bun run gen:api`，再以生成类型建立 query keys/hooks。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 15: 实现数据工作台五视图

**Files:**
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/components/data-product-workbench.tsx`
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/components/data-product-overview.tsx`
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/components/data-product-coverage.tsx`
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/components/data-product-quality.tsx`
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/components/data-product-runs.tsx`
- Create: `/home/chevy/projects/ditto-app/src/features/data-products/components/data-product-evidence.tsx`
- Create: `/home/chevy/projects/ditto-app/src/routes/platform/data-products.tsx`
- Modify: `/home/chevy/projects/ditto-app/src/features/shell/page-contracts.ts`
- Test: `/home/chevy/projects/ditto-app/src/features/data-products/components/data-product-workbench.test.tsx`

**Step 1: Write the failing tests**

断言 19 个 dataset overview、coverage timeline、DQ/PIT/provider 差异、chunk repair、certification/license；危险命令必须 preview + explicit confirm；窄屏可用、键盘可达、状态不只靠颜色。

**Step 2: Run test to verify it fails**

Run: `bun run test:run -- src/features/data-products/components/data-product-workbench.test.tsx`
Expected: FAIL，工作台不存在。

**Step 3: Write minimal implementation**

复用 shell `CatalogLayout`/`Panel` 和既有 tokens，保持本地单用户、不加 RBAC，不展示 R3/R4 功能。

**Step 4: Run test to verify it passes**

Run: 同 Step 2。
Expected: PASS。

### Task 16: 全量验证与 Definition of Done 对账

**Files:**
- Modify: `docs/plans/2026-07-17-r2-data-product-design.md`
- Create: `docs/operations/r2-data-product-runbook.md`
- Create: `docs/evidence/r2/README.md`

**Step 1: Run focused acceptance**

Run: `pixi run -e dev pytest packages/data/tests packages/application/tests packages/apps/tests -q`
Expected: PASS。

**Step 2: Run architecture and repo gate**

Run: `pixi run -e dev check`
Expected: lint、format、type、fast tests 全部 PASS。

Run: `pixi run -e dev arch-check`
Expected: PASS。

Run: `python scripts/architecture/check_architecture_smells.py`
Expected: `0 issues`。

Run: `pixi run -e dev pre-commit-run && git diff --check`
Expected: PASS / no output。

**Step 3: Run frontend gate**

Run in `/home/chevy/projects/ditto-app`: `bun run gen:api && bun run check`
Expected: Biome、TypeScript、Vitest 全部 PASS。

**Step 4: Run R2 acceptance runner**

Run fixture mode first, then live mode when provider credentials/TDX data are available. Archive only real machine-generated reports and explicitly record blocked external gates; never hand-author PASS evidence.

**Step 5: Reconcile the design DoD**

逐项更新设计文档 §16，链接真实 test/command/report evidence；只有 13 项全部有证据时才把状态改为 IMPLEMENTED。
