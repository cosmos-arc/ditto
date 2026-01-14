# ditto-web

> 量化交易系统 Web 应用 - 可视化与交互界面

## 项目状态

⏳ **待开发** - 本模块处于规划阶段，尚未开始实施

## 项目概述

Ditto Web 是量化交易系统的前端应用，提供可视化界面用于策略研究、回测分析、组合管理和风险监控。

### 核心功能

- **策略研究**: ETF 行业轮动策略参数配置与回测
- **回测分析**: 历史回测结果可视化，性能指标展示
- **组合管理**: 实时组合状态、持仓分布、调仓计划
- **风险监控**: Kill Switch 状态、回撤监控、风险预警
- **市场仪表盘**: Regime 状态、因子表现、市场概览

## 技术栈

### 前端框架（待定）

当前评估以下技术栈选项：

| 技术栈 | 优势 | 劣势 | 推荐度 |
|--------|------|------|--------|
| **Next.js 15** | - React 生态成熟<br>- SSR/SSG 支持<br>- App Router 现代<br>- TypeScript 原生支持 | - 学习曲线较陡 | ⭐⭐⭐⭐⭐ 强烈推荐 |
| **Vue 3 + Nuxt 3** | - 响应式系统优雅<br>- Composition API | - 生态相对小 | ⭐⭐⭐⭐ 推荐 |
| **SvelteKit** | - 性能优异<br>- 包体积小 | - 生态较小 | ⭐⭐⭐ 备选 |

**推荐选择**: Next.js 15 + React 18 + TypeScript
- 与项目整体技术栈（Python/FastAPI）解耦
- 丰富的图表库支持（Recharts/TradingView Lightweight Charts）
- 强大的开发者工具和生态

### UI 组件库

| 库 | 特点 | 推荐度 |
|----|------|--------|
| **shadcn/ui** | - 基于 Radix UI<br>- 可复制粘贴到项目<br>- 完全可定制 | ⭐⭐⭐⭐⭐ 强烈推荐 |
| **Mantine** | - 功能丰富<br>- 开箱即用 | ⭐⭐⭐⭐ 推荐 |
| **Ant Design** | - 企业级<br>- 中文文档完善 | ⭐⭐⭐ 备选 |

**推荐选择**: shadcn/ui + Tailwind CSS
- 现代化设计系统
- 无运行时依赖，完全可控
- 与 Tailwind CSS 深度集成

### 数据可视化

| 库 | 用途 |
|----|------|
| **Recharts** | 通用图表（折线、柱状、饼图） |
| **TradingView Lightweight Charts** | K线图、技术指标 |
| **D3.js** | 高级定制可视化 |

### 状态管理

| 方案 | 推荐度 | 用途 |
|------|--------|------|
| **Zustand** | ⭐⭐⭐⭐⭐ | 全局状态管理（推荐） |
| **TanStack Query** | ⭐⭐⭐⭐⭐ | 服务器状态管理 |
| **Jotai** | ⭐⭐⭐⭐ | 原子化状态（备选） |

### 样式方案

- **Tailwind CSS** - 原子化 CSS 框架
- **CSS Modules** - 组件级样式隔离
- **clsx / cn** - 条件类名工具

## 目录结构

```
apps/web/
├── src/
│   ├── app/                    # Next.js App Router 页面
│   │   ├── (dashboard)/        # 仪表盘路由组
│   │   │   ├── page.tsx        # 仪表盘首页
│   │   │   ├── backtest/       # 回测页面
│   │   │   ├── portfolio/      # 组合管理页面
│   │   │   └── risk/           # 风控页面
│   │   ├── (research)/         # 研究路由组
│   │   │   ├── strategies/     # 策略研究
│   │   │   └── factors/        # 因子分析
│   │   ├── api/                # API 路由（可选，用于代理）
│   │   ├── layout.tsx          # 根布局
│   │   └── globals.css         # 全局样式
│   │
│   ├── components/             # React 组件
│   │   ├── ui/                 # shadcn/ui 基础组件
│   │   ├── charts/             # 图表组件
│   │   ├── dashboard/          # 仪表盘组件
│   │   ├── backtest/           # 回测组件
│   │   ├── portfolio/          # 组合组件
│   │   └── shared/             # 共享组件
│   │
│   ├── stores/                 # Zustand 状态管理
│   │   ├── useAuthStore.ts     # 认证状态
│   │   ├── usePortfolioStore.ts # 组合状态
│   │   ├── useBacktestStore.ts  # 回测状态
│   │   └── useRiskStore.ts     # 风控状态
│   │
│   ├── types/                  # TypeScript 类型
│   │   ├── api.ts              # API 响应类型
│   │   ├── models.ts           # 业务模型类型
│   │   └── charts.ts           # 图表配置类型
│   │
│   ├── lib/                    # 工具函数
│   │   ├── api.ts              # API 客户端
│   │   ├── utils.ts            # 通用工具
│   │   └── formatters.ts       # 格式化函数
│   │
│   └── hooks/                  # React Hooks
│       ├── useBacktest.ts      # 回测 Hook
│       ├── usePortfolio.ts     # 组合 Hook
│       └── useWebSocket.ts     # WebSocket Hook
│
├── public/                     # 静态资源
├── tests/                      # 前端测试
├── package.json
├── tsconfig.json
├── tailwind.config.js
├── next.config.js
└── README.md                   # 本文档
```

## 核心页面

### 1. 仪表盘（Dashboard）

**路由**: `/`

**功能**:
- 系统 Quick View（Regime 状态、持仓概况）
- 关键指标卡片（净值、回撤、夏普比率）
- 实时风险等级（Kill Switch 状态）
- 最近调仓计划
- 市场概览（主要指数、ETF 表现）

**组件**:
- `DashboardOverview` - 总览卡片
- `RegimeIndicator` - Regime 状态指示器
- `RiskLevelCard` - 风险等级卡片
- `RecentRebalances` - 最近调仓列表

### 2. 回测分析（Backtest）

**路由**: `/backtest`

**功能**:
- 回测参数配置（日期范围、策略参数）
- 回测结果展示
  - 净值曲线
  - 回撤曲线
  - 月度收益热力图
  - 交易信号分布
- 性能指标表格（收益、波动率、夏普、最大回撤等）
- 调仓历史记录

**组件**:
- `BacktestConfigForm` - 回测配置表单
- `BacktestResults` - 回测结果容器
- `EquityCurveChart` - 净值曲线图
- `DrawdownChart` - 回撤图
- `PerformanceMetrics` - 性能指标表格
- `TradeHistoryTable` - 交易历史表

### 3. 组合管理（Portfolio）

**路由**: `/portfolio`

**功能**:
- 当前组合状态（持仓、权重）
- 调仓计划详情（待执行订单）
- 历史调仓记录
- 持仓分析
  - 行业分布
  - 因子暴露
  - 集中度分析

**组件**:
- `PortfolioOverview` - 组合总览
- `HoldingsTable` - 持仓表格
- `RebalancePlanDetail` - 调仓计划详情
- `IndustryAllocation` - 行业配置图
- `FactorExposureChart` - 因子暴露图

### 4. 风险监控（Risk）

**路由**: `/risk`

**功能**:
- Kill Switch 状态监控
- 实时回撤监控
- 风险事件日志
- 风险指标趋势
- 仓位限制检查

**组件**:
- `KillSwitchStatus` - Kill Switch 状态
- `DrawdownMonitor` - 回撤监控
- `RiskEventLog` - 风险事件日志
- `RiskMetricsChart` - 风险指标趋势

### 5. 策略研究（Strategies）

**路由**: `/strategies`

**功能**:
- 策略列表
- 策略参数配置
- 策略对比分析
- 策略性能归因

**组件**:
- `StrategyList` - 策略列表
- `StrategyConfigForm` - 策略配置表单
- `StrategyComparison` - 策略对比

### 6. 因子分析（Factors）

**路由**: `/factors`

**功能**:
- 因子定义与配置
- 因子历史表现
- 因子相关性分析
- 因子有效性测试

**组件**:
- `FactorList` - 因子列表
- `FactorPerformanceChart` - 因子表现图
- `FactorCorrelationMatrix` - 因子相关性矩阵

## API 集成

### API 基础配置

```typescript
// lib/api.ts
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const apiClient = {
  backtest: {
    run: (params: BacktestParams) => fetch('/api/backtest', { method: 'POST', body: JSON.stringify(params) }),
    getResult: (id: string) => fetch(`/api/backtest/${id}`),
  },
  portfolio: {
    getCurrent: () => fetch('/api/portfolio/current'),
    getRebalancePlan: (id: string) => fetch(`/api/portfolio/rebalance/${id}`),
  },
  risk: {
    getStatus: () => fetch('/api/risk/status'),
    getEvents: () => fetch('/api/risk/events'),
  },
};
```

### 数据获取策略

- **TanStack Query**: 用于服务器状态管理
  - 自动缓存、重试、重新验证
  - 乐观更新
  - 分页、无限滚动支持

- **SWR**: 备选方案（更轻量）

### WebSocket 集成

用于实时数据推送（回测进度、市场行情、风险事件）：

```typescript
// hooks/useWebSocket.ts
export function useWebSocket(url: string) {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    ws.onmessage = (event) => setData(JSON.parse(event.data));
    setSocket(ws);
    return () => ws.close();
  }, [url]);

  return { socket, data };
}
```

## 开发路线图

### Phase 1: 基础框架搭建（规划中）

- [ ] 初始化 Next.js 项目
- [ ] 配置 TypeScript + ESLint + Prettier
- [ ] 集成 shadcn/ui + Tailwind CSS
- [ ] 配置 TanStack Query
- [ ] 创建基础布局和路由

### Phase 2: 核心页面开发（规划中）

- [ ] 仪表盘页面
- [ ] 回测分析页面
- [ ] 组合管理页面
- [ ] 风险监控页面

### Phase 3: 高级功能（规划中）

- [ ] 策略研究工具
- [ ] 因子分析工具
- [ ] 实时数据推送
- [ ] 导出报告（PDF/Excel）

### Phase 4: 优化与部署（规划中）

- [ ] 性能优化（代码分割、懒加载）
- [ ] 响应式设计（移动端适配）
- [ ] PWA 支持
- [ ] Docker 容器化
- [ ] CI/CD 集成

## 开发指南

### 环境要求

- Node.js 20+
- pnpm (推荐) 或 npm

### 本地开发

```bash
# 安装依赖
pnpm install

# 启动开发服务器
pnpm dev

# 访问 http://localhost:3000
```

### 代码规范

- **TypeScript**: 严格模式，所有类型必须明确定义
- **ESLint**: 使用 `@typescript-eslint` + `next`
- **Prettier**: 统一代码格式
- **Husky + lint-staged**: 提交前自动检查

### 测试

```bash
# 运行测试
pnpm test

# 运行 E2E 测试（Playwright）
pnpm test:e2e

# 生成覆盖率报告
pnpm test:coverage
```

### 构建

```bash
# 生产构建
pnpm build

# 预览生产构建
pnpm preview
```

## 相关文档

- **系统设计**: `docs/design/01_system_design.md`
- **引擎设计**: `docs/design/03_engine_design.md`
- **API 文档**: `apps/port/README.md`
- **风险宪法**: `docs/design/08_risk_constitution.md`

## 技术决策记录（ADR）

### ADR-001: 选择 Next.js 作为前端框架

**状态**: 提议中

**背景**: 需要为量化交易系统选择一个前端框架

**决策**: 选择 Next.js 15 + React 18

**原因**:
- React 生态成熟，图表库支持丰富
- App Router 提供现代化的路由方案
- SSR/SSG 可以改善首屏加载性能
- TypeScript 原生支持
- 强大的开发者工具

**后果**:
- 学习曲线较陡
- 构建时间可能较长

### ADR-002: 选择 Zustand 作为状态管理方案

**状态**: 提议中

**背景**: 需要全局状态管理方案

**决策**: 使用 Zustand

**原因**:
- 简单直观，API 设计优秀
- 无需 Context Provider 包裹
- 支持 TypeScript
- 包体积小（< 1KB）

**后果**:
- 需要配合 TanStack Query 管理服务器状态

## 开发注意事项

1. **类型安全**: 所有 API 响应必须有明确的 TypeScript 类型
2. **错误处理**: 统一的错误处理机制和用户提示
3. **加载状态**: 所有异步操作必须有加载状态指示
4. **响应式设计**: 支持桌面端（优先）和移动端
5. **性能优化**:
   - 使用 React.memo 避免不必要的重渲染
   - 使用 useMemo/useCallback 优化计算和回调
   - 图表数据使用虚拟化处理大数据集
6. **可访问性**: 遵循 WCAG 2.1 AA 标准

## 常见问题

### Q: 为什么不使用 Vue.js？

A: 项目团队更熟悉 React 生态，且 React 在金融图表库支持方面更成熟。

### Q: 为什么选择 shadcn/ui 而不是 Ant Design？

A: shadcn/ui 提供更现代的设计系统，完全可控，且与 Tailwind CSS 深度集成。

### Q: 如何处理实时数据？

A: 使用 WebSocket 推送关键更新（回测进度、市场行情），配合 TanStack Query 的自动重新验证。

### Q: 如何保证数据安全？

A:
- 所有 API 请求通过后端代理（不直接访问外部 API）
- 敏感数据不存储在前端
- 使用 HTTPS + CSRF 保护
- 实施内容安全策略（CSP）

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交变更 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 许可证

MIT License - 详见项目根目录 LICENSE 文件

---

**最后更新**: 2026-01-04
**维护者**: Ditto 开发团队
