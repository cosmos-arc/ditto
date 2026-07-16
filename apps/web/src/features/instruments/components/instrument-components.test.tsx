import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { instrumentsHandlers } from "@/mocks/handlers/instruments";

import { InstrumentMetaStrip } from "./instrument-meta-strip";
import { InstrumentOverview } from "./instrument-overview";
import { InstrumentChartView } from "./instrument-chart-view";

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

beforeEach(() => server.use(...instrumentsHandlers));

describe("InstrumentMetaStrip", () => {
	it("渲染标的信息", async () => {
		render(<InstrumentMetaStrip id="600519.SH" />, { wrapper: createWrapper() });
		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
		await expect(screen.findByText("600519.SH")).resolves.toBeInTheDocument();
	});

	it("显示价格和涨跌", async () => {
		render(<InstrumentMetaStrip id="600519.SH" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/1755/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/白酒/)).resolves.toBeInTheDocument();
	});
});

describe("InstrumentOverview", () => {
	it("渲染概览标题", async () => {
		render(<InstrumentOverview id="600519.SH" />, { wrapper: createWrapper() });
		await expect(screen.findByText("基本面")).resolves.toBeInTheDocument();
	});

	it("显示财务比率", async () => {
		render(<InstrumentOverview id="600519.SH" />, { wrapper: createWrapper() });
		await expect(screen.findByText("ROE")).resolves.toBeInTheDocument();
	});
});

describe("InstrumentChartView", () => {
	it("渲染行情数据区域", async () => {
		render(<InstrumentChartView id="600519.SH" />, { wrapper: createWrapper() });
		await expect(screen.findByText("价格走势")).resolves.toBeInTheDocument();
	});

	it("显示 K 线数据表", async () => {
		render(<InstrumentChartView id="600519.SH" />, { wrapper: createWrapper() });
		await expect(screen.findByText("2026-03-10")).resolves.toBeInTheDocument();
		await expect(screen.findByText(/1750/)).resolves.toBeInTheDocument();
	});

	it("显示成交量", async () => {
		render(<InstrumentChartView id="600519.SH" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/3,210,000/)).resolves.toBeInTheDocument();
	});
});
