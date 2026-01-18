# Runtime 与 Foundation 边界重构设计

**日期**: 2026-01-17
**状态**: 设计中
**优先级**: P2（架构优化）

---

## 一、背景

### 问题陈述

ditto_datahub 下的 runtime 模块包含了多种组件，边界不够清晰：

1. **纯技术组件**（cache、file_lock、sqlite_pool）与领域相关技术组件混在一起
2. foundation/config 包含了业务配置（DataSourceSettings）和未使用的配置项
3. runtime 的命名语义模糊，与 foundation 的边界不够清晰
4. schema.sql 是项目脚本，不应混在 runtime 代码模块中

### 目标

1. **明确边界**：建立清晰的 runtime 与 foundation 划分规则
2. **提升复用**：将纯技术组件迁移到 foundation，支持跨项目复用
3. **清理冗余**：删除未使用的配置，移动业务配置到正确层级
4. **脚本分离**：将 schema.sql 等脚本文件移到专门的 scripts 目录
5. **更新规范**：将决策树和规则写入架构规范文档

---

## 二、边界划分规则

### 2.1 核心原则

| 维度 | Foundation | Runtime |
|------|-----------|---------|
| **领域知识** | 零领域概念 | 可包含领域概念 |
| **外部依赖** | 标准库 + 基础设施库 | 可依赖领域相关库 |
| **复用性** | 可独立提取为包 | 与 datahub 耦合 |
| **依赖内部模型** | 不依赖 datahub.models | 可依赖 datahub.models |

### 2.2 开发者决策树

```
这是技术组件还是业务逻辑？
├── 技术组件 → 是否依赖领域模型？
│   ├── 是 → runtime/
│   └── 否 → foundation/
└── 业务逻辑 → repositories/, stores/, models/

或：这个组件能否独立提取为单独的包给其他项目用？
├── 能 → foundation/
└── 不能（依赖 Ditto 领域模型） → runtime/

或：这是代码模块还是项目脚本？
├── Python 代码模块 → runtime/ 或 foundation/
└── SQL/Shell 脚本 → scripts/
```

### 2.3 判断示例

| 问题 | Foundation | Runtime | Scripts |
|------|-----------|---------|---------|
| 缓存实现需要知道"证券"吗？ | ✅ DataCache | ❌ | ❌ |
| 文件锁需要知道"交易日"吗？ | ✅ FileLockManager | ❌ | ❌ |
| SID 分配需要知道"股票/ETF"吗？ | ❌ | ✅ SidAllocator | ❌ |
| SQL 引擎需要知道"复权"吗？ | ❌ | ✅ SqlEngine | ❌ |
| 数据质量检查需要知道"涨跌幅"吗？ | ❌ | ✅ dq_rules | ❌ |
| 这是 Python 代码还是 SQL 脚本？ | ❌ | ❌ | ✅ schema.sql |

---

## 三、改造计划

### 3.1 组件迁移清单

#### 迁移到 foundation 的组件

| 源路径 | 目标路径 | 理由 |
|--------|---------|------|
| `datahub/runtime/cache.py` | `foundation/cache.py` | 纯技术，无领域概念 |
| `datahub/runtime/file_lock.py` | `foundation/concurrency.py` | 纯技术，并发控制 |
| `datahub/runtime/sqlite_pool.py` | `foundation/db/sqlite_pool.py` | 纯技术，数据库连接管理 |

#### 拆分设计的组件

| 源路径 | 拆分方案 |
|--------|---------|
| `datahub/runtime/freeze_manager.py` | checksum 逻辑 → `foundation/version.py`<br>freeze 领域逻辑 → 保留在 `runtime/` |

#### 保留在 datahub/runtime 的组件

| 组件 | 保留理由 |
|------|---------|
| `sid_allocator.py` | 依赖 AssetSidRange 模型，金融资产分类 |
| `sql_engine.py` | Parquet views 与数据集紧耦合 |
| `pit_helper.py` | PIT 概念属于 datahub 领域 |
| `dq_rules.py` | 强业务领域（OHLC、涨跌幅） |

#### 移动到 scripts 的脚本文件

| 源路径 | 目标路径 | 理由 |
|--------|---------|------|
| `datahub/runtime/schema.sql` | `datahub/scripts/schema.sql` | SQL 脚本文件，不是 Python 代码模块 |

---

### 3.2 foundation/config 清理计划

#### 删除的配置

```python
# 完全未使用
class APISettings:  # host, port 从未被使用

# 未使用的字段
SystemSettings.log_level    # 与 Observability 重复
SystemSettings.timezone     # 从未被读取
SystemSettings.debug        # 从未被读取
ObservabilitySettings.metrics_interval_ms  # 从未被读取

# 与 get_paths() 重复
class FileStorageSettings  # data_root, log_root 等
```

#### 清理后的 foundation/config 结构

```
ditto_foundation/config/
├── __init__.py       # 导出 get_settings()
├── settings.py       # 只保留 SystemSettings (ditto_env)
├── paths.py          # XDG 路径管理（保留）
├── initializer.py    # 配置初始化协调器（保留）
└── manager.py        # 单例管理器（保留）
```

---

### 3.3 迁移后的目录结构

```
ditto_foundation/
├── cache.py              # 新增：从 datahub/runtime 迁移
├── concurrency.py        # 新增：从 datahub/runtime 迁移
├── db/
│   └── sqlite_pool.py    # 新增：从 datahub/runtime 迁移
├── version.py            # 新增：从 freeze_manager 拆分的 checksum 逻辑
├── config/
│   ├── settings.py       # 简化：只保留 SystemSettings
│   ├── paths.py
│   ├── initializer.py
│   └── manager.py
├── observability/
└── util/

ditto_datahub/
├── scripts/              # 新增：项目脚本目录
│   └── schema.sql        # 从 runtime 移动
├── runtime/
│   ├── freeze_manager.py # 简化：移除 checksum 逻辑，使用 foundation.version
│   ├── sid_allocator.py
│   ├── sql_engine.py
│   ├── pit_helper.py
│   └── dq_rules.py
├── models/
├── repositories/
├── stores/
└── hub.py
```

---

## 四、实施步骤

### Step 1: Foundation 扩展（新增模块）

1. 创建 `foundation/cache.py`
   - 迁移 `DataCache`、`CacheStats`
   - 更新导入路径为 `ditto_foundation`
   - 添加模块文档说明通用缓存能力

2. 创建 `foundation/concurrency.py`
   - 迁移 `FileLockManager`、`LockAcquisitionError`
   - 更新导入路径为 `ditto_foundation`
   - 添加模块文档说明并发控制能力

3. 创建 `foundation/db/__init__.py` 和 `foundation/db/sqlite_pool.py`
   - 迁移 `SQLitePool`
   - 更新导入路径为 `ditto_foundation`
   - 更新 `_get_schema()` 方法中的 schema 路径引用
   - 添加模块文档说明数据库连接管理能力

4. 创建 `foundation/version.py`
   - 从 `freeze_manager.py` 拆分 checksum 计算逻辑
   - 提供通用的版本管理能力（不依赖 FreezeManifest）

### Step 2: DataHub 适配（更新引用）

1. 创建 `datahub/scripts/` 目录
   - 移动 `schema.sql` 到 `datahub/scripts/schema.sql`
   - 更新 `SQLitePool._get_schema()` 中的路径引用

2. 更新 `runtime/cache.py`
   - 改为从 `ditto_foundation.cache` 导入并 re-export
   - 或删除文件，更新所有引用方

3. 更新 `runtime/file_lock.py`
   - 改为从 `ditto_foundation.concurrency` 导入并 re-export
   - 或删除文件，更新所有引用方

4. 更新 `runtime/sqlite_pool.py`
   - 改为从 `ditto_foundation.db.sqlite_pool` 导入并 re-export
   - 或删除文件，更新所有引用方

5. 更新 `runtime/freeze_manager.py`
   - 改用 `ditto_foundation.version` 的 checksum 逻辑
   - 保留 freeze 领域逻辑（manifest 管理）

6. 更新所有引用方
   - Store 层（SecurityStore、CalendarStore）
   - Repository 层（BarsRepository、AdjFactorRepository）
   - Hub 层（DataHub）

### Step 3: Config 清理

1. 删除未使用的配置
   - 删除 `APISettings` 类
   - 删除 `SystemSettings.log_level`、`timezone`、`debug`
   - 删除 `ObservabilitySettings.metrics_interval_ms`
   - 删除 `FileStorageSettings` 类

2. 更新文档
   - 更新 `README.md` 配置说明
   - 更新示例代码中的配置引用

### Step 4: 更新架构规范文档

#### 4.1 更新 `.claude/rules/architecture.md`

在"横切层 (Foundation)"部分添加：

```markdown
### 横切层 (Foundation)

**定义**：提供跨所有层的基础设施服务，可被任何层访问

**包含模块**：
- `config` - 配置管理（Settings、路径管理）
- `observability` - 可观测性（日志、追踪、指标）
- `util` - 通用工具（校验和、日期处理）
- `cache` - 通用缓存（DataCache）
- `concurrency` - 并发控制（FileLockManager）
- `db` - 数据库连接管理（SQLitePool）
- `version` - 版本管理（Checksum、版本标识）
```

在"子领域分层规范"部分后添加"runtime 与 foundation 边界"小节：

```markdown
### Runtime 与 Foundation 边界

**核心原则**：

| 维度 | Foundation | Runtime |
|------|-----------|---------|
| **领域知识** | 零领域概念 | 可包含领域概念 |
| **外部依赖** | 标准库 + 基础设施库 | 可依赖领域相关库 |
| **复用性** | 可独立提取为包 | 与 datahub 耦合 |
| **依赖内部模型** | 不依赖 datahub.models | 可依赖 datahub.models |

**开发者决策树**：

```
这是技术组件还是业务逻辑？
├── 技术组件 → 是否依赖领域模型？
│   ├── 是 → runtime/
│   └── 否 → foundation/
└── 业务逻辑 → repositories/, stores/, models/

这是代码模块还是项目脚本？
├── Python 代码模块 → runtime/ 或 foundation/
└── SQL/Shell 脚本 → scripts/
```

**判断示例**：

| 问题 | Foundation | Runtime | Scripts |
|------|-----------|---------|---------|
| 缓存实现需要知道"证券"吗？ | ✅ DataCache | ❌ | ❌ |
| 文件锁需要知道"交易日"吗？ | ✅ FileLockManager | ❌ | ❌ |
| SID 分配需要知道"股票/ETF"吗？ | ❌ | ✅ SidAllocator | ❌ |
| SQL 引擎需要知道"复权"吗？ | ❌ | ✅ SqlEngine | ❌ |
| 这是 Python 代码还是 SQL 脚本？ | ❌ | ❌ | ✅ schema.sql |
```

#### 4.2 更新 `docs/design/01_system_design.md`

在"3.1 层次划分"的 Foundation Layer 部分添加：

```markdown
| **Foundation Layer** | 基础设施横切层 | `packages/foundation/` |
| ├── config | 配置管理 | `foundation/config/` |
| ├── observability | 可观测性 | `foundation/observability/` |
| ├── util | 通用工具 | `foundation/util/` |
| ├── cache | 通用缓存 | `foundation/cache.py` |
| ├── concurrency | 并发控制 | `foundation/concurrency.py` |
| ├── db | 数据库连接 | `foundation/db/` |
| └── version | 版本管理 | `foundation/version.py` |
```

在"3.2 目录结构"的 foundation 部分更新：

```markdown
  foundation/               # 横切层（基础设施）
    src/
      ditto_foundation/
        config/           # 配置管理
        observability/    # 可观测性
        util/             # 通用工具
        cache.py          # 通用缓存
        concurrency.py    # 并发控制
        db/               # 数据库连接
          sqlite_pool.py
        version.py        # 版本管理
```

在"3.2 目录结构"的 datahub 部分更新：

```markdown
        scripts/          # 项目脚本（SQL、Shell 等）
          schema.sql      # 数据库初始化脚本
        runtime/          # 运行时支持（领域相关技术组件）
          freeze_manager.py  # 数据版本管理
          sid_allocator.py   # SID 分配器
          sql_engine.py      # SQL 查询引擎
          pit_helper.py      # PIT 辅助函数
          dq_rules.py        # 数据质量规则
```

在"3.3 依赖关系"添加 Foundation 模块说明：

```markdown
**Foundation Layer** 包含：
- **config**：配置管理（Settings、路径管理）
- **observability**：可观测性（日志、追踪、指标）
- **util**：通用工具（校验和、日期处理）
- **cache**：通用缓存（DataCache）
- **concurrency**：并发控制（FileLockManager）
- **db**：数据库连接管理（SQLitePool）
- **version**：版本管理（Checksum、版本标识）

与 Runtime 的区别：
- **Foundation**：纯技术组件，无领域概念，可独立复用
- **Runtime**：领域相关技术组件，依赖 datahub 模型

Scripts 目录：
- **scripts**：项目脚本文件（SQL、Shell 等），与代码模块分离
```

### Step 5: 测试与验证

1. 单元测试
   - 确保所有测试通过
   - 更新测试中的导入路径

2. 集成测试
   - 验证迁移后的组件功能正常
   - 验证配置加载正常
   - 验证 schema.sql 路径引用正确

3. 类型检查
   - `pixi run type` 通过
   - 修复所有类型错误

4. 代码质量
   - `pixi run lint` 通过
   - `pixi run fmt` 格式化

---

## 五、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 导入路径变更导致引用方报错 | 高 | 先在 foundation 创建新模块，datahub re-export 过渡 |
| schema.sql 路径变更导致初始化失败 | 高 | 更新 SQLitePool._get_schema() 中的路径引用 |
| 配置清理导致现有代码报错 | 中 | 全面搜索引用，确保无遗漏 |
| freeze_manager 拆分逻辑复杂 | 中 | 仔细梳理 checksum 和 freeze 领域逻辑的边界 |
| 测试覆盖不足 | 低 | 现有测试覆盖较好，迁移后补充测试 |

---

## 六、验证清单

完成后验证：

- [x] cache、file_lock、sqlite_pool 已迁移到 foundation
- [x] freeze_manager 已拆分，checksum 逻辑在 foundation
- [x] schema.sql 已移动到 datahub/scripts/
- [x] SQLitePool._get_schema() 已更新路径引用
- [x] datahub/runtime 中原文件已删除（直接删除，非 re-export）
- [x] 所有引用方的导入路径已更新
- [x] 未使用的配置已删除
- [x] 架构规范文档已更新（包含决策树）
- [x] 所有测试通过（单元 + 集成）
- [x] 类型检查通过（pyright strict）
- [ ] 代码质量检查通过（ruff）- 部分错误在其他模块

---

## 七、参考

- 业界最佳实践：DDD 分层架构
- Foundation 层规范：`.claude/rules/foundation.md`
- DataHub 层规范：`.claude/rules/datahub.md`
- 系统设计文档：`docs/design/01_system_design.md`
