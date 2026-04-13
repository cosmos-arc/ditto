export const PROTOTYPE_NORMALIZE_CSS = `
  .proto-nav { display: none !important; }
  #default-view {
    height: 100vh !important;
    min-height: 100vh !important;
    overflow: hidden !important;
  }
  #default-view > [class*="shell"],
  #default-view > .ai-shell,
  #default-view > .intel-shell,
  #default-view > .risk-shell {
    height: 100vh !important;
    min-height: 0 !important;
    flex: 0 0 auto !important;
  }
  #default-view > .status-bar {
    height: 24px !important;
    flex: 0 0 auto !important;
  }
`;

/* ── React selectors using data-slot (stable across DOM changes) ── */

const REACT_APP_TARGETS = {
	shell: "#root > div",
	rail: "nav[aria-label='主导航']",
	header: "header",
	content: "#root > div > div:nth-child(3)",
	layout: "#root > div > div:nth-child(3) > div",
	status: "[data-slot='status-bar']",
};

const COMMAND_CENTER_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	strip: "[data-slot='pulse-strip']",
	main: "[data-slot='main']",
	sidebar: "[data-slot='sidebar-rail']",
	statusSlot: "[data-slot='status']",
};

const ANALYTICAL_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	strip: "[data-slot='strip']",
	banner: "[data-slot='banner']",
	main: "[data-slot='main']",
	activity: "[data-slot='activity']",
	analysis: "[data-slot='analysis']",
};

const RADAR_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	contextBar: "[data-slot='context-bar']",
	scopeStrip: "[data-slot='scope-strip']",
	main: "[data-slot='main']",
	rightRail: "[data-slot='right-rail']",
};

const CATALOG_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	toolbar: "[data-slot='toolbar']",
	main: "[data-slot='main']",
	detail: "[data-slot='detail']",
	filter: "[data-slot='filter-toolbar']",
};

const OPS_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	health: "[data-slot='health']",
	main: "[data-slot='main']",
	detail: "[data-slot='detail']",
};

const STUDIO_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	source: "[data-slot='source']",
	main: "[data-slot='main']",
	inspector: "[data-slot='inspector']",
	logs: "[data-slot='logs']",
};

const OBJECT_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	meta: "[data-slot='meta']",
	tabs: "[data-slot='tabs']",
	main: "[data-slot='main']",
	bottom: "[data-slot='bottom']",
};

/* ── Prototype selectors (CSS class-based from HTML files) ── */

const PROTOTYPE_APP_TARGETS = {
	rail: ".shell-rail",
	header: ".shell-header, .studio-header, .object-header",
	status: ".status-bar",
};

/* ── Page configs ── */

export const VISUAL_AUDIT_PAGES = [
	{
		route: "/",
		name: "home",
		prototype: "page-home.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-home",
			strip: ".shell-pulse",
			main: ".shell-main",
			sidebar: ".shell-sidebar",
			decision: ".decision-banner",
			queue: ".panel-grow",
			secondary: ".shell-secondary",
		},
		reactTargets: {
			shell: "#root > div",
			rail: "nav[aria-label='主导航']",
			header: "header",
			status: "[data-slot='status-bar']",
			strip: "[data-slot='pulse-strip']",
			main: "[data-slot='main']",
			sidebar: "[data-slot='sidebar-rail']",
			decision: "[data-slot='decision-banner']",
			queue: "[data-testid='priority-queue']",
			secondary: "[data-slot='home-secondary']",
		},
	},
	{
		route: "/trading",
		name: "trading",
		prototype: "page-trading-overview.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-analytical.trading-variant",
			strip: ".scope-strip",
			main: ".main-grid, .trading-main",
			session: ".scope-phase",
			positions: ".panel-positions, .positions-panel",
			orders: ".orders-panel, .panel-orders",
		},
		reactTargets: {
			...ANALYTICAL_REACT_TARGETS,
			positions: "[data-slot='positions-summary']",
			orders: "[data-slot='data-table']",
		},
	},
	{
		route: "/platform",
		name: "platform",
		prototype: "page-platform.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-ops",
			health: ".ops-health",
			main: ".ops-main",
			detail: ".ops-detail",
			pipeline: ".pipeline-table, .ops-table",
		},
		reactTargets: OPS_REACT_TARGETS,
	},
	{
		route: "/ai",
		name: "ai",
		prototype: "page-ai-overview.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".ai-shell",
			strip: ".ai-pulse",
			main: ".ai-main",
			queue: ".queue-panel, .agent-queue",
			inspector: ".ai-inspector, .inspector-panel",
		},
		reactTargets: COMMAND_CENTER_REACT_TARGETS,
	},
	{
		route: "/markets",
		name: "markets",
		prototype: "page-cross-market.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-radar",
			body: ".shell-body",
			context: ".context-bar",
			strip: ".scope-strip",
			main: ".radar-main, .main-grid",
			matrix: ".market-matrix, .cross-market-matrix",
		},
		reactTargets: {
			...RADAR_REACT_TARGETS,
			matrix: "[data-slot='cross-market-matrix']",
		},
	},
	{
		route: "/research",
		name: "research",
		prototype: "page-research.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-analytical",
			strip: ".scope-strip",
			main: ".main-grid, .research-main",
			analysis: ".analysis-band",
		},
		reactTargets: ANALYTICAL_REACT_TARGETS,
	},
	{
		route: "/trading/signals",
		name: "trading-signals",
		prototype: "page-signals-inbox.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-signals",
			toolbar: ".scope-strip",
			main: ".signals-main",
			detail: ".signal-detail, .detail-panel",
			table: ".signals-table, .signals-list",
		},
		reactTargets: CATALOG_REACT_TARGETS,
	},
	{
		route: "/trading/orders",
		name: "trading-orders",
		prototype: "page-orders-ledger.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-ledger",
			health: ".status-strip",
			main: ".orders-main, .ledger-main",
			detail: ".order-detail, .detail-panel",
			table: ".orders-table, .ledger-table",
		},
		reactTargets: OPS_REACT_TARGETS,
	},
	{
		route: "/trading/risk",
		name: "trading-risk",
		prototype: "page-risk-center.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-analytical",
			tabs: ".risk-tab-bar",
			strip: ".scope-strip",
			main: ".risk-main, .main-grid",
			alerts: ".risk-alerts, .breach-list",
		},
		reactTargets: ANALYTICAL_REACT_TARGETS,
	},
	{
		route: "/markets/screener",
		name: "markets-screener",
		prototype: "page-markets-screener.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-catalog",
			toolbar: ".filter-toolbar",
			main: ".catalog-main, .screener-main",
			detail: ".compare-cart, .catalog-detail",
			table: ".screener-table, .results-table",
		},
		reactTargets: CATALOG_REACT_TARGETS,
	},
	{
		route: "/markets/intelligence",
		name: "markets-intelligence",
		prototype: "page-markets-intelligence.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-intel",
			body: ".shell-body",
			tabs: ".intel-tab-strip",
			main: ".intel-main",
			workspace: ".intel-workspace",
		},
		reactTargets: ANALYTICAL_REACT_TARGETS,
	},
	{
		route: "/research/regime",
		name: "research-regime",
		prototype: "page-regime-monitor.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-regime",
			strip: ".scope-strip",
			tabs: ".regime-tab-bar",
			main: ".regime-main, .main-grid",
			history: ".regime-history, .history-list",
		},
		reactTargets: ANALYTICAL_REACT_TARGETS,
	},
	{
		route: "/research/strategy-studio",
		name: "research-strategy-studio",
		prototype: "page-strategy-studio.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-studio",
			header: ".studio-header",
			mode: ".studio-mode-bar",
			source: ".studio-sources",
			main: ".studio-main, .strategy-canvas",
			inspector: ".studio-inspector",
		},
		reactTargets: STUDIO_REACT_TARGETS,
	},
	{
		route: "/ai/copilot",
		name: "ai-copilot",
		prototype: "page-ai-copilot.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-copilot",
			modes: ".copilot-modes",
			source: ".copilot-sessions",
			main: ".copilot-main, .chat-panel",
			inspector: ".copilot-inspector",
		},
		reactTargets: STUDIO_REACT_TARGETS,
	},
	{
		route: "/ai/agents",
		name: "ai-agents",
		prototype: "page-agent-console.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-agent",
			tabs: ".agent-tabs",
			main: ".agent-main",
			plans: ".plan-card",
			inspector: ".agent-inspector, .detail-panel",
		},
		reactTargets: STUDIO_REACT_TARGETS,
	},
	{
		route: "/instruments/$id",
		name: "instrument-hub",
		prototype: "page-instrument-hub.html",
		resolvedRoute: "/instruments/600519",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-hub",
			header: ".object-header",
			meta: ".hub-meta",
			tabs: ".sv-header",
			main: ".hub-main, .object-main",
			bottom: ".hub-bottom",
		},
		reactTargets: OBJECT_REACT_TARGETS,
	},
	{
		route: "/markets/a-shares",
		name: "markets-a-shares",
		prototype: "page-a-shares.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-radar",
			body: ".shell-body",
			context: ".context-bar",
			strip: ".scope-strip",
			workspace: ".shell-workspace",
			main: ".main-content",
			aux: ".aux-panels",
		},
		reactTargets: {
			...RADAR_REACT_TARGETS,
			workspace: "[data-slot='main']",
			aux: "[data-slot='right-rail']",
		},
	},
	{
		route: "/research/backtest/$id",
		name: "research-backtest",
		resolvedRoute: "/research/backtest/BT-001",
		prototype: "page-backtest-result.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-hub",
			header: ".object-header",
			meta: ".hub-meta",
			tabs: ".hub-tabs",
			main: ".hub-main",
		},
		reactTargets: OBJECT_REACT_TARGETS,
	},
	{
		route: "/research/factors/$id",
		name: "research-factors",
		resolvedRoute: "/research/factors/F-001",
		prototype: "page-factor-analysis.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-hub",
			header: ".object-header",
			meta: ".hub-meta",
			tabs: ".hub-tabs",
			main: ".hub-main",
		},
		reactTargets: OBJECT_REACT_TARGETS,
	},
	{
		route: "/markets/calendar",
		name: "markets-calendar",
		prototype: "page-markets-calendar.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-catalog",
			toolbar: ".filter-toolbar",
			main: ".workspace-body",
			left: ".workspace-left",
			right: ".workspace-right",
		},
		reactTargets: CATALOG_REACT_TARGETS,
	},
	{
		route: "/strategies/$id",
		name: "strategies-detail",
		resolvedRoute: "/strategies/STR-001",
		prototype: "page-strategies-detail.html",
		prototypeTargets: {
			...PROTOTYPE_APP_TARGETS,
			shell: ".shell-hub",
			header: ".object-header",
			meta: ".hub-meta",
			tabs: ".hub-tabs",
			main: ".hub-main",
		},
		reactTargets: OBJECT_REACT_TARGETS,
	},
];
