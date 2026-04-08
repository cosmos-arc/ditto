# 全面简化计划 — Ditto 代码库

## 执行状态：✅ 全部完成（2026-04-07）

### 完成摘要

| Phase | 状态 | 净变化 |
|-------|------|--------|
| Phase 1: 死代码清理 | ✅ 完成 | ~500 行删除 |
| Phase 2: 代码去重 | ✅ 完成（Task 2.4 取消 — ISP 违规） | ~600 行删除, ~200 行新增 |
| Phase 3: 大文件拆分 | ✅ Batch D 完成，Batch E 跳过（低于阈值） | publication_facade 751→510 行 |
| Phase 4: Protocol 层重设计 | ✅ Task 4.1 完成，其余保留 | 3 类 30 行删除 |

### 关键修正

- **Protocol 数量实际为 18**（非 60+），大幅缩减 Phase 4 范围
- **Task 2.4（_CatalogReader 统一）取消** — 独立 Protocol 是 ISP 设计，非重复
- **Batch E 跳过** — materialization_orchestrator 和 market_service 分析后低于拆分阈值
- **Phase 4 缩减** — 18 个 Protocol 中仅 `RuntimeModeResolver` 为死代码（注入但未调用），其余保留

---

## Phase 1: 死代码清理（低风险） ✅

### Task 1.1: 删除空 `stores/` 目录树 ✅

- DELETE: 47 个空目录（0 Python 文件）

### Task 1.2: 移除 HotLayer Protocol 和 stub ✅

- DELETE: `packages/data/src/ditto_data/services/hot_layer/` 整个目录（197 行）
- MODIFY: `providers.py` — 移除 hot_layer 注入
- MODIFY: `derived.py` — 移除 hot_layer 参数和逻辑

### Task 1.3: 内联 `BaseStore` ABC ✅

- DELETE: `base_store.py`（110 行 ABC）
- MODIFY: ParquetStore 和 SQLiteStore 直接设置 `self._data_root`

**Phase 1 净变化**: ~500 行删除，0 行新增

---

## Phase 2: 代码去重（中低风险） ✅

### Task 2.1: 提取 `_resolve_identifier` 共享函数（API 路由） ✅

- CREATE: `interfaces/src/ditto_interfaces/api/utils/identifier.py`

### Task 2.2: 提取 `_resolve_identifier` 共享函数（CLI 查询命令） ✅

- CREATE: `interfaces/src/ditto_interfaces/cli/utils/identifier.py`

### Task 2.3: CLI ingest 命令工厂化 ✅

- MODIFY: `factory.py` — 新增 `create_instrument_command` 工厂函数
- MODIFY: `market.py` 323→143 行
- MODIFY: `capital.py` 162→34 行
- MODIFY: `fundamental.py` 288→38 行

### Task 2.4: 统一 `_CatalogReader` Protocol — ❌ 取消

**原因**: 3 个独立 `_CatalogReader` Protocol 分别服务于不同服务，是 Interface Segregation Principle 的正确应用，合并会违反 ISP。

**Phase 2 净变化**: ~600 行删除, ~200 行新增

---

## Phase 3: 大文件拆分（中风险）

### Task 3.1: 拆分 `IngestionCoordinator` — ⏭ 跳过

分析后发现方法高度耦合（通过 `self` 共享状态），提取子模块会破坏内聚性，不值得。

### Task 3.2: 拆分 `DerivedPublicationFacade` ✅

- CREATE: `_publication_helpers.py` — 11 个辅助函数
- MODIFY: `publication_facade.py` 751→510 行

### Task 3.3: 拆分 `DerivedMaterializationOrchestrator` — ⏭ 跳过

分析后低于拆分阈值，方法通过 `self` 高度耦合。

### Task 3.4: 拆分 `MarketService` — ⏭ 跳过

分析后方法通过 `self._market_repo` 高度耦合，拆分收益不足。

---

## Phase 4: Protocol 层重设计 ✅

### 分析结论

实际 Protocol 数量：**18 个**（非原计划估计的 60+）

| 分类 | 数量 | 处理 |
|------|------|------|
| 多实现/清晰扩展点（保留） | 14 | 无需修改 |
| 单实现但 DI seam 必要（保留） | 3 | 无需修改 |
| 死代码（删除） | 1 | `RuntimeModeResolver` |

### Task 4.1: 移除 `RuntimeModeResolver` 死代码 ✅

- DELETE: `RuntimeMode` enum, `RuntimeModeResolver` Protocol, `StaticRuntimeModeResolver` dataclass
- MODIFY: `DerivedQueryFacade.__init__` — 移除 `mode_resolver` 参数
- MODIFY: `providers.py` — 移除 `runtime_mode_resolver` provider
- MODIFY: `query/__init__.py` — 移除 re-exports
- MODIFY: 测试文件适配新签名

### Task 4.2: 其他 Protocol — 无需修改

所有剩余 17 个 Protocol 经分析均为架构合理设计，保留不动。

### 保留的 Protocol 清单

- Engine: SlippageModel(2), FillModel(3), SettlementModel(2), FeeModel(2)
- Portfolio: WeightAllocator(2), Constraint(3+), DecisionStage(many)
- Infrastructure: Brokerage, DataFeed, ExecutionPlanner, BuyingPowerModel
- Data: DataProvider, ExchangeTransformer
- Kernel: Clock, EventBus, CommandHandler
- Analytics: PrefixParselet, InfixParselet
- App: UniverseProvider (materialization_orchestrator.py)
- Data quality: InstrumentStoreProtocol, TdxSourceProtocol, ComparisonStoreProtocol

---

## 验证结果

```
pixi run -e dev check
  lint: All checks passed!
  fmt: 1104 files left unchanged
  type: 0 errors, 0 warnings, 0 notes
  test: 4379 passed, 25 skipped, 0 failed

pixi run -e dev arch-check
  Contracts: 22 kept, 0 broken.
```
