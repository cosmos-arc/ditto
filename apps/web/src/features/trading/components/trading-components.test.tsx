import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { tradingHandlers } from "@/mocks/handlers/trading";

import { TradingSessionStrip } from "./trading-session-strip";
import { EquityPnlBlock } from "./equity-pnl-block";
import { PositionsSummary } from "./positions-summary";
import { RiskAlertsBlock } from "./risk-alerts-block";

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

beforeEach(() => server.use(...tradingHandlers));

describe("TradingSessionStrip", () => {
	it("渲染交易阶段", async () => {
		render(<TradingSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText("continuous")).resolves.toBeInTheDocument();
	});

	it("显示现金余额", async () => {
		render(<TradingSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText(/1,250,000/)).resolves.toBeInTheDocument();
	});

	it("显示保证金信息", async () => {
		render(<TradingSessionStrip />, { wrapper: createWrapper() });
		await expect(screen.findByText(/320,000/)).resolves.toBeInTheDocument();
	});
});

describe("EquityPnlBlock", () => {
	it("渲染权益标题", async () => {
		render(<EquityPnlBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText("权益 & 盈亏")).resolves.toBeInTheDocument();
	});

	it("显示总权益", async () => {
		render(<EquityPnlBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText(/1,538,200/)).resolves.toBeInTheDocument();
	});
});

describe("PositionsSummary", () => {
	it("渲染持仓标题", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(screen.findByText("持仓汇总")).resolves.toBeInTheDocument();
	});

	it("显示所有持仓", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(screen.findByText("平安银行")).resolves.toBeInTheDocument();
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await expect(screen.findByText("宁德时代")).resolves.toBeInTheDocument();
	});

	it("显示 T+1 冻结标识", async () => {
		render(<PositionsSummary />, { wrapper: createWrapper() });
		await expect(screen.findByText("冻结 1,000")).resolves.toBeInTheDocument();
	});
});

describe("RiskAlertsBlock", () => {
	it("渲染风险标题", async () => {
		render(<RiskAlertsBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText("风控 & 预警")).resolves.toBeInTheDocument();
	});

	it("显示信号队列计数", async () => {
		render(<RiskAlertsBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText(/5 待复核/)).resolves.toBeInTheDocument();
	});

	it("显示订单计数", async () => {
		render(<RiskAlertsBlock />, { wrapper: createWrapper() });
		await expect(screen.findByText(/15 已成交/)).resolves.toBeInTheDocument();
	});
});
