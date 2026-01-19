# Checksum 统一化设计方案

**日期**: 2026-01-15
**关联**: PR #36 Code Review - 6️⃣ 数据一致性审查
**状态**: ✅ **已完成** (2026-01-15)

---

## 一、问题分析

### 1.1 当前问题

| 问题 | 描述 | 影响 |
|------|------|------|
| **计算时机不一致** | MetadataManager 在补齐 sid/source **之前**计算，ParquetStoreBase 在**之后**计算 | ingestion_log.checksum ≠ 落盘文件 checksum |
| **行顺序依赖** | `df.to_dict(as_series=False)` 保持当前行顺序，相同数据不同顺序产生不同 checksum | 重复检测失效，日志噪声 |
| **算法不统一** | MetadataManager 使用 SHA-256，ParquetStoreBase 使用 MD5(file) | 无法跨组件验证 |

### 1.2 数据设计分析

**source 字段角色**：
- `ingestion_log.PRIMARY KEY = (dataset, source, trade_date)` - source 是主键的一部分
- 落盘数据通过 `enrich_dataframe` 添加 source 列
- **结论**：source 应该参与 checksum 计算

---

## 二、设计目标

1. **时机统一**：在数据最终状态计算 checksum
2. **算法统一**：所有组件使用 MD5（性能优于 SHA-256）
3. **排序统一**：按数据集类型定义确定性行排序
4. **字段统一**：包含 DataFrame 的所有字段（包括 sid、source）

---

## 三、架构设计

### 3.1 核心：ChecksumCompute 工具类

**位置**: `packages/foundation/src/ditto_foundation/util/checksum.py`

```python
class ChecksumCompute:
    """统一的 Checksum 计算工具."""

    # 数据集排序键配置
    SORT_KEYS: dict[str, list[str]] = {
        "stock_daily": ["trade_date", "sid"],
        "etf_daily": ["trade_date", "sid"],
        "adj_factor": ["trade_date", "sid"],
        "fund_adj": ["trade_date", "sid"],
        "calendar": ["trade_date"],
        "stock_basic": ["ts_code"],
        "etf_basic": ["ts_code"],
    }

    @staticmethod
    def from_dataframe(df: pl.DataFrame, dataset: str) -> str:
        """
        计算 DataFrame 的确定性 checksum.

        流程:
        1. 按 SORT_KEYS 排序（确保确定性）
        2. 转换为字典
        3. orjson 序列化 (OPT_SORT_KEYS)
        4. 计算 MD5
        """
```

**特性**：
- ✅ 确定性：相同数据不同行顺序产生相同 checksum
- ✅ 完整性：包含所有字段（sid、source 等）
- ✅ 一致性：所有组件使用相同算法和排序策略

---

## 四、组件修改方案

### 4.1 Coordinator 删除提前计算

**文件**: `apps/port/src/ditto_port/services/ingestion/coordinator.py`

**删除**：
```python
# Line 163: 删除此行
checksum = self._metadata_manager.compute_checksum(df)
```

**修改**：
```python
# Line 221: 直接使用 write_result.checksum
self._hub.ingestion_log.save_log(
    IngestionLog(
        checksum=write_result.checksum,  # 不再 fallback
        ...
    )
)
```

### 4.2 修改 calendar checksum

**当前**：
```python
checksum = self._metadata_manager.compute_checksum(df)  # SHA-256，不含 source
```

**修改后**：
```python
from ditto_foundation.util.checksum import ChecksumCompute

checksum = ChecksumCompute.from_dataframe(df, "calendar")  # MD5，含所有字段
```

### 4.3 修改 stock_basic/etf_basic

**当前**：
```python
# register_batch 内部计算 MD5(DF)，不含 source
data_dict = df.to_dict(as_series=False)
json_bytes = orjson.dumps(data_dict, ...)
checksum = hashlib.md5(json_bytes).hexdigest()
```

**修改后**：
```python
# 添加 source 列后计算
df_with_source = df.with_columns(pl.lit(source).alias("source"))
checksum = ChecksumCompute.from_dataframe(df_with_source, dataset)
```

---

## 五、测试方案

### 5.1 单元测试

**文件**: `packages/foundation/tests/unit/util/test_checksum.py`

核心测试用例：
- `test_empty_dataframe` - 空数据验证
- `test_deterministic_irrespective_of_row_order` - 行顺序无关性（核心）
- `test_checksum_includes_all_fields` - sid/source 影响
- `test_different_source_produces_different_checksum` - source 差异
- `test_md5_algorithm` - MD5 算法验证

### 5.2 集成测试

**文件**: `apps/port/tests/integration/ingestion/test_checksum_consistency.py`

- `test_stock_daily_checksum_matches_written_file` - 验证落盘一致性
- `test_checksum_consistency_across_retries` - 多次摄入一致性

---

## 六、执行计划

### Phase 1：基础工具（TDD）
- [x] 创建 `ChecksumCompute` 工具类
- [x] 编写单元测试
- [x] 运行测试确保通过

### Phase 2：修改 Coordinator
- [x] 删除提前计算（Line 163）
- [x] 修改 calendar 使用 ChecksumCompute
- [x] 修改 stock_basic/etf_basic
- [x] 修改 save_log 使用 write_result.checksum

### Phase 3：修改 SecurityRepository
- [x] register_batch 使用 ChecksumCompute
- [x] 添加 source 列后计算

### Phase 4：验证
- [x] 运行单元测试（8/8 通过）
- [x] 运行 CI 检查（lint + type 通过）
- [x] 删除遗留代码（MetadataManager.compute_checksum, _json_serializable）
- [x] 更新 README 文档（Foundation + util）

---

## 七、影响范围

| 组件 | 修改类型 | 优先级 |
|------|----------|--------|
| ChecksumCompute | 新建 | P0 |
| coordinator.py | 修改 | P0 |
| security.py | 修改 | P0 |
| test_checksum.py | 新建 | P0 |
| test_checksum_consistency.py | 新建 | P1 |

---

## 八、设计决策记录

### 8.1 为什么选择 MD5 而非 SHA-256？

**决策**：使用 MD5

**理由**：
1. 性能更好（大数据量场景）
2. 与现有 ParquetStoreBase.file_md5 一致
3. 非安全场景，MD5 足够

### 8.2 为什么 source 参与 checksum？

**决策**：source 参与计算

**理由**：
1. ingestion_log PRIMARY KEY 包含 source
2. 落盘数据包含 source 列
3. 不同 source 应有不同的 checksum（追溯性）

### 8.3 为什么按数据集类型选择排序键？

**决策**：按数据集类型配置排序键

**理由**：
1. 不同数据集有不同的主键结构
2. calendar 只有 trade_date
3. daily 数据有 trade_date + sid
4. basic 数据有 ts_code
