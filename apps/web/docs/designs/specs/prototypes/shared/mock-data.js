/* ─────────────────────────────────────────────
 * Ditto Mock Data — Home Command Center
 * Realistic quant platform mock data for prototype rendering
 * ───────────────────────────────────────────── */

const DittoMock = {
  // ── Today Pulse Strip ──
  todayPulse: {
    date: '2026-03-28',
    session: 'A股 盘中',
    pendingActions: 7,
    criticalAlerts: 2,
    runningJobs: 3,
    pnlToday: '+¥84,230.50',
    pnlPercent: '+0.34%',
  },

  // ── Decision Banner Metrics ──
  decisionBanner: {
    totalEquity: '¥24,678,912.80',
    dailyPnl: '+¥84,230.50',
    dailyPnlPercent: '+0.34%',
    riskUtilization: '68.2%',
    marketRegime: 'Risk-On / Bullish',
    regimeType: 'bull',
    suggestion: '3 signals pending review',
  },

  // ── Pending / Next Actions ──
  pendingActions: [
    {
      id: 1,
      priority: 'critical',
      title: '600519.SH 贵州茅台 卖出信号 — RSI 背离 + 放量',
      meta: '策略: Momentum Alpha v3 · 置信度: 87%',
      time: '3m ago',
      badge: { type: 'signal', label: 'Signal' },
    },
    {
      id: 2,
      priority: 'critical',
      title: '风险限额预警 — 行业集中度 > 35%',
      meta: '白酒板块占比 37.2% · 限额: 35%',
      time: '12m ago',
      badge: { type: 'risk', label: 'Risk' },
    },
    {
      id: 3,
      priority: 'high',
      title: 'Agent 发现 — 300750.SZ 宁德时代 异常期权流',
      meta: 'Agent: Market Scanner · 认购期权成交量 4x 正常水平',
      time: '18m ago',
      badge: { type: 'agent', label: 'Agent' },
    },
    {
      id: 4,
      priority: 'high',
      title: '订单审核 — 000858.SZ 五粮液 限价买入 ¥168.50',
      meta: '提交策略: Mean Revert v2 · 数量: 500',
      time: '25m ago',
      badge: { type: 'signal', label: 'Order' },
    },
    {
      id: 5,
      priority: 'medium',
      title: '数据质量 — 510300.SH 1分钟K线缺口',
      meta: '供应商: Wind · 缺失 14:32-14:33 · 自动补全中',
      time: '42m ago',
      badge: { type: 'data', label: 'Data' },
    },
    {
      id: 6,
      priority: 'medium',
      title: '回测完成 — 价值因子 Q1 2026',
      meta: 'Sharpe: 1.42 · 最大回撤: -8.3% · 1,247 笔交易',
      time: '1h ago',
      badge: { type: 'agent', label: 'Result' },
    },
    {
      id: 7,
      priority: 'low',
      title: 'Pipeline 健康 — Wind API 请求量接近限额',
      meta: '今日 4,820 / 5,000 次请求 · 3小时后重置',
      time: '2h ago',
      badge: { type: 'system', label: 'System' },
    },
  ],

  // ── Market Snapshot ──
  marketSnapshot: [
    { name: '上证指数', price: '3,342.18', change: '+0.82%', dir: 'up' },
    { name: '深证成指', price: '10,892.56', change: '+1.12%', dir: 'up' },
    { name: '创业板指', price: '2,187.43', change: '-0.23%', dir: 'down' },
    { name: '中国波指 iVIX', price: '18.82', change: '-3.14%', dir: 'down' },
    { name: '10Y国债', price: '1.78%', change: '+0.02', dir: 'up' },
    { name: '北向资金', price: '+32.4亿', change: '+18.6亿', dir: 'up' },
  ],

  // ── Global Alerts ──
  globalAlerts: [
    {
      id: 1,
      severity: 'critical',
      title: '组合 VaR 突破 95% 分位 — ¥928K vs 限额 ¥800K',
      desc: '由贵州茅台集中持仓 + 市场波动率急升触发',
      time: '8m ago',
    },
    {
      id: 2,
      severity: 'critical',
      title: '券商连接中断 — 中信证券',
      desc: '自动重连中 · 最后心跳: 3分钟前',
      time: '15m ago',
    },
    {
      id: 3,
      severity: 'warning',
      title: '模型漂移检测 — Sentiment Alpha v2',
      desc: '预测准确率降至 52%（阈值: 55%）',
      time: '1h ago',
    },
    {
      id: 4,
      severity: 'info',
      title: '数据管道延迟 — 公告数据源',
      desc: '预计延迟 15 分钟 · ETL 任务运行中',
      time: '2h ago',
    },
  ],

  // ── Recent Signals ──
  recentSignals: [
    { ticker: '600519.SH', action: '卖出', strategy: 'Momentum Alpha v3', confidence: '87%', time: '3m ago' },
    { ticker: '000858.SZ', action: '买入', strategy: 'Mean Revert v2', confidence: '72%', time: '28m ago' },
    { ticker: '601318.SH', action: '持有', strategy: 'Regime Filter', confidence: '91%', time: '1h ago' },
    { ticker: '300750.SZ', action: '卖出', strategy: 'Momentum Alpha v3', confidence: '68%', time: '2h ago' },
    { ticker: '002594.SZ', action: '买入', strategy: 'Breakout v1', confidence: '79%', time: '3h ago' },
  ],

  // ── Recent Agent Runs ──
  recentRuns: [
    { agent: 'Market Scanner', task: 'Options flow analysis', status: 'completed', findings: 3, time: '18m ago' },
    { agent: 'Earnings Watch', task: 'Q1 earnings prep scan', status: 'running', findings: 0, time: '45m ago' },
    { agent: 'Risk Monitor', task: 'Intraday VaR check', status: 'completed', findings: 1, time: '1h ago' },
  ],

  // ── Agent Findings ──
  agentFindings: [
    { text: '300750.SZ 宁德时代认购期权成交量达正常水平 4 倍 — 疑似机构提前布局', source: 'Market Scanner · 18m ago', icon: 'insight' },
    { text: '贵州茅台与沪深300相关性从 0.82 降至 0.65（近5日）— 可能的 regime 切换信号', source: 'Risk Monitor · 1h ago', icon: 'warning' },
    { text: '基于龙虎榜数据分析，3 只新股票加入大资金监控列表', source: 'Market Scanner · 2h ago', icon: 'info' },
  ],

  // ── Data Health ──
  dataHealth: [
    { label: '行情数据', status: 'ok', statusText: 'Healthy', dotClass: 'healthy' },
    { label: '期权链', status: 'ok', statusText: 'Healthy', dotClass: 'healthy' },
    { label: '公告数据', status: 'warning', statusText: 'Delayed', dotClass: 'degraded' },
    { label: '新闻数据', status: 'ok', statusText: 'Healthy', dotClass: 'healthy' },
    { label: '基本面', status: 'ok', statusText: 'Fresh (1d)', dotClass: 'healthy' },
    { label: '另类数据', status: 'warning', statusText: 'Stale (3d)', dotClass: 'degraded' },
  ],

  // ── Workspace Shortcuts ──
  workspaceShortcuts: [
    { label: 'Markets Screener', icon: 'search', kbd: '⌘1' },
    { label: 'Strategy Studio', icon: 'code', kbd: '⌘2' },
    { label: 'Signal Inbox', icon: 'inbox', kbd: '⌘3' },
    { label: 'Risk Center', icon: 'shield', kbd: '⌘4' },
    { label: 'AI Copilot', icon: 'sparkles', kbd: '⌘5' },
    { label: 'Data Quality', icon: 'database', kbd: '⌘6' },
  ],
};
