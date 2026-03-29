/* ─────────────────────────────────────────────
 * Ditto Mock Data — Home Command Center
 * Realistic quant platform mock data for prototype rendering
 * ───────────────────────────────────────────── */

const DittoMock = {
  // ── Today Pulse Strip ──
  todayPulse: {
    date: '2026-03-28',
    session: 'US Pre-Market',
    pendingActions: 7,
    criticalAlerts: 2,
    runningJobs: 3,
    pnlToday: '+$12,847.30',
    pnlPercent: '+0.34%',
  },

  // ── Decision Banner Metrics ──
  decisionBanner: {
    totalEquity: '$3,782,456.12',
    dailyPnl: '+$12,847.30',
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
      title: 'AAPL Sell Signal — RSI Divergence + Volume Spike',
      meta: 'Strategy: Momentum Alpha v3 · Confidence: 87%',
      time: '3m ago',
      badge: { type: 'signal', label: 'Signal' },
    },
    {
      id: 2,
      priority: 'critical',
      title: 'Risk Limit Warning — Sector Concentration > 35%',
      meta: 'Technology sector at 37.2% · Limit: 35%',
      time: '12m ago',
      badge: { type: 'risk', label: 'Risk' },
    },
    {
      id: 3,
      priority: 'high',
      title: 'Agent Finding — Unusual Options Flow on NVDA',
      meta: 'Agent: Market Scanner · 4x normal volume on $450 calls',
      time: '18m ago',
      badge: { type: 'agent', label: 'Agent' },
    },
    {
      id: 4,
      priority: 'high',
      title: 'Order Review — TSLA Limit Buy $242.50',
      meta: 'Submitted by Strategy: Mean Revert v2 · Qty: 200',
      time: '25m ago',
      badge: { type: 'signal', label: 'Order' },
    },
    {
      id: 5,
      priority: 'medium',
      title: 'Data Quality — SPY 1-min bar gap detected',
      meta: 'Provider: Polygon · Missing 14:32-14:33 · Auto-fill pending',
      time: '42m ago',
      badge: { type: 'data', label: 'Data' },
    },
    {
      id: 6,
      priority: 'medium',
      title: 'Backtest Complete — Value Factor Q1 2026',
      meta: 'Sharpe: 1.42 · Max DD: -8.3% · 1,247 trades',
      time: '1h ago',
      badge: { type: 'agent', label: 'Result' },
    },
    {
      id: 7,
      priority: 'low',
      title: 'Pipeline Health — Alpha Vantage rate limit approaching',
      meta: '4,820 / 5,000 requests today · Resets in 3h',
      time: '2h ago',
      badge: { type: 'system', label: 'System' },
    },
  ],

  // ── Market Snapshot ──
  marketSnapshot: [
    { name: 'S&P 500', price: '5,432.18', change: '+0.82%', dir: 'up' },
    { name: 'NASDAQ', price: '17,234.56', change: '+1.12%', dir: 'up' },
    { name: 'Russell 2000', price: '2,087.43', change: '-0.23%', dir: 'down' },
    { name: 'VIX', price: '14.82', change: '-3.14%', dir: 'down' },
    { name: '10Y Treasury', price: '4.28%', change: '+0.02', dir: 'up' },
    { name: 'DXY', price: '104.32', change: '-0.15%', dir: 'down' },
  ],

  // ── Global Alerts ──
  globalAlerts: [
    {
      id: 1,
      severity: 'critical',
      title: 'Portfolio VaR breach at 95% — $142K vs limit $125K',
      desc: 'Triggered by AAPL concentration + market volatility spike',
      time: '8m ago',
    },
    {
      id: 2,
      severity: 'critical',
      title: 'Broker connection lost — Interactive Brokers',
      desc: 'Auto-reconnect in progress · Last heartbeat: 3m ago',
      time: '15m ago',
    },
    {
      id: 3,
      severity: 'warning',
      title: 'Model drift detected — Sentiment Alpha v2',
      desc: 'Prediction accuracy dropped to 52% (threshold: 55%)',
      time: '1h ago',
    },
    {
      id: 4,
      severity: 'info',
      title: 'Data pipeline delay — SEC filings feed',
      desc: 'Estimated 15min delay · ETL job running',
      time: '2h ago',
    },
  ],

  // ── Recent Signals ──
  recentSignals: [
    { ticker: 'AAPL', action: 'SELL', strategy: 'Momentum Alpha v3', confidence: '87%', time: '3m ago' },
    { ticker: 'MSFT', action: 'BUY', strategy: 'Mean Revert v2', confidence: '72%', time: '28m ago' },
    { ticker: 'GOOGL', action: 'HOLD', strategy: 'Regime Filter', confidence: '91%', time: '1h ago' },
    { ticker: 'AMZN', action: 'SELL', strategy: 'Momentum Alpha v3', confidence: '68%', time: '2h ago' },
    { ticker: 'NVDA', action: 'BUY', strategy: 'Breakout v1', confidence: '79%', time: '3h ago' },
  ],

  // ── Recent Agent Runs ──
  recentRuns: [
    { agent: 'Market Scanner', task: 'Options flow analysis', status: 'completed', findings: 3, time: '18m ago' },
    { agent: 'Earnings Watch', task: 'Q1 earnings prep scan', status: 'running', findings: 0, time: '45m ago' },
    { agent: 'Risk Monitor', task: 'Intraday VaR check', status: 'completed', findings: 1, time: '1h ago' },
  ],

  // ── Agent Findings ──
  agentFindings: [
    { text: 'NVDA $450 calls volume 4x normal — potential institutional positioning ahead of earnings', source: 'Market Scanner · 18m ago', icon: 'insight' },
    { text: 'Correlation between AAPL and QQQ shifted from 0.82 → 0.65 in last 5 days — regime change signal', source: 'Risk Monitor · 1h ago', icon: 'warning' },
    { text: '3 new stocks added to Whale Watch list based on 13F filing analysis', source: 'Market Scanner · 2h ago', icon: 'info' },
  ],

  // ── Data Health ──
  dataHealth: [
    { label: 'Price Feeds', status: 'ok', statusText: 'Healthy', dotClass: 'healthy' },
    { label: 'Options Chain', status: 'ok', statusText: 'Healthy', dotClass: 'healthy' },
    { label: 'SEC Filings', status: 'warning', statusText: 'Delayed', dotClass: 'degraded' },
    { label: 'News Feed', status: 'ok', statusText: 'Healthy', dotClass: 'healthy' },
    { label: 'Fundamentals', status: 'ok', statusText: 'Fresh (1d)', dotClass: 'healthy' },
    { label: 'Alt Data', status: 'warning', statusText: 'Stale (3d)', dotClass: 'degraded' },
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
