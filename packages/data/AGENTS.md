# Data 包指南

## 定位与依赖

数据平台，负责外部数据源、摄取、存储、查询、质量与 PIT 可见性。允许依赖 `kernel` 和获准的 `platform.foundation`；禁止依赖上层能力包、application 或 apps。

## 关键不变量

- 外部消费者通过 domain service 访问数据，不直接实例化 storage reader/writer。
- 查询 fail closed，传播 `knowledge_date`、publication cutoff 与 source snapshot。
- rolling/shift/as-of join 与因子输入改动必须使用 `ditto-pit-safety`。
- 摄入保留游标、冻结与质量证据；写入不可绕过既有 DQ 流程。

## 验证与参考

- `pixi run -e dev pytest packages/data/tests`
- `pixi run -e dev pytest -m pit`
- [架构快速参考](../../docs/architecture/agent-context-pack.md) · [PIT skill](../../.agents/skills/ditto-pit-safety/SKILL.md)
