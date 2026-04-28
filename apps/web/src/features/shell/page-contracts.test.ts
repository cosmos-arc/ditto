import { describe, expect, it } from "vitest";
import {
	PAGE_CONTRACTS,
	PAGE_PATTERNS,
	PROTOTYPE_SOURCES,
	SHELL_FAMILIES,
	SHELL_SLOT_MAP,
} from "./page-contracts.generated";

const IA_ROUTES = [
	"/",
	"/markets",
	"/markets/a-shares",
	"/markets/screener",
	"/markets/watchlist",
	"/markets/intelligence",
	"/markets/calendar",
	"/instruments/$id",
	"/research",
	"/research/factors",
	"/research/factors/$id",
	"/research/strategies",
	"/research/strategies/$id",
	"/research/strategies/$id/studio",
	"/research/backtest",
	"/research/backtest/$id",
	"/research/experiments",
	"/research/regime",
	"/research/universes",
	"/trading",
	"/trading/signals",
	"/trading/orders",
	"/trading/portfolio",
	"/trading/risk",
	"/platform",
	"/platform/settings",
	"/platform/agents",
] as const;

const UNIVERSAL_STATES = ["loading", "empty", "error", "stale"] as const;

describe("Generated page contracts", () => {
	it("exports the generated contract dictionaries", () => {
		expect(PAGE_PATTERNS.length).toBeGreaterThan(0);
		expect(SHELL_FAMILIES.length).toBeGreaterThan(0);
		expect(PROTOTYPE_SOURCES.length).toBeGreaterThan(0);
	});

	it("generated contracts cover every IA route", () => {
		const coveredRoutes = new Set(PAGE_CONTRACTS.map((contract) => contract.route));

		for (const route of IA_ROUTES) {
			expect(coveredRoutes.has(route), `Missing contract for ${route}`).toBe(true);
		}
	});

	it("does not emit duplicate route contracts", () => {
		const routes = PAGE_CONTRACTS.map((contract) => contract.route);
		const uniqueRoutes = new Set(routes);

		expect(uniqueRoutes.size).toBe(routes.length);
		expect(routes).toHaveLength(IA_ROUTES.length);
	});

	it("keeps required slots valid for each shell family", () => {
		for (const [_family, slots] of Object.entries(SHELL_SLOT_MAP)) {
			expect(slots.length).toBeGreaterThan(0);
			expect(slots).toContain("main");
		}

		for (const contract of PAGE_CONTRACTS) {
			const validSlots = SHELL_SLOT_MAP[contract.shellFamily];

			expect(validSlots, `Unknown shellFamily: ${contract.shellFamily}`).toBeDefined();
			for (const slot of contract.requiredSlots) {
				expect(
					validSlots.includes(slot),
					`Invalid slot "${slot}" for ${contract.route}`,
				).toBe(true);
			}
		}
	});

	it("keeps universal state coverage on every page", () => {
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
