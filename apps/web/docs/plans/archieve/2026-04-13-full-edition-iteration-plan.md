# Full Edition Iteration Plan — Goal 10.0

> **目标**: 对全部 21 个 Prototype 页面执行 `/ditto-design-cycle --iterate --goal 10.0 --level best`，
> 达到 5 维度满分标准（克制度 / 一致性 / 高级感 / 品牌方向 / 信息效率各 10.0）。
>
> **基准日期**: 2026-04-13
> **执行方式**: 手动逐页执行，分 7 批递进

---

## 当前保真度基线

| 保真度 | 页面 | 说明 |
|--------|------|------|
| ~98-99% | home, platform | L2 几何完美，L3 差异 ~7.6% |
| ~85-90% | ai, trading-signals, trading-orders | 主要问题在微观样式 |
| ~50-75% | trading-risk, strategy-studio, trading, ai-copilot, instrument-hub | 布局偏差较大 |
| ~20-40% | markets, markets-screener, markets-intelligence, research-regime, ai-agents, research | 需要大幅修复 |

## 系统性障碍（Batch 0 前必须修复）

1. **StatusBar 架构** — 审计中两侧均未找到 status-bar 选择器
2. **StudioLayout 缺失 modes row** — strategy-studio 页面布局不完整
3. **Cross-market 错误布局** — markets 页面使用了错误的布局策略

---

## 执行命令清单

### Batch 0: 基础设施修复

```bash
# 修复 3 个系统性障碍（需先手动修复，再执行迭代）
# 1. StatusBar 选择器对齐
# 2. StudioLayout modes row 实现
# 3. Cross-market 布局策略修正

# 修复完成后运行验证
bun run check
```

### Batch 1: 标杆页（已高保真 → 先拉到满分）

> 已达 98-99% 保真度，作为后续页面的风格锚点。

```bash
# 1-1. Home 首页
/ditto-design-cycle prototype/page-home.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 1-2. Platform 平台管理
/ditto-design-cycle prototype/page-platform.html \
  --iterate --goal 10.0 --max-rounds 5 --level best
```

### Batch 2: 市场家族

> 共享跨市场布局模式。以 home/platform 为风格锚点。

```bash
# 2-1. Markets 跨市场总览
/ditto-design-cycle prototype/page-cross-market.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 2-2. Markets Screener 市场筛选
/ditto-design-cycle prototype/page-markets-screener.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 2-3. Markets Intelligence 市场情报
/ditto-design-cycle prototype/page-markets-intelligence.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 2-4. A-Shares A股总览
/ditto-design-cycle prototype/page-a-shares.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 2-5. Markets Calendar 事件日历
/ditto-design-cycle prototype/page-markets-calendar.html \
  --iterate --goal 10.0 --max-rounds 5 --level best
```

### Batch 3: 研究家族

> 包含 Strategy Studio 等复杂页面，依赖 StudioLayout 基础设施。

```bash
# 3-1. Research 研究
/ditto-design-cycle prototype/page-research.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 3-2. Regime Monitor
/ditto-design-cycle prototype/page-regime-monitor.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 3-3. Strategy Studio
/ditto-design-cycle prototype/page-strategy-studio.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 3-4. Backtest Result 回测结果
/ditto-design-cycle prototype/page-backtest-result.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 3-5. Factor Analysis 因子分析
/ditto-design-cycle prototype/page-factor-analysis.html \
  --iterate --goal 10.0 --max-rounds 5 --level best
```

### Batch 4: 交易家族

> 交易相关页面共享 session strip + 健康指标条布局模式。

```bash
# 4-1. Trading Overview 交易总览
/ditto-design-cycle prototype/page-trading-overview.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 4-2. Signals Inbox 信号收件箱
/ditto-design-cycle prototype/page-signals-inbox.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 4-3. Orders Ledger 订单台账
/ditto-design-cycle prototype/page-orders-ledger.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 4-4. Risk Center 风控中心
/ditto-design-cycle prototype/page-risk-center.html \
  --iterate --goal 10.0 --max-rounds 5 --level best
```

### Batch 5: AI 家族

> AI 页面包含 Copilot 聊天视图和 Agent 控制台，交互复杂度高。

```bash
# 5-1. AI Overview
/ditto-design-cycle prototype/page-ai-overview.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 5-2. AI Copilot
/ditto-design-cycle prototype/page-ai-copilot.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 5-3. Agent Console
/ditto-design-cycle prototype/page-agent-console.html \
  --iterate --goal 10.0 --max-rounds 5 --level best
```

### Batch 6: 详情页

> 标的详情和策略详情，Object Hub 布局模式。

```bash
# 6-1. Instrument Hub 标的详情
/ditto-design-cycle prototype/page-instrument-hub.html \
  --iterate --goal 10.0 --max-rounds 5 --level best

# 6-2. Strategies Detail 策略详情
/ditto-design-cycle prototype/page-strategies-detail.html \
  --iterate --goal 10.0 --max-rounds 5 --level best
```

### Batch 7: Edition 级验收

> 所有页面达标后，运行 Edition 级跨页一致性验收。

```bash
# Edition 级验收（所有页面 done 后执行）
/ditto-design-cycle --edition-review

# 如 Edition 验收通过，生成最终报告
/ditto-design-cycle --edition-review --edition v1
```

---

## 每页执行前检查

在每个 Batch 开始前，确认：

1. **前一批所有页面已达标** — `git tag -l 'review/<task>/done'` 存在
2. **跨页一致性基线** — 从 manifest 获取最新完成的页面作为风格锚点
3. **基础设施状态** — `bun run check` 通过

## 每页执行后验证

每页达标后，确认：

1. **5 维度评分 ≥ 10.0**（或接近满分的实际最高分）
2. **P0 = 0** — 无阻断性问题
3. **VP-STANDARD 完整性** — 1536x1080 无截断
4. **VP-COMPACT 完整性** — 1366x768 无布局破坏
5. **git tag 已创建** — `review/<task>/done`

## 预期产出

- 21 个 `review/<task>/done` git tag
- 每页的审查报告在 `docs/reviews/`
- Edition manifest 更新为 `reviewed` 状态
- Edition 级验收报告

## 风险与降级

| 风险 | 缓解策略 |
|------|---------|
| goal 10.0 不可达（理论上限 < 10.0） | 如 5 轮后最高达 9.5+，视为达标 |
| 系统性障碍修复引入回归 | Batch 0 后必须 `bun run check` |
| 低保真页面需要过多轮次 | 启用突破机制（iterate.md §突破协议） |
| 跨页不一致累积 | Edition Review 阶段统一修正 |
