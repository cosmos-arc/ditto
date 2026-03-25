---
paths:
  - "src/**/*.ts"
  - "src/**/*.tsx"
---

# any 和 @ts-ignore 使用规范

## 核心原则

**核心源码零容忍**：`src/` 中不应有任何 `any`、`@ts-ignore`、`@ts-expect-error`。

**测试代码适度豁免**：测试文件中的 mock 类型可使用 `any`。

**优先使用类型系统工具**：用 `unknown` + type guard / `TypeGuard` / `Protocol` 替代。

---

## 禁止规则

### 生产代码（src）禁止项

| 规则 | 例外 | 说明 |
|------|------|------|
| `any` | 测试文件中的 mock 类型 | 通过类型修正解决 |
| `@ts-ignore` | 无 | 删除注释，修正类型 |
| `@ts-expect-error` | 无 | 删除注释，修正类型 |
| `as any` | 无 | 使用类型断言或重构 |

### 替代方案

```typescript
// ❌ 禁止：any
function processData(data: any) {}

// ✅ 正确：unknown + type guard
function processData(data: unknown) {
  if (!isValidData(data)) throw new Error("Invalid data");
  // data 现在是正确的类型
}

// ✅ 正确：泛型
function processData<T extends Data>(data: T) {}

// ✅ 正确：TypeGuard
function isUserData(data: unknown): data is UserData {
  return typeof data === "object" && data !== null && "name" in data;
}
```

---

## 允许的豁免

### 测试文件中的 mock

```typescript
// ✅ 允许：测试 mock
const mockUseQuery = vi.fn() as ReturnType<typeof vi.fn<typeof useQuery>>;
```

### 第三方库类型缺失

```typescript
// ✅ 允许：临时声明模块类型（需提交 PR 补类型）
// types/third-party.d.ts
declare module "third-party-lib" {
  export function doSomething(input: string): Promise<Result>;
}
```

---

## 修复流程

### 处理步骤

1. **理解原因**：运行 `bunx tsc --noEmit` 和 `bunx biome check .`
2. **评估方案**（按优先级）：
   - 使用 `unknown` + type guard（优先）
   - 使用泛型约束
   - 使用 `TypeGuard` / `Protocol`
   - 声明模块类型
3. **TDD 实施**：RED → GREEN → REFACTOR
4. **验证**：
   ```bash
   bunx biome check .      # 无错误
   bunx tsc --noEmit       # 0 errors
   bun run test            # 通过
   ```

### 常见问题方案

| 问题 | 解决方案 |
|------|----------|
| 第三方库无类型 | `types/` 目录声明 + 提交 PR |
| API 响应结构不确定 | `unknown` + zod schema 验证 |
| 事件处理器参数复杂 | 使用 React 事件类型 |
| 复杂联合类型 | 使用 discriminated union |

---

## 违规检测

```bash
# Biome 自动检测 noExplicitAny（生产代码 error，测试代码 off）
bunx biome check src/
```

### 验证标准

- ✅ 核心源码 `any` = 0（除测试文件）
- ✅ 核心源码 `@ts-ignore` = 0
- ✅ 核心源码 `@ts-expect-error` = 0
- ✅ tsc strict 检查通过
- ✅ biome lint 检查通过

---

## 参考资源

- [core.md](core.md) — TypeScript 核心规范
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/)
- [Biome Rules](https://biomejs.dev/linter/rules/)
