# 阶段 A 候选任务池与迁移索引

> **首次创建**：2026-07-10<br>
> **降级日期**：2026-07-15<br>
> **状态**：DEPRECATED AS EXECUTION PLAN<br>
> **用途**：保留旧 A1-A6 编号与决策历史，并指向新的 release。本文不可用于直接施工。

## 1. 为什么停止执行阶段 A 原计划

阶段 A 把日频闭环、数据扩张、组合优化、连续风控和前端产品化混在一个批次中，存在三类问题：

1. **范围过大**：A1-A6 跨越了现在的 R1、R2 和 R4，无法形成可验证的短 release。
2. **事实过期**：涨跌停、手数基础、策略 create/publish handler、账户快照和凭证优先级等能力已存在，旧计划会重复实现。
3. **施工冲突**：旧文档仍含逐步命令、测试和提交建议，会与 R1 的真实代码路径、CLI 和依赖顺序冲突。

因此，本文只保留迁移关系。唯一有效的近期施工入口是：

`docs/plans/2026-07-10-r1-implementation-plan.md`

## 2. A1-A6 迁移表

| 旧编号 | 旧意图 | 复核后的事实 | 新归属 | 处理结论 |
|---|---|---|---|---|
| A1 | stock/macro/fx/commodity promotion | stock/macro 部分数据集已有 promotion override；真正缺口是历史深度、默认环境可迁移性、fx/commodity 数据和真实 evidence | R2 | 按数据集逐一 promotion，不做“一次性全提级” |
| A2 | 补涨跌停与手数取整 | `AShareFillModel`、`target_diff.py`、`quantity_rounding.py` 已有相关能力；缺口是规则审计以及接入人工建议数量链路 | R1 / R3 | R1 复用 execution planner 并补规则矩阵测试；R3 再深化成交仿真 |
| A3 | cvxpy 组合优化 | allocator/covariance 基础已在，R1 不依赖高级求解器 | R4 | 等 Daily Decision 与账户账本稳定后独立 mini-design |
| A4 | 连续风控 | `RiskGate` 和规则基础存在；状态持久化、崩溃恢复、风险事件流仍缺 | R4 / R6 | 日频组合风险先做，盘中连续风险在 R6 |
| A5 | trading 前端 production | `ditto-app` 已有 trading 原型和部分 live adapter，但 live 页面仍混用 prototype | R1 | 后端契约稳定后完成 `VITE_USE_MOCK=false` 的真实工作流 |
| A6-1 | `wave1_env.sh` 导出 TUSHARE_TOKEN | registry 配置已有 env > keyring > config 优先级；强制 shell export 既非根因也会扩大凭证暴露 | 删除 | 改为 live acceptance preflight，凭证不写脚本、不写日志 |
| A6-2 | 策略定义 publish 流程 | create/publish command handler 和 API 已存在；缺 active-published 语义和 seed bootstrap 运营入口 | R1 | 复用现有 handler，不新造平行发布链路 |

## 3. 已撤销的旧假设

- “阶段 A 全量启动后即可商用”已撤销；R1 只允许本机内部 Beta。
- “A1 所有数据集统一 promotion”已撤销；每个数据集必须有独立 evidence。
- “A2 从零实现手数与涨跌停”已撤销；改为复用、接线和规则审计。
- “服务启动必须由 `wave1_env.sh` 导出供应商 token”已撤销；配置 provider 是唯一凭证入口。
- “`ditto ops publish-signals` 是现有命令”已撤销；当前命令属于 `ditto strategy` 组。
- “前端可以先于后端成交/账户契约完成”已撤销；前端 live 工作流依赖稳定 OpenAPI。
- “真实供应商 API 是默认 TDD 前提”已撤销；确定性测试与 live acceptance 分层运行。

## 4. 新的执行关系

```text
能力事实基准
  └─ 母路线图 R0-R7 + G1-G6
       ├─ R1 实施计划：当前唯一施工图
       ├─ R2 计划：R1 Gate 通过后再写
       ├─ R3 计划：R2 验收后再写
       └─ R4-R7：到达上一 Gate 时分别设计

本文件：仅提供 A1-A6 历史编号迁移，不进入执行链
```

## 5. 重新激活候选项的门槛

候选项进入新 release 前必须满足：

1. 重新核对源码、CLI、API、schema、前端和现有测试。
2. 写明目标用户工作流、非目标、数据来源和失败状态。
3. 明确是否涉及 schema 迁移、API 破坏性变更、外部依赖或跨仓库修改。
4. 定义确定性测试、集成测试、live acceptance 和回滚方式。
5. 映射到母路线图 release 与 release gate，并得到独立实施计划。

## 6. 历史任务去向速查

| 想找的工作 | 应阅读 |
|---|---|
| 当前能力评分与缺口 | `docs/plans/2026-07-10-capability-benchmark-design.md` |
| R0-R7 全局顺序与商业 Gate | `docs/roadmaps/ditto-development-roadmap.md` |
| 日频人工交易闭环 | `docs/plans/2026-07-10-r1-implementation-plan.md` |
| 数据扩张与 promotion | 未来 R2 实施计划 |
| 回测/选股/策略产品化 | 未来 R3 实施计划 |
| 组合优化与连续风控 | 未来 R4 实施计划 |
| AI Copilot / Agent | 未来 R5 实施计划 |
| 分钟级与盘中 | 未来 R6 实施计划 |
| 全球全品类 | 未来 R7 实施计划 |

## 7. 禁止事项

- 不从本文复制旧命令、代码片段或测试进入施工。
- 不把旧工作量估算当作承诺。
- 不因历史编号存在就默认需求仍有效。
- 不在本文追加新的实施步骤；新工作必须进入对应 release 的计划。
