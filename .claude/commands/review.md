---
name: review
description: 代码审查
---

# /review 命令

执行代码审查流程。

## 流程

1. 调用 `superpowers:requesting-code-review` 进行审查
2. 对照计划检查实现完整性
3. 检查 Ditto 规范遵守情况
4. 检查文档更新情况

## 审查要点

### 硬性规则
- [ ] TDD：测试先于实现
- [ ] PIT 安全：`closed="left"`、knowledge_date
- [ ] 风控：Kill Switch 检查
- [ ] 类型注解完整

### 代码质量
- [ ] 通过所有ci-check检查
- [ ] 嵌套 ≤ 3 层
- [ ] 无重复代码
- [ ] 有意义的命名

### 测试覆盖
- [ ] 正常路径
- [ ] 边界条件
- [ ] 异常路径
- [ ] 风控场景 100%

### 文档更新
- [ ] 模块 README 已更新（如有新模块/接口）
- [ ] Sprint 状态已更新
- [ ] Plan 文档存在（复杂任务）
- [ ] ADR 已记录（架构决策）

## 使用

```
/review
/review --focus pit-safety
/review --focus risk
/review --focus docs
```
