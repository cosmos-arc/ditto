# 模型路由策略

> **质量优先**: 审美判断和创意综合使用 Opus，结构化分析和机械操作使用 Sonnet。

---

## 阶段级模型分配

| 阶段 | 模型 | 理由 |
|------|------|------|
| Phase 0: VERSION | sonnet | git 操作，纯机械 |
| Phase 0.5: CREATE [--create] | sonnet | 基于蓝图生成 UI 原型 |
| Phase 0.5: CREATE [--create-all] | sonnet | 循环调用单页 --create，带 style anchoring |
| Phase 1: BASELINE | sonnet | 数据采集 + 脚本执行 |
| Phase 2: CREATIVE DIRECTION | **opus** | 创意方向判断，策略选择和蓝图定义 |
| Phase 3: Art Director | **opus** | 审美判断核心，气质评分 |
| Phase 3: UI Designer | **opus** | 视觉品质需要审美理解 |
| Phase 3: UX Reviewer | sonnet | 交互分析偏结构化 |
| Phase 3: Product Mgr | sonnet | 功能可用性偏结构化 |
| Phase 3: IA Specialist | sonnet | 信息架构偏结构化 |
| Phase 3: Copy Editor | sonnet | 文案审查最结构化 |
| Phase 3: Data Viz Specialist | sonnet | 数据可视化偏结构化 |
| Phase 4: CONFLICT RES. | **opus** | 多角色冲突权衡取舍 |
| Phase 5: DECISION | sonnet | 呈现选项，不涉及判断 |
| Phase 6: FIX | sonnet | 按已定方案执行 |
| Phase 7: AD 预审/复审 | **opus** | 审美把关 |
| Phase 7: impeccable skills | sonnet | 按规范执行 |
| Phase 7: REFLECT [--iterate] | **opus** | 定性反思，洞察提取 |
| Phase 8: 自动化检测 | sonnet | Lighthouse/Token/视口 |
| Phase 8: 最终气质评分 | **opus** | 最终审美裁决 |
| Phase 9: SYNC | sonnet | 文档同步 |
| Edition Review [--edition-review] | sonnet | 截图采集 + image analysis |

**实现方式**: Agent 工具调用时传入 `model` 参数，如 `Agent(prompt="...", model="opus")`。

---

## 单角色审查模型分配

| 参数 | 角色 | model | 理由 |
|------|------|-------|------|
| `--ui` | UI Designer | opus | 视觉品质需要审美判断 |
| `--ux` | UX Reviewer | sonnet | 交互分析偏结构化 |
| `--product` | Product Mgr | sonnet | 功能可用性偏结构化 |
| `--ia` | IA Specialist | sonnet | 信息架构偏结构化 |
| `--copy` | Copy Editor | sonnet | 文案审查最结构化 |
| `--ad` | Art Director | opus | 审美判断核心 |
| `--dataviz` | Data Viz Specialist | sonnet | 数据可视化偏结构化 |
