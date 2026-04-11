---
paths:
  - "src/**"
---

# 开发流程规范

## 核心原则

> **理解优先于修改** | **测试先于实现** | **简化先于重构** | **分析先于重试** | **度量优先于猜测**

## 强制流程

### 1. 代码修改流程

```
理解阶段（强制）:
├─ Read 实现文件
├─ Read 测试文件
├─ Grep 相关模式
└─ 度量 prototype（prototype-backed 页面必须）

实现阶段（TDD）:
├─ RED: 写失败测试
├─ GREEN: 最小实现
├─ SIMPLIFIER: 简化代码
└─ REFACTOR: 重构代码

验证阶段:
├─ bun run check（工程验证）
├─ 布局验证（evaluate_script 对比 bounding rect）
└─ 像素验证（UI diff 截图对比）
```

### 1.1 Prototype-backed 页面额外流程

**实现前必须**：

```
1. 启动 prototype HTTP 服务器
   cd docs/designs/specs/prototypes && python3 -m http.server 8888

2. 用 evaluate_script 提取 prototype 布局度量
   - 每个 section 的 bounding rect（x, y, w, h）
   - grid-template 值
   - flex 分配策略
   - padding / gap 值

3. 记录度量数据到页面合同或设计文档

4. React 实现必须匹配 prototype 的布局策略：
   - prototype 用 content-driven → React 不设高度约束
   - prototype 用 flex: 1 → React 用 flex-1
   - prototype 用固定 px → React 用对应值
   - 禁止无 prototype 依据的百分比（max-h-[66%] 等）
```

详见 [visual-verification.md](visual-verification.md)

### 2. 调试流程

**遇到错误 → 调用 systematic-debugging Skill**

| ❌ 错误模式 | ✅ 正确模式 |
|-------------|-------------|
| Edit → 失败 → Edit | 失败 → 分析根因 → 一次性修复 |
| Bash 失败 → 重新运行 | 检查日志 → 定位问题 → 修复 |

### 3. 前置检查清单

**每次修改前确认**：

- [ ] 是否理解了现有代码？
- [ ] 是否找到了相关测试？
- [ ] 是否检查了依赖影响？（Grep 引用）
- [ ] 是否调用了正确的 Skill？
- [ ] 是否遵循了 TDD 流程？

## 质量指标

| 指标 | 目标 | 测量 |
|------|------|------|
| 测试覆盖率 | ≥ 80% | @vitest/coverage-v8 |
| 类型检查 | 0 errors | tsc --noEmit |
| Lint 检查 | All checks passed | biome |
| 布局偏差 | < 3% | evaluate_script bounding rect 对比 |
| 像素匹配 | > 95% | UI diff 截图对比 |

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

# 完成前
# 调用 verification-before-completion Skill
bun run check
```

## 相关规范

- **SKILLS 规则**: [`CLAUDE.md`](../../CLAUDE.md)
- **工具使用标准**: [`CLAUDE.md`](../../CLAUDE.md)
- **检查清单**: [`.claude/checklists/`](../checklists/)
