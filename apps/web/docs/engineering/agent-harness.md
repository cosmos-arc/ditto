# Web 的 Agent 入口

Web 使用 [根 Harness](../../../../docs/engineering/agent-harness.md)，共享 AGENTS、PIT skill、hooks 与 changed-scope。没有独立的 Web skill 集合、Stop 测试编排或 receipt 存储。

产品与设计知识通过 [Web AGENTS](../../AGENTS.md) 按任务读取。页面合同、原型和视觉工具作为普通工程 CLI 使用，见 [页面合同](../../contracts/README.md) 与 [测试说明](testing.md)。
