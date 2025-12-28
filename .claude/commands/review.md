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

## 审查要点

### 硬性规则
- [ ] TDD：测试先于实现
- [ ] PIT 安全：`closed="left"`、knowledge_date
- [ ] 风控：Kill Switch 检查
- [ ] 类型注解完整

### 代码质量
- [ ] 函数 ≤ 50 行
- [ ] 嵌套 ≤ 3 层
- [ ] 无重复代码
- [ ] 有意义的命名

### 测试覆盖
- [ ] 正常路径
- [ ] 边界条件
- [ ] 异常路径
- [ ] 风控场景 100%

## 使用

```
/review
/review --focus pit-safety
/review --focus risk
```
