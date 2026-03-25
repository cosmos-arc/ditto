---
paths:
  - "src/**"
---

# 架构设计规范

## Feature-based 目录结构

```
src/
├── features/           # 业务功能模块（按功能划分）
│   └── {name}/
│       ├── components/ # 功能专属组件
│       ├── hooks/      # 功能专属 hooks
│       ├── types.ts    # 功能类型定义
│       └── index.ts    # barrel export
├── components/ui/      # 共享 UI 组件（shadcn/ui）
├── lib/                # 工具函数 + API 层
│   ├── api.ts          # 集中式 API 客户端（typed）
│   └── utils.ts        # 通用工具函数
├── styles/             # Design Tokens + 全局样式
├── routes/             # 路由定义
└── main.tsx            # 应用入口
```

## 各层定位

| 层级 | 路径 | 职责 |
|------|------|------|
| **Feature** | `src/features/{name}/` | 业务功能模块，自包含 |
| **共享 UI** | `src/components/ui/` | 通用 UI 组件（shadcn） |
| **API 层** | `src/lib/api.ts` | 集中式 API 客户端 |
| **工具函数** | `src/lib/utils.ts` | 纯函数工具 |
| **Design Tokens** | `src/styles/` | CSS 变量 + 全局样式 |
| **路由** | `src/routes/` | TanStack Router 路由定义 |

## 依赖规则

```
Feature → components/ui → lib → styles
   ↑
   └─ 禁止跨 Feature 直接导入组件
```

**允许的依赖**：
- Feature 内部自由引用
- Feature → `components/ui/`（共享 UI）
- Feature → `lib/`（工具/API）
- Feature → `styles/`（通过 Tailwind）

**禁止的依赖**：
- ❌ Feature A → Feature B 的内部组件（通过 barrel export）
- ❌ `components/ui/` → Feature（UI 组件不依赖业务）
- ❌ `lib/` → Feature（工具层不依赖业务）

## 状态管理

| 类型 | 工具 | 使用场景 |
|------|------|----------|
| **服务端状态** | TanStack Query | API 数据获取/缓存/同步 |
| **客户端状态** | Zustand | 全局 UI 状态、用户偏好 |
| **组件状态** | React useState | 组件内部状态 |

**原则**：
- API 数据一律走 TanStack Query，禁止用 useState 管理
- 跨组件共享状态优先考虑 Zustand，避免 prop drilling
- Zustand store 按 feature 拆分，放在 `features/{name}/hooks/`

## 路由

- 使用 TanStack Router，文件路由约定
- 路由定义在 `src/routes/`
- 路由级别的数据加载使用 TanStack Router 的 loader

## 判断决策树

```
问题：这个组件放在哪里？

1. 是 shadcn/ui 基础组件？
   YES → src/components/ui/

2. 只在某个 Feature 内使用？
   YES → src/features/{name}/components/

3. 被多个 Feature 共享？
   YES → src/components/（通用组件）或提取到 src/components/ui/（shadcn）

4. 是纯工具函数？
   YES → src/lib/utils.ts

5. 是 API 调用逻辑？
   YES → src/lib/api.ts
```
