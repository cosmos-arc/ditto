---
name: ditto-design-cycle
description: Use when creating UI prototypes from blueprints or reviewing HTML prototypes for design quality. Triggers: prototype creation, design review, UI critique, design iteration, or edition management for page prototypes.
disable-model-invocation: false
---

# /ditto-design-cycle

UI 创建与设计审查编排。两种模式：**创建模式**（`--create`，蓝图→原型）和**审查模式**（七角色并行审查）。聚焦设计交付物质量——UI 视觉、交互体验、功能可用性、界面语言、品牌气质、信息效率、信息架构、数据可视化。通过七角色并行审查识别冲突与共识，协商优化达成一致。

> **不是"对照 spec 打分"，而是"多角色专家讨论，共同优化设计"。**
> Design Spec 是**参考起点**，不是刚性约束。**用户是最终决策者**。

---

## 确定性约束 (MUST / MUST NOT)

- 审查标准 MUST 参考 [00_ditto_product_criteria.md](../../../docs/designs/specs/00_ditto_product_criteria.md)（不使用通用 UI 准则）
- 评分 MUST 使用 5 维度（克制度/一致性/高级感/品牌方向/信息效率），详见 [review-scoring.md](references/review-scoring.md)
- Phase 8 门禁 MUST 全部通过后才可设置 status="done"
- `data-contract-slot` MUST 添加在 `#default-view` 内 shell 级区块
- 三区结构 MUST 通过 10 项验证，详见 [create-mode.md](references/create-mode.md)
- 零 Inline Style MUST 为 P0 门禁（`style="..."` = 0），详见 [no-inline-style.md](../../rules/no-inline-style.md)
- 原型版本 MUST 通过 git tag 管理，详见 [version-control.md](references/version-control.md)
- 上游消费 MUST 读取 product-arch 产出物（01 + 02 + 04 + 00）
- AI MUST NOT 自行决定产品功能内容（视觉策略可自由提案，产品级变更 MUST 标记"⚠️ 需 PM 确认"）
- CREATIVE DIRECTION MUST NOT 包含 C 类产品变更
- 合同验证失败 MUST NOT 在 `--strict` 模式下继续

## 创意指导 (SHOULD / CONSIDER)

- 各角色 SHOULD 给出**冲突建议**（视觉 vs 产品 vs 信息架构）
- Claude 负责呈现冲突 + 分析权衡 + 推荐折中方案
- 审查可能产生**新的设计决策**，自动记录到 `docs/designs/decisions/`
- 如果信息架构或交互流程有重大调整，同步更新 spec 文档

## --strict 模式

> `--strict` 仅影响合同相关的 done 门禁（Step 8.16a/8.16c），不影响审查流程本身。

| 行为 | 默认模式 | `--strict` |
|------|---------|------------|
| 合同创建失败（8.16a） | WARNING，记录原因，不阻断 done | **BLOCK** |
| 合同验证失败（8.16c） | 输出失败项，不阻断 done | **BLOCK** |

---

## Reference 文件

| 文件 | 内容 |
|------|------|
| [roles.md](references/roles.md) | 七角色定义、审查清单、三区审查指引 |
| [review-scoring.md](references/review-scoring.md) | 5 维评分标准、量化指标、量化平台专用准则 |
| [iterate.md](references/iterate.md) | 自主迭代架构、退出条件、突破机制、AUTO-DECISION |
| [templates.md](references/templates.md) | Agent 输出格式、冲突协调、最终报告、ESCALATE 模板 |
| [viewport.md](references/viewport.md) | 多视口检测规则、评估脚本、UX P0 规则 |
| [sync.md](references/sync.md) | 反向同步协议（review 变更写回 spec） |
| [create-mode.md](references/create-mode.md) | Phase 0.5 CREATE 全流程（三区结构 + 合同对接 + 验证） |
| [execution-flow.md](references/execution-flow.md) | Phase 1-8 执行流程详细步骤 |
| [edition.md](references/edition.md) | Edition 机制（manifest + 批量创建 + 验收） |
| [version-control.md](references/version-control.md) | git tag 版本管理、任务名映射、回退操作 |
| [agent-protocol.md](references/agent-protocol.md) | 模型路由策略、Agent dispatch 规范 |
| [quality-levels.md](references/quality-levels.md) | 质量等级 + impeccable skills 映射 |

---

## 上游消费

| 上游产出物 | 消费方 | 用途 |
|-----------|--------|------|
| 01_product_information_architecture.md | Phase 0.5 + Phase 1 | 页面角色、导航上下文、术语表 |
| 02_core_page_blueprints.md | Phase 0.5 + Phase 3 | 模块清单、优先级、交互设计、Tab/Overlay/State Matrix |
| 04_interaction_state_spec.md | Phase 0.5 | 通用状态定义 + 页面状态映射 |
| 00_ditto_product_criteria.md | Phase 2-8 全流程 | 密度准则、字号映射、间距梯度 |
| .arch-manifest.json | Phase 0 | 检测上游完成状态 |

无上游时: `⚠️ 未检测到 product-arch 产出物，建议先运行 /ditto-product-arch`

---

## 输入

`$ARGUMENTS` — 目标 + 可选参数

```bash
# 创建模式
/ditto-design-cycle page-markets.html --create --page markets
/ditto-design-cycle page-markets.html --create --page markets --iterate --goal 8.0
/ditto-design-cycle page-markets.html --create --page markets --strict
/ditto-design-cycle --create-all                    # 批量创建（详见 edition.md）
/ditto-design-cycle --create-all --only markets,trading  # 指定页面

# 审查模式
/ditto-design-cycle page-cross-market.html          # 全流程审查
/ditto-design-cycle page-cross-market.html --level best
/ditto-design-cycle page-cross-market.html --ui     # 单角色审查
/ditto-design-cycle page-cross-market.html --polish # 仅精修
/ditto-design-cycle page-cross-market.html --iterate --goal 8.5 --max-rounds 3
/ditto-design-cycle page-cross-market.html --sync   # 反向同步
/ditto-design-cycle page-cross-market.html --baseline prototype-v2.html
/ditto-design-cycle --cleanup cross-market          # 清理历史 tag

# Edition 模式
/ditto-design-cycle --edition-review                # Edition 级验收
```

---

## 七个审查角色

| 角色 | model | 核心关注 |
|------|-------|---------|
| UI Designer | opus | Token 一致性、视觉层次、色彩排版 |
| UX Reviewer | sonnet | 可用性、可访问性、交互流程 |
| Product Mgr | sonnet | Spec 落地合规、重要性层级、产品边界守卫 |
| IA Specialist | sonnet | 信息架构、用户流程、页面蓝图、标签体系 |
| Copy Editor | sonnet | 文案清晰度、语气一致、中文表达 |
| Data Viz Specialist | sonnet | 数据可视化、色觉无障碍、Token 消费率 |
| Art Director | opus | 克制度、高级感、品牌方向锚定 |

完整角色定义、审查清单、三区审查指引见 [roles.md](references/roles.md)。

---

## 执行流程概览

### 全流程（默认）

```
Phase 0:   VERSION        → git tag 快照
Phase 0.5: CREATE         → [--create] 蓝图→原型（详见 create-mode.md）
                            │  可调用 ui-ux-pro-max:design-system 获取领域风格/配色/字体推荐
Phase 1:   BASELINE       → 基线采集 + 跨页视觉指纹
Phase 2:   CREATIVE DIR.  → 创意蓝图（详见 iterate.md）
                            │  可调用 impeccable:frontend-design 获取创意方向指导
Phase 3:   PARALLEL REVIEW → 七角色并行审查
Phase 4:   CONFLICT RES.  → 冲突协调 + 双轨权威制
Phase 5:   DECISION       → 用户决策 / AUTO-DECISION
Phase 6:   FIX            → 执行修改
Phase 7:   POLISH         → 质量提升 + AD 审批（详见 quality-levels.md）
Phase 8:   FINAL          → 门禁 + 气质评分 + 合同桥接
                            │  可调用 impeccable:critique 获取独立 UX 评分
Phase 9:   SYNC           → [--sync] 反向同步
```

每个 Phase 的详细步骤见 [execution-flow.md](references/execution-flow.md)。
模型分配见 [agent-protocol.md](references/agent-protocol.md)。

### 模式变体

| 模式 | 触发 | 流程 |
|------|------|------|
| 创建 | `--create` | VERSION → CREATE → BASELINE → 全流程 |
| 批量创建 | `--create-all` | 详见 [edition.md](references/edition.md) |
| 反馈审查 | `--review-feedback <page>` | 读取实现反馈 → BASELINE → 针对性 FIX → VERIFY → FINAL |
| 自主迭代 | `--iterate` | 详见 [iterate.md](references/iterate.md) |
| 单角色 | `--ui/--ux/--product/--ia/--copy/--ad/--dataviz` | BASELINE → 单角色 → DECISION → FIX → VERIFY |
| 仅精修 | `--polish` | BASELINE → POLISH → VERIFY → FINAL |
| Edition 验收 | `--edition-review` | 详见 [edition.md](references/edition.md) |
| 反向同步 | `--sync` | 详见 [sync.md](references/sync.md) |
