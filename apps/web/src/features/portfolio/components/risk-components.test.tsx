import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { riskHandlers } from "@/mocks/handlers/risk";
import { server } from "@/mocks/server";

import { RiskBreachesList } from "./risk-breaches-list";
import { RiskExposureSummary } from "./risk-exposure-summary";
import { RiskPage } from "./risk-page";

// @contract-handoff RiskMockWorkspace
// @contract-handoff RiskStressDetailDrawer
// @contract-handoff BreachDetailContent
// @contract-handoff RiskRuleEditorSheet
import { RiskScopeStrip } from "./risk-scope-strip";

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

	it("可选择告警使用原生按钮语义", async () => {
		render(<RiskBreachesList onSelectBreach={() => {}} />, {
			wrapper: createWrapper(),
		});

		const breach = await screen.findByRole("button", { name: /单日 VaR 超限/ });
		expect(breach).toHaveAttribute("type", "button");
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
	it("live 模式显示 Daily Decision V3 风险中心", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		const { container } = render(<RiskPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("Historical ES99")).resolves.toBeInTheDocument();
		expect(container.querySelector("[data-slot='risk-decision-center']")).toBeInTheDocument();
		expect(screen.queryByText("prototype only")).not.toBeInTheDocument();
	});

	it("渲染风控中心布局", async () => {
		render(<RiskPage />, { wrapper: createWrapper() });
		await expect(screen.findByText("风险利用率")).resolves.toBeInTheDocument();
		expect(screen.getByText("VaR 占比")).toBeInTheDocument();
		expect(screen.getByText("行业集中度")).toBeInTheDocument();
		await expect(screen.findByText("VaR(95%)")).resolves.toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "风险概览" })).toHaveAttribute("aria-selected", "true");
		expect(screen.getByText("VaR 趋势")).toBeInTheDocument();
		expect(screen.getByText("风险总览")).toBeInTheDocument();
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

	it("mock Risk 可切换压力测试并打开场景证据", async () => {
		const user = userEvent.setup();
		render(<RiskPage />, { wrapper: createWrapper() });

		await screen.findByText("VaR 趋势");
		await user.click(screen.getByRole("tab", { name: "压力测试" }));
		expect(screen.getByText("压力场景损失")).toBeInTheDocument();
		await user.click(screen.getByRole("button", { name: "查看压力测试证据" }));
		await expect(screen.findByText("压力测试证据")).resolves.toBeInTheDocument();
		expect(screen.getByText(/不会发起新的计算/)).toBeInTheDocument();
	});

	it("mock Risk 规则编辑为只读预览，不伪造写入", async () => {
		const user = userEvent.setup();
		render(<RiskPage />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "查看风险规则" }));
		await expect(screen.findByText("风险规则")).resolves.toBeInTheDocument();
		expect(screen.getByText(/当前公开合同没有规则写入端点/)).toBeInTheDocument();
		expect(screen.getByRole("button", { name: "保持只读" })).toBeDisabled();
	});
});
