import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { regimeHandlers } from "@/mocks/handlers/regime";
import { researchHandlers } from "@/mocks/handlers/research";
import { server } from "@/mocks/server";
import { FactorPage } from "./factor-page";
import { RegimePage } from "./regime-page";
import { ResearchPage } from "./research-page";

// Mock TanStack Router's useParams (used by FactorPage)
vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		useParams: () => ({ id: "f-001" }),
	};
});

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: {
			queries: { retry: false, refetchOnWindowFocus: false },
		},
	});
}

function createWrapper() {
	const queryClient = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
	};
}

// ── ResearchPage: 4 L1, 1 L2 ──

describe("ResearchPage info-level annotations", () => {
	beforeEach(() => server.use(...researchHandlers));

	it("annotates 4 L1 information units", async () => {
		render(<ResearchPage />, { wrapper: createWrapper() });

		await screen.findByText("因子监控");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("research-pulse-strip");
		expect(l1UnitNames).toContain("factor-table");
		expect(l1UnitNames).toContain("recent-runs");
		expect(l1UnitNames).toContain("experiment-queue");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates 1 L2 information unit", async () => {
		render(<ResearchPage />, { wrapper: createWrapper() });

		await screen.findByText("因子监控");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("analysis-band");
		expect(l2Units).toHaveLength(1);
	});

	it("annotates 0 L3 information units", async () => {
		render(<ResearchPage />, { wrapper: createWrapper() });

		await screen.findByText("因子监控");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		expect(l3Units).toHaveLength(0);
	});
});

// ── RegimePage: 3 L1, 1 L2 ──

describe("RegimePage info-level annotations", () => {
	beforeEach(() => server.use(...regimeHandlers));

	it("annotates 3 L1 information units", async () => {
		render(<RegimePage />, { wrapper: createWrapper() });

		await screen.findByText("当前状态");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("regime-strip");
		expect(l1UnitNames).toContain("regime-current");
		expect(l1UnitNames).toContain("regime-history");
		expect(l1Units).toHaveLength(3);
	});

	it("annotates 1 L2 information unit", async () => {
		render(<RegimePage />, { wrapper: createWrapper() });

		// Wait for strategy impact data to load (strategy name renders inside the panel)
		await screen.findByText("动量突破 v3");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("regime-strategy-impact");
		expect(l2Units).toHaveLength(1);
	});

	it("annotates 0 L3 information units", async () => {
		render(<RegimePage />, { wrapper: createWrapper() });

		await screen.findByText("当前状态");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		expect(l3Units).toHaveLength(0);
	});
});

// ── FactorPage: 2 L1, 2 L2, 2 L3 ──

const FACTOR_SCOPE = {
	snapshotId: "snapshot-r3",
	startDate: "2024-01-01",
	endDate: "2024-12-31",
	registryHash: "f".repeat(64),
} as const;

describe("FactorPage info-level annotations", () => {
	beforeEach(() => server.use(...researchHandlers));

	it("annotates 2 L1 information units", async () => {
		render(<FactorPage initialScope={FACTOR_SCOPE} />, { wrapper: createWrapper() });

		await screen.findByText("factor-diagnostic-1");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("factor-meta");
		expect(l1UnitNames).toContain("factor-diagnostics-workspace");
		expect(l1Units).toHaveLength(2);
	});

	it("annotates 2 L2 information units", async () => {
		render(<FactorPage initialScope={FACTOR_SCOPE} />, { wrapper: createWrapper() });

		await screen.findByText("factor-diagnostic-1");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("factor-diagnostics");
		expect(l2UnitNames).toContain("factor-provenance");
		expect(l2Units).toHaveLength(2);
	});

	it("annotates server-provided L3 diagnostic items", async () => {
		render(<FactorPage initialScope={FACTOR_SCOPE} />, { wrapper: createWrapper() });

		await screen.findByText("factor-diagnostic-1");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l3UnitNames.filter((n) => n === "diagnostic-item")).toHaveLength(2);
		expect(l3Units).toHaveLength(2);
	});
});
