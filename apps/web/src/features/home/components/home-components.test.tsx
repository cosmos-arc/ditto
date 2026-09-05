import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchMarketContext } from "@/features/markets";
import { useUIPreferences } from "@/features/shell/hooks/use-ui-preferences";
import { mockDecisionBanner } from "@/mocks/fixtures/home";
import { homeHandlers } from "@/mocks/handlers/home";
import { portfolioHandlers } from "@/mocks/handlers/portfolio";
import { server } from "@/mocks/server";
import { BannerSection } from "./banner-section";
import { DataHealthSection } from "./data-health-section";
import { GlobalAlertsSection } from "./global-alerts-section";
import { HomePage } from "./home-page";
import { MarketPulseSection } from "./market-pulse-section";
import { PriorityQueueSection } from "./priority-queue-section";
import { PulseSection } from "./pulse-section";
import { ResearchProgressSection } from "./research-progress-section";

const CURRENT_MARKET_CONTEXT_SCOPE = {
	asOf: "2026-08-31T09:00:00Z",
	knowledgeCutoff: "2026-08-31T09:00:00Z",
	publicationCutoff: "2026-08-31T09:00:00Z",
	sourceSnapshotIds: [
		"snapshot-stock",
		"snapshot-index",
		"snapshot-global",
		"snapshot-weights",
		"snapshot-macro",
		"snapshot-fx",
		"snapshot-commodity",
	],
} as const;

function loadMarketContext() {
	return fetchMarketContext(CURRENT_MARKET_CONTEXT_SCOPE);
}

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
	server.use(...homeHandlers, ...portfolioHandlers);
});

describe("PulseSection", () => {
	it("渲染脉动薄条", async () => {
		render(<PulseSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("盈亏")).resolves.toBeInTheDocument();
		await expect(screen.findByText("待处理")).resolves.toBeInTheDocument();
		await expect(screen.findByText("运行中")).resolves.toBeInTheDocument();
	});

	it("显示交易阶段", async () => {
		render(<PulseSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("盘中交易")).resolves.toBeInTheDocument();
	});

	it("显示盈亏百分比", async () => {
		render(<PulseSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("+0.34%")).resolves.toBeInTheDocument();
	});

	it("使用原型 24px 首页状态条高度", async () => {
		render(<PulseSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("盈亏")).resolves.toBeInTheDocument();
		const strip = document.querySelector("[data-slot='pulse-strip']");
		expect(strip).toHaveClass("h-[var(--height-status-bar)]");
	});
});

describe("BannerSection", () => {
	it("渲染决策横幅", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日主决策")).resolves.toBeInTheDocument();
	});

	it("主动作进入真实信号与风控路由", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		await expect(screen.findByRole("link", { name: "复核信号" })).resolves.toHaveAttribute("href", "/portfolio/review");
		expect(screen.getByRole("link", { name: "查看风控" })).toHaveAttribute("href", "/risk");
	});

	it("只显示聚合合同能提供的三个影响指标", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("杠杆率")).resolves.toBeInTheDocument();
		await expect(screen.findByText("回撤")).resolves.toBeInTheDocument();
		await expect(screen.findByText("风险利用率")).resolves.toBeInTheDocument();
	});

	it("不把 mock sparkline 伪装成 live 证据", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		const banner = await screen.findByTestId("decision-banner");
		const svg = banner.querySelector("svg");
		expect(svg).not.toBeInTheDocument();
	});

	it("渲染响应中的判断文案", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		await expect(screen.findByText(mockDecisionBanner.suggestion)).resolves.toBeInTheDocument();
	});
});

describe("HomePage", () => {
	it("live 模式保留同一 Command Center 工作面而不是整页占位", async () => {
		vi.stubEnv("VITE_USE_MOCK", "false");
		render(<HomePage loadMarketContext={loadMarketContext} />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日优先事项")).resolves.toBeInTheDocument();
		await expect(screen.findByText("#510300 BUY 建议待人工复核")).resolves.toBeInTheDocument();
		expect(screen.getByText("Daily Decision V3 要求人工复核后再形成执行意图。")).toBeInTheDocument();
		await expect(screen.findAllByText("风险偏好")).resolves.toHaveLength(2);
		expect(screen.getByText("今日变化与驱动")).toBeInTheDocument();
		expect(screen.getByText("证据 2 · 快照 7")).toBeInTheDocument();
		expect(screen.getByText("Agent 投影不可用；Daily Decision V3 未提供 Agent findings。")).toBeInTheDocument();
		expect(screen.queryByText("贵州茅台（600519）出现卖出信号")).not.toBeInTheDocument();
		expect(document.querySelector("[data-slot='main']")).toBeInTheDocument();
		expect(document.querySelector("[data-slot='sidebar']")).toBeInTheDocument();
		expect(screen.queryByText("prototype only")).not.toBeInTheDocument();
	});

	it("暴露 Home 主区和次级区审计目标并移除猜测高度", async () => {
		render(<HomePage />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日优先事项")).resolves.toBeInTheDocument();
		const main = document.querySelector("[data-slot='home-main']");
		const primary = document.querySelector("[data-slot='home-primary']");
		const secondary = document.querySelector("[data-slot='home-secondary']");

		expect(main).toBeInTheDocument();
		expect(primary).toBeInTheDocument();
		expect(primary).not.toHaveClass("max-h-[66%]");
		expect(secondary).toBeInTheDocument();
	});

	it("不再用即将推出占位符挤占今日工作面", async () => {
		render(<HomePage />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日优先事项")).resolves.toBeInTheDocument();
		expect(screen.queryByText("自定义工作区 — 即将推出")).not.toBeInTheDocument();
		expect(document.querySelector("[data-slot='home-secondary']")).toBeInTheDocument();
	});

	it("从优先事项打开信号证据并经二次确认交接到 Manual/Paper 复核", async () => {
		const user = userEvent.setup();
		render(<HomePage />, { wrapper: createWrapper() });

		await screen.findByText("贵州茅台（600519）出现卖出信号");
		const detailsButton = screen.getAllByRole("button", { name: "查看详情" })[0];
		if (!detailsButton) throw new Error("expected signal details button");
		await user.click(detailsButton);

		const evidence = await screen.findByRole("dialog", { name: "信号证据" });
		expect(evidence).toHaveTextContent("RSI 背离叠加放量");
		await user.click(within(evidence).getByRole("button", { name: "形成订单前检查" }));

		const handoff = await screen.findByRole("dialog", { name: "订单交接确认" });
		expect(handoff).toHaveTextContent("不会在 Home 自动创建 Paper 订单或成交");
		expect(within(handoff).getByRole("link", { name: "进入信号收件箱复核" })).toHaveAttribute(
			"href",
			"/portfolio/review",
		);
	});

	it("工作台设置只修改真实侧栏偏好", async () => {
		const user = userEvent.setup();
		render(<HomePage />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "工作台设置" }));
		const settings = await screen.findByRole("dialog", { name: "工作台设置" });
		await user.click(within(settings).getByRole("button", { name: "折叠右侧栏" }));

		expect(useUIPreferences.getState().sidebarCollapsed).toBe(true);
	});

	it("AI 建议 overlay 明确是只读后端证据摘要", async () => {
		const user = userEvent.setup();
		render(<HomePage />, { wrapper: createWrapper() });

		await user.click(await screen.findByRole("button", { name: "决策证据" }));
		const evidence = await screen.findByRole("dialog", { name: "AI 决策证据" });
		expect(evidence).toHaveTextContent("只读证据摘要");
		expect(evidence).toHaveTextContent("未调用模型");
	});
});

describe("PriorityQueueSection", () => {
	it("渲染今日优先事项标题", async () => {
		render(<PriorityQueueSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日优先事项")).resolves.toBeInTheDocument();
	});

	it("显示 5 个待处理事项", async () => {
		render(<PriorityQueueSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("贵州茅台（600519）出现卖出信号")).resolves.toBeInTheDocument();
		await expect(screen.findByText("行业集中度超限 — 科技板块 > 35%")).resolves.toBeInTheDocument();
	});

	it("显示跨域关注项副标题", async () => {
		render(<PriorityQueueSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("跨域关注项")).resolves.toBeInTheDocument();
	});
});

describe("MarketPulseSection", () => {
	it("渲染市场脉搏标题", async () => {
		render(<MarketPulseSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("市场脉搏")).resolves.toBeInTheDocument();
	});

	it("显示 4 个市场脉搏指标", async () => {
		render(<MarketPulseSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("沪深300")).resolves.toBeInTheDocument();
		await expect(screen.findByText("波动率")).resolves.toBeInTheDocument();
		await expect(screen.findByText("涨跌比")).resolves.toBeInTheDocument();
		await expect(screen.findByText("北向资金")).resolves.toBeInTheDocument();
	});

	it("显示指标值和变化", async () => {
		render(<MarketPulseSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("3,432")).resolves.toBeInTheDocument();
		await expect(screen.findByText("+0.82%")).resolves.toBeInTheDocument();
	});

	it("为带数据的指标渲染 sparkline 图表", async () => {
		render(<MarketPulseSection />, { wrapper: createWrapper() });

		// 沪深300 有 sparkline 数据
		await expect(screen.findByText("沪深300")).resolves.toBeInTheDocument();
		const sparklines = document.querySelectorAll("[data-slot='sparkline']");
		// 4 个指标中有 3 个有 sparkline 数据
		expect(sparklines.length).toBeGreaterThanOrEqual(3);
	});
});

describe("GlobalAlertsSection", () => {
	it("渲染全局预警标题", async () => {
		render(<GlobalAlertsSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("全局预警")).resolves.toBeInTheDocument();
	});

	it("显示告警内容", async () => {
		render(<GlobalAlertsSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("组合 VaR 突破 95% 分位")).resolves.toBeInTheDocument();
	});
});

describe("DataHealthSection", () => {
	it("渲染数据健康标题", async () => {
		render(<DataHealthSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("数据健康")).resolves.toBeInTheDocument();
	});

	it("显示数据提供者列表", async () => {
		render(<DataHealthSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("行情数据")).resolves.toBeInTheDocument();
		await expect(screen.findByText("期权链")).resolves.toBeInTheDocument();
	});
});

describe("ResearchProgressSection", () => {
	it("渲染研究进展标题", async () => {
		render(<ResearchProgressSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("研究进展")).resolves.toBeInTheDocument();
	});

	it("显示研究动态副标题", async () => {
		render(<ResearchProgressSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("研究动态")).resolves.toBeInTheDocument();
	});
});

describe("HomePage sidebar collapse", () => {
	beforeEach(() => {
		useUIPreferences.setState({ sidebarCollapsed: false });
	});

	it("renders expanded sidebar by default", async () => {
		render(<HomePage />, { wrapper: createWrapper() });

		await expect(screen.findByText("市场脉搏")).resolves.toBeInTheDocument();
	});

	it("renders collapsed sidebar when sidebarCollapsed is true", async () => {
		useUIPreferences.setState({ sidebarCollapsed: true });
		render(<HomePage />, { wrapper: createWrapper() });

		expect(screen.getByLabelText("市场脉搏")).toBeInTheDocument();
		expect(screen.getByLabelText("展开侧边栏")).toBeInTheDocument();
	});

	it("toggles sidebar on click", async () => {
		const user = userEvent.setup();
		render(<HomePage />, { wrapper: createWrapper() });

		await screen.findByText("今日优先事项");
		await user.click(screen.getByLabelText("折叠侧边栏"));
		expect(useUIPreferences.getState().sidebarCollapsed).toBe(true);
	});
});
