import { describe, it, expect } from "vitest";
import {
	PAGE_CONTRACTS as LEGACY_CONTRACTS,
	SHELL_SLOT_MAP as LEGACY_SLOT_MAP,
	PAGE_PATTERNS as LEGACY_PATTERNS,
	SHELL_FAMILIES as LEGACY_FAMILIES,
	PROTOTYPE_SOURCES as LEGACY_SOURCES,
} from "./page-contracts";
import {
	PAGE_CONTRACTS as GENERATED_CONTRACTS,
	SHELL_SLOT_MAP as GENERATED_SLOT_MAP,
	PAGE_PATTERNS as GENERATED_PATTERNS,
	SHELL_FAMILIES as GENERATED_FAMILIES,
	PROTOTYPE_SOURCES as GENERATED_SOURCES,
} from "./page-contracts.generated";

/* ================================================================== */
/*  Legacy contracts (21 routes, hand-authored)                       */
/* ================================================================== */

/* ------------------------------------------------------------------ */
/*  1. Type-level contract structure                                   */
/* ------------------------------------------------------------------ */

describe("Legacy PageContract type structure", () => {
	it("every contract has required fields", () => {
		for (const contract of LEGACY_CONTRACTS) {
			expect(contract).toHaveProperty("route");
			expect(contract).toHaveProperty("pagePattern");
			expect(contract).toHaveProperty("shellFamily");
			expect(contract).toHaveProperty("prototypeSource");
			expect(contract).toHaveProperty("requiredSlots");
			expect(contract).toHaveProperty("requiredStates");
		}
	});

	it("every route is a non-empty string starting with /", () => {
		for (const contract of LEGACY_CONTRACTS) {
			expect(contract.route).toMatch(/^\//);
		}
	});

	it("every pagePattern is a known pattern", () => {
		const patterns = new Set(LEGACY_PATTERNS);
		for (const contract of LEGACY_CONTRACTS) {
			expect(patterns.has(contract.pagePattern)).toBe(true);
		}
	});

	it("every shellFamily is a known family", () => {
		const families = new Set(LEGACY_FAMILIES);
		for (const contract of LEGACY_CONTRACTS) {
			expect(families.has(contract.shellFamily)).toBe(true);
		}
	});

	it("every prototypeSource is a known source type", () => {
		const sources = new Set(LEGACY_SOURCES);
		for (const contract of LEGACY_CONTRACTS) {
			expect(sources.has(contract.prototypeSource)).toBe(true);
		}
	});

	it("prototype-backed pages have prototypeRef", () => {
		for (const contract of LEGACY_CONTRACTS) {
			if (contract.prototypeSource === "prototype-backed") {
				expect(contract).toHaveProperty("prototypeRef");
				expect(contract.prototypeRef).toMatch(/\.html$/);
			}
		}
	});
});

/* ------------------------------------------------------------------ */
/*  2. Route coverage — all implemented pages are covered              */
/* ------------------------------------------------------------------ */

describe("Legacy route coverage", () => {
	const implementedRoutes = [
		"/",
		"/markets",
		"/markets/screener",
		"/markets/intelligence",
		"/markets/a-shares",
		"/markets/calendar",
		"/research",
		"/research/strategy-studio",
		"/research/regime",
		"/research/backtest/$id",
		"/research/factors/$id",
		"/trading",
		"/trading/signals",
		"/trading/orders",
		"/trading/risk",
		"/ai",
		"/ai/copilot",
		"/ai/agents",
		"/instruments/$id",
		"/strategies/$id",
		"/platform",
	] as const;

	it("covers all implemented page routes", () => {
		const coveredRoutes = new Set(LEGACY_CONTRACTS.map((c) => c.route));
		for (const route of implementedRoutes) {
			expect(coveredRoutes.has(route), `Missing contract for ${route}`).toBe(true);
		}
	});

	it("has no duplicate routes", () => {
		const routes = LEGACY_CONTRACTS.map((c) => c.route);
		const uniqueRoutes = new Set(routes);
		expect(uniqueRoutes.size).toBe(routes.length);
	});

	it("contract count matches implemented routes", () => {
		expect(LEGACY_CONTRACTS).toHaveLength(implementedRoutes.length);
	});
});

/* ------------------------------------------------------------------ */
/*  3. Slot consistency — requiredSlots must be valid for shellFamily  */
/* ------------------------------------------------------------------ */

describe("Legacy slot consistency", () => {
	it("SHELL_SLOT_MAP defines valid slots for each family", () => {
		for (const [_family, slots] of Object.entries(LEGACY_SLOT_MAP)) {
			expect(slots.length).toBeGreaterThan(0);
			expect(slots).toContain("main");
		}
	});

	it("every contract's requiredSlots are valid for its shellFamily", () => {
		for (const contract of LEGACY_CONTRACTS) {
			const validSlots = LEGACY_SLOT_MAP[contract.shellFamily];
			expect(
				validSlots,
				`Unknown shellFamily: ${contract.shellFamily}`,
			).toBeDefined();

			for (const slot of contract.requiredSlots) {
				expect(
					validSlots.includes(slot),
					`Invalid slot "${slot}" for shellFamily "${contract.shellFamily}" (${contract.route})`,
				).toBe(true);
			}
		}
	});

	it("every contract includes 'main' in requiredSlots", () => {
		for (const contract of LEGACY_CONTRACTS) {
			expect(
				contract.requiredSlots.includes("main"),
				`${contract.route} missing 'main' slot`,
			).toBe(true);
		}
	});
});

/* ------------------------------------------------------------------ */
/*  4. State coverage — universal states present                       */
/* ------------------------------------------------------------------ */

describe("Legacy state coverage", () => {
	const UNIVERSAL_STATES = ["loading", "empty", "error", "stale"] as const;

	it("every contract covers universal states", () => {
		for (const contract of LEGACY_CONTRACTS) {
			for (const state of UNIVERSAL_STATES) {
				expect(
					contract.requiredStates.includes(state),
					`${contract.route} missing universal state: ${state}`,
				).toBe(true);
			}
		}
	});
});

/* ------------------------------------------------------------------ */
/*  5. Pattern-to-shell mapping correctness (per spec)                 */
/* ------------------------------------------------------------------ */

describe("Legacy pattern-to-shell mapping correctness", () => {
	it("Command Center pages use command-center shell", () => {
		const ccPages = LEGACY_CONTRACTS.filter(
			(c) => c.pagePattern === "global-command-center",
		);
		for (const page of ccPages) {
			expect(page.shellFamily).toBe("command-center");
		}
	});

	it("Analytical Overview pages use analytical or radar shell", () => {
		const pages = LEGACY_CONTRACTS.filter(
			(c) => c.pagePattern === "analytical-overview",
		);
		for (const page of pages) {
			expect(["analytical", "radar"].includes(page.shellFamily)).toBe(true);
		}
	});

	it("Object Hub pages use object-hub shell", () => {
		const pages = LEGACY_CONTRACTS.filter(
			(c) => c.pagePattern === "object-hub",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("object-hub");
		}
	});

	it("Studio/Builder pages use studio shell", () => {
		const pages = LEGACY_CONTRACTS.filter(
			(c) => c.pagePattern === "studio-builder",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("studio");
		}
	});

	it("Queue/Ops Console pages use ops-console shell", () => {
		const pages = LEGACY_CONTRACTS.filter(
			(c) => c.pagePattern === "queue-ops-console",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("ops-console");
		}
	});

	it("Ledger/Execution Console pages use ops-console shell", () => {
		const pages = LEGACY_CONTRACTS.filter(
			(c) => c.pagePattern === "ledger-execution-console",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("ops-console");
		}
	});

	it("Catalog/Screener pages use catalog shell", () => {
		const pages = LEGACY_CONTRACTS.filter(
			(c) => c.pagePattern === "catalog-screener",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("catalog");
		}
	});
});

/* ------------------------------------------------------------------ */
/*  6. Spec compliance — known pattern misalignments                   */
/* ------------------------------------------------------------------ */

describe("Legacy spec compliance", () => {
	it("/trading/signals is Queue/Ops Console (not Catalog)", () => {
		const contract = LEGACY_CONTRACTS.find((c) => c.route === "/trading/signals");
		expect(contract?.pagePattern).toBe("queue-ops-console");
	});

	it("/trading/orders is Ledger/Execution Console (not Catalog)", () => {
		const contract = LEGACY_CONTRACTS.find((c) => c.route === "/trading/orders");
		expect(contract?.pagePattern).toBe("ledger-execution-console");
	});

	it("/ai/agents is Ops Console", () => {
		const contract = LEGACY_CONTRACTS.find((c) => c.route === "/ai/agents");
		expect(contract?.pagePattern).toBe("queue-ops-console");
	});

	it("/ai is Global Command Center", () => {
		const contract = LEGACY_CONTRACTS.find((c) => c.route === "/ai");
		expect(contract?.pagePattern).toBe("global-command-center");
	});

	it("/ai follows the page-ai-overview prototype slot contract", () => {
		const contract = LEGACY_CONTRACTS.find((c) => c.route === "/ai");
		expect(contract?.prototypeRef).toBe(
			"docs/designs/specs/prototypes/page-ai-overview.html",
		);
		expect(contract?.requiredSlots).toEqual(["pulse", "main", "sidebar"]);
	});
});

/* ------------------------------------------------------------------ */
/*  7. Prototype source classification                                 */
/* ------------------------------------------------------------------ */

describe("Legacy prototype source classification", () => {
	const prototypeBackedRoutes = [
		"/",
		"/markets",
		"/markets/screener",
		"/markets/intelligence",
		"/research",
		"/research/strategy-studio",
		"/research/regime",
		"/trading",
		"/trading/signals",
		"/trading/orders",
		"/trading/risk",
		"/ai",
		"/ai/copilot",
		"/ai/agents",
		"/instruments/$id",
		"/platform",
		"/markets/a-shares",
		"/markets/calendar",
		"/research/backtest/$id",
		"/research/factors/$id",
		"/strategies/$id",
	] as const;

	const specOnlyRoutes = [] as const;

	it("prototype-backed pages are correctly classified", () => {
		for (const route of prototypeBackedRoutes) {
			const contract = LEGACY_CONTRACTS.find((c) => c.route === route);
			expect(
				contract?.prototypeSource,
				`${route} should be prototype-backed`,
			).toBe("prototype-backed");
		}
	});

	it("spec-only pages are correctly classified", () => {
		for (const route of specOnlyRoutes) {
			const contract = LEGACY_CONTRACTS.find((c) => c.route === route);
			expect(
				contract?.prototypeSource,
				`${route} should be spec-only`,
			).toBe("spec-only");
		}
	});
});

/* ------------------------------------------------------------------ */
/*  8. Sidebar collapsibility                                          */
/* ------------------------------------------------------------------ */

describe("Legacy sidebar collapsibility", () => {
	const SIDEBAR_COLLAPSIBLE_ROUTES = ["/", "/ai", "/markets/intelligence"] as const;

	it("Home, AI Overview, and Intelligence have sidebarCollapsible: true", () => {
		for (const route of SIDEBAR_COLLAPSIBLE_ROUTES) {
			const contract = LEGACY_CONTRACTS.find((c) => c.route === route);
			expect(
				contract?.sidebarCollapsible,
				`${route} should have sidebarCollapsible: true`,
			).toBe(true);
		}
	});

	it("only designated routes have sidebarCollapsible: true", () => {
		const collapsibleRoutes = LEGACY_CONTRACTS.filter(
			(c) => c.sidebarCollapsible === true,
		);
		expect(collapsibleRoutes).toHaveLength(SIDEBAR_COLLAPSIBLE_ROUTES.length);
		for (const contract of collapsibleRoutes) {
			expect(
				(SIDEBAR_COLLAPSIBLE_ROUTES as readonly string[]).includes(contract.route),
			).toBe(true);
		}
	});
});

/* ================================================================== */
/*  Generated contracts (contract-ready pages from JSON)               */
/* ================================================================== */

describe("Generated contract structure", () => {
	it("exports PAGE_PATTERNS as a non-empty readonly tuple", () => {
		expect(GENERATED_PATTERNS.length).toBeGreaterThan(0);
	});

	it("exports SHELL_FAMILIES as a non-empty readonly tuple", () => {
		expect(GENERATED_FAMILIES.length).toBeGreaterThan(0);
	});

	it("exports PROTOTYPE_SOURCES as a non-empty readonly tuple", () => {
		expect(GENERATED_SOURCES.length).toBeGreaterThan(0);
	});

	it("SHELL_SLOT_MAP has at least one family with slots", () => {
		for (const [_family, slots] of Object.entries(GENERATED_SLOT_MAP)) {
			expect(slots.length).toBeGreaterThan(0);
			expect(slots).toContain("main");
		}
	});

	it("every generated contract has required fields", () => {
		for (const contract of GENERATED_CONTRACTS) {
			expect(contract).toHaveProperty("route");
			expect(contract).toHaveProperty("pagePattern");
			expect(contract).toHaveProperty("shellFamily");
			expect(contract).toHaveProperty("prototypeSource");
			expect(contract).toHaveProperty("requiredSlots");
			expect(contract).toHaveProperty("requiredStates");
		}
	});

	it("every generated contract covers universal states", () => {
		const universal = ["loading", "empty", "error", "stale"];
		for (const contract of GENERATED_CONTRACTS) {
			for (const state of universal) {
				expect(
					contract.requiredStates.includes(state),
					`Generated ${contract.route} missing state: ${state}`,
				).toBe(true);
			}
		}
	});

	it("every generated contract has valid shellFamily", () => {
		const families = new Set(GENERATED_FAMILIES);
		for (const contract of GENERATED_CONTRACTS) {
			expect(families.has(contract.shellFamily)).toBe(true);
		}
	});

	it("generated contracts match legacy contracts for migrated pages", () => {
		// For each generated contract, verify it matches the legacy version
		for (const generated of GENERATED_CONTRACTS) {
			const legacy = LEGACY_CONTRACTS.find((c) => c.route === generated.route);
			if (!legacy) continue; // New page not in legacy yet

			expect(generated.pagePattern).toBe(legacy.pagePattern);
			expect(generated.shellFamily).toBe(legacy.shellFamily);
			expect(generated.requiredSlots).toEqual(legacy.requiredSlots);
			expect(generated.prototypeRef).toBe(legacy.prototypeRef);
			expect(generated.sidebarCollapsible).toBe(legacy.sidebarCollapsible);
		}
	});
});
