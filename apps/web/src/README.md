# src/ 目录

> Web 应用源代码根目录

## 目录说明

本目录包含 Next.js 应用的所有源代码，采用 App Router 架构。

## 目录结构

```
src/
├── app/                    # Next.js App Router 页面
│   ├── (dashboard)/        # 仪表盘路由组
│   ├── (research)/         # 研究路由组
│   ├── api/                # API 路由（可选）
│   ├── layout.tsx          # 根布局
│   └── globals.css         # 全局样式
│
├── components/             # React 组件
│   ├── ui/                 # shadcn/ui 基础组件
│   ├── charts/             # 图表组件
│   ├── dashboard/          # 仪表盘组件
│   ├── backtest/           # 回测组件
│   ├── portfolio/          # 组合组件
│   └── shared/             # 共享组件
│
├── stores/                 # Zustand 状态管理
│   ├── useAuthStore.ts     # 认证状态
│   ├── usePortfolioStore.ts # 组合状态
│   ├── useBacktestStore.ts  # 回测状态
│   └── useRiskStore.ts     # 风控状态
│
├── types/                  # TypeScript 类型定义
│   ├── api.ts              # API 响应类型
│   ├── models.ts           # 业务模型类型
│   └── charts.ts           # 图表配置类型
│
├── lib/                    # 工具函数和库
│   ├── api.ts              # API 客户端
│   ├── utils.ts            # 通用工具
│   ├── formatters.ts       # 格式化函数
│   └── constants.ts        # 常量定义
│
└── hooks/                  # 自定义 React Hooks
    ├── useBacktest.ts      # 回测 Hook
    ├── usePortfolio.ts     # 组合 Hook
    ├── useWebSocket.ts     # WebSocket Hook
    └── useMediaQuery.ts    # 响应式 Hook
```

## 各模块说明

### app/ - Next.js App Router

使用 Next.js 15 的 App Router 架构，支持：
- 文件系统路由
- 路由组（用括号命名，不影响 URL）
- 布局组件（layout.tsx）
- 服务端组件（RSC）和客户端组件

详细文档：[app/README.md](app/README.md)

### components/ - React 组件

所有 UI 组件按功能模块组织：
- **ui/**: shadcn/ui 基础组件（Button、Card、Dialog 等）
- **charts/**: 图表组件（净值曲线、K线图等）
- **dashboard/**: 仪表盘页面专用组件
- **backtest/**: 回测页面专用组件
- **portfolio/**: 组合管理页面专用组件
- **shared/**: 跨页面共享的通用组件

详细文档：[components/README.md](components/README.md)

### stores/ - 状态管理

使用 Zustand 进行全局状态管理：
- **useAuthStore**: 用户认证状态
- **usePortfolioStore**: 组合持仓和调仓计划状态
- **useBacktestStore**: 回测配置和结果状态
- **useRiskStore**: 风险监控状态

详细文档：[stores/README.md](stores/README.md)

### types/ - 类型定义

TypeScript 类型定义：
- **api.ts**: API 请求/响应类型（与后端 Pydantic 模型对齐）
- **models.ts**: 业务领域模型类型
- **charts.ts**: 图表配置类型

详细文档：[types/README.md](types/README.md)

### lib/ - 工具函数

通用工具函数和库：
- **api.ts**: API 客户端封装（fetch/axios + TanStack Query）
- **utils.ts**: 通用工具函数（cn、clsx 等）
- **formatters.ts**: 格式化函数（数字、日期、百分比等）
- **constants.ts**: 常量定义（API 端点、图表配置等）

### hooks/ - 自定义 Hooks

可复用的 React Hooks：
- **useBacktest**: 回测逻辑封装
- **usePortfolio**: 组合数据获取
- **useWebSocket**: WebSocket 连接管理
- **useMediaQuery**: 响应式媒体查询

## 设计原则

1. **关注点分离**: 页面、组件、状态、类型、工具各司其职
2. **可复用性**: 组件和 Hooks 设计为可复用
3. **类型安全**: 所有模块都有完整的 TypeScript 类型
4. **按需导入**: 使用 tree-shaking 减小打包体积
5. **一致性**: 统一的命名和代码风格

## 导入规则

### 绝对导入

使用 `@/` 别名从 src 根目录导入：

```typescript
// ✅ 推荐
import { Button } from '@/components/ui/button';
import { useBacktest } from '@/hooks/useBacktest';
import { BacktestParams } from '@/types/api';

// ❌ 避免
import { Button } from '../../../components/ui/button';
```

### 模块导入顺序

1. React/Next.js 核心库
2. 第三方库
3. @/ 别名导入（按类型分组）
4. 相对导入（本地模块）
5. 类型导入（import type）

```typescript
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { useBacktestStore } from '@/stores/useBacktestStore';
import type { BacktestResult } from '@/types/api';
import './LocalModule.css';
```

## 文件命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| React 组件 | PascalCase | `BacktestResults.tsx` |
| Hooks | camelCase + use 前缀 | `useBacktest.ts` |
| 工具函数 | camelCase | `formatNumber.ts` |
| 类型定义 | camelCase + .ts | `api.ts` |
| 常量 | camelCase | `constants.ts` |
| 样式 | camelCase + .module.css | `Button.module.css` |

## 开发注意事项

1. **组件设计**:
   - 保持组件小而专注（单一职责）
   - 使用 TypeScript 接口定义 props
   - 添加 JSDoc 注释说明组件用途

2. **状态管理**:
   - 本地状态使用 useState
   - 全局状态使用 Zustand
   - 服务器状态使用 TanStack Query

3. **性能优化**:
   - 使用 React.memo 避免不必要的重渲染
   - 大列表使用虚拟化（react-window）
   - 懒加载路由和组件

4. **错误处理**:
   - 使用 Error Boundary 捕获组件错误
   - API 调用统一错误处理
   - 用户友好的错误提示

## 相关文档

- [app/README.md](app/README.md) - App Router 页面结构
- [components/README.md](components/README.md) - 组件库说明
- [stores/README.md](stores/README.md) - 状态管理方案
- [types/README.md](types/README.md) - 类型系统说明

---

**最后更新**: 2026-01-04
