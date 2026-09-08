# 通用开发 skills 与 Ditto 治理的职责边界

**状态**：Accepted
**日期**：2026-09-08

Matt skills 作为独立的通用开发方法由上游维护，Ditto 不复制整套 skills 并形成项目分支；项目记录来源版本及可复现安装、验证所需的适配信息，并维护自身的领域约束、工程质量门和交付约定。工作流按任务风险选择必要步骤，普通改动不强制经过完整访谈、规格和拆票流程。

这一选择减少上游方法与项目副本的双重维护，但要求项目显式处理宿主能力、审查对象和现有工程命令的衔接；上游技能最新不等于其所有默认命令均适用于 Ditto。将通用方法复制入仓库虽然能统一分发，也会使每次上游改进都变成一次项目合并与维护责任，因此未采用。

决策来源：[Issue 111](https://github.com/cosmos-arc/ditto/issues/111) 的已确认决定。
执行规则见[任务交付](../engineering/development-workflow.md)与[知识生命周期](../engineering/knowledge-lifecycle.md)。
