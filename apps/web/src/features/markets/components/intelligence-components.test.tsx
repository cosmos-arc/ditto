import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { intelligenceHandlers } from "@/mocks/handlers/intelligence";

import { IntelligenceFlowView } from "./intelligence-flow-view";
import { IntelligenceMacroView } from "./intelligence-macro-view";
import { IntelligenceFundamentalsView } from "./intelligence-fundamentals-view";

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

beforeEach(() => server.use(...intelligenceHandlers));

describe("IntelligenceFlowView", () => {
	it("渲染资金流向", async () => {
		render(<IntelligenceFlowView />, { wrapper: createWrapper() });

		await expect(screen.findByText("科技")).resolves.toBeInTheDocument();
	});

	it("显示北向资金", async () => {
		render(<IntelligenceFlowView />, { wrapper: createWrapper() });

		await expect(screen.findByText(/45\.8/)).resolves.toBeInTheDocument();
	});
});

describe("IntelligenceMacroView", () => {
	it("渲染宏观数据", async () => {
		render(<IntelligenceMacroView />, { wrapper: createWrapper() });

		await expect(screen.findByText("PMI 制造业")).resolves.toBeInTheDocument();
	});

	it("显示经济日历", async () => {
		render(<IntelligenceMacroView />, { wrapper: createWrapper() });

		const elements = await screen.findAllByText(/CPI 同比/);
		expect(elements.length).toBeGreaterThanOrEqual(1);
	});
});

describe("IntelligenceFundamentalsView", () => {
	it("渲染财报日历", async () => {
		render(<IntelligenceFundamentalsView />, { wrapper: createWrapper() });

		await expect(screen.findByText("贵州茅台")).resolves.toBeInTheDocument();
	});
});
