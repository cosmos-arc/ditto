# Sprint 0 T1: API 类型体系设计

## 概述

为 6 个业务域（platform/home/markets/instruments/research/trading/ai）的 106 个 API 端点定义 TypeScript 类型，基于 API 全链路文档手写提取。

## 目录结构

```
src/types/
├── index.ts              # barrel export
├── common.ts             # 通用类型（分页/排序/枚举/包装）
├── platform.ts           # Platform 域 8 端点
├── home.ts               # Home 域 8 端点
├── markets.ts            # Markets 域 26 端点
├── instruments.ts        # Instrument Hub 类型
├── research.ts           # Research 域 17 端点
├── trading.ts            # Trading 域 28 端点
└── ai.ts                 # AI 域 19 端点
```

## 设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 类型来源 | 手写提取 | 无 OpenAPI spec，文档已是 TS 格式 |
| 域划分 | 6 域（与文档一致） | 保持与 API 目录文档对齐 |
| 文件粒度 | 单文件/域 | 106 端点总量适中，单文件易查找 |
| 集成方式 | 独立 types 目录 | api-client 泛型参数引用，不修改 client |

## 设计原则

1. **Request/Response 分离**：每个端点对应一个 Request + Response 类型
2. **GET 无参用 `undefined`**：明确标识无请求体
3. **所有字段 `readonly`**：API 数据不可变
4. **跨域类型上提 common.ts**：MarketSession、Severity 等复用类型
5. **域内共享类型置顶**：如 ScreenerFilter、PipelineStatus 等

## 通用类型 (common.ts)

- `ApiResponse<T>` — 统一响应包装
- `PaginatedRequest` / `PaginatedResponse<T>` — 分页
- `SortDirection` / `SortField` — 排序
- `TimeRange` — 时间范围
- `Severity` / `Priority` — 告警/优先级
- `MarketSession` — 交易阶段

## 域类型模式

```typescript
// Request Types
export type GetPulseRequest = undefined;
export type RunScreenerRequest = { filters: ScreenerFilter[]; ... };

// Response Types
export type PulseResponse = { date: string; session: MarketSession; ... };

// Domain Shared Types
export type ScreenerFilter = { field: string; op: ...; value: ... };
```

## 验收标准

- `bunx tsc --noEmit` 类型检查通过
- 无 `any` 类型
- `src/types/index.ts` barrel export 全部类型
