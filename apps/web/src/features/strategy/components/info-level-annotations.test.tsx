import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { strategyHandlers } from "@/mocks/handlers/strategy";
import { server } from "@/mocks/server";
import { StrategyDetailPage } from "./strategy-detail-page";
import { StrategyPage } from "./strategy-page";

// Mock TanStack Router's useParams (used by StrategyDetailPage)
vi.mock("@tanstack/react-router", async () => {
	const actual = await vi.importActual<typeof import("@tanstack/react-router")>("@tanstack/react-router");
	return {
		...actual,
		useParams: () => ({ id: "strat-001" }),
		Link: ({
			children,
			to,
			params,
		}: {
			readonly children: ReactNode;
			readonly to: string;
			readonly params?: Readonly<Record<string, string>>;
		}) => <a href={params?.id ? to.replace("$id", params.id) : to}>{children}</a>,
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

// ── StrategyDetailPage: 3 L1 (active tab only), 3 L2, 5 L3 (派生节点) ──

describe("StrategyDetailPage info-level annotations", () => {
	beforeEach(() => server.use(...strategyHandlers));

	it("annotates 3 L1 information units (active tab only)", async () => {
		render(<StrategyDetailPage />, { wrapper: createWrapper() });

		await screen.findByText("ETF 行业轮动");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("strategy-meta");
		expect(l1UnitNames).toContain("strategy-overview");
		expect(l1Units).toHaveLength(3);
	});

	it("annotates 3 L2 information units", async () => {
		render(<StrategyDetailPage />, { wrapper: createWrapper() });

		await screen.findByText("策略流程");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("strategy-pipeline");
		expect(l2UnitNames).toContain("strategy-params");
		expect(l2UnitNames).toContain("risk-rules");
		expect(l2Units).toHaveLength(3);
	});

	it("annotates L3 pipeline node items (scorer + selector + execution + constraints)", async () => {
		render(<StrategyDetailPage />, { wrapper: createWrapper() });

		await screen.findByText("策略流程");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		const l3UnitNames = Array.from(l3Units).map((el) => el.getAttribute("data-info-unit"));

		// 派生节点：scorer + selector + execution + 2 constraints = 5
		expect(l3UnitNames.filter((n) => n === "pipeline-node")).toHaveLength(5);
		expect(l3Units).toHaveLength(5);
	});
});

// ── StrategyPage (Studio): 4 L1, 2 L2 ──

describe("StrategyPage info-level annotations", () => {
	beforeEach(() => server.use(...strategyHandlers));

	it("annotates 4 L1 information units", async () => {
		render(<StrategyPage />, { wrapper: createWrapper() });

		await screen.findByText("节点库");

		const l1Units = document.querySelectorAll("[data-info-level='l1']");
		const l1UnitNames = Array.from(l1Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l1UnitNames).toContain("studio-mode-bar");
		expect(l1UnitNames).toContain("strategy-header");
		expect(l1UnitNames).toContain("strategy-editor");
		expect(l1UnitNames).toContain("node-library");
		expect(l1Units).toHaveLength(4);
	});

	it("annotates 2 L2 information units", async () => {
		render(<StrategyPage />, { wrapper: createWrapper() });

		await screen.findByText("节点库");

		const l2Units = document.querySelectorAll("[data-info-level='l2']");
		const l2UnitNames = Array.from(l2Units).map((el) => el.getAttribute("data-info-unit"));

		expect(l2UnitNames).toContain("strategy-inspector");
		expect(l2UnitNames).toContain("validation-panel");
		expect(l2Units).toHaveLength(2);
	});

	it("annotates 0 L3 information units", async () => {
		render(<StrategyPage />, { wrapper: createWrapper() });

		await screen.findByText("节点库");

		const l3Units = document.querySelectorAll("[data-info-level='l3']");
		expect(l3Units).toHaveLength(0);
	});
});
