---
name: ditto-sprint
description: Sprint规划与任务管理
---

# /sprint 命令

使用 `superpowers:brainstorming` + `superpowers:writing-plans` 将目标拆分为可执行的Sprint任务。

## 子命令

| 命令 | 说明 |
|------|------|
| `/sprint [描述]` | 创建新Sprint |
| `/sprint --list` | 查看任务状态 |
| `/sprint --next` | 开始下一个任务（自动调用/plan） |
| `/sprint --status` | 进度报告 |

## 创建Sprint流程

### 1. 目标澄清
- 理解整体目标和关键交付物
- 明确验收标准
- 有不清楚的地方**先问**

### 2. 任务拆分
- 遵循INVEST原则（独立、可测试、有价值）
- 复杂度评估：S/M/L/XL（XL必须拆分）
- 识别依赖关系

### 3. 复杂度速查

| 等级 | 文件数 | 代码行 | 特征 |
|------|--------|--------|------|
| S | 1 | <50 | 单文件，逻辑清晰 |
| M | 2-3 | 50-150 | 有明确模式可循 |
| L | 4-6 | 150-400 | 跨模块，需设计决策 |
| XL | >6 | >400 | **必须拆分** |

**风险加权+1级**：涉及PIT、Kill Switch、Schema变更、外部API

### 4. 输出到 `docs/sprints/sprint-{name}.md`

## 工作流

```
/sprint "目标描述"  →  生成Sprint文件
/sprint --next      →  选择任务，调用/plan
/plan 输出          →  调用/dev执行
/dev 完成           →  更新Sprint状态，继续--next
```
