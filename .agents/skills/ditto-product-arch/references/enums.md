# 枚举值与映射规则

> 定义 `$ditto-product-arch` 中使用的枚举值和映射规则。
> 这些是确定性约束——MUST 使用以下值，不得自定义。

---

## shellFamily（Shell 族）

页面所属的 Shell 布局族，决定页面级别的布局框架。

| 枚举值 | 说明 | 典型页面 |
|--------|------|---------|
| `command-center` | 全局指挥中心，信息密度最高 | Home |
| `analytical` | 分析型，主辅工作面并排 | Markets Overview, Research |
| `catalog` | 目录型，列表+详情分栏 | Screener, Scanner |
| `object-hub` | 对象中心，围绕单一实体展开 | Stock Detail, Strategy Detail |
| `studio` | 工作台型，构建/编辑为主 | Backtest Builder, Strategy Editor |
| `ops-console` | 运维控制台，队列+操作为主 | Order Management, Alert Console |
| `radar` | 雷达型，全景扫描 | Market Radar, Sector Map |

## pagePattern（页面模式）

页面级别的交互模式，决定组件布局和交互范式。

| 枚举值 | 说明 | 典型页面 |
|--------|------|---------|
| `global-command-center` | 全局仪表盘，多信息流汇聚 | Home |
| `analytical-overview` | 分析概览，图表+列表混合 | Markets, Research |
| `catalog-screener` | 筛选目录，条件输入+结果列表 | Screener, Scanner |
| `object-hub` | 实体详情，围绕单一对象 | Stock, Strategy, Portfolio |
| `studio-builder` | 构建工作台，拖拽+配置 | Backtest, Strategy Builder |
| `queue-ops-console` | 队列操作台，待处理+操作按钮 | Orders, Alerts |
| `ledger-execution-console` | 账本执行台，持仓+交易记录 | Trading, Execution |
| `config-integration-console` | 配置集成台，设置+连接管理 | Settings, Data Sources |

---

## 模块→Slot 映射规则

### 命名规范

| 层级 | 命名规则 | 示例 |
|------|---------|------|
| Shell 级区块 | 取自 `SHELL_SLOT_MAP`（预定义） | `sidebar`, `header`, `main` |
| 页面级区块 | kebab-case | `decision-banner`, `priority-queue`, `market-pulse` |

### 映射格式

```
模块名 → slot名
  shell 级区块标注 [slot]
  页面级区块标注 [subSlot]
```

### 映射完整性要求

- 每个核心模块 MUST 出现在映射表中
- Shell 级区块 MUST 对应 SHELL_SLOT_MAP 中的预定义 slot
- 页面级区块 MUST 使用 kebab-case
- 映射表是 `ditto-page-contract --create` 的直接输入

---

## 通用状态清单

来自 `04_interaction_state_spec.md`，UX Strategist MUST 将这些状态映射到每个数据组件：

| 状态 | 说明 |
|------|------|
| `default` | 正常展示，数据已加载 |
| `loading` | 首次加载或刷新中 |
| `empty` | 无数据 |
| `failed` | 加载失败或错误 |
| `stale` | 数据过期（超过 staleness 阈值） |
| `selected` | 用户选中状态 |
| `bulk` | 批量操作模式 |
| `running` | 异步操作执行中（如回测运行中） |
| `blocker` | 阻塞状态（如需等待前置条件） |

数据组件 MUST 至少定义 `loading` / `empty` / `failed` 三态。
