# Ditto 产品页面完成看板

> 生成日期：2026-08-29
> 生成命令：`bun run audit:product-board`
> 口径：只认合同与可执行证据。`prototypeVerified` 不等于 `reactParityVerified`；workflow 只有在 route、live data、React parity、通用状态测试和 overlay 全部闭环时才为 ✅。

当前严格闭环：**33/36**。⬜ 表示尚无足够证据，不代表路由不存在。

| Route | Route | Live data | Visual parity | States | Overlays | Workflow |
|---|---:|---:|---:|---:|---:|---:|
| `/` | ✅ | ✅ | ✅ | 13 declared / 2 tests | 4/4 | ✅ |
| `/instruments/$id` | ✅ | ✅ | ✅ | 9 declared / 2 tests | 6/6 | ✅ |
| `/markets` | ✅ | ✅ | ✅ | 8 declared / 2 tests | 5/5 | ✅ |
| `/markets/a-shares` | ✅ | ✅ | ✅ | 7 declared / 2 tests | 4/4 | ✅ |
| `/markets/industries` | ✅ | ✅ | ⬜ | 10 declared / 1 tests | ✅ none | ⬜ |
| `/markets/screener` | ✅ | ✅ | ⬜ | 10 declared / 1 tests | ✅ none | ⬜ |
| `/markets/watchlist` | ✅ | ✅ | ✅ | 8 declared / 2 tests | 2/2 | ✅ |
| `/portfolio` | ✅ | ✅ | ✅ | 9 declared / 2 tests | ✅ none | ✅ |
| `/portfolio/manual` | ✅ | ✅ | ✅ | 10 declared / 2 tests | ✅ none | ✅ |
| `/portfolio/model` | ✅ | ✅ | ✅ | 11 declared / 3 tests | ✅ none | ✅ |
| `/portfolio/paper` | ✅ | ✅ | ✅ | 11 declared / 2 tests | ✅ none | ✅ |
| `/portfolio/review` | ✅ | ✅ | ✅ | 12 declared / 1 tests | 4/4 | ✅ |
| `/portfolio/risk` | ✅ | ✅ | ✅ | 15 declared / 2 tests | 3/3 | ✅ |
| `/portfolio/transactions` | ✅ | ✅ | ✅ | 10 declared / 1 tests | 4/4 | ✅ |
| `/research` | ✅ | ✅ | ✅ | 9 declared / 4 tests | 5/5 | ✅ |
| `/research/agent` | ✅ | ✅ | ✅ | 16 declared / 3 tests | 9/9 | ✅ |
| `/research/backtests` | ✅ | ✅ | ✅ | 12 declared / 2 tests | 1/1 | ✅ |
| `/research/backtests/$id` | ✅ | ✅ | ✅ | 18 declared / 2 tests | 5/5 | ✅ |
| `/research/experiments` | ✅ | ✅ | ✅ | 11 declared / 2 tests | 1/1 | ✅ |
| `/research/experiments/$id` | ✅ | ✅ | ✅ | 14 declared / 4 tests | ✅ none | ✅ |
| `/research/experiments/new` | ✅ | ✅ | ✅ | 13 declared / 1 tests | ✅ none | ✅ |
| `/research/factors` | ✅ | ✅ | ✅ | 8 declared / 2 tests | 1/1 | ✅ |
| `/research/factors/$id` | ✅ | ✅ | ✅ | 9 declared / 3 tests | 4/4 | ✅ |
| `/research/reviews` | ✅ | ✅ | ✅ | 10 declared / 1 tests | ✅ none | ✅ |
| `/research/reviews/$id` | ✅ | ✅ | ✅ | 16 declared / 2 tests | 1/1 | ✅ |
| `/research/strategies` | ✅ | ✅ | ✅ | 10 declared / 1 tests | 2/2 | ✅ |
| `/research/strategies/$id` | ✅ | ✅ | ✅ | 12 declared / 4 tests | 4/4 | ✅ |
| `/research/strategies/$id/studio` | ✅ | ✅ | ✅ | 16 declared / 4 tests | 5/5 | ✅ |
| `/research/universes` | ✅ | ✅ | ✅ | 16 declared / 2 tests | 2/2 | ✅ |
| `/system` | ✅ | ✅ | ✅ | 12 declared / 4 tests | 3/3 | ✅ |
| `/system/agent` | ✅ | ✅ | ✅ | 16 declared / 3 tests | 9/9 | ✅ |
| `/system/approvals` | ✅ | ✅ | ✅ | 16 declared / 3 tests | 9/9 | ✅ |
| `/system/audit` | ✅ | ✅ | ✅ | 12 declared / 4 tests | 3/3 | ✅ |
| `/system/data-products` | ✅ | ✅ | ✅ | 14 declared / 5 tests | 1/1 | ✅ |
| `/system/jobs` | ✅ | ✅ | ✅ | 12 declared / 4 tests | 3/3 | ✅ |
| `/system/settings` | ✅ | ✅ | ⬜ | 9 declared / 3 tests | 3/3 | ⬜ |
