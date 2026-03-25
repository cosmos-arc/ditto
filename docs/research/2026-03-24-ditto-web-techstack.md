# Ditto 前端技术选型清单 — 冻结版

> 基于 [2026-03-24-ditto-web-product-design.md](../research/2026-03-24-ditto-web-product-design.md) 产品设计方案，经评估后冻结的技术选型。
> 决策日期：2026-03-24

---

## 1. 开发环境

### 1.1 主环境

| 项 | 选型 | 说明 |
|----|------|------|
| 操作系统 | Windows 11 + WSL2 Ubuntu | 所有前端和 Python 命令在 WSL 内执行 |
| 编辑器 | VS Code / Cursor | 通过 Remote-WSL 扩展连接 |

### 1.2 前端工具链

| 项 | 选型 | 版本 | 说明 |
|----|------|------|------|
| 包管理 & 运行时 | **Bun** | 1.3.x | 包管理器、workspace 管理、脚本执行统一入口 |
| 框架 | **React** | 19.x | 含 React Compiler |
| 编译优化 | **React Compiler** | stable | 通过 babel-plugin-react-compiler 接入，需显式加回 Babel 依赖 |
| 构建工具 | **Vite** | 8.x | 默认 bundler 为 Rolldown（Rust 实现） |
| 样式 | **Tailwind CSS** | 4.x | CSS-first 配置（@theme 指令），零配置开箱即用 |
| UI 组件 | **shadcn/ui** | CLI v4 | 设计系统基础，代码复制到项目，完全控制 |
| Lint & Format | **Biome** | 2.x | 替代 ESLint + Prettier，内置 423+ lint 规则 |
| 路由 | **TanStack Router** | 1.x | 类型安全路由，URL 作为状态源 |
| 服务端状态 | **TanStack Query** | 5.x | 缓存、轮询、乐观更新 |
| 客户端状态 | **Zustand** | 5.x | 轻量全局状态（~3KB） |
| 表单 | **React Hook Form** | 7.x | + Zod 联动校验 |
| 表格 | **AG Grid Community** | 35.x | Community-only，Enterprise 能力由自研替代（DittoGrid） |
| K 线图表 | **Lightweight Charts** | 4.x | TradingView 官方，K 线专用 |
| 通用图表 | **ECharts** | 5.x | 热力图、散点图、多线图等 |
| 单元测试 | **Vitest** | 3.x | 与 Vite 原生集成 |
| E2E 测试 | **Playwright** | 1.58+ | 跨浏览器覆盖 |

### 1.3 React Compiler 接入方式

Vite 8 的 `@vitejs/plugin-react` 已切换到 Oxc，Babel 不再是默认依赖。React Compiler 当前依赖 `babel-plugin-react-compiler`，接入方式：

```
@vitejs/plugin-react → babel mode → babel-plugin-react-compiler
```

**已知限制**：
- 需显式加回 Babel 依赖（`@babel/core`、`@vitejs/plugin-react` 的 babel 选项）
- sourcemap 存在已知兼容问题，需手动配置 `sourcemap: true` 和 `hmr: { overlay: false }`
- 等 Oxc 原生支持 Compiler（`oxc_transform`）成熟后，迁移到 Oxc 路径可移除 Babel 依赖

**Compiler 的收益范围**：自动优化 `useMemo` / `useCallback` / `useMemo`，减少手写 memo。高频渲染组件（K 线、分时、盘口）不在此范围内（见第 4 节）。

---

## 2. 生产环境

### 2.1 部署拓扑

```
app.yourdomain.com    → Cloudflare Pages（SPA 静态托管）
api.yourdomain.com    → FastAPI（REST API）
wss://api.yourdomain.com/ws → FastAPI（WebSocket）
```

### 2.2 前端托管

| 项 | 选型 | 说明 |
|----|------|------|
| SPA 托管 | **Cloudflare Pages** | 静态资源 CDN 分发，全球边缘节点 |
| DNS 路由 | Cloudflare Proxy | 自动 HTTPS、DDoS 防护 |
| 源站暴露 | **Cloudflare Tunnel**（按需） | 源站无公网 IP 时启用，outbound-only 连接 |

### 2.3 后端服务

| 项 | 选型 | 说明 |
|----|------|------|
| API 框架 | **FastAPI** | REST API + WebSocket |
| 部署方式 | Docker → Linux 主机 | GitHub Actions 构建镜像并部署 |

### 2.4 跨域策略

前端（`app.domain.com`）调用后端（`api.domain.com`）存在跨域。FastAPI 端需配置 CORS middleware，允许 Pages 域名的请求。Cloudflare Pages preview 环境需正确指向 API 源。

### 2.5 明确不做

- **不把生产前端入口放在 FastAPI StaticFiles** — Starlette 的 StaticFiles 适合本地开发和兜底，不适合长期生产入口
- **不做 SSR / RSC 主线** — SPA 模式满足一期需求，研究工具型产品无 SEO 需求

---

## 3. Grid 方案

> **ADR：Ditto 表格层只采用 AG Grid Community。所有 Enterprise 专属能力原则上不在前端网格内复刻，而是通过 FastAPI 分析接口、外围面板、详情页和导出服务实现。**

### 3.1 选型

**AG Grid v35.x Community 版。不采购 Enterprise 许可证。**

AG Grid Community 免费可商用，覆盖量化系统全部基础表格需求。Enterprise 专属能力（Row Grouping、Pivoting、Excel Export、SSRM、Cell Selection、Master/Detail、Tree Data）不通过购买授权获取，而是通过 FastAPI 分析接口、外围面板、详情页和导出服务实现。

| 能力 | Community | 自研替代方案 |
|------|-----------|-------------|
| 排序 / 筛选 / 分页 | ✅ | — |
| 自定义单元格渲染 | ✅ | — |
| 行选择 / 虚拟滚动 | ✅ | — |
| Infinite Row Model | ✅ | — |
| CSV 导出 | ✅ | — |
| 多列排序 | ❌ | 服务端排序下推 |
| Row Grouping / Pivot | ❌ | 服务端聚合 + 平铺结果表 |
| Server-Side Row Model | ❌ | Infinite Row Model + FastAPI 分页 |
| Excel Export | ❌ | 前端 CSV 快导 + 后端 XLSX 正式导出 |
| Master/Detail / Tree Data | ❌ | Drawer / Split Pane / 详情页 |
| Cell Selection / Range | ❌ | 不做（非量化系统核心交互） |

### 3.2 架构原则

**原则一：Grid 只负责强展示，不负责重分析。**

网格的职责是展示、编辑、筛选、排序、虚拟滚动。分组、聚合、透视等分析能力优先放到服务端和外围 UI，不硬塞进 Grid 内核。

**原则二：分析能力尽量服务端化。**

用户选择"按行业分组 / 按因子分桶 / 按日期聚合 / 做横截面透视"后，前端调用分析 API，后端用 DuckDB/Polars 计算并返回已聚合的二维表，再交给 Community Grid 展示。用户看到的仍然是可排序、可过滤、可滚动的结果，但不在 Grid 内部动态做 grouping/pivot。

**原则三：层级结构尽量用页面布局表达，不用网格原生树。**

行点击后在右侧 Drawer、底部 Split Pane 或独立详情页展示该策略 / 持仓 / 标的 / 回测任务的详情。让 Grid 做入口、详情页做承载，比 Master/Detail 更清晰，也更容易和图表、日志、参数说明组合。

**原则四：导出分成 CSV 快导出和后端 XLSX 正式导出。**

Grid 负责"把当前视图导成 CSV"（Community 原生支持）；FastAPI 负责"把完整分析结果导成真正的 Excel 文件"（后端 openpyxl / xlsxwriter 生成）。既不买 Enterprise，也不会被 CSV 限死。

**原则五：Infinite Row Model 是大数据主力。**

Community 不支持 Server-Side Row Model，但 Infinite Row Model 可实现分块加载。前端将 `startRow / endRow / sortModel / filterModel` 传给后端，后端用 DuckDB/Polars 做区间分页、排序、过滤下推。

### 3.3 DittoGrid 封装层

不在页面中直接使用 `<AgGridReact />`，统一通过 DittoGrid 封装层：

```
DittoGrid
├── 默认列定义（数值/百分比/时间格式化）
├── Infinite Row Model 适配（与 FastAPI 分页接口对接）
├── 排序/筛选下推协议（sortModel / filterModel → FastAPI query params）
├── 筛选状态持久化（localStorage / URL params）
├── 列状态保存/恢复（列顺序、宽度、排序、可见性）
├── CSV 快导出（Grid 当前视图 → CSV 下载）
├── XLSX 导出触发（调用后端导出 API → 下载文件）
├── 主题（暗色/亮色模式）
└── 权限开关（列级可见性控制）
```

### 3.4 页面级能力分类

| 页面 | Community 直接支持 | 需要自研替代 |
|------|-------------------|-------------|
| 持仓 / 委托 / 成交 | ✅ 排序、筛选、分页、行选择 | — |
| 任务 / 告警 / 日志 | ✅ 排序、筛选、分页、行选择 | — |
| 因子横截面 | ✅ 平铺展示 | 服务端聚合后返回平铺表 |
| 回测结果明细 | ✅ 平铺展示 | 服务端聚合后返回平铺表 |
| 选股结果表 | ✅ 平铺展示 | 服务端分组聚合 |
| 行业轮动打分表 | ✅ 平铺展示 | 服务端分组聚合 |
| 研究分析台 | ✅ 结果表展示 | 左侧参数面板 + 中间结果表 + 右侧图表/说明 |

> **产品设计定位**：Ditto 前端偏"分析系统"，而非"浏览器内 Excel / BI 工具"。

---

## 4. 高频数据渲染策略

### 4.1 核心原则

**高频流默认绕开 React 渲染链。**

React Compiler 会帮助普通组件减少手写 memo，但它不是高频行情渲染架构的替代品。

### 4.2 渲染分工

| 层 | 负责 | 技术 |
|----|------|------|
| React | 外层布局、面板容器、筛选条件、低频 UI 状态 | React + Zustand + TanStack Query |
| 图表实例 | K 线更新、分时走势、盘口深度 | Lightweight Charts / ECharts imperative API |
| Store Subscription | 成交推送、日志流、实时 P&L | Zustand subscribe / WebSocket direct push |

### 4.3 实现模式

```typescript
// ❌ 不做：高频数据通过 React state 驱动重渲染
const [ticks, setTicks] = useState<Tick[]>([]);

// ✅ 正确：高频数据直接推送到图表实例
const chartRef = useRef<IChartApi>(null);
useEffect(() => {
  const unsub = ws.subscribe('ticks', (tick) => {
    chartRef.current?.update(tick); // imperative update
  });
  return unsub;
}, []);
```

React 只在以下场景参与渲染：面板布局变化、筛选条件切换、时间区间调整、低频统计更新。

---

## 5. CI/CD 与发布

### 5.1 前端发布链路

```
GitHub Push → Cloudflare Pages 自动构建 → CDN 分发
```

- Git integration 触发自动构建
- Preview deployments（PR 自动预览环境）
- Rollbacks（一键回滚到任意历史版本）

### 5.2 后端发布链路

```
GitHub Push → GitHub Actions → Docker Build → 部署到 Linux Docker 主机
```

### 5.3 发布策略

- **前后端版本独立发布**，不捆绑
- 前端样式、页面逻辑、小功能的发布不需要碰后端镜像
- API 契约通过 OpenAPI spec 管理，Breaking changes 需版本化

---

## 6. 冻结清单

### 6.1 确定使用

| 技术 | 版本 | 角色 |
|------|------|------|
| Bun | 1.3.x | 包管理 & 运行时 |
| React | 19.x | UI 框架 |
| React Compiler | stable | 编译优化（Babel 接入） |
| Vite | 8.x | 构建工具（Rolldown bundler） |
| Tailwind CSS | 4.x | 样式系统（CSS-first） |
| shadcn/ui | CLI v4 | 设计系统基础 |
| Biome | 2.x | Lint + Format |
| TanStack Router | 1.x | 类型安全路由 |
| TanStack Query | 5.x | 服务端状态管理 |
| Zustand | 5.x | 客户端状态管理 |
| React Hook Form + Zod | 7.x + 3.x | 表单 + 校验 |
| AG Grid Community | 35.x | 数据表格（Community-only，Enterprise 能力自研替代） |
| Lightweight Charts | 4.x | K 线图表 |
| ECharts | 5.x | 通用图表 |
| Vitest | 3.x | 单元测试 |
| Playwright | 1.58+ | E2E 测试 |
| FastAPI | — | 后端 API + WebSocket |
| Cloudflare Pages | — | SPA 托管 |
| Cloudflare Tunnel | — | 源站无公网 IP 时启用 |

### 6.2 明确不做

| ❌ 不做 | 原因 |
|---------|------|
| Next.js | SPA 模式满足需求，无 SSR/SEO 必要性 |
| SSR / RSC 主线 | 研究工具型产品，无 SEO 需求 |
| D3.js | ECharts + Lightweight Charts 已覆盖全部图表需求 |
| 生产前端入口放在 FastAPI StaticFiles | 不适合长期生产入口 |
| 先上轻量 table 再迁 Grid | 直接 AG Grid，避免二次迁移 |
| React 直接承担高频流重绘 | 架构原则：高频流绕开 React 渲染链 |
| 前后端发布绑定 | 独立发布，降低耦合 |
| pandas / pip / poetry / conda | 项目规范已冻结（polars / pixi） |

---

## 7. 备注

### 7.1 Bun 的长期维护

Anthropic 已收购 Bun 团队（2026 年）。开源许可证和社区不受影响，长期维护有保障。

### 7.2 React Compiler 迁移路径

当前通过 Babel 接入 React Compiler。待 Oxc 原生支持 Compiler（`oxc_transform`）成熟后，可迁移到 Oxc 路径，移除 Babel 依赖，进一步缩短构建时间。

### 7.3 与产品设计方案的差异

相比 [产品设计文档](../research/2026-03-24-ditto-web-product-design.md) 中提到的 `Next.js 15 + React 18`：

| 原方案 | 冻结方案 | 变更原因 |
|--------|---------|----------|
| Next.js 15 | Vite 8 (SPA) | 无 SSR 需求，Cloudflare Pages 更适合 |
| React 18 | React 19 + Compiler | 更好的自动优化 |
| pnpm | Bun | 更快的安装速度和 workspace 管理 |
| Recharts | ECharts | 更丰富的图表类型（热力图等） |
| D3.js | 排除 | ECharts + Lightweight Charts 已覆盖 |
| ESLint + Prettier | Biome | 统一工具链，更快 |
| TanStack Table | AG Grid Community | Community-only，Enterprise 能力由自研替代 |
