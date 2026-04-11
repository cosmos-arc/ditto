import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { riskHandlers } from "@/mocks/handlers/risk";

import { RiskBreachesList } from "./risk-breaches-list";
import { RiskExposureSummary } from "./risk-exposure-summary";
import { RiskScopeStrip } from "./risk-scope-strip";
import { RiskPage } from "./risk-page";

function createQueryClient(): QueryClient {
	return new QueryClient({
		defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
	});
}

function createWrapper() {
	const qc = createQueryClient();
	return function Wrapper({ children }: { children: ReactNode }) {
		return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
	};
}

beforeEach(() => server.use(...riskHandlers));

describe("RiskBreachesList", () => {
	it("渲染风控告警标题", async () => {
		render(<RiskBreachesList />, { wrapper: createWrapper() });
		await expect(screen.findByText("风控告警")).resolves.toBeInTheDocument();
	});

	it("显示告警列表", async () => {
		render(<RiskBreachesList />, { wrapper: createWrapper() });
		await expect(screen.findByText("单日 VaR 超限")).resolves.toBeInTheDocument();
		await expect(screen.findByText("行业集中度超限")).resolves.toBeInTheDocument();
	});

	it("显示告警状态", async () => {
		render(<RiskBreachesList />, { wrapper: createWrapper() });
		await expect(screen.findByText("active")).resolves.toBeInTheDocument();
		await expect(screen.findByText("acknowledged")).resolves.toBeInTheDocument();
	});
});

describe("RiskExposureSummary", () => {
	it("渲染敞口标题", async () => {
		render(<RiskExposureSummary />, { wrapper: createWrapper() });
		await expect(screen.findByText("敞口概览")).resolves.toBeInTheDocument();
	});

	it("显示总敞口", async () => {
		render(<RiskExposureSummary />, { wrapper: createWrapper() });
		await expect(screen.findByText(/185/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/62/)).resolves.toBeInTheDocument();
	});
});

describe("RiskScopeStrip", () => {
	it("渲染风险指标标签", async () => {
		render(<RiskScopeStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText("VaR(95%)")).resolves.toBeInTheDocument();
		await expect(screen.findByText("最大回撤")).resolves.toBeInTheDocument();
		await expect(screen.findByText("Beta")).resolves.toBeInTheDocument();
		await expect(screen.findByText("总敞口")).resolves.toBeInTheDocument();
		await expect(screen.findByText("净敞口")).resolves.toBeInTheDocument();
		await expect(screen.findByText("违规次数")).resolves.toBeInTheDocument();
	});

	it("显示 loading 状态", () => {
		render(<RiskScopeStrip />, { wrapper: createWrapper() });
		// During loading, strip renders skeleton placeholders (no metric labels yet)
		expect(screen.queryByText("VaR(95%)")).not.toBeInTheDocument();
	});
});

describe("RiskPage", () => {
	it("渲染风控中心布局", async () => {
		render(<RiskPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("敞口概览")).resolves.toBeInTheDocument();
		const alerts = await screen.findAllByText("风控告警");
		expect(alerts.length).toBeGreaterThanOrEqual(1);
		await expect(screen.findByText("VaR(95%)")).resolves.toBeInTheDocument();
	});
});
