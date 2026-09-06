# Domain Docs

## Layout

采用 **single-context**：根目录 `CONTEXT.md` 存放统一领域词汇表，根目录 `docs/adr/` 存放架构决策。沿用现有 ADR 及其索引。

## Before exploring, read these

- 涉及领域概念或命名时，读取根目录 `CONTEXT.md`。
- 涉及架构决策时，从 [ADR 索引](../adr/README.md) 选择与任务相关的 ADR。
- 需要当前能力平面或目录边界时，读取 [架构快速参考](../architecture/agent-context-pack.md) 与 [边界与抽象标准](../architecture/boundaries-and-abstraction-standards.md)。

可选的 CONTEXT 或 ADR 文档不存在时，静默继续；在 `domain-modeling` 实际确定术语或决策时再按需创建。

## Use the glossary's vocabulary

issue 标题、方案、假设、测试名称中的领域概念使用 `CONTEXT.md` 已定义的术语。遇到未定义概念，先核对现有用语；确有缺口时交由 `domain-modeling` 澄清并记录。

## Flag ADR conflicts

建议与现有 ADR 冲突时，明确指出 ADR 编号、冲突内容和重新讨论的理由。事实优先级遵循根目录 [AGENTS.md](../../AGENTS.md)。
