# 对账预期结果

该目录存储跨源数据对账的预期结果，用于验证不同数据源之间的一致性。

## 用途

- Tushare vs TDX 数据对账
- 验证价格、成交量等关键字段的偏差在允许范围内
- 记录已知的数据差异及原因

## 文件组织

```
reconciliation/
├── expected_reconciliation.yml      # YAML 格式的预期结果
├── reconciliation_2024-06-28.parquet # Parquet 格式的实际数据（可选）
└── README.md                        # 本文件
```

## 文件格式

### YAML 格式 (expected_reconciliation.yml)

```yaml
metadata:
  trade_date: "2024-06-28"
  tolerance:
    price: 0.0001      # 价格容差 0.01%
    volume: 0.001      # 成交量容差 0.1%

stocks:
  - instrument_id: "600519.XSHG"
    source_ticker: "600519.SH"
    expected_close: 1500.00
    expected_volume: 2500000
```

### Parquet 格式 (可选)

生成脚本：`tests/scripts/generate_reconciliation_data.py`

```bash
uv run --no-sync python tests/scripts/generate_reconciliation_data.py --date 2024-06-28
```

## 对账标准

| 字段 | 容差阈值 | 说明 |
|------|----------|------|
| 收盘价 | 0.01% | 价格精度差异 |
| 开盘价 | 0.01% | 价格精度差异 |
| 最高价 | 0.01% | 价格精度差异 |
| 最低价 | 0.01% | 价格精度差异 |
| 成交量 | 0.1% | 统计口径差异 |

## 已知差异说明

1. **成交量差异**: Tushare 对停牌复牌后的成交量可能有事后修正
2. **价格精度**: 四舍五入可能导致微小差异
3. **ST 股票**: 低流动性股票数据质量较低
