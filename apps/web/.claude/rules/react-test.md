---
paths:
  - "src/**/*.test.*"
  - "src/**/*.spec.*"
---

# React 测试规范

## 测试组件栈

**必须使用以下组件，不得替换**：

| 组件 | 用途 | 使用场景 |
|------|------|----------|
| `vitest` | 测试框架 | 所有测试 |
| `@testing-library/react` | 组件渲染/交互 | React 组件测试 |
| `@testing-library/jest-dom` | DOM 断言扩展 | 元素状态断言 |
| `@testing-library/user-event` | 用户交互模拟 | 点击/输入等操作 |
| `msw` | API Mock | 服务端状态测试 |
| `@vitest/coverage-v8` | 覆盖率 | CI 集成 |

## 测试文件位置

| 方式 | 位置 | 适用场景 |
|------|------|----------|
| **co-located** | `__tests__/` 子目录 | 组件/工具测试 |
| **同目录** | `.test.tsx` / `.spec.tsx` | 简单测试 |

```
src/features/user/
├── components/
│   └── user-profile.tsx
│   └── __tests__/
│       └── user-profile.test.tsx
├── hooks/
│   └── use-user-data.ts
│   └── __tests__/
│       └── use-user-data.test.ts
```

## 测试命名

`{Component}.{behavior}` 模式：

```typescript
describe("UserProfile", () => {
  it("renders user name", () => {});
  it("calls onUpdate when name changes", () => {});
  it("shows loading state while fetching", () => {});
  it("displays error message on failure", () => {});
});
```

## AAA 模式

```typescript
it("renders user name", () => {
  // Arrange
  render(<UserProfile name="John" />);

  // Act — 已在 render 中完成

  // Assert
  expect(screen.getByText("John")).toBeInTheDocument();
});
```

## Mock 策略

### API Mock — 使用 MSW

```typescript
import { http, HttpResponse } from "msw";

beforeAll(() =>
  server.use(
    http.get("/api/users/:id", () =>
      HttpResponse.json({ name: "John" })
    )
  )
);
```

### Hook Mock

```typescript
// 使用 vi.mock
vi.mock("../hooks/use-user-data", () => ({
  useUserData: () => ({
    data: { name: "John" },
    isLoading: false,
  }),
}));
```

## 禁止事项

| ❌ 禁止 | ✅ 正确 |
|---------|---------|
| 测试实现细节（内部 state） | 测试行为和输出 |
| `container.querySelector` | `screen.getByRole` / `screen.getByText` |
| 假测试（无断言） | 每个测试至少一个断言 |
| `vi.fn()` 无验证 | 验证调用参数/次数 |
| 测试 className 具体值 | 测试语义（role/text） |

## 覆盖率要求

- **分支覆盖率 ≥ 80%**
- **新功能必须有单元测试**
- **API 变更必须有集成测试**

```bash
bun run test --coverage
```

## E2E 测试（Phase 4）

使用 Playwright，目录：`e2e/`
