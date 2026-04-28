import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { homeHandlers } from "@/mocks/handlers/home";
import { mockDecisionBanner } from "@/mocks/fixtures/home";
import { useUIPreferences } from "@/features/shell/hooks/use-ui-preferences";

import { PulseSection } from "./pulse-section";
import { BannerSection } from "./banner-section";
import { PriorityQueueSection } from "./priority-queue-section";
import { MarketPulseSection } from "./market-pulse-section";
import { GlobalAlertsSection } from "./global-alerts-section";
import { DataHealthSection } from "./data-health-section";
import { ResearchProgressSection } from "./research-progress-section";
import { HomePage } from "./home-page";

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
	server.use(...homeHandlers);
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

	it("使用原型 32px 脉动条高度", async () => {
		render(<PulseSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("盈亏")).resolves.toBeInTheDocument();
		const strip = document.querySelector("[data-slot='pulse-strip']");
		expect(strip).toHaveClass("h-[calc(var(--density-strip-height)-4px)]");
	});
});

describe("BannerSection", () => {
	it("渲染决策横幅", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日盈亏")).resolves.toBeInTheDocument();
	});

	it("显示 CTA 操作按钮", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("查看信号总览")).resolves.toBeInTheDocument();
		await expect(screen.findByText("进入研究")).resolves.toBeInTheDocument();
		await expect(screen.findByText("查看风控")).resolves.toBeInTheDocument();
	});

	it("显示 4 个 KPI 指标", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		await expect(screen.findByText("杠杆率")).resolves.toBeInTheDocument();
		await expect(screen.findByText("回撤")).resolves.toBeInTheDocument();
		await expect(screen.findByText("IVIX")).resolves.toBeInTheDocument();
		await expect(screen.findByText("北向资金")).resolves.toBeInTheDocument();
	});

	it("显示权益 sparkline", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		const banner = await screen.findByTestId("decision-banner");
		const svg = banner.querySelector("svg");
		expect(svg).toBeInTheDocument();
	});

	it("渲染响应中的判断文案", async () => {
		render(<BannerSection />, { wrapper: createWrapper() });

		await expect(
			screen.findByText(mockDecisionBanner.suggestion),
		).resolves.toBeInTheDocument();
	});
});

describe("HomePage", () => {
	it("暴露 Home 主区和次级区审计目标并移除猜测高度", async () => {
		render(<HomePage />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日优先事项")).resolves.toBeInTheDocument();
		const main = document.querySelector("[data-slot='home-main']");
		const primary = document.querySelector("[data-slot='home-primary']");
		const secondary = document.querySelector("[data-slot='home-secondary']");

		expect(main).toBeInTheDocument();
		expect(primary).toBeInTheDocument();
		expect(primary).toHaveClass("max-h-[66%]");
		expect(secondary).toBeInTheDocument();
	});

	it("渲染 WorkspacePlaceholder", async () => {
		render(<HomePage />, { wrapper: createWrapper() });

		await expect(screen.findByText("今日优先事项")).resolves.toBeInTheDocument();
		expect(screen.getByText("自定义工作区 — 即将推出")).toBeInTheDocument();
		expect(screen.getByText(/拖拽配置个性化工作区布局/)).toBeInTheDocument();
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
