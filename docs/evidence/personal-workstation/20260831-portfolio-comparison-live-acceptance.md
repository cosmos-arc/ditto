# CMP-07 三组合与仓位预演 Live 验收

## 结果

PASS。验收使用 fresh `/private/tmp` 数据根和生产 composition/read path，写入真实 Parquet provider payload、ProviderSnapshot、校验过 checksum 的 Signal Package、SQLite Paper session/journal 与 Manual 追加式账本，再通过真实 FastAPI 和 `VITE_USE_MOCK=false` 的页面完成 MODEL / PAPER / MANUAL 三栏比较。

页面同时显示精确 `as_of`、valuation snapshot 和 source snapshot。MODEL → PAPER 分离未成交、滑点、费用与风险阻塞；MODEL → MANUAL 将差异标记为用户选择。Scenario 以 MODEL 为基线，在单仓上限 0.80、现金保留 0.20 和市场冲击 -0.05 下返回 200，换手率为 2.500001%，压力收益从 -4.2500001% 变为 -4.00%。页面只显示预演结果，没有 apply、写账户或写 target 动作。

## 视觉与交互

| viewport | 三栏宽度 | 横向溢出 | console warning/error |
|---|---:|---|---:|
| 1200×900 | 365 / 365 / 365 | 无 | 0 |
| 1366×900 | 421 / 421 / 421 | 无 | 0 |
| 1536×960 | 477 / 477 / 477 | 无 | 0 |

真实浏览器交互还发现并修复了两个仅靠直接路由单测未覆盖的 HTTP 合同问题：GET 的 snapshot array 曾被生成成 request body；POST 严格 DTO 曾拒绝 OpenAPI 声明的 JSON array。两处均新增回归断言，修复后真实 GET 和 POST 都返回 200。

## 边界声明

该验收不访问网络 provider，也不写用户配置的数据根；它证明 production read path、HTTP 契约和 live frontend 的确定性集成，不等同于真实供应商验收。`real_trading_day_count` 仍为 0，不推进 PAP-09 的 20 个真实 A 股交易日 soak。当前验收 URL 暂在 `/trading/portfolio`；I13 会按计划硬切到五域路由。

机器证据见 [20260831-portfolio-comparison-live-acceptance.json](20260831-portfolio-comparison-live-acceptance.json)。可重放夹具：

```bash
pixi run -e dev python scripts/evidence/portfolio_comparison_live_fixture.py --data-root /private/tmp/<fresh-empty-directory>
```
