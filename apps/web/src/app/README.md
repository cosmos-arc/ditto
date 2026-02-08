# app/ 目录

> Next.js App Router 页面和路由

## 目录说明

本目录使用 Next.js 15 的 App Router 架构，提供基于文件系统的路由。

## 目录结构

```
app/
├── (dashboard)/            # 仪表盘路由组
│   ├── page.tsx            # 仪表盘首页 (/)
│   ├── layout.tsx          # 仪表盘布局
│   ├── backtest/           # 回测分析
│   │   ├── page.tsx        # 回测页面 (/backtest)
│   │   ├── [id]/           # 动态路由
│   │   │   └── page.tsx    # 回测详情 (/backtest/:id)
│   │   └── components/     # 回测页面专用组件
│   ├── portfolio/          # 组合管理
│   │   ├── page.tsx        # 组合总览 (/portfolio)
│   │   ├── rebalance/      # 调仓计划
│   │   │   └── page.tsx    # 调仓详情 (/portfolio/rebalance)
│   │   └── holdings/       # 持仓明细
│   │       └── page.tsx    # 持仓列表 (/portfolio/holdings)
│   └── risk/               # 风险监控
│       ├── page.tsx        # 风控页面 (/risk)
│       └── kill-switch/    # Kill Switch
│           └── page.tsx    # KS 状态 (/risk/kill-switch)
│
├── (research)/             # 研究路由组
│   ├── page.tsx            # 研究首页 (/research)
│   ├── layout.tsx          # 研究布局
│   ├── strategies/         # 策略研究
│   │   ├── page.tsx        # 策略列表 (/research/strategies)
│   │   ├── new/            # 新建策略
│   │   │   └── page.tsx    # 策略配置 (/research/strategies/new)
│   │   └── [id]/           # 策略详情
│   │       └── page.tsx    # 策略详情页 (/research/strategies/:id)
│   └── factors/            # 因子分析
│       ├── page.tsx        # 因子列表 (/research/factors)
│       └── [id]/           # 因子详情
│           └── page.tsx    # 因子分析 (/research/factors/:id)
│
├── api/                    # API 路由（可选）
│   ├── auth/               # 认证相关
│   │   └── [...nextauth]/  # NextAuth.js
│   │       └── route.ts    # /api/auth/*
│   └── proxy/              # API 代理（可选）
│       └── [...path]/      # 代理后端 API
│           └── route.ts    # /api/proxy/*
│
├── layout.tsx              # 根布局
├── page.tsx                # 根页面（重定向到 /dashboard）
├── globals.css             # 全局样式
├── error.tsx               # 错误边界
├── not-found.tsx           # 404 页面
└── loading.tsx             # 全局加载状态
```

## 路由组（Route Groups）

使用括号命名的目录是路由组，不影响 URL 路径，但可以：
- 共享布局（layout.tsx）
- 组织代码结构
- 应用不同的中间件

### (dashboard) - 仪表盘路由组

主要面向交易员和投资者的功能页面：
- 仪表盘总览
- 回测分析
- 组合管理
- 风险监控

**特点**:
- 需要认证
- 实时数据更新
- 交互式图表

### (research) - 研究路由组

面向研究人员的功能页面：
- 策略研究和配置
- 因子分析
- 参数优化

**特点**:
- 复杂表单
- 历史数据查询
- 对比分析

## 核心页面

### 1. 仪表盘首页

**路径**: `/`

**文件**: `(dashboard)/page.tsx`

**状态**: ⏳ 待开发

**功能**:
- 系统 Quick View
- 关键指标卡片
- Regime 状态指示
- 风险等级指示
- 最近调仓计划

**数据需求**:
```typescript
interface DashboardData {
  portfolio: {
    totalValue: number;
    dailyPnL: number;
    drawdown: number;
    sharpeRatio: number;
  };
  regime: {
    state: 'Bull' | 'Osc' | 'Bear';
    confidence: number;
    updatedAt: string;
  };
  risk: {
    level: 1 | 2 | 3;
    killSwitchActive: boolean;
  };
  recentRebalances: RebalancePlan[];
}
```

**组件结构**:
```tsx
export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <DashboardOverview />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <RegimeIndicator />
        <RiskLevelCard />
        <RecentRebalances />
      </div>
      <MarketOverview />
    </div>
  );
}
```

### 2. 回测分析

**路径**: `/backtest`

**文件**: `(dashboard)/backtest/page.tsx`

**状态**: ⏳ 待开发

**功能**:
- 回测参数配置表单
- 回测结果展示（净值、回撤、指标）
- 调仓历史记录
- 导出报告

**数据需求**:
```typescript
interface BacktestParams {
  startDate: string;
  endDate: string;
  strategyId: string;
  initialCapital: number;
  rebalanceFreq: 'monthly' | 'weekly';
  maxPositions: number;
}

interface BacktestResult {
  id: string;
  status: 'running' | 'completed' | 'failed';
  params: BacktestParams;
  equity: Array<{ date: string; value: number }>;
  drawdown: Array<{ date: string; value: number }>;
  metrics: {
    totalReturn: number;
    annualizedReturn: number;
    volatility: number;
    sharpeRatio: number;
    maxDrawdown: number;
    winRate: number;
  };
  trades: Trade[];
}
```

**组件结构**:
```tsx
export default function BacktestPage() {
  return (
    <div className="space-y-6">
      <BacktestConfigForm />
      <BacktestResults />
      <PerformanceMetrics />
      <TradeHistoryTable />
    </div>
  );
}
```

### 3. 组合管理

**路径**: `/portfolio`

**文件**: `(dashboard)/portfolio/page.tsx`

**状态**: ⏳ 待开发

**功能**:
- 当前组合持仓
- 调仓计划详情
- 历史调仓记录
- 持仓分析

**数据需求**:
```typescript
interface Portfolio {
  portfolioId: string;
  totalValue: number;
  cash: number;
  positions: Position[];
  rebalancePlan: RebalancePlan | null;
}

interface Position {
  instrumentId: string;
  symbol: string;
  name: string;
  shares: number;
  marketValue: number;
  weight: number;
  avgCost: number;
  currentPrice: number;
  unrealizedPnL: number;
}
```

### 4. 风险监控

**路径**: `/risk`

**文件**: `(dashboard)/risk/page.tsx`

**状态**: ⏳ 待开发

**功能**:
- Kill Switch 状态
- 实时回撤监控
- 风险事件日志
- 仓位限制检查

**数据需求**:
```typescript
interface RiskStatus {
  killSwitchLevel: 0 | 1 | 2 | 3;
  currentDrawdown: number;
  maxDrawdown: number;
  drawdownVelocity: number;
  events: RiskEvent[];
}

interface RiskEvent {
  eventId: string;
  timestamp: string;
  level: 1 | 2 | 3;
  type: 'drawdown' | 'velocity' | 'manual';
  message: string;
  action: string;
}
```

### 5. 策略研究

**路径**: `/research/strategies`

**文件**: `(research)/strategies/page.tsx`

**状态**: ⏳ 待开发

**功能**:
- 策略列表
- 策略配置
- 策略对比
- 策略回测

### 6. 因子分析

**路径**: `/research/factors`

**文件**: `(research)/factors/page.tsx`

**状态**: ⏳ 待开发

**功能**:
- 因子列表
- 因子表现
- 因子相关性
- 因子有效性测试

## 布局系统

### 根布局（layout.tsx）

```tsx
// app/layout.tsx
import { Providers } from '@/components/Providers';
import { Sidebar } from '@/components/shared/Sidebar';
import { Header } from '@/components/shared/Header';

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <Providers>
          <div className="flex h-screen">
            <Sidebar />
            <div className="flex-1 flex flex-col">
              <Header />
              <main className="flex-1 overflow-auto p-6">
                {children}
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
```

### 路由组布局

```tsx
// app/(dashboard)/layout.tsx
export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="dashboard-container">
      {/* 仪表盘特定布局 */}
      {children}
    </div>
  );
}
```

## 特殊页面

### 错误页面（error.tsx）

捕获子路由的错误：

```tsx
'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="error-container">
      <h2>出错了！</h2>
      <p>{error.message}</p>
      <button onClick={reset}>重试</button>
    </div>
  );
}
```

### 404 页面（not-found.tsx）

```tsx
export default function NotFound() {
  return (
    <div className="not-found">
      <h2>页面未找到</h2>
      <Link href="/">返回首页</Link>
    </div>
  );
}
```

### 加载状态（loading.tsx）

```tsx
export default function Loading() {
  return <div className="loading-spinner">加载中...</div>;
}
```

## API 路由（可选）

用于代理后端 API 或实现 NextAuth.js：

```tsx
// app/api/proxy/[...path]/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function GET(
  request: NextRequest,
  { params }: { params: { path: string[] } }
) {
  const path = params.path.join('/');
  const response = await fetch(`${process.env.API_URL}/${path}`, {
    headers: request.headers,
  });

  return NextResponse.json(await response.json());
}
```

## 开发指南

### 创建新页面

1. 在对应的路由组目录下创建 `page.tsx`
2. 定义页面组件（服务端或客户端）
3. 添加必要的布局和加载状态
4. 实现错误处理

### 创建动态路由

1. 创建带方括号的目录 `[id]`
2. 在 `page.tsx` 中访问 `params`：

```tsx
interface PageProps {
  params: { id: string };
}

export default function DetailPage({ params }: PageProps) {
  const { id } = params;
  // 使用 id 获取数据
}
```

### 路由中间件

在根目录创建 `middleware.ts`：

```ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  // 认证检查
  const token = request.cookies.get('token');

  if (!token && !request.nextUrl.pathname.startsWith('/login')) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/dashboard/:path*', '/portfolio/:path*'],
};
```

## 性能优化

1. **服务端组件（RSC）**: 默认使用服务端组件，只在需要交互时使用 `'use client'`
2. **数据预取**: 使用 `generateStaticParams` 预生成静态页面
3. **流式渲染**: 使用 `<Suspense>` 实现流式加载
4. **图片优化**: 使用 Next.js `Image` 组件

```tsx
import { Suspense } from 'react';

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <AsyncComponent />
    </Suspense>
  );
}
```

## 相关文档

- [Next.js App Router 文档](https://nextjs.org/docs/app)
- [路由组文档](https://nextjs.org/docs/app/building-your-application/routing/route-groups)
- [动态路由文档](https://nextjs.org/docs/app/building-your-application/routing/dynamic-routes)

---

**最后更新**: 2026-01-04
