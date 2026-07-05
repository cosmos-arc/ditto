import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

	it("点击告警行时调用 onSelectBreach", async () => {
		const user = userEvent.setup();
		const onSelectBreach = vi.fn();
		render(<RiskBreachesList onSelectBreach={onSelectBreach} />, {
			wrapper: createWrapper(),
		});

		const breachRow = await screen.findByText("单日 VaR 超限");
		await user.click(breachRow.closest("div")!);

		expect(onSelectBreach).toHaveBeenCalledOnce();
		expect(onSelectBreach).toHaveBeenCalledWith("rb-001");
	});

	it("未传 onSelectBreach 时点击不报错", async () => {
		const user = userEvent.setup();
		render(<RiskBreachesList />, { wrapper: createWrapper() });

		const breachRow = await screen.findByText("单日 VaR 超限");
		await user.click(breachRow.closest("div")!);

		// No error thrown — component still renders
		await expect(screen.findByText("风控告警")).resolves.toBeInTheDocument();
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
	it("live 模式显示 Risk prototype only 空态", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<RiskPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("prototype only")).resolves.toBeInTheDocument();
		expect(screen.getByText("V1a 未接 live，数据待后端补齐")).toBeInTheDocument();
	});

	it("渲染风控中心布局", async () => {
		render(<RiskPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("敞口概览")).resolves.toBeInTheDocument();
		await expect(screen.findByText("VaR(95%)")).resolves.toBeInTheDocument();
	});

	it("显示风控告警列表", async () => {
		render(<RiskPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("风控告警")).resolves.toBeInTheDocument();
		await expect(screen.findByText("单日 VaR 超限")).resolves.toBeInTheDocument();
	});

	it("点击告警行打开 Drawer", async () => {
		const user = userEvent.setup();
		render(<RiskPage />, { wrapper: createWrapper() });

		const breachRow = await screen.findByText("单日 VaR 超限");
		await user.click(breachRow.closest("div")!);

		await waitFor(() => {
			expect(screen.getByText("告警详情")).toBeInTheDocument();
		});
	});

	it("Drawer 中显示告警 ID", async () => {
		const user = userEvent.setup();
		render(<RiskPage />, { wrapper: createWrapper() });

		const breachRow = await screen.findByText("单日 VaR 超限");
		await user.click(breachRow.closest("div")!);

		await waitFor(() => {
			expect(screen.getByText("ID: rb-001")).toBeInTheDocument();
		});
	});

	it("关闭 Drawer 后告警详情消失", async () => {
		const user = userEvent.setup();
		render(<RiskPage />, { wrapper: createWrapper() });

		// Open drawer
		const breachRow = await screen.findByText("单日 VaR 超限");
		await user.click(breachRow.closest("div")!);

		await waitFor(() => {
			expect(screen.getByText("告警详情")).toBeInTheDocument();
		});

		// Close drawer via the close button
		const closeButton = screen.getByRole("button", { name: "Close" });
		await user.click(closeButton);

		await waitFor(() => {
			expect(screen.queryByText("告警详情")).not.toBeInTheDocument();
		});
	});
});
