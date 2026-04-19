# ditto-product-arch 全面重构设计

> 日期: 2026-04-17
> 状态: approved
> 上游: ditto-product-discovery (Pipeline -1)
> 下游: ditto-design-cycle (Pipeline 1)

---

## 背景

上游 `ditto-product-discovery` 已完善（5 Phase + Gate + Manifest + Reference 文件），产出结构化数据（system-description YAML、constitution 23 条约束、assumptions 8 项、landscape 竞品分析）。`ditto-product-arch` 作为 Pipeline 0 存在 6 个结构性问题需要解决。

## 诊断

| # | 问题 | 严重度 | 最佳实践依据 |
|---|------|--------|-------------|
| 1 | 上游产出物未被消费 | P0 | Block: "Output should be input" |
| 2 | 无 Phase Gate | P0 | Anthropic: "Build feedback loops" |
| 3 | 无 Manifest 追踪 | P1 | 可中断可续接基本要求 |
| 4 | 约束验证缺失 | P1 | Block: "Know what agent should NOT decide" |
| 5 | Progressive Disclosure 不足 | P1 | Anthropic: "< 500 lines, split references" |
| 6 | 确定性与创意边界模糊 | P2 | Block: "Two-zone architecture" |

## 决策记录

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 上游消费方式 | 自动注入，无 discovery 时警告 | 减少用户操作，保证数据流 |
| Phase Gate 数量 | 3 个（0→1, 2→3, 4→5） | 平衡用户参与度与流程流畅性 |
| Manifest | 独立 `.arch-manifest.json` | 与 discovery-manifest 对齐，支持恢复 |
| 约束验证 | Design 注入 + Validate 检查 | 双重保障，设计时遵守 + 产出后验证 |
| Reference 文件 | 4 个文件全拆 | 主文件 < 500 行，符合 Anthropic 建议 |
| 两区分离 | MUST/MUST NOT vs SHOULD/CONSIDER 区块 | 明确确定性约束与创意指导边界 |

## 新文件结构

```
.claude/commands/
├── ditto-product-arch.md              # 主 skill（~200 行）
└── product-arch/
    ├── roles.md                       # [已有] 四角色定义
    ├── output-structure.md            # [新增] 产出物结构模板
    ├── enums.md                       # [新增] 枚举 + 映射规则
    ├── validation-rules.md            # [新增] 审计规则 + 合规检查
    └── agent-protocol.md              # [新增] Agent 协议 + Gate 规范
```

## 上游消费映射

| 上游产出物 | 注入 Phase | 注入方式 |
|-----------|-----------|---------|
| system-description entities/capabilities | Phase 1 RESEARCH | Agent prompt 上下文 |
| constitution 23 条约束 | Phase 2 DESIGN + Phase 5 VALIDATE | Agent prompt + 验证规则 |
| assumptions 高风险项 | Phase 3 SYNTHESIS | 冲突协调时标记 |
| landscape 竞品矩阵 | Phase 1 RESEARCH | Agent prompt 上下文 |

## Phase Gate

```
Phase 0 → [Gate 0→1] → Phase 1 → Phase 2 → [Gate 2→3] → Phase 3 → Phase 4 → [Gate 4→5] → Phase 5
```

| Gate | 展示内容 | 用户选择 |
|------|---------|---------|
| Gate 0→1 | 上游 digest + 范围 + spec 评分 | 确认/调整/暂停 |
| Gate 2→3 | 4 角色草案 + 冲突清单 + 违规预警 | 确认/回退/暂停 |
| Gate 4→5 | 变更摘要 + 状态覆盖 + 合规报告 | 确认/回退/暂停 |

## Manifest Schema

```json
{
  "version": 1,
  "status": "in-progress | completed",
  "mode": "create | iterate | audit",
  "startedAt": "ISO-8601",
  "completedAt": "ISO-8601 | null",
  "upstreamDigest": {
    "discoveryManifest": "path | null",
    "entityCount": "number",
    "constraintCount": "number",
    "highRiskAssumptions": "number",
    "competitorCount": "number"
  },
  "phases": {
    "0-5": { "name": "...", "status": "done|in-progress|pending", "artifacts": [] }
  },
  "validation": {
    "constitutionCompliance": "pass|fail",
    "stateCoverage": "string",
    "consistencyFailures": "number"
  }
}
```

## 两区分离

- **确定性约束 (MUST/MUST NOT)**: 文件路径、枚举值、产出物必须包含的 section、Phase Gate 位置、模型路由、验证规则
- **创意指导 (SHOULD/CONSIDER)**: 设计原则、权衡框架、竞品参考、渐进展示策略、信息密度平衡

## 行数预估

| 文件 | 当前行数 | 重构后行数 |
|------|---------|-----------|
| ditto-product-arch.md | 400 | ~200 |
| roles.md | 167 | 167 |
| output-structure.md | 0 | ~80 |
| enums.md | 0 | ~60 |
| validation-rules.md | 0 | ~90 |
| agent-protocol.md | 0 | ~120 |
| **总计** | 567 | ~717 |
