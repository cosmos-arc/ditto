# 领域词汇表（CONTEXT.md）

按 [Domain Docs](docs/agents/domain.md) 约定：本文件是唯一领域词汇表，只收术语定义，不收实现细节；架构决策见 [ADR 索引](docs/adr/README.md)。

## 数据保证（总称）

"数据保证"在票据与评审中默认指以下三分全体；单指某块时必须用全称，避免歧义。

- **正确性保证**：时间语义的正确性——什么时点可知什么。载体为 PIT 语言（knowledge date / publication cutoff / source snapshot 传播，fail-closed）。
- **可用性保证**：存储的持久化、备份与恢复。定位约束见"重拉恢复"。
- **质量保证**：对账、覆盖/完成检查、readiness 通路。

## 零同构三件套

#426 裁决维持的三件业界无同构的机器，合称"三件套"：

1. 行级 knowledge_date（行情侧逐行可知时间）；
2. cutoff 传播 + T+1 + fail-closed（可见性门）；
3. 三阶段 fetch log + complete_evidence_id（内容寻址完成证据）。

## 重拉恢复

定位基线：上游数据源（Tushare/fuyao）可重新拉取被视为最终恢复手段；本地存储损坏/污染容忍天级恢复窗口。只有不可重拉数据（paper/manual 账本、agent 存储）需要本地备份保证。
