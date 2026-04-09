import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { researchHandlers } from "@/mocks/handlers/research";

import { FactorDetailHeader } from "./factor-detail-header";
import { FactorAnalysisView } from "./factor-analysis-view";

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

beforeEach(() => server.use(...researchHandlers));

describe("FactorDetailHeader", () => {
	it("渲染因子名称", async () => {
		render(<FactorDetailHeader id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("动量因子")).resolves.toBeInTheDocument();
	});

	it("显示因子类型", async () => {
		render(<FactorDetailHeader id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("技术面")).resolves.toBeInTheDocument();
	});

	it("显示 IC 和 IR 指标", async () => {
		render(<FactorDetailHeader id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/0.052/)).resolves.toBeInTheDocument();
		await expect(screen.findByText(/0.85/)).resolves.toBeInTheDocument();
	});
});

describe("FactorAnalysisView", () => {
	it("渲染因子分析", async () => {
		render(<FactorAnalysisView id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("IC 时序")).resolves.toBeInTheDocument();
	});

	it("显示 IC 数据", async () => {
		render(<FactorAnalysisView id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText(/0.058/)).resolves.toBeInTheDocument();
	});

	it("显示行业暴露数据", async () => {
		render(<FactorAnalysisView id="f-001" />, { wrapper: createWrapper() });
		await expect(screen.findByText("科技")).resolves.toBeInTheDocument();
	});
});
