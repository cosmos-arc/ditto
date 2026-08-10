# 任务规划文档

`docs/plans/` 保存仍可能继续执行的跨会话计划；完成、废弃或仅供历史参考的计划进入 `docs/plans/archive/`。计划描述交付合同，不绑定 Claude Code 或 Codex 的命令、模式和代理拓扑。

## 何时写计划

- 多包或多阶段交付，无法在一次连续修改中安全完成。
- 需要显式 approval、数据/发布 Gate 或跨会话恢复。
- 架构决策需要在实施前固定约束和验收证据。

局部、可逆、验收清楚的修改可只使用宿主原生计划。

## 最小内容

每份活跃计划只要求：

1. 目标与不做事项；
2. 已验证的当前事实和约束；
3. 有顺序/依赖关系的 Task；
4. 每个波次的验收命令与 exit gate；
5. 必须暂停的 approval 点；
6. 当前状态、下一步和恢复所需证据。

## 宿主无关执行合同

- 按计划 Task 和依赖顺序推进，不用历史 GREEN 替代当前 diff 的验证。
- Bug、行为、公共契约、PIT、交易、风控或架构变更使用根 `AGENTS.md` 路由的 Ditto skill。
- 只读且维度独立的研究或审查可用 Claude Code/Codex 原生 subagents 并行；不要固定代理数量。
- 每个波次以计划内 exit gate 和当前 diff 的实际验证结果为准。
- 发布、真实数据、schema、架构边界和新生产依赖在标注的 approval 点暂停。

## 命名

使用 `{YYYY-MM-DD}-{主题}.md`。从 [task-template.md](task-template.md) 开始；完成后移动到 `archive/`，不改写历史执行细节。
