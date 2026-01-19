# Tushare 端到端集成测试 - 快速参考

## 一分钟快速开始

```bash
# 1. 设置 Token
export TUSHARE_TOKEN="your_token_here"

# 2. 运行测试
./run_external_tests.sh
```

## 测试命令速查

| 场景 | 命令 |
|------|------|
| 运行所有 external 测试 | `pytest ... -m external -v` |
| 跳过 external 测试（CI） | `pytest ... -m "not external" -v` |
| 运行单个测试 | `pytest ...::test_end_to_end_tushare_ingestion -v` |
| 查看测试收集 | `pytest ... --collect-only -q` |
| 运行带详细输出 | `pytest ... -v -s` |

## 测试文件位置

```
packages/datahub/tests/integration/sources/tushare/
├── test_end_to_end.py              # 主测试文件（7个测试）
├── README.md                        # 详细文档
├── IMPLEMENTATION_SUMMARY.md        # 实施总结
├── run_external_tests.sh            # Linux/macOS 脚本
└── run_external_tests.bat           # Windows 脚本
```

## 7个测试场景

1. **完整数据流** - calendar, stock_basic, stock_daily
2. **ETF 数据** - etf_basic, etf_daily
3. **复权因子** - adj_factor, fund_adj
4. **涨跌停和状态** - stock_limit, stock_status
5. **限流验证** - 多次调用验证限流
6. **错误处理** - 无效 token 异常
7. **数据一致性** - 多次调用一致性

## 常见问题

| 问题 | 解决方案 |
|------|---------|
| 未设置 Token | `export TUSHARE_TOKEN="xxx"` |
| 网络错误 | 检查防火墙/代理 |
| 数据为空 | 确认日期是交易日 |
| 认证错误 | 验证 token 有效性 |

## 前置条件

- ✅ TUSHARE_TOKEN 环境变量
- ✅ 网络连接（api.tushare.pro）
- ✅ 交易日数据（2024-01-02）

## 相关文档

- [详细 README](./README.md)
- [实施总结](./IMPLEMENTATION_SUMMARY.md)
- [重构计划](../../../../../docs/plans/2026-01-03-tushare-http-refactor.md)
