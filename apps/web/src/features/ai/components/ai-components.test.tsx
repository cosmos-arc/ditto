import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { aiHandlers } from "@/mocks/handlers/ai";

import { AiPulseStrip } from "./ai-pulse-strip";
import { AgentQuickView } from "./agent-quick-view";
import { CopilotQuickView } from "./copilot-quick-view";
import { AiPage } from "./ai-page";

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

beforeEach(() => {
	server.use(...aiHandlers);
});

// ── AiPulseStrip ──────────────────────────────────────────────

describe("AiPulseStrip", () => {
	it("渲染 3 个脉动指标卡片", async () => {
		render(<AiPulseStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("运行中计划")).resolves.toBeInTheDocument();
		await expect(
			screen.findByText("待审批"),
		).resolves.toBeInTheDocument();
		await expect(
			screen.findByText("Copilot 会话"),
		).resolves.toBeInTheDocument();
	});

	it("显示脉动数值", async () => {
		render(<AiPulseStrip />, { wrapper: createWrapper() });

		await expect(screen.findByText("3")).resolves.toBeInTheDocument();
		await expect(screen.findByText("2")).resolves.toBeInTheDocument();
		await expect(screen.findByText("5")).resolves.toBeInTheDocument();
	});
});

// ── AgentQuickView ────────────────────────────────────────────

describe("AgentQuickView", () => {
	it("渲染计划列表标题", async () => {
		render(<AgentQuickView />, { wrapper: createWrapper() });

		await expect(screen.findByText("Agent 计划")).resolves.toBeInTheDocument();
	});

	it("显示计划条目", async () => {
		render(<AgentQuickView />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("因子池优化扫描"),
		).resolves.toBeInTheDocument();
		await expect(
			screen.findByText("风控参数调优"),
		).resolves.toBeInTheDocument();
		await expect(
			screen.findByText("组合权重再平衡"),
		).resolves.toBeInTheDocument();
	});

	it("渲染近期发现标题", async () => {
		render(<AgentQuickView />, { wrapper: createWrapper() });

		await expect(screen.findByText("近期发现")).resolves.toBeInTheDocument();
	});

	it("显示发现内容", async () => {
		render(<AgentQuickView />, { wrapper: createWrapper() });

		await expect(
			screen.findByText(/动量因子 IC 连续 3 周下降/),
		).resolves.toBeInTheDocument();
	});

	it("显示发现置信度", async () => {
		render(<AgentQuickView />, { wrapper: createWrapper() });

		// The confidence values appear as child text of small elements
		const elements = await screen.findAllByText(
			(_content, element) =>
				(element?.tagName === "DIV" &&
					(element?.textContent?.startsWith("置信度") ?? false)) ??
				false,
		);
		expect(elements).toHaveLength(2);
		expect(elements[0].textContent).toContain("92%");
		expect(elements[1].textContent).toContain("87%");
	});
});

// ── CopilotQuickView ──────────────────────────────────────────

describe("CopilotQuickView", () => {
	it("渲染会话列表标题", async () => {
		render(<CopilotQuickView />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("Copilot 会话"),
		).resolves.toBeInTheDocument();
	});

	it("显示会话条目", async () => {
		render(<CopilotQuickView />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("因子衰减分析讨论"),
		).resolves.toBeInTheDocument();
		await expect(
			screen.findByText("调仓建议方案"),
		).resolves.toBeInTheDocument();
	});

	it("渲染近期输出标题", async () => {
		render(<CopilotQuickView />, { wrapper: createWrapper() });

		await expect(screen.findByText("近期输出")).resolves.toBeInTheDocument();
	});

	it("显示输出内容", async () => {
		render(<CopilotQuickView />, { wrapper: createWrapper() });

		await expect(
			screen.findByText(/动量因子 60 日 IC 序列/),
		).resolves.toBeInTheDocument();
	});
});

// ── AiPage ────────────────────────────────────────────────────

describe("AiPage", () => {
	it("渲染脉动指标区域", async () => {
		render(<AiPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("运行中计划")).resolves.toBeInTheDocument();
	});

	it("渲染 Agent 快览区域", async () => {
		render(<AiPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("Agent 计划")).resolves.toBeInTheDocument();
	});

	it("渲染 Copilot 快览区域", async () => {
		render(<AiPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("Copilot 会话"),
		).resolves.toBeInTheDocument();
	});
});
