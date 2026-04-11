import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { aiHandlers } from "@/mocks/handlers/ai";

import { AiPulseStrip } from "./ai-pulse-strip";
import { AgentQuickView } from "./agent-quick-view";
import { CopilotQuickView } from "./copilot-quick-view";
import { AiContextSidebar } from "./ai-context-sidebar";
import { AiMainContent } from "./ai-main-content";
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
	it("renders as 32px pulse-strip slot", async () => {
		render(<AiPulseStrip />, { wrapper: createWrapper() });

		const strip = await screen.findByTestId("pulse-strip");
		expect(strip).toHaveAttribute("data-slot", "pulse-strip");
	});

	it("shows inline ticker metrics", async () => {
		render(<AiPulseStrip />, { wrapper: createWrapper() });

		await expect(
			screen.findByText(/3 个运行中计划/),
		).resolves.toBeInTheDocument();
		await expect(
			screen.findByText(/2 项待审批/),
		).resolves.toBeInTheDocument();
		await expect(
			screen.findByText(/5 个 Copilot 会话/),
		).resolves.toBeInTheDocument();
	});

	it("renders action link", async () => {
		render(<AiPulseStrip />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("查看全部"),
		).resolves.toBeInTheDocument();
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

// ── AiContextSidebar ──────────────────────────────────────────

describe("AiContextSidebar", () => {
	it("renders sidebar-rail slot", () => {
		render(<AiContextSidebar />);

		expect(screen.getByTestId("sidebar-rail")).toHaveAttribute(
			"data-slot",
			"sidebar-rail",
		);
	});

	it("renders all 6 context sections", () => {
		render(<AiContextSidebar />);

		expect(screen.getByText("AI 状态概览")).toBeInTheDocument();
		expect(screen.getByText("置信度分布")).toBeInTheDocument();
		expect(screen.getByText("AI 预警")).toBeInTheDocument();
		expect(screen.getByText("资源用量")).toBeInTheDocument();
		expect(screen.getByText("活动轨迹")).toBeInTheDocument();
		expect(screen.getByText("快捷导航")).toBeInTheDocument();
	});

	it("shows status overview metrics", () => {
		render(<AiContextSidebar />);

		expect(screen.getByText("Agent Plans 今日")).toBeInTheDocument();
		expect(screen.getByText("Copilot 本周对话")).toBeInTheDocument();
		expect(screen.getByText("待审批")).toBeInTheDocument();
	});

	it("shows AI alerts with severity", () => {
		render(<AiContextSidebar />);

		expect(
			screen.getByText("情绪 Alpha v2 IC 持续衰减"),
		).toBeInTheDocument();
		expect(
			screen.getByText("Tushare API 接近频率上限"),
		).toBeInTheDocument();
	});

	it("shows resource usage metrics", () => {
		render(<AiContextSidebar />);

		expect(screen.getByText("API 调用")).toBeInTheDocument();
		expect(screen.getByText("GPU 使用")).toBeInTheDocument();
	});

	it("shows activity timeline entries", () => {
		render(<AiContextSidebar />);

		expect(
			screen.getByText("行业轮动扫描 — Q1 季报因子验证"),
		).toBeInTheDocument();
		expect(screen.getByText("价值因子 Q1 回测完成")).toBeInTheDocument();
	});

	it("shows quick navigation links", () => {
		render(<AiContextSidebar />);

		expect(screen.getByText(/Agent 管理中心/)).toBeInTheDocument();
		expect(screen.getByText(/Copilot 对话/)).toBeInTheDocument();
	});
});

// ── AiMainContent ─────────────────────────────────────────────

describe("AiMainContent", () => {
	it("renders tab navigation with 4 tabs", () => {
		render(<AiMainContent />, { wrapper: createWrapper() });

		expect(screen.getByRole("tab", { name: "Overview" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "Agents" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "Copilot" })).toBeInTheDocument();
		expect(screen.getByRole("tab", { name: "Settings" })).toBeInTheDocument();
	});

	it("shows Overview tab as active by default", () => {
		render(<AiMainContent />, { wrapper: createWrapper() });

		const overviewTab = screen.getByRole("tab", { name: "Overview" });
		expect(overviewTab).toHaveAttribute("aria-selected", "true");
	});

	it("shows Agent and Copilot quick views on Overview tab", async () => {
		render(<AiMainContent />, { wrapper: createWrapper() });

		await expect(screen.findByText("Agent 计划")).resolves.toBeInTheDocument();
		await expect(
			screen.findByText("Copilot 会话"),
		).resolves.toBeInTheDocument();
	});

	it("renders actions bar with 4 actions", () => {
		render(<AiMainContent />, { wrapper: createWrapper() });

		expect(screen.getByText("新建计划")).toBeInTheDocument();
		expect(screen.getByText("审批队列")).toBeInTheDocument();
		expect(screen.getByText("开始会话")).toBeInTheDocument();
	});

	it("switches to Agents tab on click", async () => {
		const user = userEvent.setup();
		render(<AiMainContent />, { wrapper: createWrapper() });

		const agentsTab = screen.getByRole("tab", { name: "Agents" });
		await user.click(agentsTab);

		expect(agentsTab).toHaveAttribute("aria-selected", "true");
	});

	it("switches to Copilot tab on click", async () => {
		const user = userEvent.setup();
		render(<AiMainContent />, { wrapper: createWrapper() });

		const copilotTab = screen.getByRole("tab", { name: "Copilot" });
		await user.click(copilotTab);

		expect(copilotTab).toHaveAttribute("aria-selected", "true");
	});
});

// ── AiPage ────────────────────────────────────────────────────

describe("AiPage", () => {
	it("renders pulse strip ticker", async () => {
		render(<AiPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText(/个运行中计划/),
		).resolves.toBeInTheDocument();
	});

	it("renders Agent quick view", async () => {
		render(<AiPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("Agent 计划")).resolves.toBeInTheDocument();
	});

	it("renders Copilot quick view", async () => {
		render(<AiPage />, { wrapper: createWrapper() });

		await expect(
			screen.findByText("Copilot 会话"),
		).resolves.toBeInTheDocument();
	});

	it("renders page-owned status bar", async () => {
		render(<AiPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("LIVE")).resolves.toBeInTheDocument();
	});
});
