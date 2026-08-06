import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
	PAGE_CONTRACTS,
	PAGE_PATTERNS,
	type PageLandingVisualAuditStatus,
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
	"/research/alpha",
	"/research/factors",
	"/research/factors/$id",
	"/research/strategies",
	"/research/strategies/$id",
	"/research/strategies/$id/studio",
	"/research/backtest",
	"/research/backtest/$id",
	"/research/experiments",
	"/research/experiments/new",
	"/research/experiments/$id",
	"/research/regime",
	"/research/reviews",
	"/research/reviews/$id",
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
const VISUAL_AUDIT_STATUSES = [
	"missing",
	"queued",
	"implemented",
	"verified",
] as const satisfies readonly PageLandingVisualAuditStatus[];

const GENERATED_SOURCE = readFileSync(
	resolve(process.cwd(), "src/features/shell/page-contracts.generated.ts"),
	"utf-8",
);

type LandingWithComponentRefs = {
	reactComponentRefs?: string[];
	reactTestRefs?: string[];
};

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
				expect(validSlots.includes(slot), `Invalid slot "${slot}" for ${contract.route}`).toBe(true);
			}
		}
	});

	it("keeps universal state coverage on every page", () => {
		for (const contract of PAGE_CONTRACTS) {
			for (const state of UNIVERSAL_STATES) {
				expect(contract.requiredStates.includes(state), `${contract.route} missing universal state: ${state}`).toBe(
					true,
				);
			}
		}
	});

	it("uses the React visual audit landing vocabulary", () => {
		expect(GENERATED_SOURCE).toContain(
			'export type PageLandingVisualAuditStatus = "missing" | "queued" | "implemented" | "verified";',
		);
		expect(GENERATED_SOURCE).not.toContain('"baseline" | "pass"');

		for (const contract of PAGE_CONTRACTS) {
			if (!contract.landing) continue;

			expect(
				VISUAL_AUDIT_STATUSES.includes(contract.landing.visualAuditStatus),
				`${contract.route} has invalid visualAuditStatus: ${contract.landing.visualAuditStatus}`,
			).toBe(true);
		}
	});

	it("maps implemented React route contracts to feature tests", () => {
		for (const contract of PAGE_CONTRACTS) {
			if (contract.landing?.reactRouteStatus !== "implemented") continue;
			const landing = contract.landing as typeof contract.landing & LandingWithComponentRefs;

			expect(landing.featureModule, `${contract.route} missing featureModule`).toMatch(/^src\/features\/[^/]+$/);
			expect(landing.reactTestRefs, `${contract.route} missing reactTestRefs`).toEqual(
				expect.arrayContaining([expect.stringMatching(/^src\/features\/.+\.test\.(ts|tsx)$/)]),
			);
			expect(landing.reactComponentRefs, `${contract.route} missing reactComponentRefs`).toEqual(
				expect.arrayContaining([expect.stringMatching(/^[A-Z][A-Za-z0-9]+$/)]),
			);

			const testSources = (landing.reactTestRefs ?? []).map((ref) => {
				const path = resolve(process.cwd(), ref);
				expect(existsSync(path), `${contract.route} test ref does not exist: ${ref}`).toBe(true);

				return readFileSync(path, "utf-8");
			});

			for (const componentRef of landing.reactComponentRefs ?? []) {
				const handoffMarker = `@contract-handoff ${componentRef}`;
				const jsxMarker = `<${componentRef}`;
				expect(
					testSources.some((source) => source.includes(jsxMarker) || source.includes(handoffMarker)),
					`${contract.route} reactTestRefs do not cover ${componentRef}`,
				).toBe(true);
			}
		}
	});
});
