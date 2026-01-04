# components/ 目录

> React 组件库

## 目录说明

本目录包含所有 React 组件，按功能模块组织。

## 目录结构

```
components/
├── ui/                     # shadcn/ui 基础组件
│   ├── button.tsx          # 按钮
│   ├── card.tsx            # 卡片
│   ├── dialog.tsx          # 对话框
│   ├── form.tsx            # 表单
│   ├── input.tsx           # 输入框
│   ├── table.tsx           # 表格
│   ├── tabs.tsx            # 标签页
│   ├── select.tsx          # 选择器
│   ├── toast.tsx           # 提示框
│   └── ...                 # 其他基础组件
│
├── charts/                 # 图表组件
│   ├── EquityCurve.tsx     # 净值曲线图
│   ├── DrawdownChart.tsx   # 回撤图
│   ├── KLineChart.tsx      # K线图
│   ├── FactorHeatmap.tsx   # 因子热力图
│   ├── IndustryPie.tsx     # 行业配置饼图
│   ├── PerformanceBar.tsx  # 性能指标柱状图
│   └── ChartContainer.tsx  # 图表容器（通用）
│
├── dashboard/              # 仪表盘组件
│   ├── DashboardOverview.tsx       # 总览卡片
│   ├── RegimeIndicator.tsx         # Regime 状态指示
│   ├── RiskLevelCard.tsx           # 风险等级卡片
│   ├── RecentRebalances.tsx        # 最近调仓列表
│   ├── MarketOverview.tsx          # 市场概览
│   └── MetricCard.tsx              # 指标卡片（通用）
│
├── backtest/               # 回测组件
│   ├── BacktestConfigForm.tsx      # 回测配置表单
│   ├── BacktestResults.tsx         # 回测结果容器
│   ├── BacktestStatus.tsx          # 回测状态指示
│   ├── PerformanceMetrics.tsx      # 性能指标表格
│   ├── TradeHistoryTable.tsx       # 交易历史表
│   └── BacktestComparison.tsx      # 回测对比（可选）
│
├── portfolio/              # 组合管理组件
│   ├── PortfolioOverview.tsx       # 组合总览
│   ├── HoldingsTable.tsx           # 持仓表格
│   ├── RebalancePlanDetail.tsx     # 调仓计划详情
│   ├── OrderList.tsx               # 订单列表
│   ├── IndustryAllocation.tsx      # 行业配置图
│   ├── FactorExposureChart.tsx     # 因子暴露图
│   └── ConcentrationAnalysis.tsx   # 集中度分析
│
├── risk/                   # 风控组件
│   ├── KillSwitchStatus.tsx        # Kill Switch 状态
│   ├── DrawdownMonitor.tsx         # 回撤监控
│   ├── RiskEventLog.tsx            # 风险事件日志
│   ├── RiskMetricsChart.tsx        # 风险指标趋势
│   └── RiskAlert.tsx               # 风险告警
│
├── research/               # 研究组件
│   ├── StrategyList.tsx            # 策略列表
│   ├── StrategyConfigForm.tsx      # 策略配置表单
│   ├── StrategyComparison.tsx      # 策略对比
│   ├── FactorList.tsx              # 因子列表
│   ├── FactorPerformanceChart.tsx  # 因子表现图
│   └── FactorCorrelationMatrix.tsx # 因子相关性矩阵
│
└── shared/                 # 共享组件
    ├── Sidebar.tsx                  # 侧边栏
    ├── Header.tsx                   # 顶部栏
    ├── Layout.tsx                   # 页面布局
    ├── Loading.tsx                  # 加载状态
    ├── ErrorBoundary.tsx            # 错误边界
    ├── EmptyState.tsx               # 空状态
    ├── DateTimePicker.tsx           # 日期时间选择器
    └── NumberDisplay.tsx            # 数字显示（格式化）
```

## 组件设计原则

### 1. 单一职责

每个组件只做一件事，保持简洁：

```tsx
// ✅ 好的设计
function MetricCard({ label, value, unit, trend }: MetricCardProps) {
  return (
    <Card>
      <div className="label">{label}</div>
      <div className="value">{value} {unit}</div>
      {trend && <TrendIndicator {...trend} />}
    </Card>
  );
}

// ❌ 不好的设计（功能太多）
function Dashboard({ portfolio, regime, risk, trades }) {
  // 混合了太多职责
}
```

### 2. 可复用性

组件应该是可复用的，避免硬编码：

```tsx
// ✅ 可复用
interface TableProps<T> {
  data: T[];
  columns: ColumnDef<T>[];
}

function Table<T>({ data, columns }: TableProps<T>) {
  // 通用表格实现
}

// ❌ 不可复用
function PortfolioTable({ holdings }) {
  // 硬编码了持仓表格逻辑
}
```

### 3. 类型安全

所有组件必须有完整的 TypeScript 类型定义：

```tsx
interface BacktestConfigFormProps {
  onSubmit: (params: BacktestParams) => void;
  isLoading?: boolean;
  initialValues?: Partial<BacktestParams>;
}

export function BacktestConfigForm({
  onSubmit,
  isLoading = false,
  initialValues,
}: BacktestConfigFormProps) {
  // 实现
}
```

### 4. Props 设计

- 使用明确的接口定义 props
- 使用对象传递复杂参数
- 使用 children 进行组合：

```tsx
// ✅ 使用 children
function Card({ children, className }: CardProps) {
  return <div className={cn('card', className)}>{children}</div>;
}

// 使用
<Card>
  <CardHeader>
    <CardTitle>标题</CardTitle>
  </CardHeader>
  <CardContent>内容</CardContent>
</Card>
```

## 组件分类

### UI 基础组件（ui/）

基于 shadcn/ui 的基础组件，提供原子化的 UI 元素。

**特点**:
- 高度可定制
- 可复制粘贴到项目中
- 无运行时依赖
- 完全支持 TypeScript
- 使用 Radix UI 原语

**示例**:

```tsx
// ui/button.tsx
import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';

const buttonVariants = cva(
  'inline-flex items-center justify-center rounded-md font-medium',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground',
        outline: 'border border-input bg-background',
      },
      size: {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 rounded-md px-3',
        lg: 'h-11 rounded-md px-8',
      },
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
```

**使用**:

```tsx
import { Button } from '@/components/ui/button';

<Button variant="default" size="lg">
  运行回测
</Button>
```

### 图表组件（charts/）

数据可视化组件，基于 Recharts 和 TradingView Lightweight Charts。

**特点**:
- 支持大数据集
- 响应式设计
- 交互式缩放和悬停
- 主题适配（亮色/暗色模式）

**示例**:

```tsx
// charts/EquityCurveChart.tsx
import { Line, LineChart, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

interface EquityCurveChartProps {
  data: Array<{ date: string; value: number; benchmark?: number }>;
  height?: number;
  showBenchmark?: boolean;
}

export function EquityCurveChart({
  data,
  height = 400,
  showBenchmark = true,
}: EquityCurveChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data}>
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Line
          type="monotone"
          dataKey="value"
          stroke="#8884d8"
          name="策略净值"
          dot={false}
        />
        {showBenchmark && (
          <Line
            type="monotone"
            dataKey="benchmark"
            stroke="#82ca9d"
            name="基准"
            dot={false}
            strokeDasharray="5 5"
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}
```

**使用**:

```tsx
import { EquityCurveChart } from '@/components/charts/EquityCurveChart';

<EquityCurveChart data={equityData} height={500} showBenchmark />
```

### 业务组件

按业务领域组织的高级组件。

#### 仪表盘组件（dashboard/）

展示系统总览和关键指标：

```tsx
// dashboard/MetricCard.tsx
interface MetricCardProps {
  title: string;
  value: number;
  unit?: string;
  precision?: number;
  trend?: {
    value: number;
    direction: 'up' | 'down';
  };
  icon?: React.ReactNode;
  loading?: boolean;
}

export function MetricCard({
  title,
  value,
  unit = '',
  precision = 2,
  trend,
  icon,
  loading = false,
}: MetricCardProps) {
  if (loading) {
    return <MetricCardSkeleton />;
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {formatNumber(value, precision)} {unit}
        </div>
        {trend && (
          <p className="text-xs text-muted-foreground">
            <TrendIndicator value={trend.value} direction={trend.direction} />
          </p>
        )}
      </CardContent>
    </Card>
  );
}
```

**使用**:

```tsx
import { MetricCard } from '@/components/dashboard/MetricCard';
import { TrendingUp, DollarSign } from 'lucide-react';

<MetricCard
  title="总资产"
  value={1000000}
  unit="元"
  trend={{ value: 2.5, direction: 'up' }}
  icon={<DollarSign className="h-4 w-4 text-muted-foreground" />}
/>
```

#### 回测组件（backtest/）

回测配置和结果展示：

```tsx
// backtest/BacktestConfigForm.tsx
interface BacktestConfigFormProps {
  onSubmit: (params: BacktestParams) => void;
  isLoading?: boolean;
}

export function BacktestConfigForm({ onSubmit, isLoading }: BacktestConfigFormProps) {
  const form = useForm<BacktestParams>({
    defaultValues: {
      startDate: '2020-01-01',
      endDate: '2024-12-31',
      strategyId: 'etf-rotation',
      initialCapital: 1000000,
      rebalanceFreq: 'monthly',
      maxPositions: 5,
    },
  });

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="startDate"
          render={({ field }) => (
            <FormItem>
              <FormLabel>开始日期</FormLabel>
              <FormControl>
                <Input type="date" {...field} />
              </FormControl>
            </FormItem>
          )}
        />
        {/* 更多表单字段 */}
        <Button type="submit" disabled={isLoading}>
          {isLoading ? '运行中...' : '运行回测'}
        </Button>
      </form>
    </Form>
  );
}
```

#### 组合组件（portfolio/）

组合持仓和调仓计划展示：

```tsx
// portfolio/HoldingsTable.tsx
interface HoldingsTableProps {
  holdings: Position[];
  onRebalance?: (positionId: string) => void;
}

export function HoldingsTable({ holdings, onRebalance }: HoldingsTableProps) {
  const columns: ColumnDef<Position>[] = [
    {
      accessorKey: 'symbol',
      header: '代码',
    },
    {
      accessorKey: 'name',
      header: '名称',
    },
    {
      accessorKey: 'shares',
      header: '持仓',
      cell: ({ row }) => formatNumber(row.getValue('shares'), 0),
    },
    {
      accessorKey: 'marketValue',
      header: '市值',
      cell: ({ row }) => formatCurrency(row.getValue('marketValue')),
    },
    {
      accessorKey: 'weight',
      header: '权重',
      cell: ({ row }) => `${formatNumber(row.getValue('weight') * 100, 2)}%`,
    },
    {
      id: 'actions',
      cell: ({ row }) => (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onRebalance?.(row.original.sid)}
        >
          调仓
        </Button>
      ),
    },
  ];

  return (
    <Table columns={columns} data={holdings} />
  );
}
```

#### 风控组件（risk/）

风险监控和 Kill Switch 状态：

```tsx
// risk/KillSwitchStatus.tsx
interface KillSwitchStatusProps {
  level: 0 | 1 | 2 | 3;
  active: boolean;
  reason?: string;
  onDeactivate?: () => void;
}

export function KillSwitchStatus({
  level,
  active,
  reason,
  onDeactivate,
}: KillSwitchStatusProps) {
  const levelConfig = {
    0: { label: '正常', color: 'bg-green-500' },
    1: { label: 'Level 1', color: 'bg-yellow-500' },
    2: { label: 'Level 2', color: 'bg-orange-500' },
    3: { label: 'Level 3', color: 'bg-red-500' },
  };

  const config = levelConfig[level];

  return (
    <Card className={cn('border-l-4', active && config.color)}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Kill Switch 状态</span>
          <Badge variant={active ? 'destructive' : 'default'}>
            {config.label}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {active && (
          <Alert variant="destructive">
            <AlertDescription>{reason}</AlertDescription>
          </Alert>
        )}
        {active && onDeactivate && (
          <Button
            variant="outline"
            className="mt-4"
            onClick={onDeactivate}
          >
            解除 Kill Switch
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
```

### 共享组件（shared/）

跨页面使用的通用组件。

#### 布局组件

```tsx
// shared/Layout.tsx
interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <div className="lg:pl-64">
        <Header />
        <main className="p-6">{children}</main>
      </div>
    </div>
  );
}
```

#### 加载状态

```tsx
// shared/Loading.tsx
export function Loading({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizeClasses = {
    sm: 'h-4 w-4',
    md: 'h-8 w-8',
    lg: 'h-12 w-12',
  };

  return (
    <div className="flex items-center justify-center">
      <Spinner className={cn('animate-spin', sizeClasses[size])} />
    </div>
  );
}
```

#### 空状态

```tsx
// shared/EmptyState.tsx
interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      {icon && <div className="mb-4 text-muted-foreground">{icon}</div>}
      <h3 className="text-lg font-semibold">{title}</h3>
      {description && (
        <p className="mt-2 text-sm text-muted-foreground">{description}</p>
      )}
      {action && (
        <Button className="mt-4" onClick={action.onClick}>
          {action.label}
        </Button>
      )}
    </div>
  );
}
```

## 组件开发指南

### 创建新组件

1. **确定组件职责**：组件应该做什么？
2. **定义 Props 接口**：使用 TypeScript 明确类型
3. **实现组件逻辑**：保持简洁和专注
4. **添加样式**：使用 Tailwind CSS 或 CSS Modules
5. **编写文档**：添加 JSDoc 注释
6. **编写测试**：使用 React Testing Library

### 组件模板

```tsx
'use client'; // 如果需要客户端交互

import * as React from 'react';
import { cn } from '@/lib/utils';

/**
 * 组件简短描述
 *
 * 详细说明组件的用途、使用场景等。
 *
 * @example
 * ```tsx
 * <MyComponent prop="value" />
 * ```
 */
export interface MyComponentProps {
  /**
   * 属性描述
   */
  prop: string;
  /**
   * 可选属性描述
   * @default "default"
   */
  optionalProp?: string;
  /**
   * 自定义类名
   */
  className?: string;
  /**
   * 子元素
   */
  children?: React.ReactNode;
}

export const MyComponent = React.forwardRef<HTMLDivElement, MyComponentProps>(
  ({ prop, optionalProp, className, children, ...props }, ref) => {
    return (
      <div ref={ref} className={cn('base-class', className)} {...props}>
        {prop}
        {children}
      </div>
    );
  }
);

MyComponent.displayName = 'MyComponent';
```

### 组件最佳实践

1. **使用 forwardRef**：支持 ref 转发
2. **设置 displayName**：便于调试
3. **使用 cn 工具**：合并类名
4. **展开 props**：支持 div 原生属性
5. **客户端标记**：只在必要时使用 `'use client'`
6. **性能优化**：使用 React.memo、useMemo、useCallback

### 组件测试

使用 React Testing Library：

```tsx
import { render, screen } from '@testing-library/react';
import { Button } from '@/components/ui/button';

describe('Button', () => {
  it('renders correctly', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button')).toHaveTextContent('Click me');
  });

  it('calls onClick when clicked', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click me</Button>);

    screen.getByRole('button').click();
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
});
```

## 相关文档

- [shadcn/ui 文档](https://ui.shadcn.com/)
- [Recharts 文档](https://recharts.org/)
- [Radix UI 文档](https://www.radix-ui.com/)
- [Tailwind CSS 文档](https://tailwindcss.com/)

---

**最后更新**: 2026-01-04
