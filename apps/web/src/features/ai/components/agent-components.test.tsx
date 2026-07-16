import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { aiHandlers } from "@/mocks/handlers/ai";
import { server } from "@/mocks/server";
import { AgentFindingsList } from "./agent-findings-list";
import { AgentInspectorPanel } from "./agent-inspector-panel";
import { AgentPlansList } from "./agent-plans-list";
import { AgentsPage } from "./agents-page";

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

beforeEach(() => {
	server.use(...aiHandlers);
});

// ── AgentPlansList ────────────────────────────────────────────

describe("AgentPlansList", () => {
	it("渲染计划列表标题", async () => {
		render(<AgentPlansList />, { wrapper: createWrapper() });

		await expect(screen.findByText("Agent 计划")).resolves.toBeInTheDocument();
	});

	it("显示所有计划条目", async () => {
		render(<AgentPlansList />, { wrapper: createWrapper() });

		await expect(screen.findByText("因子池优化扫描")).resolves.toBeInTheDocument();
		await expect(screen.findByText("风控参数调优")).resolves.toBeInTheDocument();
		await expect(screen.findByText("组合权重再平衡")).resolves.toBeInTheDocument();
	});

	it("显示计划目标", async () => {
		render(<AgentPlansList />, { wrapper: createWrapper() });

		await expect(screen.findByText(/评估当前因子池中 45 个因子的有效性/)).resolves.toBeInTheDocument();
	});

	it("显示状态标签", async () => {
		render(<AgentPlansList />, { wrapper: createWrapper() });

		await expect(screen.findByText("运行中")).resolves.toBeInTheDocument();
		await expect(screen.findByText("等待中")).resolves.toBeInTheDocument();
		await expect(screen.findByText("已完成")).resolves.toBeInTheDocument();
	});
});

// ── AgentFindingsList ─────────────────────────────────────────

describe("AgentFindingsList", () => {
	it("渲染发现列表标题", async () => {
		render(<AgentFindingsList />, { wrapper: createWrapper() });

		await expect(screen.findByText("Agent 发现")).resolves.toBeInTheDocument();
	});

	it("显示所有发现条目", async () => {
		render(<AgentFindingsList />, { wrapper: createWrapper() });

		await expect(screen.findByText(/动量因子 IC 连续 3 周下降至 0.028/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/低波动因子在当前市场环境下表现优异/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/科技板块与消费板块相关性从 0.3 升至 0.65/)).resolves.toBeInTheDocument();
	});

	it("显示置信度百分比", async () => {
		render(<AgentFindingsList />, { wrapper: createWrapper() });

		const confidenceElements = await screen.findAllByText(
			(_content, element) =>
				(element?.tagName === "DIV" && (element?.textContent?.startsWith("置信度") ?? false)) ?? false,
		);
		expect(confidenceElements.length).toBeGreaterThan(0);
	});

	it("显示影响等级", async () => {
		render(<AgentFindingsList />, { wrapper: createWrapper() });

		await expect(screen.findByText("高")).resolves.toBeInTheDocument();
		const mediumLabels = await screen.findAllByText("中");
		expect(mediumLabels.length).toBeGreaterThan(0);
	});

	it("显示审批状态", async () => {
		render(<AgentFindingsList />, { wrapper: createWrapper() });

		await expect(screen.findByText("待审批")).resolves.toBeInTheDocument();
		await expect(screen.findByText("已批准")).resolves.toBeInTheDocument();
		await expect(screen.findByText("已拒绝")).resolves.toBeInTheDocument();
	});
});

// ── AgentInspectorPanel ───────────────────────────────────────

describe("AgentInspectorPanel", () => {
	it("无选中计划时渲染空状态", async () => {
		render(<AgentInspectorPanel />, { wrapper: createWrapper() });

		await expect(screen.findByText(/选择一个计划/)).resolves.toBeInTheDocument();
	});

	it("选中计划时渲染计划详情", async () => {
		render(<AgentInspectorPanel planId="plan-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText("因子池优化扫描")).resolves.toBeInTheDocument();
	});

	it("显示计划目标和约束", async () => {
		render(<AgentInspectorPanel planId="plan-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/评估当前因子池中 45 个因子的有效性/)).resolves.toBeInTheDocument();
	});

	it("显示相关运行状态", async () => {
		render(<AgentInspectorPanel planId="plan-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText("因子回测")).resolves.toBeInTheDocument();
	});
});

// ── AgentsPage — OpsConsoleLayout 集成 ──────────────────────────

describe("AgentsPage", () => {
	it("渲染 Agent 发现列表（detail slot）", async () => {
		render(<AgentsPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("Agent 发现")).resolves.toBeInTheDocument();
	});

	it("主面板和详情面板均有内容", async () => {
		render(<AgentsPage />, { wrapper: createWrapper() });

		// main slot: Agent Inspector（异步加载）
		await expect(screen.findByText("因子池优化扫描")).resolves.toBeInTheDocument();
		// detail slot: Agent 发现
		expect(screen.getByText("Agent 发现")).toBeInTheDocument();
	});
});
