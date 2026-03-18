# QuestDB + Kvrocks 基础设施计划 — 审查报告

**审查日期**: 2026-03-17
**审查对象**: [2026-03-17-questdb-kvrocks-infrastructure-plan.md](./2026-03-17-questdb-kvrocks-infrastructure-plan.md)
**审查范围**: 架构一致性、ADR 对齐、风险识别、实施可行性

---

## 一、决策记录

以下决策在审查过程中与项目所有者讨论确认。

| # | 议题 | 决策 | 理由 |
|---|------|------|------|
| D1 | 同步/异步策略 | **混合模式** — Protocol 保持同步签名，infra 客户端内部用 `asyncio.to_thread()` 桥接异步操作 | 改动最小，不影响现有 Protocol 签名和调用链路 |
| D2 | infra 客户端位置 | **`packages/infra/src/ditto_infra/foundation/clients/`** | 与 `db/sqlite_pool.py` 同级，符合"技术基础设施"定位 |
| D3 | DI Provider 组织 | **合并到现有 `DerivedProvider`** | 热层当前仅服务于 derived 系统，避免 Provider 碎片化 |
| D4 | QuestDB 查询路径 | **待调研** — 需先调研 `questdb` Python 客户端的查询能力后再定 | 避免过早决策 |
| D5 | 环境变量命名 | **不带 `DITTO_` 前缀** | 与 `TUSHARE_TOKEN`、`ENVIRONMENT` 风格一致，外部基础设施用原生命名 |
| D6 | 配置文件整合 | **合并到 `config/data_store.py`** | `storage.py` 内容合并后删除；所有存储层配置集中管理 |
| D7 | TTL 机制 | **可配置 profile** — 不硬编码 | 对齐 ADR-040 的 profile 机制 |
| D8 | Docker healthcheck | **修复** — QuestDB 用 HTTP 检测，Kvrocks 用 TCP 探测 | 镜像可能缺少 `curl`/`redis-cli` |

---

## 二、Phase 1 审查

### 2.1 Docker Compose

| 项目 | 状态 | 说明 |
|------|------|------|
| 服务定义（QuestDB + Kvrocks） | OK | 端口暴露合理 |
| healthcheck — QuestDB | 需修复 | 改用 `wget -q --spider http://localhost:9000/status` |
| healthcheck — Kvrocks | 需修复 | 改用 `bash -c '</dev/tcp/localhost/6666'` |
| 网络配置 | 需补充 | 需考虑与现有 docker-compose 的互联 |
| 与生产栈分离 | OK | `docker-compose.dev.yml` 独立于 `deploy/docker/docker-compose.yml` |

### 2.2 依赖选型

| 依赖 | 状态 | 说明 |
|------|------|------|
| `questdb >= 3.0` | 需验证 | 确认 PyPI 包名和版本可用性 |
| `redis[hiredis]` | OK | Kvrocks 兼容 Redis 协议 |
| `testcontainers >= 4.0` | 需验证 | QuestDB/Kvrocks 可能无预定义模块，需用通用 `DockerContainer` |

### 2.3 配置模型

- `QuestDBSettings` / `KvrocksSettings` 放在 `packages/datahub/src/ditto_datahub/config/data_store.py`（D6）
- `enabled: bool = False` 用于 DI 切换 Real/Fake（D3）
- `ttl_profile: str = "intraday_hot"` 支持 D7
- 环境变量使用 `QUESTDB_HOST`、`KVROCKS_PORT` 等（D5）

### 2.4 infra 客户端

**QuestDBClient**（`foundation/clients/questdb.py`）:

| 设计点 | 决策 |
|--------|------|
| ILP Sender | 同步使用 `questdb.ingress.Sender`，无桥接 |
| 查询 | 待 D4 调研后确定；内部用 `asyncio.to_thread()` 桥接 |
| 健康检查 | 同步方法，内部 `asyncio.to_thread()` |
| 生命周期 | `__init__` 初始化，`close()` 清理 |

**KvrocksClient**（`foundation/clients/kvrocks.py`）:

| 设计点 | 决策 |
|--------|------|
| 连接池 | `redis.asyncio.ConnectionPool` |
| 暴露底层 client | 允许 — 通过 `.redis` 属性暴露（Kvrocks 操作种类多，完全封装代价大） |
| 同步桥接 | `.get()`/`.set()` 等同步方法内部用 `asyncio.to_thread()` |
| 健康检查 | `PING` 命令，结果缓存 |

### 2.5 InMemory Fake

| 实现 | 状态 | 说明 |
|------|------|------|
| `InMemoryHotLayerReader` | 需增强 | 需要与 `InMemoryHotLayerWriter` 共享存储 |
| `InMemoryHotLayerWriter` | 需补充 | 计划中缺失详细设计 |
| `InMemoryStateStore` | 建议增加 TTL 模拟 | 至少提供简单的过期检查，否则无法测试 TTL 行为 |

### 2.6 DI Provider

- 在 `DerivedProvider` 中添加热层相关 `@provide` 方法（D3）
- `derived_query_facade()` 中将 `UnavailableHotLayerReader()` 替换为条件注入
- 条件注入逻辑：根据 `enabled` 配置选择 Real 或 InMemory 实现

### 2.7 Testcontainers

- `packages/infra/tests/conftest.py` 添加 session-scoped fixtures
- 使用通用 `DockerContainer` 配置 QuestDB/Kvrocks
- 等待策略：TCP 端口探测

---

## 三、Phase 2 审查

### 3.1 DDL 管理

| 项目 | 状态 | 说明 |
|------|------|------|
| 核心表 DDL（bar_1m_hot, f_1m_hot） | OK | 与 ADR-028 对齐 |
| 物化视图 DDL | 需注意 | QuestDB 版本兼容性；`CREATE MATERIALIZED VIEW IF NOT EXISTS` 可能不被所有版本支持 |
| LOB 表 DDL | 需预留扩展点 | lob_5s_hot/lob_1m_mv/lob_1s_hot 不在本计划范围，但 DDL 管理器应有扩展能力 |
| TTL 硬编码 | 需改为 profile | 对齐 D7；DDL 管理器接收 `ttl_days` 参数而非硬编码 |

### 3.2 QuestDBReader

- 查询路径待 D4 调研后确定
- SQL 参数化：需确认所选查询路径是否支持命名参数
- 结果转换：无论走 HTTP REST 还是 PG Wire，最终需返回 `pl.DataFrame`

### 3.3 QuestDBWriter

| 项目 | 状态 | 说明 |
|------|------|------|
| ILP 写入 | OK | `questdb.ingress.Sender` 是同步 API |
| 批量 buffer 管理 | 需明确 | 谁负责 flush？建议 `write_frame()` 结束时自动 flush |
| 数据格式转换 | 需类型约束 | `frame: pl.DataFrame` 的 schema 应与目标表列匹配，建议用 TypedDict 或 dataclass 约束 |

### 3.4 KvrocksStore

| 项目 | 状态 | 说明 |
|------|------|------|
| HASH/BLOB 双模式 | OK | 与 ADR-031 对齐 |
| 同步/异步桥接 | 需实现 | Protocol 签名同步，底层 `redis.asyncio` 异步 |
| Key 构建 | 需统一 | 使用 `namespace.py` 的构建函数，不在方法中硬编码 |
| 批量操作 Pipeline | OK | `pipeline(transaction=False)` 正确 |
| `scan_iter` + `delete` | 需注意 | 大数据量下可能阻塞，但当前场景（单因子 snapshot 清理）可接受 |

### 3.5 命名空间

| 项目 | 状态 | 说明 |
|------|------|------|
| 三种 key 模式 | OK | 与 ADR-040 对齐 |
| TTL 常量 | 建议关联配置 | 与 `KvrocksSettings` 或 D7 profile 关联 |
| 反向解析 | 建议增加 | `parse_key()` 函数用于调试和监控 |

---

## 四、Phase 3 审查

### 4.1 物化双写

| 项目 | 状态 | 说明 |
|------|------|------|
| 双写策略 | 需明确 | 应为 **best-effort** — QuestDB 写入失败不影响主链路 Parquet 写入 |
| 失败处理 | 需补充 | try/except 包裹，失败记录 metrics 和日志 |
| 依赖注入 | OK | `DerivedMaterializationOrchestrator` 添加 `hot_layer_writer` 参数 |

### 4.2 查询热层路由

| 项目 | 状态 | 说明 |
|------|------|------|
| 现有路由逻辑 | OK | `DerivedQueryFacade.get_latest()` 已有 ONLINE → 热层 → 回退逻辑 |
| RuntimeMode 持久化 | 需 fallback | Kvrocks 不可用时，本地默认 OFFLINE 模式 |
| `StaticRuntimeModeResolver` 替换 | 需设计 | 动态 resolver 依赖 `StateStore`，需确保依赖链无循环 |

### 4.3 STATE 因子盘前初始化

| 项目 | 状态 | 说明 |
|------|------|------|
| StateInitializer 复用 | 建议 | 复用现有物化引擎，只负责"物化结果 → Kvrocks snapshot"的转换 |
| 不同因子的初始化逻辑 | 需考虑 | 不同 STATE 因子需要不同计算逻辑，建议通过 factor spec 配置驱动 |

### 4.4 RuntimeMode 持久化

| 项目 | 状态 | 说明 |
|------|------|------|
| 模式切换验证 | 需实现 | 对齐 ADR-030 的 `ALLOWED_MODE_TRANSITIONS` |
| Prometheus 指标 | 可选 | ADR-030 的第三层隔离可后续迭代 |

### 4.5 盘后回补 Flow

| 项目 | 状态 | 说明 |
|------|------|------|
| 回补范围 | 需补充 | 计划只考虑了 bar_1m 回补，应包含 f_1m_hot 回补和 Kvrocks 状态初始化 |
| Flow 统一 | 建议 | 合并为一个 Flow，按顺序执行 bar 回补 → factor 回补 → Kvrocks 初始化 |

---

## 五、ADR 对齐差距

| ADR | 要求 | 计划覆盖 | 差距 |
|-----|------|---------|------|
| ADR-028 | 8 张热表 DDL | 3 张表 + 3 视图 | LOB 表 DDL 需预留扩展点 |
| ADR-029 | 四类因子分级 | FactorServeMode 已定义 | STATE 初始化复用策略未明确 |
| ADR-030 | 四层隔离保护 | 第一、二层 | 第三层（Prometheus）和第四层（CLI/API）为未来迭代 |
| ADR-031 | schema_ver 迁移 | migrate_snapshot() | BLOB 迁移回写策略需更多设计 |
| ADR-040 | TTL profile 机制 | DDL 硬编码 5 天 | 需改为可配置 profile（D7） |

---

## 六、风险清单

| # | 风险 | 严重性 | 缓解措施 |
|---|------|--------|---------|
| R1 | 同步 Protocol + 异步底层客户端的桥接复杂度 | 高 | 使用 `asyncio.to_thread()`；注意 event loop 嵌套问题 |
| R2 | testcontainers 对 QuestDB/Kvrocks 的支持 | 中 | 使用通用 `DockerContainer`；提前验证 |
| R3 | ILP 无 ACK，写入后无法确认持久化 | 中 | 回补流程中做写入后验证（查询验证） |
| R4 | QuestDB Python 客户端能力不确定 | 中 | D4 调研前置 |
| R5 | Kvrocks 不可用时 RuntimeMode fallback | 中 | 本地默认 OFFLINE；Kvrocks 恢复后自动升级 |
| R6 | 物化双写失败导致 QuestDB 与 Parquet 不一致 | 低 | best-effort 策略；异步回补修复 |
| R7 | Docker 镜像 healthcheck 工具缺失 | 低 | 使用 HTTP/TCP 探测（D8） |

---

## 七、Phase 拆分优化建议

当前 Phase 1 较大（7 个子任务），建议拆分为更小的里程碑：

| 原 Phase | 建议拆分 | 核心交付 |
|----------|---------|---------|
| Phase 1 | **Phase 1a** | Docker Compose + 配置模型 + pixi 依赖（纯配置，无代码） |
| Phase 1 | **Phase 1b** | infra 客户端骨架 + Testcontainers（基础设施骨架） |
| Phase 1 | **Phase 1c** | InMemory Fake + DI Provider 条件注入（可测试的骨架） |
| Phase 2 | **Phase 2a** | DDL 管理器 + QuestDBReader/Writer（QuestDB 读写） |
| Phase 2 | **Phase 2b** | KvrocksStore + namespace（Kvrocks 读写） |
| Phase 3 | **Phase 3a** | 物化双写 + 查询路由升级（端到端盘后链路） |
| Phase 3 | **Phase 3b** | STATE 初始化 + RuntimeMode 持久化 + 回补 Flow（盘中链路） |

---

## 八、待办项（计划修订时需处理）

- [ ] **D4**：调研 `questdb` Python 客户端的查询能力（HTTP REST vs PG Wire vs 官方客户端）
- [ ] **D8**：验证 QuestDB 和 Kvrocks Docker 镜像中的可用工具（curl/redis-cli/wget）
- [ ] **D6**：合并 `config/storage.py` 到 `config/data_store.py`
- [ ] **D7**：DDL 管理器支持 TTL profile 参数
- [ ] 确认 `questdb` PyPI 包名和版本范围
- [ ] 确认 testcontainers-python 对 QuestDB/Kvrocks 的支持程度
- [ ] 设计 InMemoryFake 的共享存储机制（Reader/Writer 跨实例）
- [ ] 设计 InMemoryStateStore 的 TTL 模拟
- [ ] 物化双写的失败处理和 metrics 定义
- [ ] RuntimeMode 动态 resolver 的 Kvrocks fallback 策略
