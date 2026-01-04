# types/ 目录

> TypeScript 类型定义

## 目录说明

本目录包含所有 TypeScript 类型定义，与后端 Pydantic 模型对齐。

## 类型分类

```
┌─────────────────────────────────────────────────────────────┐
│                       类型系统分层                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  1. API 类型 (api.ts)        - API 请求/响应类型            │
│  2. 业务模型 (models.ts)     - 领域实体类型                  │
│  3. 图表类型 (charts.ts)     - 图表配置类型                  │
│  4. 表单类型 (forms.ts)      - 表单数据类型                  │
│  5. 通用类型 (common.ts)     - 通用工具类型                  │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构

```
types/
├── api.ts              # API 请求/响应类型
├── models.ts           # 业务领域模型类型
├── charts.ts           # 图表配置类型
├── forms.ts            # 表单数据类型
├── common.ts           # 通用工具类型
└── index.ts            # 导出所有类型
```

## 核心 API 类型

### api.ts - API 请求/响应类型

与后端 FastAPI Pydantic 模型完全对齐。

```typescript
// ============================================================================
// 通用 API 类型
// ============================================================================

/**
 * API 响应基础结构
 */
export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
  meta?: {
    timestamp: string;
    requestId: string;
  };
}

/**
 * 分页请求参数
 */
export interface PaginationParams {
  page: number;
  pageSize: number;
  sortBy?: string;
  sortOrder?: 'asc' | 'desc';
}

/**
 * 分页响应
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

// ============================================================================
// 组合 API 类型
// ============================================================================

/**
 * 组合总览
 */
export interface PortfolioOverview {
  portfolioId: string;
  totalValue: number;
  cash: number;
  positionsCount: number;
  dailyPnL: number;
  dailyPnLPct: number;
  unrealizedPnL: number;
  drawdown: number;
  sharpeRatio: number;
  updatedAt: string;
}

/**
 * 持仓明细
 */
export interface Position {
  sid: string;
  symbol: string;
  name: string;
  shares: number;
  avgCost: number;
  currentPrice: number;
  marketValue: number;
  weight: number;
  unrealizedPnL: number;
  unrealizedPnLPct: number;
}

/**
 * 调仓计划
 */
export interface RebalancePlan {
  planId: string;
  portfolioId: string;
  tradeDate: string;
  status: 'pending' | 'approved' | 'executed' | 'cancelled';
  orders: Order[];
  summary: {
    totalOrders: number;
    estimatedTurnover: number;
    estimatedCost: number;
  };
  riskCheckResult?: RiskCheckResult;
  createdAt: string;
  updatedAt: string;
}

/**
 * 订单
 */
export interface Order {
  orderId: string;
  sid: string;
  symbol: string;
  name: string;
  action: 'buy' | 'sell';
  orderType: 'market' | 'limit';
  targetShares: number;
  targetWeight: number;
  limitPrice?: number;
  reason: string;
}

/**
 * 风险检查结果
 */
export interface RiskCheckResult {
  passed: boolean;
  level: 0 | 1 | 2 | 3;
  warnings: string[];
  errors: string[];
  checkTime: string;
}

// ============================================================================
// 回测 API 类型
// ============================================================================

/**
 * 回测请求参数
 */
export interface BacktestRequest {
  startDate: string;
  endDate: string;
  strategyId: string;
  initialCapital: number;
  rebalanceFreq: 'monthly' | 'weekly';
  maxPositions: number;
  minWeight: number;
  maxWeight: number;
  costModel?: {
    commissionRate: number;
    slippageRate: number;
    minCommission: number;
  };
}

/**
 * 回测结果
 */
export interface BacktestResult {
  runId: string;
  status: 'running' | 'completed' | 'failed';
  params: BacktestRequest;
  progress?: number;

  // 净值数据
  equity: Array<{
    date: string;
    value: number;
    benchmark?: number;
  }>;

  // 回撤数据
  drawdown: Array<{
    date: string;
    value: number;
  }>;

  // 性能指标
  metrics: PerformanceMetrics;

  // 交易记录
  trades: Trade[];

  // 调仓记录
  rebalances: Array<{
    date: string;
    orders: Order[];
    turnover: number;
    cost: number;
  }>;

  startedAt: string;
  completedAt?: string;
  error?: string;
}

/**
 * 性能指标
 */
export interface PerformanceMetrics {
  // 收益指标
  totalReturn: number;
  annualizedReturn: number;
  benchmarkReturn?: number;
  excessReturn?: number;

  // 风险指标
  volatility: number;
  downsideVolatility?: number;
  maxDrawdown: number;
  avgDrawdown: number;

  // 风险调整收益
  sharpeRatio: number;
  sortinoRatio?: number;
  calmarRatio?: number;

  // 交易指标
  winRate: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;

  // 其他指标
  totalTrades: number;
  avgHoldingPeriod: number;
  turnover: number;
}

/**
 * 交易记录
 */
export interface Trade {
  tradeId: string;
  sid: string;
  symbol: string;
  name: string;
  action: 'buy' | 'sell';
  shares: number;
  price: number;
  cost: number;
  tradeDate: string;
  reason: string;
}

// ============================================================================
// 风控 API 类型
// ============================================================================

/**
 * 风险状态
 */
export interface RiskStatus {
  killSwitchLevel: 0 | 1 | 2 | 3;
  killSwitchActive: boolean;
  currentDrawdown: number;
  maxDrawdown: number;
  drawdownVelocity: number;
  velocityLimit: number;
  lastCheckTime: string;
}

/**
 * 风险事件
 */
export interface RiskEvent {
  eventId: string;
  timestamp: string;
  level: 1 | 2 | 3;
  type: 'drawdown' | 'velocity' | 'manual' | 'system';
  message: string;
  action: string;
  resolvedAt?: string;
  resolvedBy?: string;
}

/**
 * Kill Switch 配置
 */
export interface KillSwitchConfig {
  enabled: boolean;
  level1Threshold: number;  // 回撤阈值
  level2Threshold: number;
  level3Threshold: number;
  velocityThreshold: number;  // 回撤速度阈值
  autoRecovery: boolean;
  recoveryThreshold: number;
}

// ============================================================================
// 研究 API 类型
// ============================================================================

/**
 * 策略定义
 */
export interface Strategy {
  strategyId: string;
  name: string;
  description: string;
  type: 'etf_rotation' | 'stock_selection' | 'convertible_bond';
  lifecycleState: 'research' | 'paper' | 'live_small' | 'live_full' | 'deprecated';
  config: StrategyConfig;
  performance?: {
    sharpeRatio: number;
    maxDrawdown: number;
    totalReturn: number;
  };
  createdAt: string;
  updatedAt: string;
}

/**
 * 策略配置
 */
export interface StrategyConfig {
  rebalanceFreq: 'monthly' | 'weekly';
  maxPositions: number;
  minWeight: number;
  maxWeight: number;
  regime: {
    bullMaxWeight: number;
    oscillationMaxWeight: number;
    bearMaxWeight: number;
  };
  factors: FactorWeightConfig[];
}

/**
 * 因子权重配置
 */
export interface FactorWeightConfig {
  factorId: string;
  name: string;
  weight: number;
  direction: 'long' | 'short';
}

/**
 * 因子定义
 */
export interface Factor {
  factorId: string;
  name: string;
  description: string;
  category: 'momentum' | 'value' | 'volatility' | 'crowding' | 'custom';
  formula: string;
  dataFields: string[];
  status: 'active' | 'deprecated';
  performance?: {
    ic: number;
    ir: number;
    hitRate: number;
  };
}

/**
 * 因子分析结果
 */
export interface FactorAnalysis {
  factorId: string;
  startDate: string;
  endDate: string;
  ic: number;
  ir: number;
  hitRate: number;
  decay: Array<{
    period: number;
    ic: number;
  }>;
  correlation?: Record<string, number>;
}

// ============================================================================
// 市场 API 类型
// ============================================================================

/**
 * Regime 状态
 */
export interface RegimeStatus {
  currentRegime: 'Bull' | 'Oscillation' | 'Bear';
  confidence: number;
  probabilities: {
    bull: number;
    oscillation: number;
    bear: number;
  };
  indicators: {
    trendStrength: number;
    volatility: number;
    breadth: number;
  };
  updatedAt: string;
}

/**
 * 市场概览
 */
export interface MarketOverview {
  date: string;
  indices: Array<{
    code: string;
    name: string;
    value: number;
    change: number;
    changePct: number;
  }>;
  etfPerformance: Array<{
    sid: string;
    symbol: string;
    name: string;
    value: number;
    change: number;
    changePct: number;
  }>;
}

// ============================================================================
// 系统状态 API 类型
// ============================================================================

/**
 * 系统健康状态
 */
export interface SystemHealth {
  status: 'healthy' | 'degraded' | 'unhealthy';
  version: string;
  uptime: number;
  services: Array<{
    name: string;
    status: 'up' | 'down';
    lastCheck: string;
  }>;
  dataQuality: {
    lastUpdate: string;
    completeness: number;
    issues: string[];
  };
}
```

## 业务模型类型

### models.ts - 领域实体类型

```typescript
// ============================================================================
// 核心实体
// ============================================================================

/**
 * 证券标识
 */
export interface SecurityIdentifier {
  sid: string;           // 内部唯一 ID
  srcCode: string;       // 源系统代码
  source: string;        // 数据源（tushare/akshare）
  type: 'stock' | 'etf' | 'index' | 'futures';
}

/**
 * 证券基本信息
 */
export interface Security {
  sid: string;
  symbol: string;
  name: string;
  type: SecurityIdentifier['type'];
  listDate: string;
  delistDate?: string;
  exchange: string;
  sector?: string;
  industry?: string;
  metadata?: Record<string, unknown>;
}

/**
 * 生命周期状态
 */
export type LifecycleState =
  | 'research'
  | 'paper'
  | 'live_small'
  | 'live_full'
  | 'deprecated';

/**
 * 信号类型
 */
export type SignalType = 'buy' | 'sell' | 'hold';

/**
 * 调仓类型
 */
export type RebalanceType =
  | 'scheduled'   // 定期调仓
  | 'triggered'   // 触发式调仓
  | 'manual';     // 手动调仓
```

## 图表类型

### charts.ts - 图表配置类型

```typescript
import { AxisOptions, ChartOptions } from 'react-chartjs-2';

// ============================================================================
// 通用图表类型
// ============================================================================

/**
 * 数据点
 */
export interface DataPoint {
  x: string | number;
  y: number;
  metadata?: Record<string, unknown>;
}

/**
 * 时间序列数据
 */
export interface TimeSeriesData {
  date: string;
  value: number;
  benchmark?: number;
}

/**
 * 数据集配置
 */
export interface DatasetConfig {
  label: string;
  data: Array<number | DataPoint>;
  borderColor?: string;
  backgroundColor?: string;
  borderWidth?: number;
  borderDash?: number[];
  tension?: number;
  fill?: boolean;
}

/**
 * 图表配置
 */
export interface ChartConfig {
  type: 'line' | 'bar' | 'pie' | 'scatter' | 'candlestick';
  datasets: DatasetConfig[];
  options?: ChartOptions;
}

// ============================================================================
// 净值曲线图表
// ============================================================================

export interface EquityCurveConfig extends ChartConfig {
  type: 'line';
  showBenchmark: boolean;
  showDrawdown: boolean;
  yAxis: {
    left: { label: string; range: [number, number] };
    right?: { label: string; range: [number, number] };
  };
}

// ============================================================================
// K线图表
// ============================================================================

export interface KLineData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface KLineChartConfig {
  data: KLineData[];
  indicators?: {
    ma?: Array<{ period: number; color: string }>;
    bollinger?: { period: number; stdDev: number };
  };
  annotations?: Array<{
    type: 'buy' | 'sell';
    date: string;
    price: number;
  }>;
}

// ============================================================================
// 热力图
// ============================================================================

export interface HeatmapData {
  x: string;
  y: string;
  value: number;
  metadata?: Record<string, unknown>;
}

export interface HeatmapConfig {
  data: HeatmapData[];
  colorScale: {
    min: string;
    max: string;
    type: 'sequential' | 'diverging';
  };
  axisLabels: {
    x: string;
    y: string;
  };
}

// ============================================================================
// 饼图
// ============================================================================

export interface PieData {
  label: string;
  value: number;
  color?: string;
}

export interface PieChartConfig {
  data: PieData[];
  showPercentage: boolean;
  showLabels: boolean;
  innerRadius?: number;  // 环形图
}
```

## 表单类型

### forms.ts - 表单数据类型

```typescript
// ============================================================================
// 回测配置表单
// ============================================================================

export interface BacktestFormData {
  // 日期范围
  startDate: string;
  endDate: string;

  // 策略配置
  strategyId: string;
  strategyName?: string;

  // 资金配置
  initialCapital: number;

  // 调仓配置
  rebalanceFreq: 'monthly' | 'weekly';
  rebalanceDay?: number;  // 每月/周的几号

  // 持仓配置
  maxPositions: number;
  minWeight: number;
  maxWeight: number;

  // 成本模型
  enableCostModel: boolean;
  commissionRate?: number;
  slippageRate?: number;
  minCommission?: number;

  // 高级选项
  enableStopLoss?: boolean;
  stopLossThreshold?: number;
  enableRegimeFilter?: boolean;
}

// ============================================================================
// 策略配置表单
// ============================================================================

export interface StrategyFormData {
  // 基本信息
  name: string;
  description: string;
  type: 'etf_rotation' | 'stock_selection';

  // 调仓配置
  rebalanceFreq: 'monthly' | 'weekly';
  rebalanceDay?: number;

  // 持仓配置
  maxPositions: number;
  minWeight: number;
  maxWeight: number;

  // Regime 配置
  bullMaxWeight: number;
  oscillationMaxWeight: number;
  bearMaxWeight: number;

  // 因子配置
  factors: Array<{
    factorId: string;
    weight: number;
    direction: 'long' | 'short';
  }>;

  // 风控配置
  enableRiskControl: boolean;
  maxDrawdown?: number;
  killSwitchLevel?: 1 | 2 | 3;
}

// ============================================================================
// 因子配置表单
// ============================================================================

export interface FactorFormData {
  // 基本信息
  name: string;
  description: string;
  category: 'momentum' | 'value' | 'volatility' | 'crowding' | 'custom';

  // 因子公式
  formula: string;
  dataFields: string[];

  // 参数配置
  parameters: Record<string, number | string>;

  // 测试配置
  testStartDate: string;
  testEndDate: string;
  decayPeriods: number[];
}

// ============================================================================
// 调仓计划表单
// ============================================================================

export interface RebalanceFormData {
  planId?: string;
  tradeDate: string;

  // 调仓类型
  rebalanceType: 'scheduled' | 'triggered' | 'manual';

  // 手动调仓配置
  customOrders?: Array<{
    sid: string;
    action: 'buy' | 'sell';
    shares: number;
    reason: string;
  }>;

  // 审批配置
  requireApproval: boolean;
  notes?: string;
}
```

## 通用类型

### common.ts - 工具类型

```typescript
// ============================================================================
// 基础类型
// ============================================================================

/**
 * 可选字段（所有字段可选）
 */
export type Partial<T> = {
  [P in keyof T]?: T[P];
};

/**
 * 必需字段（所有字段必需）
 */
export type Required<T> = {
  [P in keyof T]-?: T[P];
};

/**
 * 提取部分字段
 */
export type Pick<T, K extends keyof T> = {
  [P in K]: T[P];
};

/**
 * 排除部分字段
 */
export type Omit<T, K extends keyof T> = Pick<T, Exclude<keyof T, K>>;

// ============================================================================
// 工具类型
// ============================================================================

/**
 * 只读类型
 */
export type ReadOnly<T> = {
  readonly [P in keyof T]: T[P];
};

/**
 * 深度只读
 */
export type DeepReadOnly<T> = {
  readonly [P in keyof T]: T[P] extends object ? DeepReadOnly<T[P]> : T[P];
};

/**
 * 可空类型
 */
export type Nullable<T> = T | null;

/**
 * 可能未定义类型
 */
export type Maybe<T> = T | undefined;

/**
 * 枚举值类型
 */
export type ValueOf<T> = T[keyof T];

// ============================================================================
// 时间类型
// ============================================================================

/**
 * ISO 8601 日期字符串
 */
export type ISODateString = string;

/**
 * Unix 时间戳（秒）
 */
export type UnixTimestamp = number;

/**
 * 日期范围
 */
export interface DateRange {
  start: ISODateString;
  end: ISODateString;
}

// ============================================================================
// 分页类型
// ============================================================================

/**
 * 排序方向
 */
export type SortOrder = 'asc' | 'desc';

/**
 * 排序配置
 */
export interface SortConfig {
  field: string;
  order: SortOrder;
}

/**
 * 分页配置
 */
export interface PaginationConfig {
  page: number;
  pageSize: number;
  total?: number;
}

// ============================================================================
// 选择器类型
// ============================================================================

/**
 * 选项
 */
export interface Option<T = string> {
  label: string;
  value: T;
  disabled?: boolean;
  metadata?: Record<string, unknown>;
}

/**
 * 选择器配置
 */
export interface SelectConfig<T = string> {
  options: Option<T>[];
  value?: T;
  multiple?: boolean;
  searchable?: boolean;
  placeholder?: string;
}

// ============================================================================
// 表格类型
// ============================================================================

/**
 * 列配置
 */
export interface ColumnConfig<T = unknown> {
  key: string;
  title: string;
  dataIndex?: keyof T;
  render?: (value: unknown, record: T) => React.ReactNode;
  sortable?: boolean;
  filterable?: boolean;
  width?: number;
  align?: 'left' | 'center' | 'right';
}

/**
 * 表格选择
 */
export interface TableSelection<T> {
  selectedRows: T[];
  selectedRowKeys: string[];
  onSelect: (record: T, selected: boolean) => void;
  onSelectAll: (selected: boolean) => void;
}

// ============================================================================
// 状态类型
// ============================================================================

/**
 * 加载状态
 */
export type LoadingState = 'idle' | 'loading' | 'success' | 'error';

/**
 * 异步状态
 */
export interface AsyncState<T, E = Error> {
  status: LoadingState;
  data?: T;
  error?: E;
}

/**
 * 创建异步状态
 */
export function createAsyncState<T>(): AsyncState<T> {
  return {
    status: 'idle',
  };
}

// ============================================================================
// 颜色类型
// ============================================================================

/**
 * 颜色值
 */
export type ColorValue =
  | string  // hex, rgb, hsl, color name
  | { r: number; g: number; b: number; a?: number };  // rgba object

/**
 * 主题颜色
 */
export type ThemeColor =
  | 'primary'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'error'
  | 'info';

// ============================================================================
// 尺寸类型
// ============================================================================

/**
 * 尺寸
 */
export type Size = 'xs' | 'sm' | 'md' | 'lg' | 'xl';

/**
 * 屏幕尺寸断点
 */
export type Breakpoint = 'sm' | 'md' | 'lg' | 'xl' | '2xl';

/**
 * 响应式值
 */
export type ResponsiveValue<T> = T | {
  base?: T;
  sm?: T;
  md?: T;
  lg?: T;
  xl?: T;
  '2xl'?: T;
};
```

## 类型使用示例

### 在组件中使用

```typescript
import { BacktestResult, BacktestRequest } from '@/types/api';
import { BacktestFormData } from '@/types/forms';

function BacktestResults({ result }: { result: BacktestResult }) {
  return (
    <div>
      <h2>回测结果</h2>
      <Metrics metrics={result.metrics} />
      <EquityCurve data={result.equity} />
      <TradeHistory trades={result.trades} />
    </div>
  );
}

function BacktestConfig() {
  const [formData, setFormData] = useState<BacktestFormData>({
    startDate: '2020-01-01',
    endDate: '2024-12-31',
    strategyId: 'etf-rotation',
    initialCapital: 1000000,
    rebalanceFreq: 'monthly',
    maxPositions: 5,
    minWeight: 0.1,
    maxWeight: 0.3,
    enableCostModel: true,
  });

  const handleSubmit = () => {
    const request: BacktestRequest = {
      ...formData,
      costModel: formData.enableCostModel ? {
        commissionRate: 0.0003,
        slippageRate: 0.0001,
        minCommission: 5,
      } : undefined,
    };

    // 提交请求
  };
}
```

### 在 API 客户端中使用

```typescript
import type { ApiResponse, PaginatedResponse, PortfolioOverview } from '@/types/api';

export async function fetchPortfolio(
  portfolioId: string
): Promise<ApiResponse<PortfolioOverview>> {
  const response = await fetch(`/api/portfolios/${portfolioId}`);
  return response.json();
}

export async function fetchPositions(
  portfolioId: string,
  params: PaginationParams
): Promise<ApiResponse<PaginatedResponse<Position>>> {
  const url = new URL(`/api/portfolios/${portfolioId}/positions`);
  url.searchParams.set('page', params.page.toString());
  url.searchParams.set('pageSize', params.pageSize.toString());

  const response = await fetch(url.toString());
  return response.json();
}
```

## 类型最佳实践

### 1. 与后端对齐

确保前端类型与后端 Pydantic 模型完全一致：

```python
# 后端 FastAPI 模型
from pydantic import BaseModel

class PortfolioOverview(BaseModel):
    portfolio_id: str
    total_value: float
    cash: float
    positions_count: int
```

```typescript
// 前端类型（字段名转为 camelCase）
export interface PortfolioOverview {
  portfolioId: string;
  totalValue: number;
  cash: number;
  positionsCount: int;
}
```

### 2. 使用类型守卫

```typescript
function isBacktestResult(value: unknown): value is BacktestResult {
  return (
    typeof value === 'object' &&
    value !== null &&
    'runId' in value &&
    'status' in value &&
    'metrics' in value
  );
}

function processData(data: unknown) {
  if (isBacktestResult(data)) {
    // TypeScript 知道这是 BacktestResult
    console.log(data.metrics.sharpeRatio);
  }
}
```

### 3. 使用泛型

```typescript
interface ApiResponse<T> {
  data: T;
  success: boolean;
}

// 使用
type PortfolioResponse = ApiResponse<PortfolioOverview>;
type BacktestResponse = ApiResponse<BacktestResult>;
```

### 4. 导出类型

```typescript
// types/index.ts
export * from './api';
export * from './models';
export * from './charts';
export * from './forms';
export * from './common';

// 使用
import { BacktestResult, Position, ChartConfig } from '@/types';
```

## 相关文档

- [TypeScript 官方文档](https://www.typescriptlang.org/)
- [React TypeScript Cheatsheet](https://react-typescript-cheatsheet.netlify.app/)
- [后端 Pydantic 模型](../../apps/server/src/ditto_server/models/)

---

**最后更新**: 2026-01-04
