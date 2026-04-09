import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { instrumentsHandlers } from "@/mocks/handlers/instruments";

import { InstrumentMetaStrip } from "./instrument-meta-strip";
import { InstrumentOverview } from "./instrument-overview";

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
