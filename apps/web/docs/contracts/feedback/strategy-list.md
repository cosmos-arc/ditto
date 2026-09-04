# Strategy List 实现反馈

## 原型缺陷：绩效指标缺少可验证制品

- 模块：Performance Summary / Strategy Table / Detail
- 描述：当前 `GET /v1/strategies` 只提供策略身份、版本、标签、生命周期与创建时间；没有绑定不可变 backtest/review artifact，也没有 snapshot、时间范围或证据 hash。原型中的 Sharpe、年化收益和 MDD 因而不能作为生产数据渲染。
- 实现：保留摘要与表格的信息层级，但将所有未绑定绩效明确显示为「未评估」，不使用 `0` 或原型样例值。
- 建议：未来只有在列表响应携带可追溯的 backtest/review artifact 引用后，才恢复对应绩效列和聚合摘要。

## 设计改进：删除动作应符合 append-only 治理

- 模块：Strategy Table / 删除确认 Overlay
- 描述：后端策略版本采用 append-only 治理且没有策略 `DELETE` 端点；原型中的“删除全部版本和回测记录”会误导用户并破坏审计语义。
- 实现：保留破坏性确认入口，但将其收敛为前往版本治理/弃用流程，不发送 `DELETE`。
- 建议：后续原型将“删除”统一改为“弃用版本”，并在 active pointer 仍指向目标版本时显示阻断原因。
