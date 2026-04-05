# QuestDB + Kvrocks 基础设施修订实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在不破坏现有同步接口、分层边界和 Parquet 真相层约束的前提下，落地可重建的 QuestDB/Kvrocks 热层基础设施，并补齐 ADR-040 要求的 `bar_1m` 冷回放前置能力。

**Architecture:** 本计划先修正语义和前置条件，再实现基础设施骨架。QuestDB 只负责热序列、DDL 与时间窗口查询，Kvrocks 负责 latest snapshot 与控制面状态，Parquet 继续作为唯一长期真相层，并新增最小化的 `bar_1m` 冷回放窗口支撑热层重建。

**Tech Stack:** Python 3.13、Polars、orjson、QuestDB ILP client、psycopg、redis、httpx、testcontainers、Docker Compose、Dishka、pytest、Pixi

---

## 一、修订背景

原始计划存在五个会导致返工的结构性问题，本修订版统一纠正：

1. **QuestDB 与 Kvrocks 的 serving 语义混淆**
   - 原计划默认 `get_latest()` 从 QuestDB 读取。
   - 但 ADR-029/030 的正式口径是：`latest` 优先 Kvrocks，`recent series` 优先 QuestDB。

2. **同步协议 + 异步客户端桥接方案不成立**
   - 当前 `DerivedQueryFacade`、`DerivedMaterializationOrchestrator`、`HotLayerReader`、`StateStore` 均为同步接口。
   - 在这个基础上引入 `redis.asyncio` + `asyncio.to_thread()` 只会增加复杂度，不会减少改动。

3. **配置接入点判断错误**
   - 当前 Port 侧只会加载 `config/{env}/data_store.env`。
   - 新增独立 `questdb.env` / `kvrocks.env` 不修改加载链路就不会生效。

4. **ADR-040 的前置条件在代码中尚不存在**
   - 文档要求保留 30 天标准化 `bar_1m` 冷回放窗口。
   - 现有 Market Store 仍以日频 Parquet 为主，尚无分钟真相层可供 QuestDB/Kvrocks 重建。

5. **现有 hot-layer 抽象不足以承载 ADR-031**
   - `StateStore` 只有 bytes 级 `get/set`，无法表达 HASH/BLOB 双 ABI。
   - `HotLayerReader.read_latest()` 也无法同时承载 Kvrocks latest 与 QuestDB series 两种职责。

---

## 二、冻结决策

以下决策在 2026-03-17 已收敛，可直接作为实施基线。

| # | 议题 | 决策 |
|---|------|------|
| D1 | 接口风格 | **全链路保持同步**；不引入 `redis.asyncio` / `asyncio.to_thread()` 桥接 |
| D2 | QuestDB 查询路径 | **`questdb` 仅用于 ILP 写入；查询/DDL 统一走 `psycopg` (PGWire)** |
| D3 | QuestDB 健康检查 | **Docker 与 testcontainers 都基于 health server / PGWire 可用性验证** |
| D4 | Kvrocks 客户端 | **使用同步 `redis.Redis`**；健康检查以 `PING` 为准 |
| D5 | 客户端位置 | **`packages/infra/src/ditto_infra/foundation/clients/`** |
| D6 | Provider 落点 | **并入现有 `DerivedProvider`**，不新建独立 hot-layer provider 模块 |
| D7 | 配置入口 | **仍然只使用 `config/*/data_store.env`**；新增 QuestDB/Kvrocks 嵌套配置 |
| D8 | 环境变量风格 | **支持原生 `QUESTDB_*` / `KVROCKS_*` 覆盖**，但文件内采用 `QUESTDB__*` / `KVROCKS__*` 嵌套键 |
| D9 | `storage.py` | **保留**；它只是派生 DTO，不是第二套配置真相源 |
| D10 | 协议语义 | **拆分 latest snapshot、hot series、control state、snapshot store**，不再继续扩 `HotLayerReader.read_latest()` |
| D11 | 前置里程碑 | **新增 Phase 0：补齐 stock `bar_1m` 冷回放基础** |
| D12 | 双写策略 | **best-effort**；Parquet/Artifact 主链路成功优先，热层失败记录日志与 metrics，后续通过回补修复 |
| D13 | RuntimeMode 持久化 | **后移到 Phase 3b**；先把 hot-path 语义跑通，再做动态 resolver |
| D14 | Docker 版本策略 | **显式 pin 版本，不使用 `latest`** |
| D15 | 测试策略 | **单元测试使用共享 InMemory fake；集成测试使用通用 `DockerContainer`** |

---

## 三、范围与非目标

### 本计划包含

- stock `bar_1m` Parquet 冷回放基础
- QuestDB/Kvrocks 配置、依赖、部署与基础健康检查
- hot-layer 协议重构与共享 InMemory fake
- QuestDB 热表 DDL、分钟热序列读写
- Kvrocks latest snapshot / checkpoint / control-state 实现
- derived query routing 纠偏
- materialization best-effort 双写
- runtime mode 持久化与回补/重建 flow

### 本计划明确不包含

- LOB 热表（`lob_5s_hot`、`lob_1m_mv`、`lob_1s_hot`）
- 流式引擎 / queue consumer / intraday stream runtime
- QuestDB pushdown 策略实现
- Prometheus/Grafana 全量监控面板
- 多市场分钟真相层全面铺开
- benchmark TTL profile 的专项压测

---

## 四、里程碑总览

| Phase | 名称 | 核心目标 | 关键交付 |
|------|------|----------|---------|
| Phase 0 | `bar_1m` 冷回放前置层 | 补齐 ADR-040 的可重建前提 | stock `bar_1m` store + 30 天清理策略 |
| Phase 1a | 配置、依赖与部署骨架 | 让 QuestDB/Kvrocks 可以被稳定拉起与注入 | `data_store` 嵌套配置 + pinned compose + 依赖 |
| Phase 1b | 语义纠偏与 InMemory fake | 先把抽象改正确，再写真实实现 | latest/snapshot/control-state 契约 + 共享 fake backend |
| Phase 1c | infra 同步客户端 + testcontainers | 建立稳定的连接与集成测试基座 | QuestDB/Kvrocks sync client + GenericContainer fixtures |
| Phase 2a | QuestDB 热序列实现 | 跑通 DDL、ILP 写入、时间窗口读取 | DDL manager + writer + series reader |
| Phase 2b | Kvrocks snapshot/control-state | 跑通 namespace、TTL policy、snapshot ABI | snapshot store + control-state store + key builder |
| Phase 3a | Derived 接线与双写 | 把真实热层接到 query/materialization | query facade routing + best-effort dual write |
| Phase 3b | RuntimeMode 持久化与回补 flow | 跑通降级/恢复与 rebuild 主线 | dynamic resolver + runtime mode store + backfill flow |

---

## 五、任务清单

### Task 1: 补齐 stock `bar_1m` 冷回放前置层

**目的**

先补齐 ADR-040 要求的最小真相层，否则 QuestDB/Kvrocks 的“可重建”只有文档语义，没有实现落点。

**Files**

- Create: `packages/data/src/ditto_data/storage/market/stock/bars_minute/__init__.py`
- Create: `packages/data/src/ditto_data/storage/market/stock/bars_minute/bars_reader.py`
- Create: `packages/data/src/ditto_data/storage/market/stock/bars_minute/bars_writer.py`
- Modify: `packages/data/src/ditto_data/config/data_store.py`
- Modify: `packages/infra/src/ditto_infra/foundation/config/providers/data_root.py`
- Modify: `apps/port/src/ditto_interfaces/registry/datahub/market.py`
- Test: `packages/data/tests/unit/storage/market/stock/bars_minute/test_bars_minute_store_unit.py`

**实现要点**

1. 新增 dataset `market/stock/bars_minute`
2. 继续复用现有 `ParquetStore + YearlyPartition`，不在本阶段引入新的分区策略
3. 在 `DataStoreSettings` 中补充 `market_stock_bars_minute_path`
4. 在 `DataRootInitProvider` 中创建 `market/stock/bars_minute`
5. 先只做 stock MVP，ETF/index 的分钟真相层后续再扩
6. 30 天保留策略先由回补/清理 flow 承担，不在 store 层做隐式 TTL

**验证**

- `pixi run -e dev pytest packages/data/tests/unit/storage/market/stock/bars_minute/test_bars_minute_store_unit.py -v`

**建议提交**

- `feat(datahub): add stock bar_1m parquet replay store`

---

### Task 2: 调整配置模型、依赖与部署骨架

**目的**

建立真实可用的配置和部署入口，避免后续实现建立在无效 env 文件和 `latest` 镜像之上。

**Files**

- Modify: `pixi.toml`
- Modify: `packages/data/src/ditto_data/config/data_store.py`
- Modify: `apps/port/src/ditto_interfaces/registry/infra/config.py`
- Modify: `config/development/data_store.env`
- Modify: `config/testing/data_store.env`
- Modify: `config/production/data_store.env`
- Create: `deploy/derived/docker-compose.dev.yml`
- Create: `deploy/derived/questdb/server.conf`
- Create: `deploy/derived/kvrocks/kvrocks.conf`
- Create: `deploy/derived/README.md`
- Test: `apps/port/tests/registry/test_config_datahub_unit.py`

**实现要点**

1. 在 `DataStoreSettings` 中新增：
   - `questdb: QuestDBSettings`
   - `kvrocks: KvrocksSettings`
2. QuestDB settings 至少包含：
   - `enabled`
   - `host`
   - `ilp_port`
   - `pg_port`
   - `health_port`
   - `user`
   - `password`
   - `ttl_profile`
3. Kvrocks settings 至少包含：
   - `enabled`
   - `host`
   - `port`
   - `password`
   - `db`
   - `snapshot_ttl_seconds`
   - `checkpoint_ttl_seconds`
4. `ConfigProvider.data_store_settings()` 保持从 `data_store.env` 读取，但额外接受 `QUESTDB_*` / `KVROCKS_*` 原生环境变量覆盖
5. `pixi.toml` 新增：
   - `questdb`
   - `psycopg`
   - `redis`
   - `testcontainers`
6. `deploy/derived/docker-compose.dev.yml` 使用显式版本：
   - QuestDB：`questdb/questdb:9.3.3`
   - Kvrocks：`apache/kvrocks:2.15.0`
7. 不改动现有 `deploy/docker/docker-compose.yml`

**验证**

- `pixi run -e dev pytest apps/port/tests/registry/test_config_datahub_unit.py -v`

**建议提交**

- `feat(config): add questdb kvrocks nested settings and dev compose`

---

### Task 3: 纠正 hot-layer 协议语义并提供共享 InMemory fake

**目的**

先把抽象层改对，再实现真实客户端，避免后续所有代码都绑在错误协议上。

**Files**

- Modify: `packages/data/src/ditto_data/services/hot_layer/__init__.py`
- Modify: `packages/data/src/ditto_data/services/__init__.py`
- Modify: `apps/port/src/ditto_interfaces/services/derived/__init__.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/in_memory_backend.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/in_memory_series_reader.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/in_memory_snapshot_store.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/in_memory_control_state_store.py`
- Test: `packages/data/tests/unit/services/test_hot_layer_unit.py`
- Test: `apps/port/tests/unit/services/derived/test_query_facade_unit.py`

**实现要点**

1. 废弃“QuestDB 负责 latest”这一错误语义
2. 将当前抽象拆分为最少四类：
   - `HotSeriesReader`
   - `HotProjectionWriter`
   - `LatestSnapshotStore`
   - `ControlStateStore`
3. 如果需要兼容旧测试，可保留 placeholder，但命名必须体现真实职责
4. InMemory fake 必须共享同一个 backend，避免 reader/writer 跨实例后数据断裂
5. InMemory snapshot store 必须能模拟 TTL 到期
6. namespace 相关逻辑暂不写死在 fake 中，为 Task 6 预留注入点

**验证**

- `pixi run -e dev pytest packages/data/tests/unit/services/test_hot_layer_unit.py -v`
- `pixi run -e dev pytest apps/port/tests/unit/services/derived/test_query_facade_unit.py -v`

**建议提交**

- `refactor(datahub): split hot layer contracts by semantic role`

---

### Task 4: 实现 infra 同步客户端与 testcontainers 基座

**目的**

提供真实连接、生命周期管理和集成测试夹具，为后续 DataHub 层实现提供稳定基础。

**Files**

- Create: `packages/infra/src/ditto_infra/foundation/clients/__init__.py`
- Create: `packages/infra/src/ditto_infra/foundation/clients/questdb.py`
- Create: `packages/infra/src/ditto_infra/foundation/clients/kvrocks.py`
- Modify: `packages/infra/src/ditto_infra/foundation/__init__.py`
- Create: `packages/infra/tests/conftest.py`
- Create: `packages/infra/tests/integration/clients/test_questdb_client_integration.py`
- Create: `packages/infra/tests/integration/clients/test_kvrocks_client_integration.py`

**实现要点**

1. `QuestDBClient`
   - ILP writer：官方 `questdb.ingress.Sender`
   - query/DDL：`psycopg.Connection`
   - `health_check()` 同时验证 health port 与 PGWire 可用性
2. `KvrocksClient`
   - 使用同步 `redis.Redis`
   - `health_check()` 发送 `PING`
   - 暴露同步 pipeline 能力
3. testcontainers
   - 统一使用 `testcontainers.core.container.DockerContainer`
   - QuestDB 暴露 `9009/8812/9003`
   - Kvrocks 暴露 `6666`
4. 不在这一层引入 DataHub 业务逻辑

**验证**

- `pixi run -e dev pytest packages/infra/tests/integration/clients/test_questdb_client_integration.py -v`
- `pixi run -e dev pytest packages/infra/tests/integration/clients/test_kvrocks_client_integration.py -v`

**建议提交**

- `feat(infra): add sync questdb and kvrocks clients`

---

### Task 5: 实现 QuestDB 热序列读写与 DDL 管理

**目的**

让 QuestDB 具备最小可用的“热表创建 + ILP 写入 + 时间窗口读取”能力。

**Files**

- Create: `packages/data/src/ditto_data/services/hot_layer/questdb_ddl.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/questdb_series_reader.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/questdb_hot_writer.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/questdb_frame_codec.py`
- Test: `packages/data/tests/integration/services/hot_layer/test_questdb_ddl_integration.py`
- Test: `packages/data/tests/integration/services/hot_layer/test_questdb_series_reader_integration.py`
- Test: `packages/data/tests/integration/services/hot_layer/test_questdb_hot_writer_integration.py`

**实现要点**

1. DDL manager 必须接受 `ttl_profile` 或 `ttl_days`，不得硬编码 `5 DAYS`
2. 首批只落：
   - `bar_1m_hot`
   - `f_1m_hot`
   - `bar_5m_mv`
   - `bar_15m_mv`
   - `bar_60m_mv`
3. LOB 相关 DDL 仅保留扩展点，不在本阶段实现
4. `QuestDBHotWriter.write_frame()` 内部自动 flush，不把 flush 责任外泄给 orchestrator
5. 返回结果统一转成 `pl.DataFrame`
6. SQL 参数绑定统一走 PGWire，不拼接字符串

**验证**

- `pixi run -e dev pytest packages/data/tests/integration/services/hot_layer/test_questdb_ddl_integration.py -v`
- `pixi run -e dev pytest packages/data/tests/integration/services/hot_layer/test_questdb_series_reader_integration.py -v`
- `pixi run -e dev pytest packages/data/tests/integration/services/hot_layer/test_questdb_hot_writer_integration.py -v`

**建议提交**

- `feat(datahub): add questdb hot table ddl and series io`

---

### Task 6: 实现 Kvrocks namespace、snapshot store 与 control-state store

**目的**

落实 ADR-031/040 的命名空间和 TTL 语义，让 Kvrocks 真正承担 latest snapshot 与控制面状态职责。

**Files**

- Create: `packages/data/src/ditto_data/services/hot_layer/namespace.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/kvrocks_snapshot_store.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/kvrocks_control_state_store.py`
- Create: `packages/data/src/ditto_data/services/hot_layer/kvrocks_snapshot_codec.py`
- Test: `packages/data/tests/unit/services/hot_layer/test_namespace_unit.py`
- Test: `packages/data/tests/integration/services/hot_layer/test_kvrocks_snapshot_store_integration.py`
- Test: `packages/data/tests/integration/services/hot_layer/test_kvrocks_control_state_store_integration.py`

**实现要点**

1. 统一 key 前缀：
   - root state：`ditto:derived:state:{entity_type}:{entity_id}`
   - snapshot：`ditto:derived:state:{entity_type}:{entity_id}:snapshot:{instance_key}`
   - checkpoint：`ditto:derived:checkpoint:{entity_type}:{entity_id}:{partition_key}`
2. 实现 `build_*` 与 `parse_key()`，禁止业务代码散落硬编码 key
3. snapshot store 支持：
   - HASH 模式
   - BLOB 模式
   - `schema_ver` 演进
4. control-state store 默认无 TTL；snapshot/checkpoint 使用 settings 中的 TTL
5. 大批量清理允许 `scan_iter + delete`，但只用于限定场景

**验证**

- `pixi run -e dev pytest packages/data/tests/unit/services/hot_layer/test_namespace_unit.py -v`
- `pixi run -e dev pytest packages/data/tests/integration/services/hot_layer/test_kvrocks_snapshot_store_integration.py -v`
- `pixi run -e dev pytest packages/data/tests/integration/services/hot_layer/test_kvrocks_control_state_store_integration.py -v`

**建议提交**

- `feat(datahub): add kvrocks snapshot and control state stores`

---

### Task 7: 接线 Derived query facade，并修正 serving 路由

**目的**

把热层接到实际查询入口，并把当前错误的“QuestDB latest 优先”改成与 ADR 一致的正式语义。

**Files**

- Modify: `apps/port/src/ditto_interfaces/services/derived/query_facade.py`
- Modify: `apps/port/src/ditto_interfaces/registry/datahub/derived.py`
- Modify: `apps/port/tests/unit/services/derived/test_query_facade_unit.py`
- Modify: `packages/data/src/ditto_data/services/__init__.py`

**实现要点**

1. `get_latest()`
   - ONLINE：优先从 Kvrocks latest snapshot 读取
   - OFFLINE：走 cold layer
   - DEGRADED：允许 cold fallback，但必须显式可观测
2. `get_series()`
   - ONLINE：优先 QuestDB recent series
   - OFFLINE：cold layer
3. `compare_sources()`
   - 继续对比 serving/offline，但 serving 侧来源变为 QuestDB/Kvrocks 正式语义
4. `DerivedProvider` 中不再硬编码 `UnavailableHotLayerReader()`
5. 本阶段的 runtime mode 仍可保持静态 resolver，不提前实现持久化

**验证**

- `pixi run -e dev pytest apps/port/tests/unit/services/derived/test_query_facade_unit.py -v`

**建议提交**

- `feat(port): wire derived query facade to hot snapshot and hot series`

---

### Task 8: 落实双写、RuntimeMode 持久化与回补/重建 flow

**目的**

在不影响现有 artifact 主链路的前提下，把热层写入、降级恢复和 rebuild 主线补齐。

**Files**

- Modify: `apps/port/src/ditto_interfaces/services/derived/materialization_orchestrator.py`
- Modify: `apps/port/src/ditto_interfaces/registry/datahub/derived.py`
- Create: `apps/port/src/ditto_interfaces/services/derived/runtime_mode_store.py`
- Create: `apps/port/src/ditto_interfaces/services/derived/runtime_mode_resolver.py`
- Create: `apps/port/src/ditto_interfaces/services/derived/hot_layer_backfill_flow.py`
- Create: `apps/port/src/ditto_interfaces/services/derived/state_snapshot_rebuild_flow.py`
- Test: `apps/port/tests/unit/services/derived/test_materialization_hot_write_unit.py`
- Test: `apps/port/tests/unit/services/derived/test_runtime_mode_resolver_unit.py`
- Test: `apps/port/tests/integration/services/derived/test_hot_layer_backfill_integration.py`

**实现要点**

1. materialization 双写必须是 best-effort
   - artifact / catalog 主链路成功优先
   - 热层失败只记录日志、metrics、补偿任务
2. RuntimeMode 持久化通过 Kvrocks control-state store 保存
3. 必须校验 ADR-030 的 `ALLOWED_MODE_TRANSITIONS`
4. 回补 flow 顺序固定为：
   - Parquet `bar_1m` 回补 QuestDB `bar_1m_hot`
   - 已发布 SERIES 结果回补 QuestDB `f_1m_hot`
   - 已发布 STATE 结果重建 Kvrocks snapshot
5. 30 天外的数据恢复不依赖热层，改由上游源重放或重新物化

**验证**

- `pixi run -e dev pytest apps/port/tests/unit/services/derived/test_materialization_hot_write_unit.py -v`
- `pixi run -e dev pytest apps/port/tests/unit/services/derived/test_runtime_mode_resolver_unit.py -v`
- `pixi run -e dev pytest apps/port/tests/integration/services/derived/test_hot_layer_backfill_integration.py -v`

**建议提交**

- `feat(port): add hot layer dual write and runtime mode persistence`

---

## 六、统一验证顺序

每个任务完成后跑对应 targeted tests；里程碑结束后跑一次小闭环；全部完成后跑全量 gate。

### 里程碑级验证

1. `pixi run -e dev pytest packages/data/tests/unit/services/test_hot_layer_unit.py -v`
2. `pixi run -e dev pytest apps/port/tests/unit/services/derived/test_query_facade_unit.py -v`
3. `pixi run -e dev pytest packages/infra/tests/integration/clients -v`
4. `pixi run -e dev pytest packages/data/tests/integration/services/hot_layer -v`

### 最终门禁

1. `pixi run -e dev check`
2. 如有较多集成测试新增，再补：
   - `pixi run -e dev test --integration`

---

## 七、风险与缓解

| 风险 | 严重性 | 缓解 |
|------|--------|------|
| `bar_1m` 真相层缺失导致回补 flow 无法闭环 | 高 | 把 Phase 0 作为硬前置，未完成不得开始 Phase 3 |
| QuestDB DDL / MV 兼容性差异 | 中 | 集成测试里显式校验 DDL 建表、查询与 MV 可用性 |
| Kvrocks snapshot ABI 演进复杂 | 中 | 强制 `schema_ver` 与 codec 层集中实现 |
| 双写失败造成热层与 artifact 短期不一致 | 中 | best-effort + flow 回补 + metrics 告警 |
| RuntimeMode 过早持久化引入更多耦合 | 中 | 明确后移到 Phase 3b |
| Docker 版本漂移 | 中 | compose 与 testcontainers 都显式 pin 版本 |

---

## 八、完成定义

满足以下条件才可视为本计划完成：

- stock `bar_1m` 冷回放层已落地，且有 30 天清理/重建语义
- QuestDB/Kvrocks 配置通过 `data_store.env` 与原生环境变量同时可用
- QuestDB 热表 DDL、读写与 Kvrocks snapshot/control-state 全部有集成测试
- `DerivedQueryFacade` 已按“Kvrocks latest / QuestDB series / cold fallback”运行
- materialization 双写为 best-effort，失败不破坏 artifact 主链路
- RuntimeMode 持久化与回补 flow 可运行
- `pixi run -e dev check` 通过

---

## 九、执行顺序建议

严格按以下顺序实施，不要跳步：

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7
8. Task 8

原因：

- Task 1 决定是否具备 ADR-040 的实现前提
- Task 3 决定真实实现面对的协议是否正确
- Task 4 是 QuestDB/Kvrocks 真实实现的公共底座
- Task 7/8 依赖前面全部基础设施与语义收敛

---

## 十、版本注记

本计划中的版本选择基于 2026-03-17 可获得的官方口径：

- QuestDB Docker：`9.3.3`
- Kvrocks Docker：`2.15.0`
- Python query client：`psycopg`
- QuestDB Python ILP client：`questdb`

后续如果版本漂移，更新原则是：

1. 先更新本计划与 `deploy/derived/*`
2. 再更新 `pixi.toml`
3. 最后补集成测试验证，不允许只改镜像标签
