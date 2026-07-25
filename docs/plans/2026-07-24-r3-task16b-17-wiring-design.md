# R3 Task 16b + 17 接线设计

> **设计事实源补充**：修订 [2026-07-19 R3 design](2026-07-19-r3-a-share-research-strategy-governance-design.md) §10.1（见本文 §2.2）
> **实施计划**：[2026-07-19 R3 plan](2026-07-19-r3-a-share-research-strategy-governance-implementation-plan.md) Task 16b（剩余接入）+ Task 17
> **状态**：✅ 已实施完成（2026-07-25，commit #3c 三子 commit `763f6d99`/`2646b067`/`9ca0dad5`）。Task 16b 全部接入 + strategy_spec 纯 payload 收尾。test --fast 11160 passed + 37 contracts + type/lint 全绿。预先存在 slow integration/e2e 失败（路由期望/EngineConfig golden/backtest published e2e）是 R3 历史遗留（commit #3b 就存在，--fast 跳过），属 Task 17/backtest golden 范围，独立修复。
> **分支**：`docs/r3-research-governance-design`

---

## 1. 背景与目标

Task 15（governance 控制面：领域模型 + SQLite append-only store + GovernanceService）与 Task 16a（`StrategyPromotionProcess`：evidence-gated publish + activate）已完成，DI 已注册。但存在断点：

**governance 写得出、生产读不到。** `GovernanceService.publish`/`activate` 已能把 active pointer 写进 `strategy_governance.active_pointer`，但 R1/EOD/runtime_builder 三处仍读 `StrategyCatalogService.get_latest_published`（旧的 `strategy_spec.status='published'` 语义）。governance 与生产读取未接通，W4 退出门禁（"R1/EOD 只读取 active pointer"）未满足。

本设计目标：
1. **Task 16b**：把 governance 接入生产读取路径，`strategy_spec` 降级为纯 immutable payload，governance 成为唯一状态源。
2. **Task 17**：暴露 strategy governance + research REST API/CLI，解锁 ditto-app live 接线。

**本轮范围**：16b 全部接入 + Task 17 全部后端 API（不含 W5 ditto-app 前端）。不考虑兼容（未上线），dev/test 库重建。

---

## 2. 核心架构决策

### 2.1 governance 唯一状态源 + `strategy_spec` 降级为纯 payload

- `strategy_spec` 表 → **纯 immutable payload 存储**（加 `spec_hash`/`parent_version`，移 `status`/`updated_at`，INSERT-only，移 `update_status`/`get_latest_published`）。
- `strategy_governance` → **唯一状态真相源**（version 状态机 draft→review→published→deprecated + active_pointer）。
- 读取统一走 active pointer：`get_active_published(strategy_id)` = governance `get_active_pointer` → 回查 `strategy_spec` payload；无 pointer → `None`（调用方走现有 `NO_ACTIVE_STRATEGY`/`AppBuilderError` fail-closed）。
- **无 fallback、无 migration**：旧 seed 数据由 `seed_bootstrap` 改造重建（`create_draft` → `publish` → `activate`）。

### 2.2 内容寻址 payload（修订 design §10.1）

**发现**：governance `strategy_version` 表已存 `spec_json`（design §10.1 要求自包含），但**零消费方**（全包仅字段定义，service/promotion 不读）。与 `strategy_spec` 形成 payload 双存冗余。

**决策**：采用**内容寻址模式**——`strategy_spec` 是唯一 payload 源，governance `strategy_version` **去掉 `spec_json` 列**，只存 `spec_hash` 引用。理由：
1. 零功能损失：两表同库同包 + 都 immutable + 同源写入，governance 通过 `(strategy_id, version)` join `strategy_spec` 拿到的 payload 与自存完全一致；自包含是审美收益非功能收益。
2. 与项目既有范式同构：Task 13 内容寻址 artifact index（payload 存一次、按 hash 寻址）、`StrategyPromotionProcess` 用 `bundle_hash` 引用 `ReviewPacket`。governance 用 `spec_hash` 引用 payload 与之一致。
3. 单一事实源 = 长期可维护：消除双存一致性负担。

**design §10.1 修订**：把"version 表含 spec_json（自包含）"收敛为"version 表存 spec_hash 引用 + payload 由内容寻址 store 单一持有，仍不可变"。§10.1 核心不变量（version payload 不可变、只 insert）完全保留。

---

## 3. Schema 变更（已批准）

两表均在 metadata SQLite，共享同一 `SQLitePool`（已确认 [di/storage.py](../../packages/strategy/src/ditto_strategy/di/storage.py)）。无数据需保留，dev/test 库删 `.sqlite` 重新 `init_schema`。

### 3.1 `strategy_spec` 表（唯一 payload 源，immutable）

```sql
CREATE TABLE IF NOT EXISTS strategy_spec (
    strategy_id    TEXT NOT NULL,
    version        INT  NOT NULL,
    name           TEXT NOT NULL,
    spec_json      TEXT NOT NULL,
    spec_hash      TEXT NOT NULL,          -- 新增：canonical hash，内容寻址锚点
    parent_version INT,                     -- 新增：governance 血缘对齐
    tags           TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (strategy_id, version)
);
CREATE INDEX IF NOT EXISTS idx_spec_hash ON strategy_spec(spec_hash);
-- 删除：status 列、updated_at 列、idx_spec_status 索引、idx_spec_strategy_id（保留或按需）
```

### 3.2 `strategy_governance.strategy_version` 表（去 spec_json）

```sql
CREATE TABLE IF NOT EXISTS strategy_version (
    strategy_id    TEXT NOT NULL,
    version        INT  NOT NULL,
    parent_version INT,
    schema_version INT  NOT NULL,
    spec_hash      TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    PRIMARY KEY (strategy_id, version)
);
-- 删除：spec_json 列
```

---

## 4. 接入点改造清单

### 4.A strategy 存储层

**[contracts.py](../../packages/strategy/src/ditto_strategy/contracts.py)**
- `StrategyCatalogReader`：移除 `get_latest_published`/`list_latest_published`，新增 `get_active_published(strategy_id) -> StrategySpecRecord | None`
- `StrategyCatalogWriter`：移除 `update_status`；`save` 保留（INSERT-only 语义）
- `StrategyRunStatusWriter`：**不动**（是 run 状态，非 spec 状态）

**[strategy_catalog_service.py](../../packages/strategy/src/ditto_strategy/storage/sqlite/services/strategy_catalog_service.py)**
- `StrategySpecReaderProtocol`：同上移除/新增
- `StrategySpecWriterProtocol`：移除 `update_status`
- `StrategyCatalogService`：构造注入 governance 窄 port（`get_active_pointer`）；实现 `get_active_published` = pointer → `_reader.get_spec(strategy_id, pointer.active_version)`；移除 `publish_spec`/`get_latest_published`/`list_latest_published`

**[strategy_spec_store.py](../../packages/strategy/src/ditto_strategy/storage/sqlite/strategy_spec_store.py)**
- DDL：§3.1
- `save`：`INSERT OR REPLACE` → **INSERT only**（重复 PK 抛 `IntegrityError`）
- 删除：`update_status` + `_UPDATE_STATUS_SQL`、`get_latest_published` + `_GET_LATEST_PUBLISHED_SQL`、`_LIST_LATEST_PUBLISHED_SQL`、`_CREATE_INDEX_STATUS`
- 保留：`get_spec`、`list_versions`、`list_all_latest`（纯 payload 浏览，~30 调用方依赖）
- `_row_to_record`：移除 status/updated_at，加 spec_hash/parent_version
- `StrategySpecRecord`（[models.py](../../packages/strategy/src/ditto_strategy/models.py)）：加 `spec_hash`/`parent_version`，移除 `status`

### 4.B governance service 扩展

**[governance/service.py](../../packages/strategy/src/ditto_strategy/governance/service.py)**
- 新增 `create_draft(strategy_id, version, spec, name, tags, parent_version)`：计算 `canonical_spec_hash`，**同事务**写 `strategy_spec(payload,hash)` + `governance.version(state=draft)`
- 注入 `SQLiteStrategySpecWriter`（构造参数）
- **实施要点**：确认 `SQLitePool` 事务模型（是否提供 transaction context / 共享 connection）。create_draft 同事务跨两个 store 写入，落地点二选一：
  - (a) governance service 持 spec_writer，在 service 层开 pool 事务编排两 store 低层写入；
  - (b) 在 strategy 包新增 `StrategySpecGovernanceCoordinator` 持 spec_writer + governance store，pool 事务内编排。
  - 偏好 (b)：保持 governance store 职责单一（不知 strategy_spec 表）。commit #2 实施时定。

**[governance/models.py](../../packages/strategy/src/ditto_strategy/governance/models.py)**
- `StrategyVersion`：移除 `spec_json` 字段
- `governance/store.py`：`_INSERT_VERSION`/`_GET_VERSION`/`_LIST_VERSIONS` SQL 去 `spec_json`

### 4.C R1/EOD/runtime_builder 切读

| 文件 | 改动 |
|---|---|
| [runtime_builder.py:90](../../packages/application/src/ditto_application/builders/runtime_builder.py#L90) | `get_latest_published` → `get_active_published`；删除 :99 `record.status != "published"` 检查（由 get_active_published 保证） |
| [daily_decision.py:134](../../packages/application/src/ditto_application/queries/daily_decision.py#L134) | 经 `StrategyQueryFacade.get_active_published`（见 4.D）切读 |
| [eod.py:251](../../packages/apps/src/ditto_apps/jobs/flows/eod.py#L251) | `catalog.get_latest_published` → `get_active_published` |

三处 `None` 分支复用现有 fail-closed：[daily_decision.py:589](../../packages/application/src/ditto_application/queries/daily_decision.py#L589) `NO_ACTIVE_STRATEGY`、[eod.py:384](../../packages/apps/src/ditto_apps/jobs/flows/eod.py#L384)、runtime_builder `AppBuilderError`。

### 4.D query/command 重构

**[queries/strategy.py](../../packages/application/src/ditto_application/queries/strategy.py)**
- `StrategyQueryFacade`：`get_latest_published` → `get_active_published`；`list_latest_published` → `list_active`
- `to_spec_info`（[contracts.py](../../packages/application/src/ditto_application/contracts.py)）：`StrategySpecInfo.status` 从 governance state 映射（`active`/`draft`/`deprecated` 等），不再读 `record.status`。被 4 处 read model 读取：`_planning_request_identity.py:204/306`、`_executor_probe.py:84/129`、`cli/commands/strategy.py:43`、`api/routes/strategy.py:63`

**[commands/strategy.py](../../packages/application/src/ditto_application/commands/strategy.py)**
- `CreateStrategyHandler` → 调 `governance.create_draft`（不再 `save_spec` + status draft）
- `PublishStrategyHandler` → 调 promotion process / `governance.publish + activate`（不再 `publish_spec`）
- `UpdateStrategyHandler` → append-only 下"更新=派生新 version"：`create_draft(parent_version=existing.version, version=new)`

**新增 [commands/strategy_governance.py](../../packages/application/src/ditto_application/commands/strategy_governance.py)**（Task 16 Step 3）
- `SubmitReview`/`Approve`/`Reject`/`Publish`/`Deprecate`/`Reactivate` Command + Handler
- 调 `GovernanceService`；`Publish` 经 `StrategyPromotionProcess`（evidence-gated）

### 4.E seed_bootstrap 改造

**[seed_bootstrap.py](../../packages/application/src/ditto_application/processes/strategy/seed_bootstrap.py)**
- `SeedCreatePort.create` 实现 → `governance.create_draft`
- `SeedPublishPort.publish` 实现 → `governance.publish + activate`
- [seed_bootstrap.py:149](../../packages/application/src/ditto_application/processes/strategy/seed_bootstrap.py#L149) `existing.status != "published"` → 查 governance active pointer 是否指向该 version
- port 实现（[apps/registry/contexts/strategy.py:80](../../packages/apps/src/ditto_apps/registry/contexts/strategy.py#L80)）改为注入 governance service

---

## 5. 集成测试（commit #4）

- **promotion 全流程**：seed(`create_draft`→`publish`→`activate`) → R1/daily_decision 读到 active version + payload
- **active 切换**：publish v2 → activate → R1 读到 v2（pointer 切换）
- **fail-closed**：无 pointer → `NO_ACTIVE_STRATEGY`/`AppBuilderError`
- **append-only**：重复 `save` 抛 `IntegrityError`；`update_status` 方法不存在
- **CAS**：pointer conflict（expected revision 不匹配）→ 失败
- **evidence gate**：stale bundle_hash / hard gate fail → publish 拒绝（Task 16a 已覆盖，回归）

---

## 6. Task 17（REST API / CLI）

**strategy governance routes**（扩展 [api/routes/strategy.py](../../packages/apps/src/ditto_apps/api/routes/strategy.py) 或新建 governance routes）
- `GET /strategies/{id}/versions` — list versions
- `GET /strategies/{id}/active` — get active pointer + payload
- `POST /strategies/{id}/versions/{v}/submit-review` / `approve` / `reject`
- `POST /strategies/{id}/versions/{v}/publish` — 经 promotion process
- `POST /strategies/{id}/versions/{v}/reactivate` — reason + confirmation + expected revision
- `POST /strategies/{id}/versions/{v}/deprecate`

**research catalog routes**（新建 `research_catalog_routes.py`）
- factor catalog / descriptor / experiment CRUD（部分已在 `research_experiment_routes.py`：detail + gates）

**CLI**（新建 `cli/commands/research.py`）+ **research context**（新建 `registry/contexts/research.py`）

**route 模式**（已调研，与已提交的 `research_experiment_routes.py` 一致）：`APIRouter(prefix, tags)` + `@inject` + `FromComponent()` 注入 facade + `run_blocking`(asyncio.to_thread) + `APIResponse[T]` + `NotFoundError`。

**maturity**：`/api/v1/research: experimental` 已注册（[maturity.py:39](../../packages/apps/src/ditto_apps/api/maturity.py#L39)）；strategy governance routes 按现有 `/api/v1/strategies` 成熟度。

**OpenAPI codegen 验证**：起 server → `openapi.json` 含 strategy governance + research 资源。

**测试**：route 契约 + 409（pointer conflict）/422（stale evidence）+ DI（FromComponent）+ live boundary（`VITE_USE_MOCK=false` 不回退）。

---

## 7. 提交节奏（6 个独立可验证提交）

| # | 提交 | 范围 | TDD 锚点 |
|---|---|---|---|
| 1 | `feat(strategy): immutable spec payload store` | spec schema(§3.1) + `strategy_spec_store` append-only + `StrategySpecRecord`(spec_hash/parent_version，移 status) + governance 去 spec_json(§3.2) + `StrategyVersion` model | 拒重复 PK 抛 IntegrityError；spec_hash 计算；spec_json 不在 governance；update_status 移除 |
| 2 | `feat(strategy): bridge catalog to governance active pointer` | contracts/catalog_service 接 governance + `get_active_published` + `create_draft`（同事务原子写，落地点 §4.B） | get_active_published(pointer→payload)；create_draft 原子性；无 pointer→None |
| 3 | `feat(strategy): read active pointer in production paths` | R1/EOD/runtime_builder 切读(§4.C) + queries/strategy + commands/strategy 重构(§4.D) + seed_bootstrap(§4.E) | 三处切读；fail-closed 复用；seed 全流程；to_spec_info status 映射 |
| 4 | `feat(strategy): govern active strategy publication` | strategy_governance commands(§4.D) + 集成测试(§5) | promotion 全流程；active 切换；CAS；fail-closed |
| 5 | `feat(api): expose governed strategy workflows` | strategy governance routes + 测试 + maturity | route 契约；409/422；DI；reactivate 语义 |
| 6 | `feat(api): expose governed research workflows` | research catalog routes + CLI + context + OpenAPI codegen 验证 | live boundary；OpenAPI 零 diff |

每个提交：RED → GREEN → REFACTOR，独立 `pytest` + `type`。提交 4 后跑 `arch-check`（W4 门禁）。提交 6 后跑 `pixi run -e dev check`。

---

## 8. 风险与回滚

| 风险 | 缓解 |
|---|---|
| create_draft 跨 store 同事务（SQLitePool 事务模型） | §4.B 实施要点：commit #2 先确认 SQLitePool API，偏好 coordinator 模式(b) |
| `StrategySpecInfo.status` 语义变更影响 4 处 read model | §4.D：统一从 governance state 映射，TDD 覆盖每处 |
| append-only 破坏现有 update 覆盖语义 | `UpdateStrategyHandler` 改派生新 version（§4.D），保留 CLI 入口 |
| 移除 `status` 列破坏依赖 `.status` 的测试 | grep 全包 `.status`（spec 相关），逐处改造；commit #1 含回归 |
| governance store schema 改动（去 spec_json）影响 Task 15b 测试 | 同步更新 `test_strategy_governance_store_unit.py` |

**回滚**：每提交独立，可 `git revert` 单提交。schema 变更在 commit #1，回滚后 dev/test 库重建即可。
