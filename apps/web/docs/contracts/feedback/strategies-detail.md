# Strategy Detail 实现反馈

## 证据边界：缺少可验证绩效制品

- 模块：Header / KPI / 策略状态
- 描述：策略详情接口只返回服务端策略定义、生命周期和版本身份；没有绑定不可变 backtest/review artifact，也没有 snapshot、时间范围或 registry hash。原型中的 Sharpe、年化收益、最大回撤与胜率无法安全复用。
- 实现：保留绩效证据区，但统一显示「未评估」并解释缺失的证据范围；不使用 `0` 或原型样例值。
- 建议：仅在响应携带可追溯的回测制品身份后展示绩效，并同时显示 snapshot、时间范围与 registry hash。

## 流程收窄：提交回测只做规划交接

- 模块：提交回测 Sheet
- 描述：策略详情页没有足够输入直接创建合规回测，仍缺 snapshot、时间范围、registry hash、资源预算与 Preflight 结果。
- 实现：携带精确 strategy id/version 前往实验创建器，不在详情页伪造实验或回测写入。
- 建议：实验创建页消费显式路由上下文后，再恢复预填体验；创建动作仍由 Preflight 结果约束。

## 治理修正：删除与覆盖式回滚不符合版本合同

- 模块：弃用 / 版本回滚 Overlay
- 描述：后端策略版本是 append-only，提供 audited deprecate/reactivate command，没有策略 `DELETE` 或覆盖历史版本的 rollback API。
- 实现：将原型“删除”收敛为记录 actor/reason 的版本弃用；“回滚”只引导到版本治理，并明确 active pointer revision 与精确确认要求，不发送不存在的 rollback 请求。
- 建议：原型后续将“删除策略”改为“弃用版本”，并把回滚表述统一为受控的 active pointer 变更。

## 审计修正：Object Hub 默认视图结构

- 模块：Prototype visual audit
- 描述：原型把嵌套 `.object-header` 当成整页 Header，且默认视图内的高风险确认摘要占用了隐式网格行，使 main/bottom 的结构测量失真。
- 实现：审计以外层 `.shell-header` 为结构目标，并在默认视图归一化时移除审计专用确认摘要；三种目标视口均通过且无控制台或选择器警告。
