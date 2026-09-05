# PIT 快照预期数据

该目录存储黄金数据集的 PIT（Point-In-Time）快照预期结果，用于验证数据查询的时点隔离性。

## 用途

- 存储 Parquet 格式的快照文件
- 验证 PIT 查询无未来数据泄漏
- 作为测试断言的黄金标准

## 文件命名规范

```
<instrument_id>_as_of_<YYYY-MM-DD>.parquet
```

示例：`000001_as_of_2024-06-30.parquet`

## 注意事项

- 快照数据应与黄金数据集配置（`config/default/golden_dataset.yml`）保持一致
- 文件生成后应通过版本控制追踪，确保测试可复现
