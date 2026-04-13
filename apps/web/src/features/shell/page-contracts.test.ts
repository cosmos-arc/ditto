import { describe, it, expect } from "vitest";
import {
	PAGE_CONTRACTS,
	type PageContract,
	SHELL_SLOT_MAP,
	PAGE_PATTERNS,
	SHELL_FAMILIES,
	PROTOTYPE_SOURCES,
} from "./page-contracts";

/* ------------------------------------------------------------------ */
/*  1. Type-level contract structure                                   */
/* ------------------------------------------------------------------ */

describe("PageContract type structure", () => {
	it("every contract has required fields", () => {
		for (const contract of PAGE_CONTRACTS) {
			expect(contract).toHaveProperty("route");
			expect(contract).toHaveProperty("pagePattern");
			expect(contract).toHaveProperty("shellFamily");
			expect(contract).toHaveProperty("prototypeSource");
			expect(contract).toHaveProperty("requiredSlots");
			expect(contract).toHaveProperty("requiredStates");
		}
	});

	it("every route is a non-empty string starting with /", () => {
		for (const contract of PAGE_CONTRACTS) {
			expect(contract.route).toMatch(/^\//);
		}
	});

	it("every pagePattern is a known pattern", () => {
		const patterns = new Set(PAGE_PATTERNS);
		for (const contract of PAGE_CONTRACTS) {
			expect(patterns.has(contract.pagePattern)).toBe(true);
		}
	});

	it("every shellFamily is a known family", () => {
		const families = new Set(SHELL_FAMILIES);
		for (const contract of PAGE_CONTRACTS) {
			expect(families.has(contract.shellFamily)).toBe(true);
		}
	});

	it("every prototypeSource is a known source type", () => {
		const sources = new Set(PROTOTYPE_SOURCES);
		for (const contract of PAGE_CONTRACTS) {
			expect(sources.has(contract.prototypeSource)).toBe(true);
		}
	});

	it("prototype-backed pages have prototypeRef", () => {
		for (const contract of PAGE_CONTRACTS) {
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

describe("Route coverage", () => {
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
		const coveredRoutes = new Set(PAGE_CONTRACTS.map((c) => c.route));
		for (const route of implementedRoutes) {
			expect(coveredRoutes.has(route), `Missing contract for ${route}`).toBe(true);
		}
	});

	it("has no duplicate routes", () => {
		const routes = PAGE_CONTRACTS.map((c) => c.route);
		const uniqueRoutes = new Set(routes);
		expect(uniqueRoutes.size).toBe(routes.length);
	});

	it("contract count matches implemented routes", () => {
		expect(PAGE_CONTRACTS).toHaveLength(implementedRoutes.length);
	});
});

/* ------------------------------------------------------------------ */
/*  3. Slot consistency — requiredSlots must be valid for shellFamily  */
/* ------------------------------------------------------------------ */

describe("Slot consistency", () => {
	it("SHELL_SLOT_MAP defines valid slots for each family", () => {
		for (const [_family, slots] of Object.entries(SHELL_SLOT_MAP)) {
			expect(slots.length).toBeGreaterThan(0);
			expect(slots).toContain("main");
		}
	});

	it("every contract's requiredSlots are valid for its shellFamily", () => {
		for (const contract of PAGE_CONTRACTS) {
			const validSlots = SHELL_SLOT_MAP[contract.shellFamily];
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
		for (const contract of PAGE_CONTRACTS) {
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

describe("State coverage", () => {
	const UNIVERSAL_STATES = ["loading", "empty", "error", "stale"] as const;

	it("every contract covers universal states", () => {
		for (const contract of PAGE_CONTRACTS) {
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

describe("Pattern-to-shell mapping correctness", () => {
	it("Command Center pages use command-center shell", () => {
		const ccPages = PAGE_CONTRACTS.filter(
			(c) => c.pagePattern === "global-command-center",
		);
		for (const page of ccPages) {
			expect(page.shellFamily).toBe("command-center");
		}
	});

	it("Analytical Overview pages use analytical or radar shell", () => {
		const pages = PAGE_CONTRACTS.filter(
			(c) => c.pagePattern === "analytical-overview",
		);
		for (const page of pages) {
			expect(["analytical", "radar"].includes(page.shellFamily)).toBe(true);
		}
	});

	it("Object Hub pages use object-hub shell", () => {
		const pages = PAGE_CONTRACTS.filter(
			(c) => c.pagePattern === "object-hub",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("object-hub");
		}
	});

	it("Studio/Builder pages use studio shell", () => {
		const pages = PAGE_CONTRACTS.filter(
			(c) => c.pagePattern === "studio-builder",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("studio");
		}
	});

	it("Queue/Ops Console pages use ops-console shell", () => {
		const pages = PAGE_CONTRACTS.filter(
			(c) => c.pagePattern === "queue-ops-console",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("ops-console");
		}
	});

	it("Ledger/Execution Console pages use ops-console shell", () => {
		const pages = PAGE_CONTRACTS.filter(
			(c) => c.pagePattern === "ledger-execution-console",
		);
		for (const page of pages) {
			expect(page.shellFamily).toBe("ops-console");
		}
	});

	it("Catalog/Screener pages use catalog shell", () => {
		const pages = PAGE_CONTRACTS.filter(
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

describe("Spec compliance — pattern alignment per 11_ditto_page_pattern_library", () => {
	it("/trading/signals is Queue/Ops Console (not Catalog)", () => {
		const contract = PAGE_CONTRACTS.find((c) => c.route === "/trading/signals");
		expect(contract?.pagePattern).toBe("queue-ops-console");
	});

	it("/trading/orders is Ledger/Execution Console (not Catalog)", () => {
		const contract = PAGE_CONTRACTS.find((c) => c.route === "/trading/orders");
		expect(contract?.pagePattern).toBe("ledger-execution-console");
	});

	it("/ai/agents is Ops Console", () => {
		const contract = PAGE_CONTRACTS.find((c) => c.route === "/ai/agents");
		expect(contract?.pagePattern).toBe("queue-ops-console");
	});

	it("/ai is Global Command Center", () => {
		const contract = PAGE_CONTRACTS.find((c) => c.route === "/ai");
		expect(contract?.pagePattern).toBe("global-command-center");
	});

	it("/ai follows the page-ai-overview prototype slot contract", () => {
		const contract = PAGE_CONTRACTS.find((c) => c.route === "/ai");
		expect(contract?.prototypeRef).toBe(
			"docs/designs/specs/prototypes/page-ai-overview.html",
		);
		expect(contract?.requiredSlots).toEqual(["pulse", "main", "sidebar"]);
	});
});

/* ------------------------------------------------------------------ */
/*  7. Prototype source classification                                 */
/* ------------------------------------------------------------------ */

describe("Prototype source classification", () => {
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
			const contract = PAGE_CONTRACTS.find((c) => c.route === route);
			expect(
				contract?.prototypeSource,
				`${route} should be prototype-backed`,
			).toBe("prototype-backed");
		}
	});

	it("spec-only pages are correctly classified", () => {
		for (const route of specOnlyRoutes) {
			const contract = PAGE_CONTRACTS.find((c) => c.route === route);
			expect(
				contract?.prototypeSource,
				`${route} should be spec-only`,
			).toBe("spec-only");
		}
	});
});
