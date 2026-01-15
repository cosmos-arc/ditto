---
name: ditto-plan
description: 生成结构化开发任务规划
---

# /plan 命令

使用 `superpowers:brainstorming` + `superpowers:writing-plans` 将需求拆解为可执行的开发计划，开始

**开始前有任何问题先向我询问澄清，直到完全无疑问！！**

## 输入

$ARGUMENTS（Sprint Phase 或需求描述）

## 执行流程

### Step 1: 需求理解
1. 查看 `docs/sprints/` 了解当前Sprint上下文
2. 查看 `docs/design/` 确认架构约束
3. 有不明确之处，**先问再做**

### Step 2: 任务拆解
1. 拆分为原子任务（单一职责）
2. 标注复杂度：S/M/L（XL必须继续拆）
3. 识别依赖关系，确定执行顺序，是否可并行
4. 每个任务必须有明确验收标准

### Step 3: 生成计划文件

输出到 `docs/plans/{date}-{feature}.md`：

```markdown
# 开发计划: {feature}

## 概述
- Sprint: {id} | Phase: {name}
- 创建时间: {timestamp}

## 技术方案
{关键决策，1-2段}

## 任务清单

### Phase 1: {name}
- [ ] **Task 1.1**: {描述} `[S]`
  - 验收: {标准}
  - 文件: {涉及文件}

### Phase 2: ...

## 风险
{已识别风险及缓解}
```

## Ditto 硬性规则

- 涉及数据操作 → 必须说明PIT处理方式
- 涉及交易逻辑 → 必须包含Kill Switch检查点
- 每个任务 → 必须有对应测试要求
