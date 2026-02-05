# ParquetStore 优化设计

> 创建日期: 2026-01-27
> 状态: 实施

## 背景

代码审查发现 DataHub Store 层存在以下问题：
1. **PartitionStrategy 未实现**：分区策略硬编码，无法扩展
2. **缺少谓词下推**：读取全部数据再过滤，未利用 Parquet 优势

## 目标

- 实现 PartitionStrategy 抽象，支持可配置的分区策略
- 实现谓词下推优化，减少 I/O 和内存占用

## 设计

### Phase 1: PartitionStrategy 抽象

#### 接口设计

```python
class PartitionStrategy(ABC):
    """分区策略抽象基类"""

    @abstractmethod
    def get_partition_key(self, date_str: str) -> str:
        """从日期字符串提取分区键"""
        pass

    @abstractmethod
    def get_filename(self, partition_key: str) -> str:
        """生成分区文件名"""
        pass

    @abstractmethod
    def get_partitions_from_filters(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> list[str]:
        """根据日期范围获取需要读取的分区键列表"""
        pass
```

#### YearlyPartition 实现

```python
class YearlyPartition(PartitionStrategy):
    """按年分区策略"""

    def get_partition_key(self, date_str: str) -> str:
        return date_str[:4]

    def get_filename(self, partition_key: str) -> str:
        return f"{partition_key}.parquet"

    def get_partitions_from_filters(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> list[str]:
        if not start_date and not end_date:
            return []

        start_year = int(start_date[:4]) if start_date else None
        end_year = int(end_date[:4]) if end_date else None

        if start_year and end_year:
            return [str(y) for y in range(start_year, end_year + 1)]
        elif start_year:
            return [str(start_year)]
        elif end_year:
            return [str(end_year)]

        return []
```

#### ParquetStore 重构

```python
class ParquetStore(BaseStore):
    def __init__(
        self,
        data_root: Path,
        partition_strategy: PartitionStrategy = YearlyPartition(),
    ) -> None:
        super().__init__(data_root)
        self._partition = partition_strategy

    def _get_path(self, dataset: str, partition_key: str) -> Path:
        return self._data_root / dataset / self._partition.get_filename(partition_key)

    def _get_partition_key(self, date_str: str) -> str:
        return self._partition.get_partition_key(date_str)

    def _collect_paths(
        self,
        dataset: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[Path]:
        partition_keys = self._partition.get_partitions_from_filters(start_date, end_date)

        if not partition_keys:
            return list((self._data_root / dataset).glob("*.parquet"))

        return [
            self._get_path(dataset, key)
            for key in partition_keys
            if self._get_path(dataset, key).exists()
        ]
```

### Phase 2: 谓词下推优化

#### 实现方法

```python
def _build_parquet_filters(
    self,
    sids: list[int] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Any:
    """构建 PyArrow 谓词下推过滤器"""
    import pyarrow.dataset as ds

    filters: list[Any] = []

    if sids:
        filters.append(ds.field("sid").isin(sids))

    if start_date:
        filters.append(ds.field("trade_date") >= start_date)

    if end_date:
        filters.append(ds.field("trade_date") <= end_date)

    if not filters:
        return None

    return filters[0] if len(filters) == 1 else filters[0] & filters[1]
```

#### 集成到 read()

```python
def read(self, dataset: str, ...) -> pl.DataFrame:
    # ... 收集 paths ...

    # 构建谓词下推过滤器
    filters = self._build_parquet_filters(sids, start_date, end_date)

    # 使用 pyarrow_filters 参数
    df = pl.read_parquet(paths, pyarrow_filters=filters)

    # ... 应用剩余过滤条件 ...
    return df
```

## 实施计划

| 阶段 | 任务 | 优先级 |
|------|------|--------|
| Phase 1.1 | 新建 partition_strategy.py | P0 |
| Phase 1.2 | 重构 ParquetStore 使用 PartitionStrategy | P0 |
| Phase 1.3 | 添加 PartitionStrategy 单元测试 | P0 |
| Phase 2.1 | 实现 _build_parquet_filters() | P1 |
| Phase 2.2 | 集成谓词下推到 read() | P1 |
| Phase 2.3 | 添加谓词下推测试 | P1 |

## 未采纳的设计

### TableSchema 系统

**原因**：
- 表结构变更不频繁，用 migration SQL 管理更清晰
- 测试中可以在 conftest.py 里统一创建测试表
- 增加抽象层会增加不必要的复杂度

**替代方案**：保持现有的脚本初始化逻辑

### MonthlyPartition

**原因**：YAGNI 原则，需要时再实现

## 参考资料

- [代码审查报告](../design/2026-01-24-datahub-store-layer-design.md)
- [Polars 文档 - read_parquet](https://pola-rs.github.io/polars/docs/python/api/reference/api/polars.read_parquet.html)
- [PyArrow Dataset - Predicate Pushdown](https://arrow.apache.org/docs/python/dataset.html#filtering)
