import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { strategyHandlers } from "@/mocks/handlers/strategy";
import { StrategyDetailPage } from "./strategy-detail-page";
import { StrategyPage } from "./strategy-page";

// Mock TanStack Router's useParams (used by StrategyDetailPage)
vi.mock("@tanstack/react-router", async () => {
	const actual =
		await vi.importActual<typeof import("@tanstack/react-router")>(
			"@tanstack/react-router",
		);
	return {
		...actual,
		useParams: () => ({ id: "strat-001" }),
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
		return (
			<QueryClientProvider client={queryClient}>
				{children}
			</QueryClientProvider>
		);
	};
}

// ── StrategyDetailPage: 3 L1 (active tab only), 3 L2, 3 L3 ──

describe("StrategyDetailPage info-level annotations", () => {
	beforeEach(() => server.use(...strategyHandlers));

	it("annotates 3 L1 information units (active tab only)", async () => {
		render(<StrategyDetailPage />, { wrapper: createWrapper() });

		// Wait for strategy data to load
		await screen.findByText("多因子动量策略 v3");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("strategy-meta");
		expect(l1UnitNames).toContain("strategy-overview");
		expect(l1Units).toHaveLength(3);
	});

	it("annotates 3 L2 information units", async () => {
		render(<StrategyDetailPage />, { wrapper: createWrapper() });

		await screen.findByText("策略流程");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("strategy-pipeline");
		expect(l2UnitNames).toContain("factor-weights");
		expect(l2UnitNames).toContain("risk-rules");
		expect(l2Units).toHaveLength(3);
	});

	it("annotates 3 L3 pipeline node items", async () => {
		render(<StrategyDetailPage />, { wrapper: createWrapper() });

		await screen.findByText("策略流程");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l3UnitNames.filter((n) => n === "pipeline-node")).toHaveLength(3);
		expect(l3Units).toHaveLength(3);
	});
});

// ── StrategyPage (Studio): 4 L1, 1 L2 ──

describe("StrategyPage info-level annotations", () => {
	beforeEach(() => server.use(...strategyHandlers));

	it("annotates 4 L1 information units", async () => {
		render(<StrategyPage />, { wrapper: createWrapper() });

		await screen.findByText("因子库");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l1UnitNames).toContain("studio-mode-bar");
		expect(l1UnitNames).toContain("strategy-header");
		expect(l1UnitNames).toContain("strategy-code");
		expect(l1UnitNames).toContain("factor-browser");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates 1 L2 information unit", async () => {
		render(<StrategyPage />, { wrapper: createWrapper() });

		await screen.findByText("因子库");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map(
			(el) => el.getAttribute("data-info-unit"),
		);

		expect(l2UnitNames).toContain("strategy-inspector");
		expect(l2Units).toHaveLength(1);
	});

	it("annotates 0 L3 information units", async () => {
		render(<StrategyPage />, { wrapper: createWrapper() });

		await screen.findByText("因子库");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		expect(l3Units).toHaveLength(0);
	});
});
