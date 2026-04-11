/**
 * Page Contracts — 页面合同表
 *
 * 每个页面的 pattern / shell / source / slots / states 定义。
 * 这是实现与 specs/prototypes 收敛的唯一真源。
 *
 * @see docs/designs/specs/11_ditto_page_pattern_library.md
 * @see docs/plans/2026-04-10-prototype-recovery-design.md §5
 */

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

/** Page Pattern 枚举值 — 来自 11_ditto_page_pattern_library.md */
export const PAGE_PATTERNS = [
	"global-command-center",
	"analytical-overview",
	"catalog-screener",
	"object-hub",
	"studio-builder",
	"queue-ops-console",
	"ledger-execution-console",
	"config-integration-console",
] as const;

/** Shell Family 枚举值 — 来自 10_ditto_shell_family_spec.md */
export const SHELL_FAMILIES = [
	"command-center",
	"analytical",
	"catalog",
	"object-hub",
	"studio",
	"ops-console",
] as const;

/** 原型来源类型 */
export const PROTOTYPE_SOURCES = ["prototype-backed", "spec-only"] as const;

/** Shell Family → 合法 Slot 映射 */
export const SHELL_SLOT_MAP: Record<ShellFamily, string[]> = {
	"command-center": ["pulse", "main", "sidebar"],
	analytical: ["strip", "main", "activity", "analysis"],
	catalog: ["toolbar", "main", "detail"],
	"object-hub": ["meta", "tabs", "main", "bottom"],
	studio: ["source", "main", "inspector", "logs"],
	"ops-console": ["health", "main", "detail"],
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export type PagePattern = (typeof PAGE_PATTERNS)[number];
export type ShellFamily = (typeof SHELL_FAMILIES)[number];
export type PrototypeSource = (typeof PROTOTYPE_SOURCES)[number];

export interface PageContract {
	/** 页面路由 */
	route: string;
	/** 对应 Page Pattern（来自 spec §11） */
	pagePattern: PagePattern;
	/** 对应 Shell Family（来自 spec §10） */
	shellFamily: ShellFamily;
	/** 原型来源类型 */
	prototypeSource: PrototypeSource;
	/** HTML 原型文件路径（仅 prototype-backed 页面） */
	prototypeRef?: string;
	/** 页面必须填充的 slot 列表 */
	requiredSlots: string[];
	/** 页面必须覆盖的 UI 状态列表 */
	requiredStates: string[];
	/**
	 * 原型是否包含 StatusBar。
	 * 若为 true，页面渲染 `<StatusBar />`（fixed 定位）
	 * 并给布局根容器加 `pb-(--height-status-bar)` 防止内容被遮挡。
	 */
	hasStatusBar?: boolean;
}

/* ------------------------------------------------------------------ */
/*  Universal states                                                   */
/* ------------------------------------------------------------------ */

const UNIVERSAL_STATES = ["loading", "empty", "error", "stale"] as const;

/* ------------------------------------------------------------------ */
/*  Page Contracts — 21 implemented routes                             */
/* ------------------------------------------------------------------ */

export const PAGE_CONTRACTS: readonly PageContract[] = [
	/* ── Group A: Prototype-backed ─────────────────────────────────── */

	// 01 Global Command Center
	{
		route: "/",
		pagePattern: "global-command-center",
		shellFamily: "command-center",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-home.html",
		requiredSlots: ["pulse", "main", "sidebar"],
		requiredStates: [...UNIVERSAL_STATES, "no-alerts", "has-critical"],
		// home prototype has NO status bar
	},
	{
		route: "/ai",
		pagePattern: "global-command-center",
		shellFamily: "command-center",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-ai-overview.html",
		requiredSlots: ["pulse", "main", "sidebar"],
		requiredStates: [...UNIVERSAL_STATES, "no-agents", "has-pending"],
		hasStatusBar: true,
	},

	// 02 Analytical Overview Workspace
	{
		route: "/markets",
		pagePattern: "analytical-overview",
		shellFamily: "analytical",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-cross-market.html",
		requiredSlots: ["strip", "main", "activity", "analysis"],
		requiredStates: [...UNIVERSAL_STATES],
		hasStatusBar: true,
	},
	{
		route: "/markets/intelligence",
		pagePattern: "analytical-overview",
		shellFamily: "analytical",
		prototypeSource: "prototype-backed",
		prototypeRef:
			"docs/designs/specs/prototypes/page-markets-intelligence.html",
		requiredSlots: ["strip", "main", "activity"],
		requiredStates: [...UNIVERSAL_STATES],
		hasStatusBar: true,
	},
	{
		route: "/research",
		pagePattern: "analytical-overview",
		shellFamily: "analytical",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-research.html",
		requiredSlots: ["strip", "main", "activity", "analysis"],
		requiredStates: [...UNIVERSAL_STATES],
		// research prototype has NO status bar
	},
	{
		route: "/research/regime",
		pagePattern: "analytical-overview",
		shellFamily: "analytical",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-regime-monitor.html",
		requiredSlots: ["strip", "main", "activity", "analysis"],
		requiredStates: [...UNIVERSAL_STATES],
		hasStatusBar: true,
	},
	{
		route: "/trading",
		pagePattern: "analytical-overview",
		shellFamily: "analytical",
		prototypeSource: "prototype-backed",
		prototypeRef:
			"docs/designs/specs/prototypes/page-trading-overview.html",
		requiredSlots: ["strip", "main", "activity", "analysis"],
		requiredStates: [...UNIVERSAL_STATES],
		hasStatusBar: true,
	},
	{
		route: "/trading/risk",
		pagePattern: "analytical-overview",
		shellFamily: "analytical",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-risk-center.html",
		requiredSlots: ["strip", "main", "activity", "analysis"],
		requiredStates: [...UNIVERSAL_STATES],
		hasStatusBar: true,
	},

	// 03 Catalog / Screener Workspace
	{
		route: "/markets/screener",
		pagePattern: "catalog-screener",
		shellFamily: "catalog",
		prototypeSource: "prototype-backed",
		prototypeRef:
			"docs/designs/specs/prototypes/page-markets-screener.html",
		requiredSlots: ["toolbar", "main", "detail"],
		requiredStates: [...UNIVERSAL_STATES, "selected-row"],
		// screener prototype has NO status bar
	},

	// 04 Object Hub
	{
		route: "/instruments/$id",
		pagePattern: "object-hub",
		shellFamily: "object-hub",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-instrument-hub.html",
		requiredSlots: ["meta", "tabs", "main"],
		requiredStates: [...UNIVERSAL_STATES, "not-found"],
		hasStatusBar: true,
	},

	// 05 Studio / Builder
	{
		route: "/research/strategy-studio",
		pagePattern: "studio-builder",
		shellFamily: "studio",
		prototypeSource: "prototype-backed",
		prototypeRef:
			"docs/designs/specs/prototypes/page-strategy-studio.html",
		requiredSlots: ["source", "main", "inspector"],
		requiredStates: [...UNIVERSAL_STATES, "no-session", "running"],
		hasStatusBar: true,
	},
	{
		route: "/ai/copilot",
		pagePattern: "studio-builder",
		shellFamily: "studio",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-ai-copilot.html",
		requiredSlots: ["source", "main", "inspector"],
		requiredStates: [...UNIVERSAL_STATES, "no-session", "chatting"],
		hasStatusBar: true,
	},
	{
		route: "/ai/agents",
		pagePattern: "studio-builder",
		shellFamily: "studio",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-agent-console.html",
		requiredSlots: ["source", "main", "inspector"],
		requiredStates: [...UNIVERSAL_STATES, "no-agents", "agent-running"],
		hasStatusBar: true,
	},

	// 06 Queue / Ops Console
	{
		route: "/trading/signals",
		pagePattern: "queue-ops-console",
		shellFamily: "ops-console",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-signals-inbox.html",
		requiredSlots: ["health", "main", "detail"],
		requiredStates: [
			...UNIVERSAL_STATES,
			"selected-row",
			"sheet-open",
		],
		hasStatusBar: true,
	},

	// 07 Ledger / Execution Console
	{
		route: "/trading/orders",
		pagePattern: "ledger-execution-console",
		shellFamily: "ops-console",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-orders-ledger.html",
		requiredSlots: ["health", "main", "detail"],
		requiredStates: [
			...UNIVERSAL_STATES,
			"selected-row",
			"order-active",
		],
		hasStatusBar: true,
	},

	// 06 Queue / Ops Console
	{
		route: "/platform",
		pagePattern: "queue-ops-console",
		shellFamily: "ops-console",
		prototypeSource: "prototype-backed",
		prototypeRef: "docs/designs/specs/prototypes/page-platform.html",
		requiredSlots: ["health", "main", "detail"],
		requiredStates: [...UNIVERSAL_STATES, "pipeline-running"],
		hasStatusBar: true,
	},

	/* ── Group B: Spec-only ────────────────────────────────────────── */

	// 02 Analytical Overview (spec-only)
	{
		route: "/markets/a-shares",
		pagePattern: "analytical-overview",
		shellFamily: "analytical",
		prototypeSource: "spec-only",
		requiredSlots: ["strip", "main", "activity"],
		requiredStates: [...UNIVERSAL_STATES],
	},

	// 03 Catalog / Screener (spec-only)
	{
		route: "/markets/calendar",
		pagePattern: "catalog-screener",
		shellFamily: "catalog",
		prototypeSource: "spec-only",
		requiredSlots: ["toolbar", "main"],
		requiredStates: [...UNIVERSAL_STATES],
	},

	// 04 Object Hub (spec-only)
	{
		route: "/research/backtest/$id",
		pagePattern: "object-hub",
		shellFamily: "object-hub",
		prototypeSource: "spec-only",
		requiredSlots: ["meta", "tabs", "main"],
		requiredStates: [...UNIVERSAL_STATES, "not-found"],
	},
	{
		route: "/research/factors/$id",
		pagePattern: "object-hub",
		shellFamily: "object-hub",
		prototypeSource: "spec-only",
		requiredSlots: ["meta", "tabs", "main"],
		requiredStates: [...UNIVERSAL_STATES, "not-found"],
	},
	{
		route: "/strategies/$id",
		pagePattern: "object-hub",
		shellFamily: "object-hub",
		prototypeSource: "spec-only",
		requiredSlots: ["meta", "tabs", "main"],
		requiredStates: [...UNIVERSAL_STATES, "not-found"],
	},
] as const satisfies readonly PageContract[];
