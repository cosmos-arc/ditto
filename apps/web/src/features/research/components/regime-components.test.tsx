import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { server } from "@/mocks/server";
import { regimeHandlers } from "@/mocks/handlers/regime";

import { RegimeCurrentView } from "./regime-current-view";
import { RegimeHistoryList } from "./regime-history-list";
import { RegimeStrategyImpact } from "./regime-strategy-impact";

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

beforeEach(() => server.use(...regimeHandlers));

describe("RegimeCurrentView", () => {
	it("渲染当前状态", async () => {
		render(<RegimeCurrentView />, { wrapper: createWrapper() });

		await expect(screen.findByText("risk_on")).resolves.toBeInTheDocument();
	});

	it("显示置信度", async () => {
		render(<RegimeCurrentView />, { wrapper: createWrapper() });

		await expect(screen.findByText("78%")).resolves.toBeInTheDocument();
	});
});

describe("RegimeHistoryList", () => {
	it("渲染历史切换", async () => {
		render(<RegimeHistoryList />, { wrapper: createWrapper() });

		const elements = await screen.findAllByText("volatile");
		expect(elements.length).toBeGreaterThanOrEqual(1);
	});

	it("显示触发原因", async () => {
		render(<RegimeHistoryList />, { wrapper: createWrapper() });

		await expect(screen.findByText(/北向资金/)).resolves.toBeInTheDocument();
	});
});

describe("RegimeStrategyImpact", () => {
	it("渲染策略影响", async () => {
		render(<RegimeStrategyImpact />, { wrapper: createWrapper() });

		await expect(screen.findByText("动量突破 v3")).resolves.toBeInTheDocument();
	});

	it("显示调整建议", async () => {
		render(<RegimeStrategyImpact />, { wrapper: createWrapper() });

		const elements = await screen.findAllByText(/适配度/);
		expect(elements.length).toBeGreaterThanOrEqual(1);
	});
});
