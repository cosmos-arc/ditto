import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it } from "vitest";
import { aiHandlers } from "@/mocks/handlers/ai";
import { server } from "@/mocks/server";
import { CopilotChatView } from "./copilot-chat-view";
import { CopilotPage } from "./copilot-page";
import { CopilotSessionList } from "./copilot-session-list";

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

// ── CopilotSessionList ────────────────────────────────────────

describe("CopilotSessionList", () => {
	it("渲染会话列表标题", async () => {
		render(<CopilotSessionList />, { wrapper: createWrapper() });

		await expect(screen.findByText("会话列表")).resolves.toBeInTheDocument();
	});

	it("显示所有会话条目", async () => {
		render(<CopilotSessionList />, { wrapper: createWrapper() });

		await expect(screen.findByText("因子衰减分析讨论")).resolves.toBeInTheDocument();
		await expect(screen.findByText("调仓建议方案")).resolves.toBeInTheDocument();
		await expect(screen.findByText("回测框架使用指南")).resolves.toBeInTheDocument();
	});

	it("显示会话模式", async () => {
		render(<CopilotSessionList />, { wrapper: createWrapper() });

		await expect(screen.findByText("研究")).resolves.toBeInTheDocument();
		await expect(screen.findByText("交易")).resolves.toBeInTheDocument();
		await expect(screen.findByText("编码")).resolves.toBeInTheDocument();
	});
});

// ── CopilotChatView ───────────────────────────────────────────

describe("CopilotChatView", () => {
	it("渲染聊天消息", async () => {
		render(<CopilotChatView sessionId="session-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText("最近动量因子的 IC 表现怎么样？有没有衰减趋势？")).resolves.toBeInTheDocument();
	});

	it("显示助手回复", async () => {
		render(<CopilotChatView sessionId="session-001" />, {
			wrapper: createWrapper(),
		});

		await expect(screen.findByText(/根据最近 60 个交易日的 IC 序列分析/)).resolves.toBeInTheDocument();
	});

	it("区分用户和助手消息", async () => {
		render(<CopilotChatView sessionId="session-001" />, {
			wrapper: createWrapper(),
		});

		// User messages should have role indicators
		const userLabels = await screen.findAllByText("你");
		expect(userLabels.length).toBeGreaterThan(0);

		// Assistant messages should have role indicators
		const copilotLabels = await screen.findAllByText("Copilot");
		expect(copilotLabels.length).toBeGreaterThan(0);
	});
});

// ── CopilotPage ───────────────────────────────────────────────

describe("CopilotPage", () => {
	it("渲染会话列表区域", async () => {
		render(<CopilotPage />, { wrapper: createWrapper() });

		await expect(screen.findByText("会话列表")).resolves.toBeInTheDocument();
	});
});
