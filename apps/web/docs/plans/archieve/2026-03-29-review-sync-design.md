# 设计方案：Product Review 反向同步 + 决策增强

**日期**: 2026-03-29
**状态**: 已确认，待实施
**涉及文件**: `.claude/commands/ditto-design-review.md`

---

## 背景与动机

当前 `ditto-design-review` 流程在 Phase 7 FINAL 生成审查报告后结束。审查过程中产生的设计变更（P0/P1 修复方案、冲突协商结果、新的设计决策）仅记录在 review report 中，不会回写到原始设计文档（信息架构、蓝图、组件规范等）。长期累积后，spec 文档与实际实现/决策逐渐脱节。

同时，各角色 agent 在提出问题时缺乏业界参考依据，用户需要自行判断方案的优劣，决策轮次多、负担重。

## 设计决策摘要

| # | 决策 | 选择 | 理由 |
|---|------|------|------|
| 1 | 同步范围 | 仅同步用户确认采纳的 P0/P1 + 冲突妥协方案 | 设计文档是契约，P2/建议性质是灵感，不混入 |
| 2 | 业界调研形式 | 轻量内联 — P0/P1 附带 2-3 个业界参考 + 简短对比 | review 流程已重，独立调研报告增加 token 消耗 |
| 3 | 同步触发方式 | 独立 `--sync` 命令，用户验收后手动触发 | 验收和同步分离，未采纳的改动不会回写 |
| 4 | 同步清单粒度 | 按目标文档归类 | 同步执行单元是文档，直接对应 Edit 操作 |
| 5 | 文档更新方式 | 混合模式：修正型改正文，新增/补充型写 changelog | 修正不改正文会 perpetuate 错误；频繁插入正文会散乱 |
| 6 | 确认级别 | 按类型分级：修正逐条确认，新增/补充批量确认 | 改正文影响大需把关，追加 changelog 风险低可批量 |

---

## 变更一：角色 Agent 业界调研内联

### 范围

仅 P0、P1 问题附带调研对比。P2 和纯建议不附带。

### 输出格式

每个 P0/P1 问题的报告结构从：

```markdown
| ID | 问题 | 位置 | 建议 | 理由 |
```

变为：

```markdown
### [P0] ID-xxx: 问题描述

**现状**：...
**影响**：...

**方案对比**：
| 方案 | 业界参考 | 优势 | 劣势 |
|------|---------|------|------|
| A: xxx | Linear / Raycast | ... | ... |
| B: xxx | Bloomberg Terminal | ... | ... |
| C: xxx | 自研方案 | ... | ... |

**推荐**：方案 A，因为...
```

### 执行方式

各角色 agent 在发现问题后，通过 WebSearch 查找 2-3 个业界参考，形成轻量对比表格，直接嵌入问题报告。不额外产出文档。

---

## 变更二：FINAL 阶段生成待同步清单

### 触发

Phase 7 FINAL 自动执行，作为 report 生成的一部分。

### 输入

- 冲突协商中用户确认采纳的 P0/P1 变更
- 用户在 DECISION 阶段明确接受的修复方案

### 输出格式

嵌入 review report 末尾：

```markdown
## 待同步清单

> 以下变更已通过验收，可使用 `/ditto-design-review <file> --sync` 同步到设计文档。

### design/specs/01_product_information_architecture.md
| # | 变更类型 | 描述 | 来源 |
|---|---------|------|------|
| 1 | 修正 | Home Banner 优先事项配比从 3:2:1 改为 4:2:1 | P0-UI-03 |

### design/specs/13_ditto_component_spec.md
| # | 变更类型 | 描述 | 来源 |
|---|---------|------|------|
| 1 | 新增 | StatCard 组件新增紧凑模式规范 | P1-UX-02 |
| 2 | 补充 | StatCard 空状态处理规则 | P1-Product-01 |

### docs/designs/decisions/
| # | 变更类型 | 描述 | 来源 |
|---|---------|------|------|
| 1 | 新增 | ADR: 市场脉搏模块采用指标摘要模式 | P0-Conflict-01 |
```

### 变更类型定义

- **修正**：原文档描述与实际实现/决策不一致，需改正文
- **新增**：review 过程中产生的新的设计决策或规范条目
- **补充**：原文档缺失某方面的描述，需补充

---

## 变更三：SYNC 独立阶段

### 触发方式

```bash
/ditto-design-review <file> --sync
```

### 前置条件

对应的 review report 存在且包含待同步清单。如果没有，提示用户先完成 review。

### 执行流程

```
1. 读取最新 review report 中的待同步清单
2. 按变更类型分组
   ├─ 修正型 → 逐条展示 diff，用户逐条确认
   └─ 新增/补充型 → 批量展示 changelog 条目，用户一次性确认
3. 执行文档更新
   ├─ 修正型 → 直接编辑 spec 正文
   └─ 新增/补充型 → 追加到目标文档末尾的 ## Changelog 章节
4. 特殊处理：新增 ADR → 生成独立文件到 docs/designs/decisions/
5. 验证：检查文档内部引用一致性
6. 产出同步摘要
```

### 混合模式更新规则

| 变更类型 | 更新方式 | 确认方式 |
|---------|---------|---------|
| 修正 | 直接编辑 spec 正文 | 逐条展示 diff + 确认 |
| 新增 | 追加到文档末尾 `## Changelog` | 批量展示 + 一次性确认 |
| 补充 | 追加到文档末尾 `## Changelog` | 批量展示 + 一次性确认 |
| 新增 ADR | 生成独立文件到 `docs/designs/decisions/` | 展示内容 + 确认 |

### Changelog 条目格式

```markdown
## Changelog

### 2026-03-29 — Product Review: page-cross-market

- **[新增]** StatCard 组件新增紧凑模式：宽 120px，字号 12px，仅显示主指标（来源: P1-UX-02）
- **[补充]** StatCard 空状态规则：无数据时显示「暂无数据」+ 灰色占位图形（来源: P1-Product-01）
```

### 完整流程图

```
Phase 1-7（不变）: VERSION → BASELINE → PARALLEL → CONFLICT → DECISION → FIX → POLISH
Phase 8 FINAL（增强）: 报告 + 生成「待同步清单」
                    ↓ 用户验收确认
Phase 9 SYNC（新增）: /ditto-design-review <file> --sync
```

---

## 对现有文件的改动范围

| 文件 | 改动内容 |
|------|---------|
| `.claude/commands/ditto-design-review.md` | 输入参数增加 `--sync`；Agent 输出格式增加方案对比；FINAL 增加待同步清单；新增 Phase 9 SYNC；更新流程图 |
| `design/specs/*.md` | SYNC 的输出目标，不是输入，review 时不会被修改 |
| `docs/designs/decisions/*.md` | SYNC 的输出目标（新增 ADR） |
