import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
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
	"/markets/industries",
	"/markets/screener",
	"/markets/watchlist",
	"/instruments/$id",
	"/research",
	"/research/factors",
	"/research/experiments",
	"/research/backtests",
	"/research/strategies",
	"/research/agent",
	"/research/reviews",
	"/research/universes",
	"/portfolio",
	"/portfolio/model",
	"/portfolio/paper",
	"/portfolio/manual",
	"/portfolio/transactions",
	"/portfolio/risk",
	"/portfolio/review",
	"/system",
	"/system/data-products",
	"/system/jobs",
	"/system/agent",
	"/system/approvals",
	"/system/settings",
	"/system/audit",
] as const;

const RETIRED_PRODUCT_PREFIXES = ["/trading", "/platform"] as const;

const UNIVERSAL_STATES = ["loading", "empty", "error", "stale"] as const;
const GENERATED_SOURCE = readFileSync(
	resolve(process.cwd(), "src/features/shell/page-contracts.generated.ts"),
	"utf-8",
);
const EDITION_MANIFEST = JSON.parse(
	readFileSync(resolve(process.cwd(), "docs/designs/specs/prototypes/.edition-manifest.json"), "utf-8"),
) as { readonly reactOnlyRoutes?: readonly { readonly route: string }[] };

type LandingWithComponentRefs = {
	reactComponentRefs?: string[];
	reactTestRefs?: string[];
};

type R1R5Contract = {
	liveData?: {
		readPaths?: string[];
		writePaths?: string[];
		mockFallback?: boolean;
	};
	overlays: Array<{ reactComponent: string }>;
	security?: {
		browserCredentialInputs?: string[];
		browserPersistence?: string[];
		forbiddenClientFields?: string[];
		providerConfiguration?: string;
	};
	states: {
		pageSpecific: string[];
		universal: string[];
	};
};

const readR1R5Contract = (id: string): R1R5Contract =>
	JSON.parse(readFileSync(resolve(process.cwd(), `docs/contracts/pages/${id}.contract.json`), "utf-8")) as R1R5Contract;

describe("Generated page contracts", () => {
	it("exports the generated contract dictionaries", () => {
		expect(PAGE_PATTERNS.length).toBeGreaterThan(0);
		expect(SHELL_FAMILIES.length).toBeGreaterThan(0);
		expect(PROTOTYPE_SOURCES.length).toBeGreaterThan(0);
	});

	it("generated contracts cover every IA route", () => {
		const coveredRoutes = new Set([
			...PAGE_CONTRACTS.map((contract) => contract.route),
			...(EDITION_MANIFEST.reactOnlyRoutes ?? []).map((entry) => entry.route),
		]);

		for (const route of IA_ROUTES) {
			expect(coveredRoutes.has(route), `Missing contract for ${route}`).toBe(true);
		}
	});

	it("does not emit duplicate route contracts", () => {
		const routes = PAGE_CONTRACTS.map((contract) => contract.route);
		const uniqueRoutes = new Set(routes);

		expect(uniqueRoutes.size).toBe(routes.length);
		expect(routes.length).toBeGreaterThanOrEqual(IA_ROUTES.length);
	});

	it("removes every retired product-domain contract instead of keeping aliases", () => {
		for (const contract of PAGE_CONTRACTS) {
			for (const prefix of RETIRED_PRODUCT_PREFIXES) {
				expect(contract.route === prefix || contract.route.startsWith(`${prefix}/`), contract.route).toBe(false);
			}
		}
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

	it("separates frozen prototype verification from React parity verification", () => {
		expect(GENERATED_SOURCE).toContain("prototypeVerified: boolean;");
		expect(GENERATED_SOURCE).toContain("reactParityVerified: boolean;");
		expect(GENERATED_SOURCE).not.toContain("visualAuditStatus");

		for (const contract of PAGE_CONTRACTS) {
			if (!contract.landing) continue;
			const landing = contract.landing as unknown as Record<string, unknown>;

			expect(landing["prototypeVerified"], `${contract.route} missing prototypeVerified`).toBeTypeOf("boolean");
			expect(landing["reactParityVerified"], `${contract.route} missing reactParityVerified`).toBeTypeOf("boolean");
			expect(
				landing["visualAuditStatus"],
				`${contract.route} still exposes ambiguous visualAuditStatus`,
			).toBeUndefined();
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

describe("R1-R5 live page contracts", () => {
	const requiredStates = {
		"research-agent-lab": [
			"disabled",
			"degraded",
			"running",
			"partial",
			"blocked",
			"waiting-approval",
			"approval-expired",
			"guardrail-blocked",
			"cancelled",
			"failed",
			"completed",
			"reconnecting",
		],
		system: [
			"pipeline-running",
			"source-degraded",
			"fallback-active",
			"promotion-blocked",
			"approval-expired",
			"remediation-empty",
		],
		"model-portfolio": [
			"ready",
			"review-required",
			"blocked",
			"partial",
			"solver-failed",
			"reconciliation-mismatch",
			"no-positions",
		],
		"portfolio-risk": [
			"ready",
			"review-required",
			"blocked",
			"partial",
			"tail-risk-unavailable",
			"factor-risk-unavailable",
			"stress-scenario-unavailable",
			"reconciliation-mismatch",
			"provenance-missing",
			"shadow-opinion-unavailable",
		],
	} as const;

	it("freezes the required operational state matrix", () => {
		for (const [id, states] of Object.entries(requiredStates)) {
			const contract = readR1R5Contract(id);
			expect(contract.states.pageSpecific, id).toEqual(expect.arrayContaining([...states]));
		}
	});

	it("maps every in-scope overlay to a concrete React component", () => {
		for (const id of Object.keys(requiredStates)) {
			const contract = readR1R5Contract(id);
			expect(contract.overlays, id).not.toContainEqual(
				expect.objectContaining({ reactComponent: "PrototypeOnlyOverlay" }),
			);
		}
	});

	it("declares live Agent and Daily Decision V3 API boundaries without mock fallback", () => {
		const agent = readR1R5Contract("research-agent-lab");
		expect(agent.liveData).toMatchObject({
			mockFallback: false,
			readPaths: expect.arrayContaining([
				"/api/v1/agent/capabilities",
				"/api/v1/agent/runs",
				"/api/v1/agent/approvals",
				"/api/v1/agent/campaigns",
			]),
		});
		expect(agent.security).toMatchObject({
			browserCredentialInputs: [],
			browserPersistence: [],
			providerConfiguration: "server-only",
			forbiddenClientFields: expect.arrayContaining(["api_key", "authorization", "base_url", "model_id"]),
		});

		for (const id of ["model-portfolio", "portfolio-risk"]) {
			expect(readR1R5Contract(id).liveData).toMatchObject({
				mockFallback: false,
				readPaths: expect.arrayContaining(["/api/v1/manual/daily-decision/v3"]),
			});
		}
	});
});
