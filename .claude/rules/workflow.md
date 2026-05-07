---
paths:
  - "**/*.py"
---

# 开发流程规范

## 核心原则

> **理解优先于修改** | **测试先于实现** | **简化先于重构** | **分析先于重试**

## 强制流程

### 1. 代码修改流程

```
理解阶段（强制）:
├─ Read 实现文件
├─ Read 测试文件
└─ Grep 相关模式

实现阶段（TDD）:
├─ RED: 写失败测试
├─ GREEN: 最小实现
├─ SIMPLIFIER: 简化代码
└─ REFACTOR: 重构代码

验证阶段:
└─ verification-before-completion
```

### 2. 调试流程

**遇到错误 → 调用 systematic-debugging Skill**

| ❌ 错误模式          | ✅ 正确模式                  |
| -------------------- | ---------------------------- |
| Edit → 失败 → Edit   | 失败 → 分析根因 → 一次性修复 |
| Bash 失败 → 重新运行 | 检查日志 → 定位问题 → 修复   |

### 3. 前置检查清单

**每次修改前确认**：

- [ ] 是否理解了现有代码？
- [ ] 是否找到了相关测试？
- [ ] 是否检查了依赖影响？（Grep 引用）
- [ ] 是否调用了正确的 Skill？
- [ ] 是否遵循了 TDD 流程？

## 质量指标

| 指标       | 目标              | 测量         |
| ---------- | ----------------- | ------------ |
| 测试覆盖率 | ≥ 80%             | pytest-cov   |
| 类型检查   | 0 errors          | basedpyright |
| Lint 检查  | All checks passed | ruff         |
| 架构边界   | 36 contracts kept | import-linter |

## 快速参考

```bash
# 开发前
git status
git branch --show-current

# 修改前（强制）
Read <file>
Read <test_file>
Grep "<pattern>"

# 调试
# 调用 systematic-debugging Skill

# 架构检查
pixi run -e dev arch-check

# 完成前
# 调用 verification-before-completion Skill
pixi run -e dev check     # lint + fmt + type + test --fast
pixi run -e dev ci        # 完整 CI
```

## 相关规范

- **SKILLS 规则**: [`CLAUDE.md`](../../CLAUDE.md)
- **工具使用标准**: [`CLAUDE.md`](../../CLAUDE.md)
- **代码变更检查清单**: [`.claude/checklists/code-change.md`](../checklists/code-change.md)
- **调试检查清单**: [`.claude/checklists/debug.md`](../checklists/debug.md)
- **架构规范**: [`.claude/rules/architecture.md`](architecture.md)
- **测试规范**: [`.claude/rules/python-test.md`](python-test.md)
