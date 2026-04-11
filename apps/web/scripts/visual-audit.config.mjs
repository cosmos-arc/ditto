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

const REACT_APP_TARGETS = {
	shell: "#root > div",
	rail: "nav[aria-label='主导航']",
	header: "header",
	content: "#root > div > div:nth-child(3)",
	layout: "#root > div > div:nth-child(3) > div",
	status: "[data-slot='status-bar']",
};

const PROTOTYPE_APP_TARGETS = {
	rail: ".shell-rail",
	header: ".shell-header, .studio-header, .object-header",
	status: ".status-bar",
};

const ANALYTICAL_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	strip: "#root > div > div:nth-child(3) > div > div:nth-child(1)",
	main: "#root > div > div:nth-child(3) > div > div:nth-child(2)",
	activity: "#root > div > div:nth-child(3) > div > div:nth-child(3)",
	analysis: "#root > div > div:nth-child(3) > div > div:nth-child(4)",
	session: "[data-slot='session-strip']",
	scope: "[data-slot='scope-strip']",
};

const CATALOG_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	toolbar: "#root > div > div:nth-child(3) > div > div:nth-child(1)",
	main: "#root > div > div:nth-child(3) > div > div:nth-child(2)",
	detail: "#root > div > div:nth-child(3) > div > div:nth-child(3)",
	filter: "[data-slot='filter-toolbar']",
	table: "[data-slot='data-table']",
};

const OPS_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	health: "#root > div > div:nth-child(3) > div > div:nth-child(1)",
	main: "#root > div > div:nth-child(3) > div > div:nth-child(2)",
	detail: "#root > div > div:nth-child(3) > div > div:nth-child(3)",
};

const STUDIO_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	source: "#root > div > div:nth-child(3) > div > div:nth-child(1)",
	main: "#root > div > div:nth-child(3) > div > div:nth-child(2)",
	inspector: "#root > div > div:nth-child(3) > div > div:nth-child(3)",
	logs: "#root > div > div:nth-child(3) > div > div:nth-child(4)",
};

const OBJECT_REACT_TARGETS = {
	...REACT_APP_TARGETS,
	meta: "#root > div > div:nth-child(3) > div > div:nth-child(1)",
	tabs: "#root > div > div:nth-child(3) > div > div:nth-child(2)",
	main: "#root > div > div:nth-child(3) > div > div:nth-child(3)",
	bottom: "#root > div > div:nth-child(3) > div > div:nth-child(4)",
};

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
			main: "[data-slot='home-main']",
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
		reactTargets: {
			...REACT_APP_TARGETS,
			layout: "#root > div > div:nth-child(3) > div",
			strip: "[data-slot='session-strip']",
			main: "#root > div > div:nth-child(3) > div > div:nth-child(2)",
			sidebar: "#root > div > div:nth-child(3) > div > div:nth-child(3)",
		},
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
			...ANALYTICAL_REACT_TARGETS,
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
		reactTargets: {
			...ANALYTICAL_REACT_TARGETS,
			analysis: "[data-slot='analysis-band']",
		},
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
];
