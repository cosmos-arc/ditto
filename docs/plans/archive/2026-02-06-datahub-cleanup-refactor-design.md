# datahub 清理重构设计文档

**创建日期**: 2026-02-06
**状态**: 已批准
**执行策略**: 渐进式（阶段 1 + 阶段 2）

---

## 1. 设计概要

### 目标
清理 datahub 包的遗留代码，统一 Domains 层实现模式，提升架构一致性。

### 变更范围
- **阶段 1**：文档清理（极低风险）
- **阶段 2**：Domains 层统一（中等风险）
- **阶段 3**：Stores 层优化（**暂缓执行**）

---

## 2. 目录结构变更

### 变更前后对比

```
# 变更前
packages/data/src/ditto_data/
├── accessors/
│   ├── internal/
│   │   ├── adjustment.py
│   │   ├── enrichment.py          # 删除（已搬迁到 ditto-port）
│   │   └── pit.py
│   └── instrument_accessor.py     # 删除（功能迁移到 MetadataService）
│
├── domains/features/technical/
│   ├── indicator_store.py
│   └── indicator_metadata_store.py
│
└── stores/
    └── universe_store.py
```

```
# 变更后
packages/data/src/ditto_data/
├── helpers/                           # 原 accessors/，重命名
│   ├── __init__.py
│   ├── adjustment.py                  # 复权计算
│   └── pit.py                         # PIT 工具
│
├── domains/
│   ├── features/technical/
│   │   ├── technical_indicator_store.py
│   │   └── technical_indicator_metadata_store.py
│   │
│   └── metadata/
│       ├── metadata_service.py        # 扩展
│       └── universe/
│           ├── __init__.py
│           └── universe_store.py      # 从 stores/ 迁移
│
└── stores/
    └── (universe_store.py 已删除)
```

---

## 3. MetadataService API 扩展

### 新增方法

```python
class MetadataService:
    # ... 现有方法 ...

    @traced("metadata.security.register_securities_batch")
    def register_securities_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        src_code_col: str = "ts_code",
    ) -> tuple[str, str]:
        """
        批量注册证券（跳过已存在的）。

        迁移自 InstrumentsAccessor.register_batch()

        Args:
            df: 包含证券元数据的 DataFrame
            source: 数据源标识符
            asset_class: 资产类别
            src_code_col: 源代码列名

        Returns:
            (file_path, checksum) 元组
        """

    @traced("metadata.security.resolve_or_create_batch")
    def resolve_or_create_batch(
        self,
        df: pl.DataFrame,
        source: str,
        asset_class: Literal["stock", "etf"],
        src_code_col: str = "ts_code",
    ) -> dict[str, int]:
        """
        批量解析 src_code，不存在则自动创建证券。

        迁移自 InstrumentsAccessor.resolve_or_create_batch()

        Args:
            df: 包含证券元数据的 DataFrame
            source: 数据源标识符
            asset_class: 资产类别
            src_code_col: 源代码列名

        Returns:
            {src_code: sid} 映射字典
        """
```

**注意**：`enrich_with_sid` 功能不由 datahub 提供，由 ditto-port Application 层自行实现。

---

## 4. 依赖变更

### hub.py

```python
# 移除
- from ditto_data.accessors.instrument_accessor import InstrumentsAccessor

# MetadataService 保持现有依赖注入（已有 sid_allocator）
```

### Provider 配置

`apps/port/src/ditto_port/registry/datahub.py`:
- 移除 `InstrumentsAccessor` provider
- 证券注册功能通过 `hub.metadata.resolve_or_create_batch()` 调用

### Application 层（ditto-port）

`apps/port/src/ditto_port/services/ingestion/data_writer.py`:
- 使用 `hub.metadata.resolve_or_create_batch()` 批量注册
- Application 层自行组合数据

---

## 5. 测试迁移

### 测试目录结构

```
packages/data/tests/
├── unit/
│   ├── helpers/                          # 原 accessors/
│   │   ├── test_adjustment_unit.py
│   │   └── test_pit_unit.py
│   │
│   ├── domains/
│   │   ├── features/technical/
│   │   │   └── test_technical_indicator_store_unit.py
│   │   │
│   │   └── metadata/
│   │       ├── universe/
│   │       │   └── test_universe_store_unit.py
│   │       └── test_metadata_service_unit.py  # 新增
│   │
│   └── stores/                            # 移除 universe 相关测试
│
└── integration/
    └── domains/metadata/universe/
        └── test_universe_store_integration.py
```

---

## 6. 文档更新

### 新建文档
- `helpers/README.md` - 说明纯函数工具用途

### 更新文档
- `stores/README.md` - 移除 UniverseStore 引用
- `packages/data/README.md` - 更新架构描述

### 删除文档
- `accessors/README.md`（目录重命名后无意义）

---

## 7. 验证计划

每个阶段完成后运行：

```bash
# 类型检查
pixi run -e dev type

# 代码检查
pixi run -e dev lint

# 单元测试
pixi run -e dev test --unit

# 集成测试
pixi run -e dev test --integration

# 完整 CI
pixi run -e dev ci
```

---

## 8. 风险缓解

| 风险 | 缓解措施 |
|------|----------|
| 导入路径破坏 | 全量测试覆盖，分步提交 |
| 依赖注入配置错误 | 逐个测试验证，保留回滚点 |
| Application 层调用失败 | 确保 MetadataService API 完全兼容 |

---

## 9. 回滚计划

每个阶段完成后创建 git commit：
- `阶段1完成：清理文档`
- `阶段2完成：统一Domains层实现模式`
