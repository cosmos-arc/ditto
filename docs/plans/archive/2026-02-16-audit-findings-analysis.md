# 架构审计发现分析

> 分析日期：2026-02-16
> 状态：进行中

## 审计发现清单

### ✅ 确认修复

| ID | 严重度 | 问题 | 修复方案 | Effort |
|----|--------|------|---------|--------|
| ARCH-001 | High | DQSeverity 定义在 Infra，Core 反向依赖 | 下沉到 Core，删除 Infra 和 DataHub 的重复定义 | S |
| ARCH-003 | Blocker | 启动失败静默继续，服务可能以不完整配置运行 | STARTUP 场景引入 fail-fast | S |
| ENG-002 | Medium | `detect_asset_class` 重复定义 | MarketService 调用 `InstrumentIdRange.detect_asset_class`，删除私有方法 | S |
| ENG-003 | High | SQLitePool 连接为线程本地，close() 仅关闭当前线程 | 增加 `close_all()` 追踪所有线程连接 | M |
| ENG-006 | Low | 遗留代码未清理 | 删除 `jobs/context.py` 中的废弃函数和 `scripts/archive/` | S |

### ✅ 确认重构

| ID | 严重度 | 问题 | 修复方案 | Effort |
|----|--------|------|---------|--------|
| ARCH-004 | Medium | CLIExecutor 参数透传地狱（存储 6 个服务但不使用） | 重构依赖链，CLIExecutor 只接收已组装的 coordinator + backfill_manager | M |

### ❌ 移除（误判或非问题）

| ID | 原判断 | 分析结论 |
|----|--------|---------|
| ARCH-002 | DQSeverity 多处重复 | 合并到 ARCH-001 统一处理 |
| ARCH-005 | Port→DataHub 167 imports 过度绑定 | **误判**：Port 是应用层，DataHub 是数据层，依赖方向正确。registry/datahub 的 82 处导入是 DI 注册绑定的职责 |
| ENG-001 | Dataset handlers 重复 | **非重复**：三处映射视角不同（配置/读取/写入），暂不处理收益一般 |

### ⏳ 合并处理

| ID | 问题 | 合并到 |
|----|------|--------|
| ENG-004 | CLI 通过 os.environ 注入配置覆盖 | **ARCH-004**（依赖链重构时一并解决） |

### ✅ 已修复

| ID | 问题 | 状态 |
|----|------|------|
| ENG-005 | 日志测试端点生产环境暴露 | 已有运行时 404 检查，可选：按环境条件注册 |

---

## 详细分析

### ARCH-001/002: DQSeverity 归属问题

**当前状态**：
```
Infra (定义) ← Core (使用)  ❌ 依赖方向错误
DataHub (定义，未使用)      ❌ 死代码
```

**验证发现**：
- Infra 定义 DQSeverity 但**内部完全不使用**，只是 re-export
- DataHub 定义 DQSeverity 但**源码从未使用**，只有测试引用
- Core 才是真正的消费者（3 处源码 + 1 处测试）

**修复方案**：
```
Core (定义 + 使用)           ✅ 真源
Infra → 删除整个 foundation/quality/ 目录
DataHub → 删除 DQSeverity 定义
```

**改动文件**：
- `+ packages/core/src/ditto_core/quality/severity.py`（新增）
- `- packages/infra/src/ditto_infra/foundation/quality/`（整个目录删除）
- `~ packages/datahub/src/ditto_datahub/models/common.py`（删除 DQSeverity）
- `~ 6 处导入修正`：`from ditto_infra.foundation import DQSeverity` → `from ditto_core.quality import DQSeverity`

---

### ARCH-003: 启动初始化 fail-fast

**问题位置**：`initializer.py:107-113`

```python
except Exception as e:
    logger.error(f"Config init {provider.name} failed: {e}")
    results[provider.name] = InitResult(
        provider=provider.name,
        success=False,
        message=f"{type(e).__name__}: {e}",
    )
    # 不 raise，继续执行
```

**风险**：服务可能以不完整 schema/配置运行。

**修复方案**：STARTUP 场景引入 fail-fast：
```python
if scope == InitScope.STARTUP and any(not r.success for r in results.values()):
    raise ConfigInitError(f"Startup initialization failed: {failed_providers}")
```

---

### ARCH-004: CLIExecutor 依赖链重构

**当前依赖链**：
```
CLIExecutor
  ├── 存储 6 个服务（但不直接使用任何！）
  ├── create_coordinator() → 透传 6 个服务
  │     └── IngestionCoordinator
  │           └── IngestionDataWriter（真正的消费者）
  └── BackfillManager
```

**问题**：
- CLIExecutor 是"参数中转站" — 存储 6 个服务但一个不用
- 每次新增服务依赖，需要同步修改 4 处

**修复方案**：CLIExecutor 只接收已组装好的依赖：
```python
# Before
class CLIExecutor:
    def __init__(self, metadata, market, fundamental, capital, macro, source, log, source_name):
        ...

# After
class CLIExecutor:
    def __init__(self, coordinator: IngestionCoordinator, backfill_manager: BackfillManager):
        self._coordinator = coordinator
        self._backfill_manager = backfill_manager
```

---

### ARCH-005: Port→DataHub 导入分析

**按目录分布**：

| 目录 | 导入数 | 性质 | 判断 |
|------|--------|------|------|
| `registry/datahub` | 82 | DI 注册绑定 DataHub 实现 | ✅ 合理 — registry 职责 |
| `services/ingestion` | 29 | 编排层调用数据服务 | ✅ 合理 — 应用层编排数据层 |
| `cli` | 22 | CLI 调用数据服务 | ✅ 合理 |
| `registry/contexts` | 14 | 上下文管理 | ✅ 合理 |

**结论**：Port 作为应用编排层，依赖 DataHub 的服务和模型是**职责所在**，不存在"过度绑定"问题。

---

### ENG-002: detect_asset_class 重复

**重复代码位置**：
- `models/common.py` — `InstrumentIdRange.detect_asset_class()` [类方法]
- `services/market_service.py` — `_detect_asset_class_from_instrument_ids()` [私有方法]

**两者逻辑完全相同**：
```python
# 都是这段逻辑
stock_range = get_range("stock")
etf_range = get_range("etf")
has_stock = any(stock_range.min_id <= id <= stock_range.max_id for id in ids)
...
```

**修复**：删除 MarketService 的私有方法，直接调用 `InstrumentIdRange.detect_asset_class()`

---

### ENG-003: SQLitePool 连接泄漏

**问题**：`close()` 只关闭当前线程的连接，后台线程连接可能滞留。

```python
def close(self) -> None:
    if hasattr(self._local, "conn"):
        self._local.conn.close()  # 只关闭当前线程
```

**修复**：
1. 增加 `_all_connections: list[sqlite3.Connection]` 追踪所有线程连接
2. 增加 `close_all()` 方法关闭所有连接
3. 应用 shutdown 时强制调用

---

### ENG-005: 日志测试端点

**当前状态**：已有运行时检查
```python
@app.get("/api/v1/logs/test")
async def generate_test_logs():
    env = get_environment()
    if env.is_production:
        raise HTTPException(status_code=404, detail="Not found")
```

**剩余问题**：路由始终注册，仍会暴露在 OpenAPI 文档中。

**可选修复**：按环境条件注册路由（仅 dev/testing）

---

### ENG-006: 遗留代码

**待清理**：
- `apps/port/src/ditto_port/jobs/context.py` — `create_metadata_context()`, `create_dq_context()` 已被替代
- `scripts/archive/*.deprecated` — 归档脚本

---

## 修复计划（一次性修复）

用户选择：**B) 一次性修复** — P0 + P1 合并处理

### PR 清单

| PR | 覆盖 ID | 内容 | Effort | 优先级 |
|----|---------|------|--------|--------|
| PR-1 | ARCH-001/002 | DQSeverity 下沉到 Core，删除 Infra/DataHub 重复定义 | S | High |
| PR-2 | ARCH-003 | 启动初始化 fail-fast（STARTUP 场景） | S | Blocker |
| PR-3 | ARCH-004 + ENG-004 | CLIExecutor 依赖链重构 + 消除 os.environ 副作用 | M | Medium |
| PR-4 | ENG-002 | 删除重复的 `detect_asset_class`，调用 `InstrumentIdRange` | S | Medium |
| PR-5 | ENG-003 | SQLitePool 增加 `close_all()`，追踪所有线程连接 | M | High |
| PR-6 | ENG-006 | 清理遗留代码（jobs/context.py, scripts/archive） | S | Low |
| PR-7 | ENG-005 | （可选）生产环境按条件注册日志测试端点 | S | Low |

### 执行顺序建议

```
Phase 1: 基础修复（无依赖）
├── PR-1: DQSeverity 下沉
├── PR-2: 启动 fail-fast
└── PR-4: 删除重复方法

Phase 2: 架构重构
└── PR-3: CLIExecutor 依赖链重构

Phase 3: 清理完善
├── PR-5: SQLitePool close_all
├── PR-6: 清理遗留代码
└── PR-7: 日志端点（可选）
```

### 回滚策略

| PR | 回滚策略 |
|----|---------|
| PR-1 | 保留兼容 re-export 一个版本后删除 |
| PR-2 | 保留单点开关将 raise 降级为 error log |
| PR-3 | 先新增入口，验证后删除旧入口 |
| PR-5 | 保留旧 close() 路径，close_all() 逐步接入 |

---

## 变更记录

- 2026-02-16：初始分析，确认 ARCH-001/003/004/ENG-002/003/006，移除 ARCH-005/ENG-001
- 2026-02-16：ENG-004 合并到 ARCH-004，更新修复计划
