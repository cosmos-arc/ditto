---
paths:
  - "src/components/**"
---

# 组件规范

## 基础原则

### shadcn/ui 优先

**shadcn/ui 组件作为基础，禁止重复造轮子。**

在创建新组件前，先检查 shadcn/ui 是否已有对应组件：
- `src/components/ui/` 目录
- [shadcn/ui 文档](https://ui.shadcn.com/)

### CVA 变体模式

使用 `class-variance-authority`（CVA）管理组件变体：

```tsx
import { cva, type VariantProps } from "class-variance-authority";

const buttonVariants = cva("inline-flex items-center justify-center", {
  variants: {
    variant: {
      default: "bg-primary text-white",
      destructive: "bg-destructive text-white",
      outline: "border border-input",
    },
    size: {
      default: "h-10 px-4",
      sm: "h-8 px-2",
    },
  },
  defaultVariants: {
    variant: "default",
    size: "default",
  },
});
```

### data-slot 精确样式

使用 `data-slot` 属性实现精确样式覆盖：

```tsx
// ✅ 正确
<div data-slot="card-header" className="flex flex-col gap-1.5 p-6" />

// CSS 中
[data-slot="card-header"] {
  /* 精确样式 */
}
```

## 组件 Props 规范

### 类型定义

```tsx
// ✅ 正确：显式定义 Props interface
interface UserProfileProps {
  name: string;
  avatar?: string;
  onUpdate: (name: string) => void;
}

function UserProfile({ name, avatar, onUpdate }: UserProfileProps) {
  // ...
}

// ❌ 禁止：内联类型定义
function UserProfile({ name }: { name: string }) {
  // ...
}
```

### 受控 vs 非受控

- 默认提供受控模式（`value` + `onChange`）
- 通过 `defaultValue` 支持非受控模式
- 不混合两种模式

## 可组合性优先

- 优先组合（composition）而非继承
- 使用 `children` prop 实现内容插槽
- 复杂组件使用 compound component 模式

## 导出规范

```tsx
// 每个组件文件导出组件 + Props 类型
export { UserProfile };
export type { UserProfileProps };
```
