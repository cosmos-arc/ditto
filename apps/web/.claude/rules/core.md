---
paths:
  - "src/**/*.ts"
  - "src/**/*.tsx"
---

# TypeScript 核心规范

## 代码规模规范

| 指标 | 限制 | 检查方式 |
|------|------|----------|
| **单文件行数** | ≤ 300 行 | 手动检查 |
| **组件行数** | ≤ 200 行 | 手动检查 |
| **函数长度** | ≤ 30 行 | Biome (useBlockStatements + 代码审查) |
| **嵌套深度** | ≤ 3 层 | Biome |
| **参数个数** | ≤ 5 个 | Biome (useMaxParams) |
| **复杂度** | ≤ 15 (认知复杂度) | Biome (noExcessiveCognitiveComplexity) |
| **行长度** | ≤ 120 | Biome (lineWidth) |

**检查命令**：
```bash
bunx biome check .
bunx tsc --noEmit
```

---

### 重构指导

#### 文件 > 300 行

| 情况 | 重构策略 |
|------|----------|
| 多个相关组件 | 按职责拆分到多个文件 |
| 单个组件过大 | 提取自定义 hooks / 子组件 |
| 大量工具函数 | 提取到 `lib/` |

#### 核心原则

> **单一职责原则（SRP）> 固定行数**

当判断是否需要拆分时，优先考虑：
1. 这个组件/文件是否只有一个改变的理由？
2. 如果要修改它，是否总是因为同一个原因？
3. 它的方法是否都在服务于同一个概念？

---

## 命名规范

```typescript
// 组件：PascalCase
function UserProfileCard() {}
const Dashboard = () => {}

// Hook：use 前缀 + PascalCase
function useUserData() {}
function useModal() {}

// 文件：kebab-case
// user-profile-card.tsx
// use-user-data.ts

// 常量：UPPER_SNAKE
const MAX_RETRY_COUNT = 3;

// 变量/函数：camelCase
const fetchUserData = () => {};
```

## 类型规范

- 公开函数 100% 类型注解，返回类型明确
- 优先使用 `interface` 定义对象类型，`type` 用于联合类型/工具类型
- 导入排序由 Biome 自动处理

## 必须通过

`bun run check` 所有检查

## TDD 流程

```
┌─────────────────────────────────────────┐
│  RED     写失败测试 → 运行确认失败       │
│  GREEN   最小实现 → 运行确认通过         │
│  REFACTOR 优化代码 → 确保测试仍通过      │
└─────────────────────────────────────────┘
```
