# Agent 包指南

## 定位与依赖

`ditto_agent` 是 apps 与 application 之间的治理型 Agent 平面，拥有运行时、工具调度、模型 adapter、Agent SQLite、Episode/replay 与 eval。允许依赖 `ditto_application` 和获准的横向 `ditto_platform` 技术合同；禁止直接依赖任何 capability、`analysis` 或 `apps`。

## 关键不变量

- 模型只返回结构化 intent；状态、权限、PIT、预算、审批和副作用由确定性 host 决定。
- 所有业务工具只调用 application 叶级合同，不直接读取 capability storage、research SQLite 或 apps registry。
- Fake/scripted model 是默认测试 provider；live 调用必须经过 feature flag、egress policy 和 A4。
- `store=false`、本地可恢复状态、hash-chain audit、脱敏 OTel 和无 publish/order/broker tools 是硬边界。
- 缺 cutoff、snapshot、version 或 authority 时 fail closed，禁止 latest/wall-clock fallback。

## 验证与参考

- `pixi run -e dev pytest packages/agent/tests`
- `pixi run -e dev arch-check`
- [R5 设计](../../docs/plans/2026-08-12-r5-governed-quant-research-agent-design.md) · [架构快速参考](../../docs/architecture/agent-context-pack.md)
